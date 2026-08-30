"""
Populates home/data/movesets.json, movedex.json, and move_categories.json --
the data behind the prep sheet's "Moves" tab. Movesets and move metadata are
mirrored from Pokemon Showdown's public data (github.com/smogon/pokemon-showdown)
rather than hand-entered; the prep-sheet category tags (entry hazard,
screens, etc.) aren't part of that data and are curated by hand below.

Only Pokemon that appear on some season's draft board are kept (not the
full ~1300-species dex), and only moves that fall in a tracked category
(not full movepools) -- this keeps the mirrored files a small fraction of
the size of the source data. Re-run this whenever a new season's draft
board adds Pokemon this hasn't seen yet.
"""
import json
import re

import requests
from django.core.management.base import BaseCommand, CommandError

from home.data_access import DATA_DIR
from home.models import S1Pokedex, S2Pokedex, S3Pokedex, S4Pokedex
from .load_s1_pokedex import NAME_OVERRIDES as EXTRA_NAME_OVERRIDES
from .load_s4_pokedex import resolve_pokedex_key

LEARNSETS_URL = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/learnsets.ts"
MOVES_URL = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/moves.ts"

# A couple of draft-board names resolve_pokedex_key()/NAME_OVERRIDES don't
# cover -- gendered Nidoran have no Mega/regional/Tera pattern to fall
# back on.
NIDORAN_OVERRIDES = {"Nidoran-Female": "nidoranf", "Nidoran-Male": "nidoranm"}

# Showdown's data doesn't tag moves with these prep-sheet categories, so
# this list is curated by hand. Checked at load time against the live
# movedex, so a stale/renamed move id fails loudly instead of silently
# vanishing. "priority" is derived from moves.ts's own priority field
# instead of hand-listed here.
MOVE_CATEGORIES = {
    "entry_hazard": [
        "stealthrock", "spikes", "toxicspikes", "stickyweb",
        "ceaselessedge", "stoneaxe",
    ],
    "hazard_removal": ["rapidspin", "defog", "courtchange", "tidyup", "mortalspin"],
    "healing": [
        "recover", "roost", "slackoff", "softboiled", "milkdrink", "moonlight",
        "morningsun", "synthesis", "rest", "wish", "painsplit", "purify",
        "shoreup", "strengthsap", "lifedew", "junglehealing", "healorder",
        "aromatherapy", "healbell", "leechseed", "swallow", "present",
    ],
    "momentum": [
        "uturn", "voltswitch", "flipturn", "partingshot", "teleport",
        "batonpass", "chillyreception", "shedtail",
    ],
    "item_removal": ["knockoff", "trick", "switcheroo", "thief", "covet"],
    "status": [
        "thunderwave", "willowisp", "toxic", "poisonpowder", "stunspore",
        "sleeppowder", "spore", "hypnosis", "sing", "glare", "nuzzle",
        "darkvoid", "yawn", "confuseray", "swagger", "flatter",
        "toxicthread", "grasswhistle", "lovelykiss", "sweetkiss",
    ],
    "disruption": [
        "taunt", "encore", "torment", "disable", "whirlwind", "roar",
        "dragontail", "circlethrow", "haze", "trickroom", "imprison",
        "destinybond", "spite", "clearsmog", "partingshot", "yawn",
    ],
    "screens": ["reflect", "lightscreen", "auroraveil"],
    "vgc_moves": [
        "allyswitch", "brickbreak", "coaching", "followme", "helpinghand",
        "ragepowder", "snarl", "wideguard",
    ],
    "speed_control": ["bulldoze", "electroweb", "icywind", "tailwind", "trickroom"],
}

