"""
Populates the s4_pokedex table from draft_board.json, sprites.json, and
pokedex.json. draft_board.json is the source of truth for which Pokemon
are included -- anything in sprites.json/pokedex.json but not on the
draft board is skipped.

sprites.json and draft_board.json already share identical keys (the
draft board's display names, e.g. "Mega Venusaur", "Alolan Muk"), so
those two join trivially. pokedex.json is keyed by Showdown's own
lowercase species ID instead (e.g. "venusaurmega", "muckalola" ->
actually "alolamuk" is wrong, real id is "mukalola"), so draft-board
names have to be translated to that ID convention -- see resolve_pokedex_key().
"""
import json
import re
import unicodedata

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR
from home.models import S4Pokedex

# A few forme names that don't fit the general Mega/regional-prefix rules
# below and have to be mapped by hand.
NAME_OVERRIDES = {
    "Landorus-Incarnate": "landorus",
    "Thundurus-Incarnate": "thundurus",
    "Tornadus-Incarnate": "tornadus",
    "Enamorus-Incarnate": "enamorus",
    "Zygarde-50%": "zygarde",
    "Urshifu-Single-Strike": "urshifu",
    "Basculegion-M": "basculegion",
    "Calyrex-Ice-Rider": "calyrexice",
    "Calyrex-Shadow-Rider": "calyrexshadow",
    "Lycanroc-Midday": "lycanroc",
    "Paldean Tauros": "taurospaldeacombat",
    "Paldean Tauros Aqua": "taurospaldeaaqua",
    "Paldean Tauros Blaze": "taurospaldeablaze",
    # Draft board doesn't distinguish Meowstic's gender-locked Mega forms;
    # default to the male entry, matching Showdown's own bare-"meowstic"-is-male
    # convention.
    "Mega Meowstic": "meowsticmmega",
}

REGIONAL_PREFIXES = {"Alolan": "alola", "Galarian": "galar", "Hisuian": "hisui", "Paldean": "paldea"}


def _norm(s):
    """Lowercase, alnum-only, with accented characters transliterated
    rather than dropped (so "Flabébé" -> "flabebe", matching Showdown's
    own dex key, not "flabb")."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def resolve_pokedex_key(name, pokedex):
    """Map a draft_board.json display name to its pokedex.json key, or
    None if no mapping is found."""
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
    help = "Load the s4_pokedex table from draft_board.json, sprites.json, and pokedex.json."

    def handle(self, *args, **options):
        with open(DATA_DIR / "draft_board.json", encoding="utf-8") as f:
            points_by_name = json.load(f)
        with open(DATA_DIR / "sprites.json", encoding="utf-8") as f:
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
            rows.append(S4Pokedex(
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

        S4Pokedex.objects.all().delete()
        S4Pokedex.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} row(s) into s4_pokedex."))
        if unmapped:
            self.stdout.write(self.style.WARNING(
                f"{len(unmapped)} name(s) had no pokedex.json match (species data left blank): {unmapped}"
            ))
