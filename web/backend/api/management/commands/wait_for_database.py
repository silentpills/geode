"""Wait a bounded time for PostgreSQL before running migrations."""

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, connection


class Command(BaseCommand):
    help = "Wait for a database connection; exit unsuccessfully after the timeout."

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=float, default=60)

    def handle(self, *args, **options):
        deadline = time.monotonic() + options["timeout"]
        connection.settings_dict.setdefault("OPTIONS", {})["connect_timeout"] = 5
        while True:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                self.stdout.write("Database connection ready.")
                return
            except OperationalError:
                connection.close()
                if time.monotonic() >= deadline:
                    raise CommandError(
                        "Database unavailable. Check POSTGRES_* settings and server connectivity."
                    ) from None
                time.sleep(min(1, max(0, deadline - time.monotonic())))
