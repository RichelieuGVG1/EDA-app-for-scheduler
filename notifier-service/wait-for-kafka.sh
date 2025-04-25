#!/usr/bin/env bash
set -e

# Проверка на аргументы
if [ -z "$1" ]; then
  echo "Usage: $0 host:port [timeout] [command]"
  exit 1
fi

host_port="$1"
shift
timeout=60

# Если передан таймаут (второй аргумент)
if [[ "$1" =~ ^[0-9]+$ ]]; then
  timeout="$1"
  shift
fi

echo "Waiting up to ${timeout}s for ${host_port}..."

# Разделить host и port
IFS=":" read host port <<< "$host_port"

# Проверка что host и port заданы
if [ -z "$host" ] || [ -z "$port" ]; then
  echo "Invalid host:port format. Example: kafka:9092"
  exit 1
fi

start_ts=$(date +%s)
while :; do
  if nc -z "$host" "$port" 2>/dev/null; then
    echo "Host ${host}:${port} is available!"
    break
  fi
  now_ts=$(date +%s)
  if (( now_ts - start_ts >= timeout )); then
    echo "Timeout reached after ${timeout}s waiting for ${host}:${port}"
    exit 1
  fi
  sleep 1
done

# Если передана команда, выполняем её
if [ "$#" -gt 0 ]; then
  echo "Executing: $@"
  exec "$@"
fi
