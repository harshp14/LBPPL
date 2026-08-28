"""
Populates the s4_free_agency_log table from free_agency_log.json. One row
per transaction, in the same order as the source file (oldest first);
drops/pickups are kept as JSON columns, mirroring the source file's own
shape.
"""
import json

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR
from home.models import S4FreeAgencyLog


class Command(BaseCommand):
    help = "Load the s4_free_agency_log table from free_agency_log.json."

    def handle(self, *args, **options):
        with open(DATA_DIR / "free_agency_log.json", encoding="utf-8") as f:
            transactions = json.load(f)["transactions"]

        rows = [
            S4FreeAgencyLog(
                coach=txn["coach"],
                team_name=txn.get("team_name"),
                drops=txn.get("drops", []),
                pickups=txn.get("pickups", []),
            )
            for txn in transactions
        ]

        S4FreeAgencyLog.objects.all().delete()
        S4FreeAgencyLog.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} row(s) into s4_free_agency_log."))
