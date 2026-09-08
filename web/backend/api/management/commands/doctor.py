"""Read-only checks for the configuration and database used by this process."""

import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Check configuration, database connectivity, migration status, and media access."

    def handle(self, *args, **options):
        failures = []
        db = settings.DATABASES["default"]
        self.stdout.write(
            f"Database: {db['HOST']}:{db['PORT']}/{db['NAME']} (user {db['USER']})"
        )
        if not db["PASSWORD"] or db["PASSWORD"] == "your_secure_password_here":
            failures.append("Set POSTGRES_PASSWORD to your database password.")
        if (
            not settings.SECRET_KEY
            or settings.SECRET_KEY == "generate-a-secure-key-here"
        ):
            failures.append("Generate DJANGO_SECRET_KEY before deployment.")
        if settings.DEBUG:
            failures.append("Set DJANGO_DEBUG=False before deployment.")
        if not settings.ALLOWED_HOSTS:
            failures.append(
                "Set DJANGO_ALLOWED_HOSTS to the hostnames serving the application."
            )
        media = Path(settings.MEDIA_ROOT)
        if not media.is_dir() or not os.access(media, os.W_OK):
            failures.append(f"Create a writable media directory: {media}")
        connection.settings_dict.setdefault("OPTIONS", {})["connect_timeout"] = 5
        try:
            executor = MigrationExecutor(connection)
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if pending:
                failures.append(f"{len(pending)} migrations pending; run db:migrate.")
            else:
                self.stdout.write("Database connection and migrations: ready.")
        except DatabaseError:
            failures.append(
                "Database unavailable; check credentials, hostname, port, and server access."
            )
        if failures:
            raise CommandError("\n".join(failures))
        self.stdout.write(self.style.SUCCESS("Configuration checks passed."))
