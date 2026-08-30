#!/bin/sh
set -eu

database_path="${AELORA_GATEWAY_DB:-/app/data/gateway.db}"
database_dir="$(dirname "$database_path")"

mkdir -p "$database_dir"
chown aelora:aelora "$database_dir"
if [ -e "$database_path" ]; then
  chown aelora:aelora "$database_path"
fi

exec gosu aelora "$@"
