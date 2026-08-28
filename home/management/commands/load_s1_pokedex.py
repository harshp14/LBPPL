"""
Populates the s1_pokedex table from home/data/s1/draft_board.json and
home/data/s1/sprites.json, plus the shared home/data/pokedex.json species
reference. Mirrors load_s2_pokedex.py; see that command for the general
approach.
"""
import json

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR
from home.models import S1Pokedex
from .load_s4_pokedex import NAME_OVERRIDES as S4_NAME_OVERRIDES, REGIONAL_PREFIXES, resolve_pokedex_key

# S4's overrides plus S1-specific formes that aren't handled by the general
# Mega/regional-prefix rules.
NAME_OVERRIDES = {
    **S4_NAME_OVERRIDES,
    "Ogerpon-Heartflame": "ogerponhearthflame",
    "Ogerpon-Teal": "ogerpon",
    "Basculegion-Female": "basculegionf",
    "Basculegion-Male": "basculegion",
    "Indeedee-Female": "indeedeef",
    "Indeedee-Male": "indeedee",
}


def resolve(name, pokedex):
    direct = resolve_pokedex_key(name, pokedex)
    if direct:
        return direct
    if name in NAME_OVERRIDES:
        key = NAME_OVERRIDES[name]
        return key if key in pokedex else None
    return None


class Command(BaseCommand):
    help = "Load the s1_pokedex table from home/data/s1/draft_board.json and sprites.json."

    def handle(self, *args, **options):
        with open(DATA_DIR / "s1" / "draft_board.json", encoding="utf-8") as f:
            points_by_name = json.load(f)
        with open(DATA_DIR / "s1" / "sprites.json", encoding="utf-8") as f:
            sprite_by_name = json.load(f)
        with open(DATA_DIR / "pokedex.json", encoding="utf-8") as f:
            pokedex = json.load(f)

        rows = []
        unmapped = []
        for name, points in points_by_name.items():
            pokedex_key = resolve(name, pokedex)
            entry = pokedex.get(pokedex_key, {})
            if pokedex_key is None:
                unmapped.append(name)

            base_stats = entry.get("baseStats", {})
            rows.append(S1Pokedex(
                name=name,
                points=points,
                sprite_id=sprite_by_name.get(name, ""),
                pokedex_num=entry.get("num"),
                types=entry.get("types", []),
                base_hp=base_stats.get("hp"),
                base_atk=base_stats.get("atk"),
                base_def=base_stats.get("def"),
                base_spa=base_stats.get("spa"),
                base_spd=base_stats.get("spd"),
                base_spe=base_stats.get("spe"),
                abilities=entry.get("abilities", {}),
                height_m=entry.get("heightm"),
                weight_kg=entry.get("weightkg"),
                color=entry.get("color"),
                evos=entry.get("evos", []),
                egg_groups=entry.get("eggGroups", []),
                tier=entry.get("tier"),
            ))

        S1Pokedex.objects.all().delete()
        S1Pokedex.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} row(s) into s1_pokedex."))
        if unmapped:
            self.stdout.write(self.style.WARNING(
                f"{len(unmapped)} name(s) had no pokedex.json match (species data left blank): {unmapped}"
            ))
