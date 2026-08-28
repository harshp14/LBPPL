"""
Populates the s1_rosters table from home/data/s1/rosters.json. Mirrors
load_s2_rosters.py.

S1 had a unique "Tera Captain" mechanic on top of the normal draft: each
coach spent a separate 15-point budget (captaining a Pokemon costs the same
as its draft price) to designate 2-3 of their own Pokemon as Tera Captains,
each granted 3 Tera Crystal types. Rather than a separate table, that data
is carried inline on the relevant entries in S1Rosters.pokemon as
`is_tera_captain` / `tera_types` -- see home/data/s1/rosters.json. This
command just validates those assignments against the S1 rules and warns
(without blocking the import) if historical data doesn't fit the rules
cleanly.
"""
import json

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR
from home.models import S1Pokedex, S1Rosters

CAPTAIN_BUDGET = 15
MAX_CAPTAIN_COST = 9

# Species banned from being made a Tera Captain regardless of cost (from the
# S1 "Pokemon Board" tab's "Tera Banned" tier).
TERA_BANNED = {
    "Alcremie", "Araquanid", "Basculegion-Female", "Basculegion-Male", "Blaziken",
    "Cetitan", "Chandelure", "Comfey", "Delphox", "Diancie", "Emboar", "Fezandipiti",
    "Floatzel", "Frosmoth", "Hisuian Braviary", "Hitmonlee", "Hoopa", "Iron Thorns",
    "Kilowattrel", "Lucario", "Meloetta", "Oricorio", "Paldean Tauros Aqua",
    "Paldean Tauros Blaze", "Polteageist", "Porygon2", "Regieleki", "Registeel",
    "Sinistcha", "Staraptor", "Torterra", "Venomoth",
}


class Command(BaseCommand):
    help = "Load the s1_rosters table from home/data/s1/rosters.json."

    def handle(self, *args, **options):
        with open(DATA_DIR / "s1" / "rosters.json", encoding="utf-8") as f:
            teams = json.load(f)["teams"]

        types_by_name = dict(S1Pokedex.objects.values_list("name", "types"))

        rows = []
        for team in teams:
            self._validate_captains(team, types_by_name)
            rows.append(S1Rosters(
                coach_name=team["coach_name"],
                team_name=team.get("team_name"),
                logo=team.get("logo", ""),
                pokemon=team.get("pokemon", []),
                free_agents_used=team.get("free_agents_used", 0),
            ))

        S1Rosters.objects.all().delete()
        S1Rosters.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} row(s) into s1_rosters."))

    def _validate_captains(self, team, types_by_name):
        coach = team["coach_name"]
        captains = [p for p in team.get("pokemon", []) if p.get("is_tera_captain")]
        if not captains:
            return

        total_cost = sum(p["points"] for p in captains)
        if total_cost > CAPTAIN_BUDGET:
            self.stdout.write(self.style.WARNING(
                f"{coach}: captain cost {total_cost} exceeds the {CAPTAIN_BUDGET}pt budget"
            ))
        if not (1 <= len(captains) <= 3):
            self.stdout.write(self.style.WARNING(
                f"{coach}: {len(captains)} tera captain(s) assigned (rule allows 2-3)"
            ))

        for p in captains:
            name, points, tera_types = p["name"], p["points"], p.get("tera_types", [])
            if name in TERA_BANNED:
                self.stdout.write(self.style.WARNING(f"{coach}: {name} is on the Tera Banned list"))
            elif points > MAX_CAPTAIN_COST:
                self.stdout.write(self.style.WARNING(
                    f"{coach}: {name} costs {points}pts, over the {MAX_CAPTAIN_COST}pt captain limit"
                ))
            if len(tera_types) != 3:
                self.stdout.write(self.style.WARNING(f"{coach}: {name} has {len(tera_types)} tera type(s), expected 3"))
            stab = types_by_name.get(name, [])
            if stab and not any(t in stab for t in tera_types):
                self.stdout.write(self.style.WARNING(
                    f"{coach}: {name}'s tera types {tera_types} include no STAB match (its types: {stab})"
                ))
