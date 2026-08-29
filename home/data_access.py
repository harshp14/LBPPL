"""
Data access layer. All roster data reads/writes go through here, so the
backend (currently a JSON file) can be swapped for a real database later
without touching views.py.
"""
import json
import re
from datetime import datetime
from pathlib import Path

from . import discord_webhooks, replay_parser
from .models import S1Pokedex, S2Pokedex, S3Pokedex, S4Pokedex

DATA_DIR = Path(__file__).resolve().parent / "data"

FREE_AGENT_CAP = 5
POINTS_CAP_BY_SEASON = {"1": 120, "2": 120, "3": 125, "4": 120}


def get_points_cap(season):
    return POINTS_CAP_BY_SEASON[season]

SPRITE_BASE_URL = "https://play.pokemonshowdown.com/sprites/home/"

# Season 4 was the first season built, so its data files live at the root
# of DATA_DIR for backwards compatibility; seasons 1-3 live in their own
# subdirectory (e.g. home/data/s2/).
POKEDEX_MODELS = {"1": S1Pokedex, "2": S2Pokedex, "3": S3Pokedex, "4": S4Pokedex}


def _season_dir(season):
    return DATA_DIR if season == "4" else DATA_DIR / f"s{season}"


# Each season's *_pokedex table (points + sprite + species data for every
# Pokemon on that season's draft board) is small and effectively static --
# it only changes when someone reruns load_s{n}_pokedex. Pull each one once,
# lazily, on first use instead of hitting the DB on every lookup.
_pokedex_cache = {}
_board_by_norm_cache = {}


def _get_pokedex(season):
    if season not in _pokedex_cache:
        _pokedex_cache[season] = {p.name: p for p in POKEDEX_MODELS[season].objects.all()}
    return _pokedex_cache[season]

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
    # Ogerpon's Embody Aspect changes its displayed species to a "-Tera"
    # variant on Terastallizing; the draft board only tracks the mask
    # forme itself, not a separate Tera'd entry.
    "Ogerpon-Tera": "Ogerpon",
    "Ogerpon-Teal-Tera": "Ogerpon",
    "Ogerpon-Wellspring-Tera": "Ogerpon-Wellspring",
    "Ogerpon-Hearthflame-Tera": "Ogerpon-Hearthflame",
    "Ogerpon-Cornerstone-Tera": "Ogerpon-Cornerstone",
}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _get_board_by_norm(season):
    if season not in _board_by_norm_cache:
        _board_by_norm_cache[season] = {_norm(name): name for name in _get_pokedex(season)}
    return _board_by_norm_cache[season]


def canonicalize_pokemon_name(name, season):
    """Map any naming-convention variant of a Pokémon name (raw Showdown
    species like "Venusaur-Mega", a battle-only forme like "Palafin-Hero")
    to the exact name used as the key in that season's pokedex table. Falls
    back to the input unchanged if nothing matches, so callers never get
    None. This is what keeps sprites and point lookups working no matter
    which naming convention upstream data (replay parsing, manual entry)
    happens to use."""
    name = _BARE_SPECIES_OVERRIDES.get(name, name)
    name = _BATTLE_FORME_OVERRIDES.get(name, name)

    board_by_norm = _get_board_by_norm(season)
    direct = board_by_norm.get(_norm(name))
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
            match = board_by_norm.get(_norm(cand))
            if match:
                return match

    return name


def get_sprite_url(pokemon_name, season):
    """Showdown "Home"-style sprite URL for a Pokémon name in a given
    season, or None if we don't have a mapping (see that season's pokedex
    table)."""
    entry = _get_pokedex(season).get(canonicalize_pokemon_name(pokemon_name, season))
    return f"{SPRITE_BASE_URL}{entry.sprite_id}.png" if entry and entry.sprite_id else None


def _load(season, filename, default):
    path = _season_dir(season) / filename
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(season, filename, data):
    path = _season_dir(season) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_rosters(season):
    """Return the list of team roster dicts (team_name, coach_name, logo,
    pokemon) for a season, or [] if that season has no rosters.json yet."""
    return _load(season, "rosters.json", {"teams": []})["teams"]


def get_draft_board(season):
    """Return draft board columns for a season, sorted most to least
    expensive, with a trailing "Banned" column (points 0) for mons with no
    point value."""
    pokemon_by_points = {}
    for name, entry in _get_pokedex(season).items():
        pokemon_by_points.setdefault(entry.points, []).append(name)

    columns = []
    for points in sorted(pokemon_by_points, reverse=True):
        label = "Banned" if points == 0 else f"{points} Point{'s' if points != 1 else ''}"
        columns.append({
            "label": label,
            "points": points,
            "pokemon": sorted(pokemon_by_points[points]),
        })
    return columns


