FROM flink:1.19-scala_2.12-java11

# ── Install Python 3 ──────────────────────────────────────────────────────────
# The official Flink image is Java-only. PyFlink requires Python 3.8+ installed
# in the same container so the JVM can spawn a Python process for job execution.
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# ── Install PyFlink (must match the Flink image version exactly) ──────────────
RUN pip3 install --no-cache-dir apache-flink==1.19.0

# ── Install extra Python deps used by the jobs ────────────────────────────────
RUN pip3 install --no-cache-dir \
    python-dateutil==2.9.0

# ── Copy connector JARs into Flink's lib directory ───────────────────────────
# Drop your downloaded JARs into flink/lib/ before building.
# See flink/lib/README.md for download instructions.
COPY lib/*.jar /opt/flink/lib/

# ── Copy job files ────────────────────────────────────────────────────────────
COPY jobs/ /opt/flink/jobs/
COPY sql/  /opt/flink/sql/