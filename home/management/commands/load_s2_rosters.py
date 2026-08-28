"""
Populates the s2_rosters table from home/data/s2/rosters.json. Mirrors
load_s4_rosters.py.
"""
import json

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR
from home.models import S2Rosters


class Command(BaseCommand):
    help = "Load the s2_rosters table from home/data/s2/rosters.json."

    def handle(self, *args, **options):
        with open(DATA_DIR / "s2" / "rosters.json", encoding="utf-8") as f:
            teams = json.load(f)["teams"]

        rows = [
            S2Rosters(
                coach_name=team["coach_name"],
                team_name=team.get("team_name"),
                logo=team.get("logo", ""),
                pokemon=team.get("pokemon", []),
                free_agents_used=team.get("free_agents_used", 0),
            )
            for team in teams
        ]

        S2Rosters.objects.all().delete()
        S2Rosters.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} row(s) into s2_rosters."))