def get_schedule(season):
    """Return the list of week dicts (week, label, matches) for a season's
    schedule, or [] if that season has no schedule.json yet. Pokémon names
    in each match's stats are canonicalized to the draft board's naming
    convention, so callers never see raw Showdown-style names regardless of
    how they ended up in the stored data."""
    weeks = _load(season, "schedule.json", {"weeks": []})["weeks"]
    for week in weeks:
        for match in week["matches"]:
            stats = match.get("stats")
            if stats:
                for mon in stats["player1"] + stats["player2"]:
                    mon["pokemon"] = canonicalize_pokemon_name(mon["pokemon"], season)
    return weeks


def get_upcoming_games(season):
    """Matches that have a proposed day to play but no replay submitted
    yet, across every week, soonest first (scheduled_day is stored as an
    ISO yyyy-mm-dd string, so a plain string sort is chronological)."""
    upcoming = [
        {
            "week": week["week"],
            "week_label": week["label"],
            "match_index": index,
            "player1": match["player1"],
            "player2": match["player2"],
            "scheduled_day": match["scheduled_day"],
        }
        for week in get_schedule(season)
        for index, match in enumerate(week["matches"])
        if match.get("scheduled_day") and not match.get("replay_url")
    ]
    return sorted(upcoming, key=lambda m: m["scheduled_day"])


# Every numeric per-Pokemon field the replay parser produces (damage
# splits, healing, statuses, hazards, boosts, etc.) - kept in sync with
# the parser instead of duplicated here, so a new tracked stat shows up
# in career totals automatically.
STAT_SUM_FIELDS = replay_parser.STAT_FIELDS

_HEALING_PCT_FIELDS = [
    "healing_received_move_pct", "healing_received_wish_pct", "healing_received_leech_seed_pct",
    "healing_received_item_ability_pct", "healing_received_terrain_pct", "healing_received_other_pct",
]


def healing_received_total_pct(mon):
    """Sum of a Pokemon's healing_received_*_pct breakdown fields, as a %
    of max HP (works on both a single match's per-mon stats dict and a
    get_statistics() row)."""
    return sum(mon.get(f, 0) for f in _HEALING_PCT_FIELDS)


def _new_stat_row():
    return {
        "games_played": 0, "kills": 0, "direct_kills": 0,
        "indirect_kills": 0, "deaths": 0, "self_kos": 0,
        **{f: 0 for f in STAT_SUM_FIELDS},
    }


def _accumulate_stat_row(row, mon):
    row["games_played"] += 1
    row["kills"] += mon["kills"]
    row["direct_kills"] += mon.get("direct_kills", 0)
    row["indirect_kills"] += mon.get("indirect_kills", 0)
    row["deaths"] += 1 if mon["died"] else 0
    row["self_kos"] += 1 if mon.get("self_ko") else 0
    for field in STAT_SUM_FIELDS:
        row[field] += mon.get(field, 0)


def _aggregate_schedule_stats(weeks):
    """Sum every logged battle's per-Pokemon stats (keyed by canonicalized
    name) across a season's weeks. Shared by get_statistics and
    get_all_time_statistics so both sum the exact same fields the same
    way."""
    agg = {}
    for week in weeks:
        for match in week["matches"]:
            stats = match.get("stats")
            if not stats:
                continue
            for mon in stats["player1"] + stats["player2"]:
                row = agg.setdefault(mon["pokemon"], _new_stat_row())
                _accumulate_stat_row(row, mon)
    return agg


