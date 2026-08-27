"""
Data access layer. All roster data reads/writes go through here, so the
backend (currently a JSON file) can be swapped for a real database later
without touching views.py.
"""
import json
import re
from pathlib import Path

from . import replay_parser

DATA_DIR = Path(__file__).resolve().parent / "data"

FREE_AGENT_CAP = 5
POINTS_CAP = 120

SPRITE_BASE_URL = "https://play.pokemonshowdown.com/sprites/home/"

_sprite_ids = None
_board_by_norm = None

# Showdown's own species string for these is genuinely just the base name
# (not context-dependent) -- Landorus/Thundurus/Tornadus's Showdown species
# is the Incarnate forme, and Zygarde's is always the 50% forme.
_BARE_SPECIES_OVERRIDES = {
    "Landorus": "Landorus-Incarnate",
    "Thundurus": "Thundurus-Incarnate",
    "Tornadus": "Tornadus-Incarnate",
    "Enamorus": "Enamorus-Incarnate",
    "Zygarde": "Zygarde-50%",
}
# Battle-only formes (post-switch-in transformations) that the draft board
# doesn't track separately -- they're drafted/costed under the base entry.
_BATTLE_FORME_OVERRIDES = {
    "Palafin-Hero": "Palafin",
    "Terapagos-Terastal": "Terapagos",
}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def canonicalize_pokemon_name(name):
    """Map any naming-convention variant of a Pokémon name (raw Showdown
    species like "Venusaur-Mega", a battle-only forme like "Palafin-Hero")
    to the exact name used as the key in draft_board.json / sprites.json.
    Falls back to the input unchanged if nothing matches, so callers never
    get None. This is what keeps sprites and point lookups working no
    matter which naming convention upstream data (replay parsing, manual
    entry) happens to use."""
    global _board_by_norm
    if _board_by_norm is None:
        _board_by_norm = {_norm(k): k for k in _load("draft_board.json")}

    name = _BARE_SPECIES_OVERRIDES.get(name, name)
    name = _BATTLE_FORME_OVERRIDES.get(name, name)

    direct = _board_by_norm.get(_norm(name))
    if direct:
        return direct

    parts = name.split("-")
    if len(parts) >= 2:
        base, forme = parts[0], parts[1:]
        forme_head = forme[0].lower()
        candidates = []
        if forme_head == "mega":
            if len(forme) == 2 and forme[1] in ("X", "Y"):
                candidates.append(f"Mega {base} {forme[1]}")
            candidates.append(f"Mega {base}")
        elif forme_head in ("alola", "galar", "hisui", "paldea"):
            prefix = {"alola": "Alolan", "galar": "Galarian", "hisui": "Hisuian", "paldea": "Paldean"}[forme_head]
            candidates.append(f"{prefix} {base}")
        for cand in candidates:
            match = _board_by_norm.get(_norm(cand))
            if match:
                return match

    return name


def get_sprite_url(pokemon_name):
    """Showdown "Home"-style sprite URL for a Pokémon name, or None if we
    don't have a mapping (see data/sprites.json, built from pokedex.json)."""
    global _sprite_ids
    if _sprite_ids is None:
        _sprite_ids = _load("sprites.json")
    sprite_id = _sprite_ids.get(canonicalize_pokemon_name(pokemon_name))
    return f"{SPRITE_BASE_URL}{sprite_id}.png" if sprite_id else None


