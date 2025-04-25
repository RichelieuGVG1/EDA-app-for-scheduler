#!/usr/bin/env bash
set -e

host="$1"
shift
timeout=60

# Опционально: вы можете передавать timeout как второй аргумент
if [[ "$1" =~ ^[0-9]+$ ]]; then
  timeout="$1"
  shift
fi

echo "Waiting up to ${timeout}s for ${host}…"

start_ts=$(date +%s)
while :; do
  if nc -z $(echo $host | tr ':' ' '); then
    echo "Host ${host} is available!"
    break
  fi
  now_ts=$(date +%s)
  if (( now_ts - start_ts >= timeout )); then
    echo "Timeout reached after ${timeout}s waiting for ${host}"
    exit 1
  fi
  sleep 1
done

# После разделителя — реальная команда, переданная в docker-compose
if [ "$#" -gt 0 ]; then
  echo "Executing: $@"
  exec "$@"
fi