def get_statistics(season):
    """Aggregate per-Pokémon career stats across every logged battle in a
    season's schedule.json. Every damage/healing stat is a "_pct" field --
    % of max HP per hit, summed across appearances -- never a flat HP
    number: replays never reveal a Pokemon's real max HP (EVs are only
    known to the creator), so a flat HP total would be meaningless. Only
    Pokémon that have appeared in at least one battle are included.
    Returns rows sorted by kills, most first."""
    agg = _aggregate_schedule_stats(get_schedule(season))
    pokedex = _get_pokedex(season)

    rows = []
    for name, row in agg.items():
        points = pokedex[name].points if name in pokedex else 0
        entry = {
            "name": name,
            "sprite": get_sprite_url(name, season),
            "games_played": row["games_played"],
            "kills": row["kills"],
            "direct_kills": row["direct_kills"],
            "indirect_kills": row["indirect_kills"],
            "deaths": row["deaths"],
            "self_kos": row["self_kos"],
            "kills_per_death": round(row["kills"] / row["deaths"], 2) if row["deaths"] else row["kills"],
            "kills_per_point": round(row["kills"] / points, 2) if points else None,
        }
        entry.update({f: row[f] for f in STAT_SUM_FIELDS})
        entry["healing_received_total_pct"] = healing_received_total_pct(row)
        rows.append(entry)

    return sorted(rows, key=lambda r: r["kills"], reverse=True)


ALL_TIME_SEASONS = ["1", "2", "3", "4"]


def get_all_time_statistics():
    """Aggregate per-Pokémon career stats across every logged battle in
    every season's schedule.json (see get_statistics for field semantics).
    Point costs vary season to season, so there's no single "kills per
    point" that means anything across seasons -- that field is omitted
    here. A season with no schedule.json yet (no battles logged) simply
    contributes nothing. Returns rows sorted by kills, most first."""
    agg = {}
    sprite_by_name = {}
    for season in ALL_TIME_SEASONS:
        for name, row in _aggregate_schedule_stats(get_schedule(season)).items():
            total = agg.setdefault(name, _new_stat_row())
            for field, value in row.items():
                total[field] += value
            if name not in sprite_by_name:
                sprite = get_sprite_url(name, season)
                if sprite:
                    sprite_by_name[name] = sprite

    rows = []
    for name, row in agg.items():
        entry = {
            "name": name,
            "sprite": sprite_by_name.get(name),
            "games_played": row["games_played"],
            "kills": row["kills"],
            "direct_kills": row["direct_kills"],
            "indirect_kills": row["indirect_kills"],
            "deaths": row["deaths"],
            "self_kos": row["self_kos"],
            "kills_per_death": round(row["kills"] / row["deaths"], 2) if row["deaths"] else row["kills"],
        }
        entry.update({f: row[f] for f in STAT_SUM_FIELDS})
        entry["healing_received_total_pct"] = healing_received_total_pct(row)
        rows.append(entry)

    return sorted(rows, key=lambda r: r["kills"], reverse=True)


def set_match_replay(season, week, match_index, replay_url):
    """Persist a user-submitted replay link for one match. Returns False if
    the season has no schedule.json yet or the week/match couldn't be
    found, True on success."""
    path = _season_dir(season) / "schedule.json"
    if not path.exists():
        return False
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    target_week = next((w for w in data["weeks"] if w["week"] == week), None)
    if target_week is None or not (0 <= match_index < len(target_week["matches"])):
        return False

    target_week["matches"][match_index]["replay_url"] = replay_url
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return True


def set_match_game_time(season, week, match_index, day):
    """Persist a coach-proposed day to play an unplayed match, and post it
    to Discord. Returns (True, None) on success or (False, error_message)
    on failure."""
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return False, "Day must be a valid date (YYYY-MM-DD)."

    path = _season_dir(season) / "schedule.json"
    if not path.exists():
        return False, "Couldn't find that match."
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    target_week = next((w for w in data["weeks"] if w["week"] == week), None)
    if target_week is None or not (0 <= match_index < len(target_week["matches"])):
        return False, "Couldn't find that match."
    match = target_week["matches"][match_index]

    match["scheduled_day"] = day
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    discord_webhooks.notify_game_time(season, target_week["label"], match["player1"], match["player2"], day)
    return True, None


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


def set_match_from_replay(season, week, match_index, replay_url):
    """Fetch and parse a replay, then persist the full per-Pokemon stats
    (kills, deaths, turns active, damage%, etc.) plus the derived
    winner/margin for one match. Returns (True, None) on success or
    (False, error_message) on failure. Raises replay_parser.ReplayParseError
    on fetch/parse failure (caller decides how to handle that)."""
    path = _season_dir(season) / "schedule.json"
    if not path.exists():
        return False, "Couldn't find that match."
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    target_week = next((w for w in data["weeks"] if w["week"] == week), None)
    if target_week is None or not (0 <= match_index < len(target_week["matches"])):
        return False, "Couldn't find that match."
    match = target_week["matches"][match_index]

    parsed = replay_parser.parse_replay(replay_url)

    rosters = {team["coach_name"]: team for team in get_rosters(season)}
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
        mon["pokemon"] = canonicalize_pokemon_name(mon["pokemon"], season)

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

    match_url = f"{discord_webhooks.SITE_BASE_URL}/schedule/?week={week}&match={match_index}"
    discord_webhooks.notify_battle_concluded(
        season, team1.get("team_name"), team1["coach_name"],
        team2.get("team_name"), team2["coach_name"], replay_url, match_url,
    )
    return True, None


