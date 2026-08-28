"""
Populates the s3_schedule table from home/data/s3/schedule.json. Mirrors
load_s2_schedule.py / load_s4_schedule.py.
"""
import json

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR
from home.models import S3Schedule


class Command(BaseCommand):
    help = "Load the s3_schedule table from home/data/s3/schedule.json."

    def handle(self, *args, **options):
        with open(DATA_DIR / "s3" / "schedule.json", encoding="utf-8") as f:
            weeks = json.load(f)["weeks"]

        rows = []
        for week in weeks:
            for i, match in enumerate(week["matches"]):
                rows.append(S3Schedule(
                    week=week["week"],
                    week_label=week["label"],
                    match_index=i,
                    player1=match["player1"],
                    player2=match["player2"],
                    replay_url=match.get("replay_url"),
                    winner=match.get("winner"),
                    margin=match.get("margin"),
                    stats=match.get("stats"),
                ))

        S3Schedule.objects.all().delete()
        S3Schedule.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} row(s) into s3_schedule."))
