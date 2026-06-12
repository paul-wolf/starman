"""Smoke-test command: poll the dish once and print parsed status to stdout."""

import json
from django.core.management.base import BaseCommand
from dish import grpc_client


class Command(BaseCommand):
    help = "Poll the dish once and print the parsed status (smoke test)"

    def handle(self, *args, **options):
        self.stdout.write("Connecting to dish...")
        status = grpc_client.get_status()

        if status is None:
            self.stderr.write(self.style.ERROR("Could not reach dish — check DISH_GRPC_TARGET and routing."))
            return

        raw = status.pop("raw", {})

        self.stdout.write(self.style.SUCCESS("\n--- Parsed status ---"))
        self.stdout.write(json.dumps(status, indent=2, default=str))

        self.stdout.write(self.style.SUCCESS("\n--- Raw payload (top-level keys) ---"))
        self.stdout.write(json.dumps(list(raw.keys()), indent=2))
