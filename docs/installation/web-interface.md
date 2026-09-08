# Web interface setup

Deploy this fork from `dev`. It contains the processing library, Django API,
Celery workers, and React frontend in one checkout. There are no release or PyPI
publication steps.

## Configure

Install Docker Engine with the Compose plugin. The backend lock currently
supports Linux x86-64 deployment; native Pixi development also supports Apple
Silicon. From the repository root:

```bash
cp .env.example .env
mkdir -p var/media
```

Edit `.env`. Choose a database password and generate `DJANGO_SECRET_KEY` with
`python3 -c 'import secrets; print(secrets.token_urlsafe(50))'`. Set the hostnames
in `DJANGO_ALLOWED_HOSTS`, the public URL in `VITE_API_URL`, and `APP_PORT`.
Include `127.0.0.1` in allowed hosts for the container readiness probe. Set
`USER_ID_TO_SAVE_FILES` and `GROUP_ID_TO_SAVE_FILES` to your `id -u` and `id -g`,
and ensure the media directory is writable by that user.

The default media mount is `./var/media`; set `MEDIA_FOLDER_HOST_PATH` if using
another directory. Processing configuration in `gnss_data.cfg` is needed for CLI
processing, not for basic web setup.

## Start with bundled PostgreSQL

```bash
docker compose --profile bundled-db up --build -d --wait
```

The backend waits for PostgreSQL, runs the complete migration chain, and starts
Gunicorn, Celery, Beat, and a loopback-only Redis instance. A failed migration
stops startup. The frontend waits until the API readiness probe reports a
reachable database with no pending migrations.

Create your administrator explicitly:

```bash
docker compose exec backend python manage.py createadmin --username yourname
```

Enter the new password at the prompt. There is no default login. The command
validates password strength and refuses to overwrite an existing user. For
noninteractive provisioning, pass `DJANGO_SUPERUSER_PASSWORD` through the process
environment and add `--noinput`; avoid passwords in command-line arguments.

Open `http://localhost:8080` (or your configured URL). Native administrator
creation uses `pixi run -e web admin:create --username yourname`.

## Use an external database

Configure the connection settings described in [Database setup](database-setup.md).
Omit the bundled database profile:

```bash
docker compose up --build -d --wait
```

If you previously started the bundled service, stop it explicitly with
`docker compose --profile bundled-db stop postgres`. Omitting a profile does not
stop an already running container.

## Check and maintain

```bash
docker compose ps
docker compose logs --tail=100 backend
docker compose exec backend python manage.py doctor
docker compose exec backend python manage.py changepassword yourname
```

The read-only doctor checks configuration, database connectivity, migrations, and
media access without printing passwords. Readiness is available without login
at `/api/health-check`; it returns 503 for an unavailable or unmigrated database.
It does not monitor Celery throughput or GNSS processing jobs.

Use TLS at your reverse proxy for public access, set `DJANGO_HTTPS=True`, and set
allowed hosts/CORS origins to the URLs you serve. The edge proxy must replace
client-supplied forwarding headers and set `X-Forwarded-Proto: https`; restrict
access to the application port to that proxy. The bundled frontend preserves
that HTTPS indication when forwarding to Django. `VITE_API_URL` is baked into the
frontend build; rebuild after changing it.

See [operations](../development/operations.md) for backups, restore rehearsal,
and updates. Keep `.env` and uploaded media outside Git.