def _load(filename):
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def _save(filename, data):
    with open(DATA_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_rosters():
    """Return the list of team roster dicts (team_name, coach_name, logo, pokemon)."""
    with open(DATA_DIR / "rosters.json", encoding="utf-8") as f:
        data = json.load(f)
    return data["teams"]


def get_draft_board():
    """Return draft board columns, sorted most to least expensive, with a
    trailing "Banned" column (points 0) for mons with no point value."""
    with open(DATA_DIR / "draft_board.json", encoding="utf-8") as f:
        points_by_pokemon = json.load(f)

    pokemon_by_points = {}
    for name, points in points_by_pokemon.items():
        pokemon_by_points.setdefault(points, []).append(name)

    columns = []
    for points in sorted(pokemon_by_points, reverse=True):
        label = "Banned" if points == 0 else f"{points} Point{'s' if points != 1 else ''}"
        columns.append({
            "label": label,
            "points": points,
            "pokemon": sorted(pokemon_by_points[points]),
        })
    return columns


def get_schedule():
    """Return the list of week dicts (week, label, matches) for the schedule.
    Pokémon names in each match's stats are canonicalized to the draft
    board's naming convention, so callers never see raw Showdown-style
    names regardless of how they ended up in the stored data."""
    with open(DATA_DIR / "schedule.json", encoding="utf-8") as f:
        data = json.load(f)
    for week in data["weeks"]:
        for match in week["matches"]:
            stats = match.get("stats")
            if stats:
                for mon in stats["player1"] + stats["player2"]:
                    mon["pokemon"] = canonicalize_pokemon_name(mon["pokemon"])
    return data["weeks"]


STAT_SUM_FIELDS = [
    "turns_active", "damage_dealt", "damage_taken", "indirect_damage",
    "statuses_inflicted", "missed_moves", "dodged_moves",
    "resisted_hits_taken", "super_effective_hits_taken", "hazards_set",
]


def get_statistics():
    """Aggregate per-Pokémon career stats across every logged battle in
    schedule.json. Every stat (turns active, statuses inflicted, raw
    damage dealt/taken/indirect, etc.) is summed across appearances --
    no percentages. "Dmg Taken" is shown as damage_taken / max_hp, both
    flat sums with no division, so a career total reads like "820/1089"
    rather than a computed ratio. Only Pokémon that have appeared in at
    least one battle are included. Returns rows sorted by kills, most
    first."""
    weeks = get_schedule()
    points_by_pokemon = _load("draft_board.json")

    agg = {}
    for week in weeks:
        for match in week["matches"]:
            stats = match.get("stats")
            if not stats:
                continue
            for mon in stats["player1"] + stats["player2"]:
                row = agg.setdefault(mon["pokemon"], {
                    "games_played": 0, "kills": 0, "deaths": 0, "max_hp": 0,
                    **{f: 0 for f in STAT_SUM_FIELDS},
                })
                row["games_played"] += 1
                row["kills"] += mon["kills"]
                row["deaths"] += 1 if mon["died"] else 0
                row["max_hp"] += mon.get("max_hp", 0)
                for field in STAT_SUM_FIELDS:
                    row[field] += mon.get(field, 0)

    rows = []
    for name, row in agg.items():
        games = row["games_played"]
        points = points_by_pokemon.get(name, 0)
        entry = {
            "name": name,
            "sprite": get_sprite_url(name),
            "games_played": games,
            "kills": row["kills"],
            "deaths": row["deaths"],
            "kills_per_death": round(row["kills"] / row["deaths"], 2) if row["deaths"] else row["kills"],
            "kills_per_point": round(row["kills"] / points, 2) if points else None,
            "max_hp": row["max_hp"],
        }
        entry.update({f: row[f] for f in STAT_SUM_FIELDS})
        rows.append(entry)

    return sorted(rows, key=lambda r: r["kills"], reverse=True)


def set_match_replay(week, match_index, replay_url):
    """Persist a user-submitted replay link for one match. Returns False if
    the week/match couldn't be found, True on success."""
    path = DATA_DIR / "schedule.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    target_week = next((w for w in data["weeks"] if w["week"] == week), None)
    if target_week is None or not (0 <= match_index < len(target_week["matches"])):
        return False

    target_week["matches"][match_index]["replay_url"] = replay_url
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return True


def _normalize_pokemon_name(name):
    """Collapse naming-convention differences (roster sheet vs raw Showdown
    log) so the same Pokemon compares equal either way, e.g. 'Mega
    Venusaur' / 'Venusaur-Mega' both become 'venusaur'."""
    n = name.lower()
    for prefix in ("mega ", "alolan ", "galarian ", "hisuian ", "paldean "):
        if n.startswith(prefix):
            n = n[len(prefix):]
    for suffix in ("-mega", "-alola", "-galar", "-hisui", "-paldea", "-incarnate", "-hero", "-therian"):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return re.sub(r"[^a-z0-9]", "", n)


def set_match_from_replay(week, match_index, replay_url):
    """Fetch and parse a replay, then persist the full per-Pokemon stats
    (kills, deaths, turns active, damage%, etc.) plus the derived
    winner/margin for one match. Returns (True, None) on success or
    (False, error_message) on failure. Raises replay_parser.ReplayParseError
    on fetch/parse failure (caller decides how to handle that)."""
    path = DATA_DIR / "schedule.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    target_week = next((w for w in data["weeks"] if w["week"] == week), None)
    if target_week is None or not (0 <= match_index < len(target_week["matches"])):
        return False, "Couldn't find that match."
    match = target_week["matches"][match_index]

    parsed = replay_parser.parse_replay(replay_url)

    rosters = {team["coach_name"]: team for team in get_rosters()}
    team1 = rosters.get(match["player1"])
    team2 = rosters.get(match["player2"])
    if team1 is None or team2 is None:
        return False, "Couldn't match the players in this replay to a coach's roster."

    roster1_names = {_normalize_pokemon_name(mon["name"]) for mon in team1["pokemon"]}
    roster2_names = {_normalize_pokemon_name(mon["name"]) for mon in team2["pokemon"]}
    parsed_p1_names = {_normalize_pokemon_name(mon["pokemon"]) for mon in parsed["p1"]}
    parsed_p2_names = {_normalize_pokemon_name(mon["pokemon"]) for mon in parsed["p2"]}

    score_forward = len(roster1_names & parsed_p1_names) + len(roster2_names & parsed_p2_names)
    score_reverse = len(roster1_names & parsed_p2_names) + len(roster2_names & parsed_p1_names)
    if score_forward >= score_reverse:
        side_of_player1, side_of_player2 = "p1", "p2"
    else:
        side_of_player1, side_of_player2 = "p2", "p1"

    for mon in parsed["p1"] + parsed["p2"]:
        mon["pokemon"] = canonicalize_pokemon_name(mon["pokemon"])

    stats = {
        "player1": parsed[side_of_player1],
        "player2": parsed[side_of_player2],
    }
    deaths1 = sum(1 for mon in stats["player1"] if mon["died"])
    deaths2 = sum(1 for mon in stats["player2"] if mon["died"])

    winner_side = parsed.get("winner_side")
    if winner_side == side_of_player1:
        winner = "player1"
    elif winner_side == side_of_player2:
        winner = "player2"
    elif deaths1 != deaths2:
        winner = "player1" if deaths1 < deaths2 else "player2"
    else:
        winner = None

    match["replay_url"] = replay_url
    match["stats"] = stats
    match["winner"] = winner
    match["margin"] = abs(deaths1 - deaths2) if winner else None

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return True, None


def get_roster_points(team):
    """Sum a team's current point spend on demand, never stored."""
    return sum(mon["points"] for mon in team["pokemon"])


def get_free_agents():
    """Draftable (non-banned) Pokémon not currently on any roster."""
    points_by_pokemon = _load("draft_board.json")
    rostered = {mon["name"] for team in get_rosters() for mon in team["pokemon"]}
    agents = [
        {"name": name, "points": points}
        for name, points in points_by_pokemon.items()
        if points > 0 and name not in rostered
    ]
    return sorted(agents, key=lambda a: a["name"])


def get_free_agency_log():
    """Past free agency transactions, most recent first."""
    return list(reversed(_load("free_agency_log.json")["transactions"]))


def submit_free_agency(coach_name, drop_names, pickup_names):
    """Validate and, if valid, apply a free agency move: drop_names come off
    the coach's roster, pickup_names (drafted at their board cost) go on.
    Returns (True, None) on success or (False, error_message) on failure.
    Nothing is written unless every check passes.
    """
    if not drop_names and not pickup_names:
        return False, "Add at least one Pokémon to drop or pick up."

    if len(set(pickup_names)) != len(pickup_names):
        return False, "The same free agent was selected more than once."

    rosters = _load("rosters.json")
    team = next((t for t in rosters["teams"] if t["coach_name"] == coach_name), None)
    if team is None:
        return False, "Unknown coach."

    roster_by_name = {mon["name"]: mon["points"] for mon in team["pokemon"]}
    for name in drop_names:
        if name not in roster_by_name:
            return False, f"{name} is not on {coach_name}'s roster."

    points_by_pokemon = _load("draft_board.json")
    rostered_elsewhere = {
        mon["name"]
        for t in rosters["teams"]
        for mon in t["pokemon"]
        if t is not team
    }
    for name in pickup_names:
        if points_by_pokemon.get(name, 0) <= 0:
            return False, f"{name} is not a draftable Pokémon."
        if name in rostered_elsewhere or (name in roster_by_name and name not in drop_names):
            return False, f"{name} is already on a roster."

    remaining_agents = FREE_AGENT_CAP - team.get("free_agents_used", 0)
    if len(pickup_names) > remaining_agents:
        return False, f"{coach_name} only has {remaining_agents} free agent pickup(s) left."

    current_points = get_roster_points(team)
    drop_points = sum(roster_by_name[name] for name in drop_names)
    pickup_points = sum(points_by_pokemon[name] for name in pickup_names)
    new_points = current_points - drop_points + pickup_points
    if new_points > POINTS_CAP:
        return False, f"That would put {coach_name} at {new_points} points (cap is {POINTS_CAP})."

    remaining_pokemon = [mon for mon in team["pokemon"] if mon["name"] not in drop_names]
    remaining_pokemon += [{"name": name, "points": points_by_pokemon[name]} for name in pickup_names]
    team["pokemon"] = remaining_pokemon
    team["free_agents_used"] = team.get("free_agents_used", 0) + len(pickup_names)
    _save("rosters.json", rosters)

    log = _load("free_agency_log.json")
    log["transactions"].append({
        "coach": coach_name,
        "team_name": team.get("team_name"),
        "drops": [{"name": name, "points": roster_by_name[name]} for name in drop_names],
        "pickups": [{"name": name, "points": points_by_pokemon[name]} for name in pickup_names],
    })
    _save("free_agency_log.json", log)

    return True, None
