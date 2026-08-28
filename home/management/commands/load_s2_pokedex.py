"""
Populates the s2_pokedex table from home/data/s2/draft_board.json and
home/data/s2/sprites.json, plus the shared home/data/pokedex.json species
reference. draft_board.json is the source of truth for which Pokemon are
included -- anything in pokedex.json but not on the draft board is skipped.
Mirrors load_s4_pokedex.py; see that command for the general approach.
"""
import re
import unicodedata

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR
from home.models import S2Pokedex
from .load_s4_pokedex import NAME_OVERRIDES as S4_NAME_OVERRIDES, REGIONAL_PREFIXES
import json

# S4's overrides plus a few forms that only show up on the S2 board.
NAME_OVERRIDES = {
    **S4_NAME_OVERRIDES,
    "Eternamax Eternatus": "eternatuseternamax",
    "Nidoran-Female": "nidoranf",
    "Nidoran-Male": "nidoranm",
}


def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def resolve_pokedex_key(name, pokedex):
    direct = _norm(name)
    if direct in pokedex:
        return direct

    if name in NAME_OVERRIDES:
        return NAME_OVERRIDES[name] if NAME_OVERRIDES[name] in pokedex else None

    if name.startswith("Mega "):
        rest = name[len("Mega "):]
        parts = rest.rsplit(" ", 1)
        if len(parts) == 2 and parts[1] in ("X", "Y", "Z"):
            base, letter = parts
            key = _norm(base) + "mega" + letter.lower()
        else:
            key = _norm(rest) + "mega"
        return key if key in pokedex else None

    if name.startswith("Primal "):
        key = _norm(name[len("Primal "):]) + "primal"
        return key if key in pokedex else None

    parts = name.split(" ", 1)
    if len(parts) == 2 and parts[0] in REGIONAL_PREFIXES:
        key = _norm(parts[1]) + REGIONAL_PREFIXES[parts[0]]
        return key if key in pokedex else None

    return None


class Command(BaseCommand):
    help = "Load the s2_pokedex table from home/data/s2/draft_board.json and sprites.json."

    def handle(self, *args, **options):
        with open(DATA_DIR / "s2" / "draft_board.json", encoding="utf-8") as f:
            points_by_name = json.load(f)
        with open(DATA_DIR / "s2" / "sprites.json", encoding="utf-8") as f:
            sprite_by_name = json.load(f)
        with open(DATA_DIR / "pokedex.json", encoding="utf-8") as f:
            pokedex = json.load(f)

        rows = []
        unmapped = []
        for name, points in points_by_name.items():
            pokedex_key = resolve_pokedex_key(name, pokedex)
            entry = pokedex.get(pokedex_key, {})
            if pokedex_key is None:
                unmapped.append(name)

            base_stats = entry.get("baseStats", {})
            rows.append(S2Pokedex(
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

        S2Pokedex.objects.all().delete()
        S2Pokedex.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} row(s) into s2_pokedex."))
        if unmapped:
            self.stdout.write(self.style.WARNING(
                f"{len(unmapped)} name(s) had no pokedex.json match (species data left blank): {unmapped}"
            ))
