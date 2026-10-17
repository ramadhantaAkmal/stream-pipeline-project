import http.client
import json
import logging
import os
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote


DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "9273"))
SCRAPE_INTERVAL = float(os.getenv("SCRAPE_INTERVAL", "10"))
TRACKED_CONTAINERS = {
    "clickhouse",
    "flink-jobmanager",
    "flink-taskmanager",
    "kafka",
}
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("container-metrics-exporter")

metrics_lock = threading.Lock()
metrics_snapshot = {
    "docker_up": 0,
    "errors": {},
    "containers": [],
}


class DockerSocketConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float = 5):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def docker_get(path: str):
    connection = DockerSocketConnection(DOCKER_SOCKET)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        payload = response.read()
        if response.status != 200:
            raise RuntimeError(
                f"Docker API {path} returned HTTP {response.status}: "
                f"{payload.decode('utf-8', errors='replace')}"
            )
        return json.loads(payload)
    finally:
        connection.close()


def container_working_set(memory_stats: dict) -> int:
    usage = int(memory_stats.get("usage", 0))
    stats = memory_stats.get("stats", {})
    inactive_file = stats.get("total_inactive_file", stats.get("inactive_file", 0))
    return max(0, usage - int(inactive_file))


def read_container_stats(container: dict):
    container_id = container["Id"]
    names = container.get("Names", [])
    name = names[0].lstrip("/") if names else container_id[:12]
    if name not in TRACKED_CONTAINERS and not name.startswith("flink-taskmanager-"):
        return None, None

    try:
        stats = docker_get(
            f"/containers/{quote(container_id, safe='')}/stats?stream=false"
        )
        cpu_usage = stats.get("cpu_stats", {}).get("cpu_usage", {})
        memory_stats = stats.get("memory_stats", {})
        return (
            {
                "id": container_id,
                "name": name,
                "cpu_seconds": int(cpu_usage.get("total_usage", 0)) / 1_000_000_000,
                "memory_bytes": container_working_set(memory_stats),
            },
            None,
        )
    except (
        http.client.HTTPException,
        KeyError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        logger.error("Unable to collect Docker stats for %s: %s", name, error)
        return None, (name, 1)


def collect_container_metrics():
    global metrics_snapshot
    try:
        containers = docker_get("/containers/json")
        snapshot = []
        errors = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            for result, error in executor.map(read_container_stats, containers):
                if result is not None:
                    snapshot.append(result)
                if error is not None:
                    name, failed = error
                    errors[name] = failed

        with metrics_lock:
            metrics_snapshot = {
                "docker_up": 1,
                "errors": errors,
                "containers": snapshot,
            }
    except (
        http.client.HTTPException,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        logger.exception("Unable to list running Docker containers: %s", error)
        with metrics_lock:
            metrics_snapshot = {
                "docker_up": 0,
                "errors": {},
                "containers": [],
            }


def collection_loop():
    while True:
        collect_container_metrics()
        threading.Event().wait(SCRAPE_INTERVAL)


def escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/-/healthy":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        if self.path != "/metrics":
            self.send_error(404)
            return

        with metrics_lock:
            snapshot = metrics_snapshot

        lines = [
            "# HELP container_metrics_exporter_docker_up Whether the Docker API is reachable.",
            "# TYPE container_metrics_exporter_docker_up gauge",
            f"container_metrics_exporter_docker_up {snapshot['docker_up']}",
            "# HELP container_metrics_exporter_container_scrape_error Whether stats collection failed for a container.",
            "# TYPE container_metrics_exporter_container_scrape_error gauge",
        ]
        for name, error in sorted(snapshot["errors"].items()):
            lines.append(
                f'container_metrics_exporter_container_scrape_error{{name="{escape_label(name)}"}} {error}'
            )

        lines.extend(
            [
                "# HELP container_cpu_usage_seconds_total Total CPU time used by a Docker container.",
                "# TYPE container_cpu_usage_seconds_total counter",
                "# HELP container_memory_working_set_bytes Current Docker container memory usage excluding inactive file cache.",
                "# TYPE container_memory_working_set_bytes gauge",
            ]
        )
        for container in snapshot["containers"]:
            labels = (
                f'name="{escape_label(container["name"])}",'
                f'id="{escape_label(container["id"])}"'
            )
            lines.append(
                f"container_cpu_usage_seconds_total{{{labels}}} "
                f'{container["cpu_seconds"]:.9f}'
            )
            lines.append(
                f"container_memory_working_set_bytes{{{labels}}} "
                f'{container["memory_bytes"]}'
            )

        body = ("\n".join(lines) + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        logger.info("%s - %s", self.address_string(), format_string % args)


if __name__ == "__main__":
    threading.Thread(target=collection_loop, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), MetricsHandler)
    logger.info("Serving Docker container metrics on port %s", LISTEN_PORT)
    server.serve_forever()
