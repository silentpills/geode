#!/bin/sh
# Validate role configuration before the official entrypoint creates PGDATA.
set -eu
: "${POSTGRES_PASSWORD:?Set POSTGRES_ADMIN_PASSWORD in the GeoDE environment}"
: "${GEODE_OWNER:?Set POSTGRES_USER}" "${GEODE_OWNER_PASSWORD:?Set POSTGRES_PASSWORD}"
: "${GEODE_APP:?Set POSTGRES_APP_USER}" "${GEODE_APP_PASSWORD:?Set POSTGRES_APP_PASSWORD}"

for role in "$GEODE_OWNER" "$GEODE_APP"; do
    case "$role" in
        postgres|pg_*|public|none)
            echo "Choose a non-reserved PostgreSQL role for GeoDE." >&2
            exit 1 ;;
    esac
    if [ "$(printf '%s' "$role" | wc -c)" -gt 63 ]; then
        echo "PostgreSQL role names must fit in 63 bytes." >&2
        exit 1
    fi
done
if [ "$GEODE_OWNER" = "$GEODE_APP" ]; then
    echo "The schema and application roles must have different names." >&2
    exit 1
fi
if [ "$GEODE_OWNER_PASSWORD" = "$GEODE_APP_PASSWORD" ] ||
   [ "$GEODE_OWNER_PASSWORD" = "$POSTGRES_PASSWORD" ] ||
   [ "$GEODE_APP_PASSWORD" = "$POSTGRES_PASSWORD" ]; then
    echo "Use three distinct passwords for the bundled database roles." >&2
    exit 1
fi
exec docker-entrypoint.sh "$@"
