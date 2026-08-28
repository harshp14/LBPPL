"""
Populates the s1_schedule table from home/data/s1/schedule.json. Mirrors
load_s2_schedule.py. Only regular-season weeks (Rounds 1-13 on the source
sheet) are included -- the playoff bracket was left out, matching how S2/S4
were loaded. Per-match margin and stats aren't available from the sheet for
S1 (only win/loss per week, not score), so both are left null.
"""
import json

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR
from home.models import S1Schedule


class Command(BaseCommand):
    help = "Load the s1_schedule table from home/data/s1/schedule.json."

    def handle(self, *args, **options):
        with open(DATA_DIR / "s1" / "schedule.json", encoding="utf-8") as f:
            weeks = json.load(f)["weeks"]

        rows = []
        for week in weeks:
            for i, match in enumerate(week["matches"]):
                rows.append(S1Schedule(
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

        S1Schedule.objects.all().delete()
        S1Schedule.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} row(s) into s1_schedule."))
