import time

from auditlog.context import set_actor
from auditlog.middleware import AuditlogMiddleware as _AuditlogMiddleware
from django.utils.functional import SimpleLazyObject
from django.db.utils import OperationalError as DatabaseOperationalError
from django.db import connections
from django.http import JsonResponse


class CustomAuditlogMiddleware(_AuditlogMiddleware):
    """
    This middleware fixes the issue with the auditlog middleware where the actor is not set correctly.
    Source: https://github.com/jazzband/django-auditlog/issues/115
    """

    def __call__(self, request):
        remote_addr = self._get_remote_addr(request)

        user = SimpleLazyObject(lambda: getattr(request, "user", None))

        context = set_actor(actor=user, remote_addr=remote_addr)

        with context:
            return self.get_response(request)


class DatabaseHealthCheckMiddleware:
    """
    DRF exception handler cannot catch OperationalError by itself, so this
    middleware probes the database before passing the request through.

    To avoid running SELECT 1 on every single request, we cache the result
    for a short period (default 5 seconds).  A failure clears the cache
    immediately so the next request retries.
    """
    _CACHE_TTL = 5  # seconds

    def __init__(self, get_response):
        self.get_response = get_response
        self._last_check_time = 0.0
        self._last_check_ok = False

    def _db_error_response(self):
        return JsonResponse(
            {
                "type": "database_error",
                "errors": [
                    {
                        "code": "database_error",
                        "detail": "Error when trying to connect to database",
                    }
                ]
            },
            status=503
        )

    def __call__(self, request):
        now = time.monotonic()
        if self._last_check_ok and (now - self._last_check_time) < self._CACHE_TTL:
            try:
                return self.get_response(request)
            except DatabaseOperationalError:
                self._last_check_ok = False
                return self._db_error_response()

        db_conn = connections['default']
        try:
            with db_conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        except DatabaseOperationalError:
            self._last_check_ok = False
            return self._db_error_response()
        else:
            self._last_check_time = now
            self._last_check_ok = True
            return self.get_response(request)
