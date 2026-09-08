# Operations

## Before an update

Record the deployed `git rev-parse HEAD`, retain `.env` securely, and take a
matching database and media backup. Use commits on `dev` as deployment versions.
This fork does not publish packages or create automated releases.

## Bundled database backup and restore rehearsal

Pause application writers while taking a matching database/media snapshot:

```bash
mkdir -p backups
docker compose stop frontend backend
docker compose --profile bundled-db exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/geode.dump
tar -C var/media -czf backups/media.tar.gz .
docker compose start backend frontend
```

Adjust the media path if configured differently. Check each command's exit
status; an empty or partial dump is not a backup. Copy completed backups to
separate storage. Do not commit credentials, dumps, or uploaded files.

Rehearse restoration into a **new empty database**, leaving the source intact:

```bash
docker compose --profile bundled-db exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" geode_restore_check'
docker compose --profile bundled-db exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d geode_restore_check --exit-on-error --no-owner' < backups/geode.dump
docker compose exec -e POSTGRES_DB=geode_restore_check backend python manage.py migrate --check
mkdir -p var/media-restore-check
tar -C var/media-restore-check -xzf backups/media.tar.gz
```

Use a different new database name for another rehearsal. The API and migration
tests exercise this `pg_dump`/`pg_restore` round trip on an isolated PostgreSQL
cluster. For an external server, use its equivalent client tools and credentials.
A real recovery also restores media, points the application at the restored
database, runs migrations for the chosen checkout, and verifies login and station
metadata before resuming writers.

## Upgrade procedure

After backing up, update the reviewed `dev` checkout and rebuild:

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

Use Pixi 0.80.0, as pinned in CI and Docker. The `runtime` and `web` environments
share a solve group, so backend tests and Docker use the same Python and library
versions. The runtime excludes pytest, Ruff, and other development tools.
SQLite is constrained to a compatible current library; an old monolithic
package previously shadowed `libsqlite` and broke Python/pre-commit imports.
The frontend uses Node 22 with `npm ci` and its committed package lock.

For an intentional Python update, edit `pixi.toml` or run `pixi update`, review
`pixi.lock`, and run the checks in [Contributing](contributing.md). Keep the Pixi
version in the manifest, Dockerfile, and CI aligned. Do not maintain a second
backend requirements file. Django 5.2 LTS remains the selected series; the schema
repair did not require a major framework upgrade. Django REST Framework moves
to 3.17.2 for the security fixes documented in its
[release notes](https://www.django-rest-framework.org/community/release-notes/#3172).
The runtime audit also prompted targeted updates to aiohttp, click,
pydantic-settings, and soupsieve.

The Python security workflow audits the runtime's locked PyPI dependencies and
fails on vulnerabilities or an empty dependency selection. Conda native packages
are outside that audit; the Docker workflow also reports image vulnerabilities
with Trivy. Frontend security advisories require reviewing the npm dependency
tree; do not apply `npm audit fix --force` without checking compatibility.