# Both moves.ts and learnsets.ts are one-tab-indented "id: { ... }," object
# literals at the top level -- this finds each entry's key and text span
# regardless of which file it's applied to.
_ENTRY_RE = re.compile(r'^\t"?([a-zA-Z0-9]+)"?: \{$', re.M)


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _top_level_blocks(text):
    matches = list(_ENTRY_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        yield m.group(1), text[start:end]


def _parse_moves(text):
    """id -> {name, priority}, read directly out of moves.ts's source text
    instead of executing it (the file has real TS syntax -- and function
    bodies -- inside move effect handlers, so it isn't valid JSON/JS on
    its own; we only need these two fields, both trivial to regex out)."""
    moves = {}
    for move_id, block in _top_level_blocks(text):
        name_match = re.search(r'name:\s*"([^"]*)"', block)
        if not name_match:
            continue
        priority_match = re.search(r'priority:\s*(-?\d+)', block)
        moves[move_id] = {
            "name": name_match.group(1),
            "priority": int(priority_match.group(1)) if priority_match else 0,
        }
    return moves


def _parse_learnsets(text):
    """species key -> list of move ids it can learn (any generation/method
    -- Showdown keeps this list current-gen-obtainable via Home transfers,
    so presence alone is enough for "can this Pokemon plausibly run X" on
    a prep sheet). Formes with no learnset of their own (Therian, Origin,
    Mega, ...) aren't included here; see learnset_key_for's baseSpecies
    fallback below."""
    learnsets = {}
    for species_key, block in _top_level_blocks(text):
        ls_match = re.search(r'learnset:\s*\{(.*?)\n\t\t\},', block, re.S)
        if ls_match:
            learnsets[species_key] = re.findall(r'\n\t\t\t"?([a-zA-Z0-9]+)"?:', ls_match.group(1))
    return learnsets


class Command(BaseCommand):
    help = "Mirror Pokemon Showdown movesets and tag prep-sheet move categories for every drafted Pokemon."

    def handle(self, *args, **options):
        with open(DATA_DIR / "pokedex.json", encoding="utf-8") as f:
            pokedex = json.load(f)

        moves_text = requests.get(MOVES_URL, timeout=30).text
        learnsets_text = requests.get(LEARNSETS_URL, timeout=30).text
        movedex_full = _parse_moves(moves_text)
        learnsets = _parse_learnsets(learnsets_text)

        tagged_move_ids = sorted({m for moves in MOVE_CATEGORIES.values() for m in moves})
        unknown = [m for m in tagged_move_ids if m not in movedex_full]
        if unknown:
            raise CommandError(f"MOVE_CATEGORIES references unknown move id(s), fix the list: {unknown}")

        priority_moves = sorted(m for m, d in movedex_full.items() if d["priority"] > 0)
        categories = {**MOVE_CATEGORIES, "priority": priority_moves}
        tracked_move_ids = sorted({m for moves in categories.values() for m in moves})

        drafted_names = set()
        for model in (S1Pokedex, S2Pokedex, S3Pokedex, S4Pokedex):
            drafted_names.update(model.objects.exclude(points=0).values_list("name", flat=True))

        def resolve(name):
            if name in NIDORAN_OVERRIDES:
                return NIDORAN_OVERRIDES[name]
            key = resolve_pokedex_key(name, pokedex)
            if key:
                return key
            if name in EXTRA_NAME_OVERRIDES:
                key = EXTRA_NAME_OVERRIDES[name]
                return key if key in pokedex else None
            if name.endswith("-Tera"):
                return resolve(name[: -len("-Tera")])
            return None

        def learnset_key_for(species_key):
            """Follow baseSpecies chains for battle-only formes (Mega,
            Therian, Origin, ...) whose learnsets.ts entry has no
            'learnset' of its own -- Showdown reuses the base forme's full
            movepool for these instead of duplicating it."""
            seen = set()
            key = species_key
            while key and key not in seen:
                seen.add(key)
                if key in learnsets:
                    return key
                base = pokedex.get(key, {}).get("baseSpecies")
                key = _norm(base) if base else None
            return None

        movesets = {}
        unmapped = []
        for name in sorted(drafted_names):
            species_key = resolve(name)
            ls_key = learnset_key_for(species_key) if species_key else None
            if ls_key is None:
                unmapped.append(name)
                continue
            movesets[name] = sorted(set(learnsets[ls_key]) & set(tracked_move_ids))

        movedex = {m: {"name": movedex_full[m]["name"]} for m in tracked_move_ids}

        with open(DATA_DIR / "movesets.json", "w", encoding="utf-8") as f:
            json.dump(movesets, f, indent=2, ensure_ascii=False)
        with open(DATA_DIR / "movedex.json", "w", encoding="utf-8") as f:
            json.dump(movedex, f, indent=2, ensure_ascii=False)
        with open(DATA_DIR / "move_categories.json", "w", encoding="utf-8") as f:
            json.dump(categories, f, indent=2)

        self.stdout.write(self.style.SUCCESS(
            f"Wrote movesets for {len(movesets)} Pokemon, {len(movedex)} tracked moves, {len(categories)} categories."
        ))
        if unmapped:
            self.stdout.write(self.style.WARNING(f"{len(unmapped)} name(s) had no learnset match: {unmapped}"))
