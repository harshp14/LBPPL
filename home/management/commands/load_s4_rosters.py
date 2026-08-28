"""
Populates the s4_rosters table from rosters.json. One row per team, keyed
by coach_name; each team's drafted Pokemon (name + points) are kept as a
single JSON column rather than a separate table, mirroring the source
file's own shape.
"""
import json

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR
from home.models import S4Rosters


class Command(BaseCommand):
    help = "Load the s4_rosters table from rosters.json."

    def handle(self, *args, **options):
        with open(DATA_DIR / "rosters.json", encoding="utf-8") as f:
            teams = json.load(f)["teams"]

        rows = [
            S4Rosters(
                coach_name=team["coach_name"],
                team_name=team.get("team_name"),
                logo=team.get("logo", ""),
                pokemon=team.get("pokemon", []),
                free_agents_used=team.get("free_agents_used", 0),
            )
            for team in teams
        ]

        S4Rosters.objects.all().delete()
        S4Rosters.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} row(s) into s4_rosters."))
