"""
Populates the s2_free_agency_log table from
home/data/s2/free_agency_log.json. Mirrors load_s4_free_agency_log.py.
"""
import json

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR
from home.models import S2FreeAgencyLog


class Command(BaseCommand):
    help = "Load the s2_free_agency_log table from home/data/s2/free_agency_log.json."

    def handle(self, *args, **options):
        with open(DATA_DIR / "s2" / "free_agency_log.json", encoding="utf-8") as f:
            transactions = json.load(f)["transactions"]

        rows = [
            S2FreeAgencyLog(
                coach=txn["coach"],
                team_name=txn.get("team_name"),
                drops=txn.get("drops", []),
                pickups=txn.get("pickups", []),
            )
            for txn in transactions
        ]

        S2FreeAgencyLog.objects.all().delete()
        S2FreeAgencyLog.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} row(s) into s2_free_agency_log."))
