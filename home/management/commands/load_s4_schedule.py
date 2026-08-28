"""
Populates the s4_schedule table from schedule.json. One row per match;
match_index is the match's position within its week's matches list, so
(week, match_index) reproduces the same address set_match_replay() and
set_match_from_replay() use against the JSON file. Per-Pokemon stats are
kept as a single JSON column rather than a separate table, mirroring the
source file's own shape.
"""
import json

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR
from home.models import S4Schedule


class Command(BaseCommand):
    help = "Load the s4_schedule table from schedule.json."

    def handle(self, *args, **options):
        with open(DATA_DIR / "schedule.json", encoding="utf-8") as f:
            weeks = json.load(f)["weeks"]

        rows = []
        for week in weeks:
            for i, match in enumerate(week["matches"]):
                rows.append(S4Schedule(
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

        S4Schedule.objects.all().delete()
        S4Schedule.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} row(s) into s4_schedule."))
