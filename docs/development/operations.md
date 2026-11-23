# Operations

## Before an update

Record the deployed `git rev-parse HEAD`, retain `.env` securely, and take a
matching database and media backup. Use commits on `dev` as deployment versions.
This fork does not publish packages or create automated releases.

## Bundled database backup and restore rehearsal

For a processing installation, pause CLI submissions and scheduled commands first.
Let scientific workers finish, check the job receipts, and stop the worker
processes before taking matching database, media, archive and solution snapshots.
Then pause the web services:

```bash
umask 077
mkdir -p backups
docker compose stop frontend backend
docker compose --profile bundled-db exec -T postgres sh -c 'pg_dump -U "$GEODE_OWNER" -d "$POSTGRES_DB" -Fc' > backups/geode.dump
tar -C var/media -czf backups/media.tar.gz .
docker compose start backend frontend
```

Adjust the media path if configured differently. Check each command's exit
status; an empty or partial dump is not a backup. Copy completed backups to
separate storage. Do not commit credentials, dumps, or uploaded files.

Rehearse restoration into a **new empty database**, leaving the source intact:

```bash
docker compose --profile bundled-db exec -T postgres sh -c 'createdb -U postgres -O "$GEODE_OWNER" geode_restore_check'
docker compose --profile bundled-db exec -T postgres sh -c 'pg_restore -U "$GEODE_OWNER" -d geode_restore_check --exit-on-error --no-owner --no-privileges' < backups/geode.dump
docker compose --profile bundled-db exec -T postgres sh -c 'psql -U "$GEODE_OWNER" -d geode_restore_check -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/20-geode-grants.sql'
docker compose exec -e POSTGRES_DB=geode_restore_check backend python manage.py migrate --check
mkdir -p var/media-restore-check
tar -C var/media-restore-check -xzf backups/media.tar.gz
```

Use a different new database name for another rehearsal. The API and migration
tests exercise this `pg_dump`/`pg_restore` round trip on an isolated PostgreSQL
cluster. For an external server, use its equivalent client tools and credentials.
Bring up a restored processing installation with an empty, isolated compute
queue. Reconcile queued or running receipts with the restored files before
submitting work. Retain the original broker volume for investigation.
A real recovery also restores media, points the application at the restored
database, runs migrations for the chosen checkout, and verifies login and station
metadata before resuming writers.

## Upgrade procedure

For a PostgreSQL major-version change, keep the old instance and volume until
the new one is validated. Take the dump **using the old installation's settings**.
For example, earlier Compose releases exported the owner as `POSTGRES_USER`
inside the database container. Select a new Compose project name and new loopback
ports for the target, and restore media into a separate directory. Copy and
update the target's environment file with the bootstrap, owner, and app passwords.
Start **only** the target `postgres` service first. Restore the dump into its
empty `POSTGRES_DB` with the owner's login using `pg_restore --exit-on-error
--no-owner --no-privileges`. Apply `20-geode-grants.sql` to that database as
in the rehearsal above. Then bring up the complete target project, run
`manage.py doctor`, and verify a login, station records, and uploaded media
before using the new instance. Use the same project name and environment file
throughout with `docker compose -p <target-project> --env-file <target-env>`.

For a same-major update, back up, update the reviewed `dev` checkout and rebuild:

```bash
docker compose --profile bundled-db up --build -d --wait
docker compose exec backend python manage.py doctor
```

Omit the profile for external PostgreSQL. Failed migrations stop the backend;
inspect logs and repair the cause instead of marking migrations applied manually.
If rollback is necessary after a schema change, restore the matching database
and media backup along with the old checkout. Reverting application code alone
may not reverse database changes.

## Dependency and environment maintenance

Use the project-pinned Pixi from `mise.toml`. The `runtime` and `web` environments
share a solve group, so backend tests and Docker use the same Python and library
versions. The runtime excludes pytest, Ruff, and other development tools.
SQLite is constrained to a compatible current library; an old monolithic
package previously shadowed `libsqlite` and broke Python/pre-commit imports.
The frontend uses Node 22 with `npm ci` and its committed package lock.

For an intentional Python update, edit `pixi.toml` or run `pixi update <packages>`, review
`pixi.lock`, and run the checks in [Contributing](contributing.md). Keep the Pixi
version in `mise.toml`, the Pixi manifest, Dockerfile, and CI aligned. The
backend uses Django 5.2 LTS and Django REST Framework 3.18 from the shared
lockfile.

The Python security workflow audits the runtime's locked PyPI dependencies and
fails on vulnerabilities or an empty dependency selection. Conda native packages
are outside that audit; the Docker workflow also reports image vulnerabilities
with Trivy. Frontend security advisories require reviewing the npm dependency
tree; do not apply `npm audit fix --force` without checking compatibility.

## Interrupted scientific processing

Use `pixi run --locked compute:status JOB_UUID` before resubmitting a job.
A worker that disappears during an external program may leave a running receipt.
Check the process, station/day files and database records together.

For GAMIT, normal targeted rebuilds use a sibling `.<session>-attempt-*`
directory. A failed or dry attempt can be inspected there while the previous
published subnet remains available. If an old subnet directory has no matching
statistics, archive that subnet directory separately before retrying. If
statistics exist without the corresponding files, or a `.previous` tree or
`.geode-publish-pending` marker remains, reconcile the database and the files
from the same completed attempt. The project/day purge is an explicit fresh
start and can remove other subnets for that day.
