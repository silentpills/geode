"""Create the first administrator explicitly; never install default credentials."""

import getpass
import os

from api.models import Role, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Create an administrator with a new password (existing users are never overwritten)."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", default="")
        parser.add_argument("--noinput", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if User.objects.filter(username=options["username"]).exists():
            raise CommandError(
                "That username already exists. Use changepassword to reset its password."
            )
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not password and not options["noinput"]:
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Password (again): "):
                raise CommandError("Passwords do not match.")
        if not password:
            raise CommandError(
                "Provide a password interactively or through DJANGO_SUPERUSER_PASSWORD."
            )
        user = User(username=options["username"], email=options["email"])
        try:
            validate_password(password, user=user)
        except ValidationError as error:
            raise CommandError("; ".join(error.messages)) from error
        role, _ = Role.objects.get_or_create(
            name="admin",
            defaults={"role_api": False, "allow_all": True, "is_active": True},
        )
        if not role.allow_all or not role.is_active:
            raise CommandError(
                "Existing admin role is restricted or inactive; review it before creating an administrator."
            )
        User.objects.create_superuser(
            username=user.username, email=user.email, password=password, role=role
        )
        self.stdout.write(self.style.SUCCESS("Administrator created."))
