"""Retention and downsampling for TelemetryReading.

Retention tiers (all configurable via arguments):
  < --raw-days old        keep every row  (default: 7 days)
  < --minute-days old     keep 1 per minute (default: 30 days)
  < --hour-days old       keep 1 per hour   (default: 365 days)
  >= --hour-days old      delete entirely

Run on a schedule (e.g. daily via cron or systemd timer) to keep the
SQLite file from growing unbounded on the Pi.
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone
from datetime import timedelta

from dish.models import WatchdogConfig


class Command(BaseCommand):
    help = "Downsample and prune old TelemetryReading rows"

    def add_arguments(self, parser):
        parser.add_argument("--raw-days",    type=int, default=7,   help="Keep all rows newer than this many days (default: 7)")
        parser.add_argument("--minute-days", type=int, default=30,  help="Keep 1/minute for rows older than --raw-days up to this age (default: 30)")
        parser.add_argument("--hour-days",   type=int, default=365, help="Keep 1/hour for rows older than --minute-days up to this age (default: 365)")
        parser.add_argument("--dry-run",     action="store_true",   help="Report counts without deleting anything")

    def handle(self, *args, **options):
        now = timezone.now()
        raw_cutoff    = now - timedelta(days=options["raw_days"])
        minute_cutoff = now - timedelta(days=options["minute_days"])
        hour_cutoff   = now - timedelta(days=options["hour_days"])
        dry           = options["dry_run"]

        if dry:
            self.stdout.write("Dry run — no rows will be deleted.\n")

        with connection.cursor() as cur:
            deleted_old    = self._prune_oldest(cur, hour_cutoff, dry)
            deleted_hourly = self._downsample_hourly(cur, minute_cutoff, hour_cutoff, dry)
            deleted_minute = self._downsample_minute(cur, raw_cutoff, minute_cutoff, dry)

        total = deleted_old + deleted_hourly + deleted_minute
        self.stdout.write(
            self.style.SUCCESS(
                f"Retention complete: {deleted_minute} rows downsampled to 1/min, "
                f"{deleted_hourly} to 1/hr, {deleted_old} oldest deleted. "
                f"Total removed: {total}"
            )
        )
        if not dry:
            WatchdogConfig.objects.filter(pk=1).update(last_retain_at=now)

    def _prune_oldest(self, cur, hour_cutoff, dry):
        """Delete all rows older than hour_cutoff (beyond the 1/hr tier)."""
        cur.execute(
            "SELECT COUNT(*) FROM dish_telemetryreading WHERE timestamp < %s",
            [hour_cutoff],
        )
        count = cur.fetchone()[0]
        if not dry and count:
            cur.execute(
                "DELETE FROM dish_telemetryreading WHERE timestamp < %s",
                [hour_cutoff],
            )
        return count

    def _downsample_hourly(self, cur, minute_cutoff, hour_cutoff, dry):
        """Keep 1 row per hour for rows between minute_cutoff and hour_cutoff."""
        cur.execute(
            """
            SELECT COUNT(*) FROM dish_telemetryreading
            WHERE timestamp >= %s AND timestamp < %s
              AND id NOT IN (
                SELECT MIN(id) FROM dish_telemetryreading
                WHERE timestamp >= %s AND timestamp < %s
                GROUP BY strftime('%%Y-%%m-%%d %%H', timestamp)
              )
            """,
            [minute_cutoff, hour_cutoff, minute_cutoff, hour_cutoff],
        )
        count = cur.fetchone()[0]
        if not dry and count:
            cur.execute(
                """
                DELETE FROM dish_telemetryreading
                WHERE timestamp >= %s AND timestamp < %s
                  AND id NOT IN (
                    SELECT MIN(id) FROM dish_telemetryreading
                    WHERE timestamp >= %s AND timestamp < %s
                    GROUP BY strftime('%%Y-%%m-%%d %%H', timestamp)
                  )
                """,
                [minute_cutoff, hour_cutoff, minute_cutoff, hour_cutoff],
            )
        return count

    def _downsample_minute(self, cur, raw_cutoff, minute_cutoff, dry):
        """Keep 1 row per minute for rows between raw_cutoff and minute_cutoff."""
        cur.execute(
            """
            SELECT COUNT(*) FROM dish_telemetryreading
            WHERE timestamp >= %s AND timestamp < %s
              AND id NOT IN (
                SELECT MIN(id) FROM dish_telemetryreading
                WHERE timestamp >= %s AND timestamp < %s
                GROUP BY strftime('%%Y-%%m-%%d %%H:%%M', timestamp)
              )
            """,
            [raw_cutoff, minute_cutoff, raw_cutoff, minute_cutoff],
        )
        count = cur.fetchone()[0]
        if not dry and count:
            cur.execute(
                """
                DELETE FROM dish_telemetryreading
                WHERE timestamp >= %s AND timestamp < %s
                  AND id NOT IN (
                    SELECT MIN(id) FROM dish_telemetryreading
                    WHERE timestamp >= %s AND timestamp < %s
                    GROUP BY strftime('%%Y-%%m-%%d %%H:%%M', timestamp)
                  )
                """,
                [raw_cutoff, minute_cutoff, raw_cutoff, minute_cutoff],
            )
        return count