def get_roster_points(team):
    """Sum a team's current point spend on demand, never stored."""
    return sum(mon["points"] for mon in team["pokemon"])


def get_free_agents(season):
    """Draftable (non-banned) Pokémon not currently on any roster in a season."""
    rostered = {mon["name"] for team in get_rosters(season) for mon in team["pokemon"]}
    agents = [
        {"name": name, "points": entry.points}
        for name, entry in _get_pokedex(season).items()
        if entry.points > 0 and name not in rostered
    ]
    return sorted(agents, key=lambda a: a["name"])


def get_accolades(season):
    """Season awards/superlatives (finals matchup, player/Pokémon/match
    award categories, community superlatives) from that season's
    superlatives.json, or an empty structure if that season hasn't had
    any voted on yet."""
    return _load(season, "superlatives.json", {
        "finals": None,
        "player_awards": [],
        "pokemon_awards": [],
        "match_awards": [],
        "community": [],
    })


def get_free_agency_log(season):
    """Past free agency transactions for a season, most recent first."""
    return list(reversed(_load(season, "free_agency_log.json", {"transactions": []})["transactions"]))


def submit_free_agency(season, coach_name, drop_names, pickup_names):
    """Validate and, if valid, apply a free agency move: drop_names come off
    the coach's roster, pickup_names (drafted at their board cost) go on.
    Returns (True, None) on success or (False, error_message) on failure.
    Nothing is written unless every check passes.
    """
    if not drop_names and not pickup_names:
        return False, "Add at least one Pokémon to drop or pick up."

    if len(set(pickup_names)) != len(pickup_names):
        return False, "The same free agent was selected more than once."

    pokedex = _get_pokedex(season)
    rosters = _load(season, "rosters.json", {"teams": []})
    team = next((t for t in rosters["teams"] if t["coach_name"] == coach_name), None)
    if team is None:
        return False, "Unknown coach."

    roster_by_name = {mon["name"]: mon["points"] for mon in team["pokemon"]}
    for name in drop_names:
        if name not in roster_by_name:
            return False, f"{name} is not on {coach_name}'s roster."

    rostered_elsewhere = {
        mon["name"]
        for t in rosters["teams"]
        for mon in t["pokemon"]
        if t is not team
    }
    for name in pickup_names:
        entry = pokedex.get(name)
        if entry is None or entry.points <= 0:
            return False, f"{name} is not a draftable Pokémon."
        if name in rostered_elsewhere or (name in roster_by_name and name not in drop_names):
            return False, f"{name} is already on a roster."

    remaining_agents = FREE_AGENT_CAP - team.get("free_agents_used", 0)
    if len(pickup_names) > remaining_agents:
        return False, f"{coach_name} only has {remaining_agents} free agent pickup(s) left."

    points_cap = get_points_cap(season)
    current_points = get_roster_points(team)
    drop_points = sum(roster_by_name[name] for name in drop_names)
    pickup_points = sum(pokedex[name].points for name in pickup_names)
    new_points = current_points - drop_points + pickup_points
    if new_points > points_cap:
        return False, f"That would put {coach_name} at {new_points} points (cap is {points_cap})."

    remaining_pokemon = [mon for mon in team["pokemon"] if mon["name"] not in drop_names]
    remaining_pokemon += [{"name": name, "points": pokedex[name].points} for name in pickup_names]
    team["pokemon"] = remaining_pokemon
    team["free_agents_used"] = team.get("free_agents_used", 0) + len(pickup_names)
    _save(season, "rosters.json", rosters)

    log = _load(season, "free_agency_log.json", {"transactions": []})
    log["transactions"].append({
        "coach": coach_name,
        "team_name": team.get("team_name"),
        "drops": [{"name": name, "points": roster_by_name[name]} for name in drop_names],
        "pickups": [{"name": name, "points": pokedex[name].points} for name in pickup_names],
    })
    _save(season, "free_agency_log.json", log)

    discord_webhooks.notify_free_agency(season, coach_name, team.get("team_name"), drop_names, pickup_names)

    return True, None
