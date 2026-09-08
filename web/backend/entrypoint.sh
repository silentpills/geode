#!/bin/bash
set -euo pipefail
# The generated hook activates the same locked environment used for API tests.
if [[ -f /app/runtime-hook.sh ]]; then
    source /app/runtime-hook.sh
fi
python /app/web/backend/manage.py wait_for_database --timeout "${DATABASE_WAIT_SECONDS:-60}"
python /app/web/backend/manage.py migrate --noinput
exec "$@"
