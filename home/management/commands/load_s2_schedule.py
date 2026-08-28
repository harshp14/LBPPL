"""
Populates the s2_schedule table from home/data/s2/schedule.json. Mirrors
load_s4_schedule.py. Only regular-season weeks are included -- the source
sheet's playoff bracket tab was intentionally left out when this file was
built.
"""
import json

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR
from home.models import S2Schedule


class Command(BaseCommand):
    help = "Load the s2_schedule table from home/data/s2/schedule.json."

    def handle(self, *args, **options):
        with open(DATA_DIR / "s2" / "schedule.json", encoding="utf-8") as f:
            weeks = json.load(f)["weeks"]

        rows = []
        for week in weeks:
            for i, match in enumerate(week["matches"]):
                rows.append(S2Schedule(
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

        S2Schedule.objects.all().delete()
        S2Schedule.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} row(s) into s2_schedule."))
