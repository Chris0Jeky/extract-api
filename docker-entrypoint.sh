#!/bin/sh
set -eu

# Started as root (the image default), repair ownership of the idempotency store's
# directory, which a platform may mount root-owned, then replace PID 1 with the app as
# extract (10001): no new privileges, no inheritable capabilities. Started as any other
# user (a platform forcing a UID), run the app unchanged.
if [ "$(id -u)" = 0 ]; then
    database_path=${IDEMPOTENCY_DB_PATH:-/data/idempotency.sqlite}
    # Allowlist, checked before creating anything and again after resolving symlinks: root
    # only ever touches the data mount, whatever IDEMPOTENCY_DB_PATH says.
    directory=$(realpath -m -- "$(dirname -- "$database_path")")
    case "$directory" in
        /data|/data/*) ;;
        *)
            echo "refusing to change idempotency ownership outside /data: $directory" >&2
            exit 1
            ;;
    esac
    mkdir -p -- "$directory"
    directory=$(cd "$directory" && pwd -P)
    case "$directory" in
        /data|/data/*) ;;
        *)
            echo "refusing to change idempotency ownership outside /data: $directory" >&2
            exit 1
            ;;
    esac
    chown --no-dereference 10001:10001 "$directory"
    # Only regular database files and SQLite sidecars immediately in this directory.
    # Do not follow symlinks, recurse into subdirectories, or change other files.
    database_name=$(basename -- "$database_path")
    find "$directory" -maxdepth 1 -type f -links 1 \
        \( -name "$database_name" -o -name "$database_name-wal" \
        -o -name "$database_name-shm" -o -name "$database_name-journal" \
        -o -name '*.sqlite' -o -name '*.sqlite-*' \
        -o -name '*.sqlite3' -o -name '*.sqlite3-*' \) \
        -exec chown --no-dereference 10001:10001 {} +
    exec setpriv --reuid=10001 --regid=10001 --init-groups --no-new-privs --inh-caps=-all -- "$@"
fi

exec "$@"
