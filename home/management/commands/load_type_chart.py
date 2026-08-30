"""
Populates home/data/type_chart.json -- the 18x18 type effectiveness table
behind the prep sheet's Type Matchup section, mirrored from Pokemon
Showdown's public data (the same github.com/smogon/pokemon-showdown
source as load_movesets.py) rather than hand-entered.

Source encodes damage-taken as a code per (defending type, attacking
type): 0 = normal, 1 = super effective (weak), 2 = not very effective
(resists), 3 = no effect (immune). We store it as the multiplier
directly (1, 2, 0.5, 0) since that's what a matchup calculation needs.
"""
import json
import re

import requests
from django.core.management.base import BaseCommand, CommandError

from home.data_access import DATA_DIR

TYPE_CHART_URL = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/typechart.ts"

TYPES = [
    "Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison",
    "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark",
    "Steel", "Fairy",
]
_TYPE_SET = {t.lower() for t in TYPES}

CODE_TO_MULTIPLIER = {0: 1, 1: 2, 2: 0.5, 3: 0}

# Same one-tab-indented "id: { ... }," shape as moves.ts/learnsets.ts.
_ENTRY_RE = re.compile(r'^\t"?([a-zA-Z0-9]+)"?: \{$', re.M)


def _top_level_blocks(text):
    matches = list(_ENTRY_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        yield m.group(1), text[start:end]


class Command(BaseCommand):
    help = "Mirror Pokemon Showdown's type effectiveness chart for the prep sheet's Type Matchup section."

    def handle(self, *args, **options):
        text = requests.get(TYPE_CHART_URL, timeout=30).text

        chart = {}
        for defending_type, block in _top_level_blocks(text):
            if defending_type not in _TYPE_SET:
                continue
            dt_match = re.search(r'damageTaken:\s*\{([^}]*)\}', block, re.S)
            if not dt_match:
                raise CommandError(f"No damageTaken block found for type '{defending_type}'")

            row = {}
            for attacking_type, code in re.findall(r'([A-Za-z]+):\s*(\d+),?', dt_match.group(1)):
                if attacking_type.lower() in _TYPE_SET:
                    row[attacking_type] = CODE_TO_MULTIPLIER[int(code)]
            if len(row) != len(TYPES):
                raise CommandError(f"Expected {len(TYPES)} attacking types for '{defending_type}', got {len(row)}")
            chart[defending_type.capitalize()] = row

        missing = [t for t in TYPES if t not in chart]
        if missing:
            raise CommandError(f"Missing defending type(s) in mirrored chart: {missing}")

        with open(DATA_DIR / "type_chart.json", "w", encoding="utf-8") as f:
            json.dump(chart, f, indent=2)

        self.stdout.write(self.style.SUCCESS(f"Wrote type_chart.json ({len(chart)} defending types)."))
