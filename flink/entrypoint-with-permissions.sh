#!/bin/sh
set -eu

chown -R flink:flink /opt/flink/checkpoints
exec /docker-entrypoint.sh "$@"
