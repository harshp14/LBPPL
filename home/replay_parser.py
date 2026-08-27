"""
Parses a Pokemon Showdown replay page into per-Pokemon match stats.

Fetches the replay HTML, pulls the raw protocol log out of it, and walks
the log line by line tracking two sides' rosters, active Pokemon, and HP,
attributing kills/damage/status/hazards/misses to whichever Pokemon caused
them. Returns one row per Pokemon per side, ready to drop into a match's
"stats" object in schedule.json.
"""
import re
import ssl
import urllib.request

# The league's replay host (champsnatdex.dedyn.io) has been serving an
# expired TLS cert. The data itself is public, non-sensitive replay logs,
# so we skip verification for this one known, trusted host rather than
# fail every fetch.
_UNVERIFIED_SSL_CONTEXT = ssl._create_unverified_context()

STAT_FIELDS = [
    "turns_active", "damage_dealt", "damage_taken",
    "statuses_inflicted", "missed_moves", "dodged_moves",
    "resisted_hits_taken", "super_effective_hits_taken", "hazards_set",
    "indirect_damage",
]

_LOG_RE = re.compile(r'<script type="text/plain" class="battle-log-data">(.*?)</script>', re.S)


class ReplayParseError(Exception):
    pass


def fetch_replay_log(replay_url):
    req = urllib.request.Request(replay_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20, context=_UNVERIFIED_SSL_CONTEXT) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    match = _LOG_RE.search(html)
    if not match:
        raise ReplayParseError(f"No battle log found at {replay_url}")
    return match.group(1)


def _side_of(slot):
    """'p1a: Foo' -> 'p1'"""
    return slot.split(":")[0].strip()[:2]


def _nick_of(slot):
    """'p1a: Foo' -> 'p1|Foo' (a stable per-side nickname key)."""
    side, _, name = slot.partition(": ")
    return f"{side.strip()[:2]}|{name.strip()}"


def _parse_hp(hp_str):
    """'330/363' -> (330, 363); '0 fnt' -> (0, None); handles status suffixes."""
    hp_str = hp_str.split(" ")[0]
    if hp_str == "0":
        return 0, None
    cur, _, mx = hp_str.partition("/")
    try:
        return int(cur), int(mx)
    except ValueError:
        return None, None


class _Mon:
    def __init__(self, key, side, species):
        self.key = key
        self.side = side
        self.species = species
        self.hp = None
        self.max_hp = None
        self.kills = 0
        self.died = False
        self.stats = {f: 0 for f in STAT_FIELDS}


def parse_replay(replay_url):
    """Fetch + parse a replay. Returns {'player1': [...], 'player2': [...]}
    where player1/player2 correspond to Showdown p1/p2 respectively (the
    caller is responsible for matching those to the schedule's actual
    player1/player2, e.g. by comparing rosters)."""
    log = fetch_replay_log(replay_url)
    return _parse_log(log)


def _parse_log(log):
    mons = {}  # nick_key -> _Mon
    active = {"p1": None, "p2": None}  # side -> nick_key
    usernames = {"p1": None, "p2": None}
    winner_side = None
    last_move = None  # (attacker_key, move_name, target_key)
    last_damage_source = {}  # target_key -> attacker_key or None (indirect)
    status_source = {}  # target_key -> attacker_key who inflicted their current status
    hazard_setter = {}  # (side_with_hazard, hazard_name) -> attacker_key
    weather = [None, None]  # [weather_name, setter_key] - whoever's ability/move is currently causing residual weather damage
    STATUS_DAMAGE_TAGS = {"[from] psn", "[from] tox", "[from] brn"}

    def get_or_create(nick_key, side, species):
        mon = mons.get(nick_key)
        if mon is None:
            mon = _Mon(nick_key, side, species)
            mons[nick_key] = mon
        else:
            mon.species = species  # keep latest form (e.g. after mega evo)
        return mon

    def apply_hp(mon, hp_field):
        """Returns the raw HP lost (prev - cur), not a percentage - these
        replays expose real HP numbers (e.g. "330/363"), so damage is
        tracked and reported as actual HP rather than %-of-max."""
        cur, mx = _parse_hp(hp_field)
        if mx is not None:
            mon.max_hp = mx
        prev = mon.hp
        mon.hp = cur
        if prev is None:
            return None
        return prev - cur

    for raw_line in log.split("\n"):
        line = raw_line.strip("\r")
        if not line.startswith("|"):
            continue
        parts = line.split("|")
        cmd = parts[1] if len(parts) > 1 else ""

        if cmd == "switch" or cmd == "drag":
            slot, details = parts[2], parts[3]
            species = details.split(",")[0].strip()
            side = _side_of(slot)
            nick_key = _nick_of(slot)
            mon = get_or_create(nick_key, side, species)
            if len(parts) > 4:
                apply_hp(mon, parts[4])
            active[side] = nick_key

        elif cmd == "replace":
            # Illusion breaking: the mon at this slot was disguised as a
            # teammate's nickname; the mon with the accumulated stats is
            # whichever one is currently active (tracked via `active`),
            # NOT necessarily keyed by this line's own nickname text. Rename
            # that mon's key to what future lines will call it, and fix its
            # species for display.
            slot, details = parts[2], parts[3]
            side = _side_of(slot)
            new_key = _nick_of(slot)
            true_species = details.split(",")[0].strip()
            old_key = active.get(side)
            if old_key and old_key in mons:
                mon = mons[old_key]
                mon.species = true_species
                if old_key != new_key:
                    existing = mons.get(new_key)
                    if existing is not None and existing is not mon:
                        # Same true identity revealed again after switching
                        # out and back in disguised differently - fold this
                        # period's stats into its running total.
                        existing.species = true_species
                        existing.kills += mon.kills
                        existing.died = existing.died or mon.died
                        for f in STAT_FIELDS:
                            existing.stats[f] += mon.stats[f]
                        existing.hp, existing.max_hp = mon.hp, mon.max_hp
                        del mons[old_key]
                        target_key = new_key
                    else:
                        mon.key = new_key
                        mons[new_key] = mon
                        del mons[old_key]
                        target_key = new_key
                    active[side] = target_key
                    if last_move:
                        atk, mv, tgt = last_move
                        last_move = (
                            target_key if atk == old_key else atk,
                            mv,
                            target_key if tgt == old_key else tgt,
                        )
                    for k, v in list(last_damage_source.items()):
                        if v == old_key:
                            last_damage_source[k] = target_key
                    if old_key in last_damage_source:
                        last_damage_source[target_key] = last_damage_source.pop(old_key)
            else:
                mon = get_or_create(new_key, side, true_species)
                active[side] = new_key

        elif cmd == "detailschange" or cmd == "-formechange":
            slot, details = parts[2], parts[3]
            nick_key = _nick_of(slot)
            mon = mons.get(nick_key)
            if mon:
                mon.species = details.split(",")[0].strip()

        elif cmd == "turn":
            for side, nick_key in active.items():
                if nick_key and nick_key in mons:
                    mons[nick_key].stats["turns_active"] += 1

        elif cmd == "move":
            attacker_slot, move_name = parts[2], parts[3]
            target_slot = parts[4] if len(parts) > 4 and parts[4] else None
            attacker_key = _nick_of(attacker_slot)
            if target_slot:
                target_key = _nick_of(target_slot)
            elif last_move and last_move[0] == attacker_key:
                # Continuing/charge moves (e.g. an auto-triggered Solar
                # Beam) sometimes omit the target - it's still hitting
                # whoever this attacker last targeted.
                target_key = last_move[2]
            else:
                target_key = None
            last_move = (attacker_key, move_name, target_key)

        elif cmd == "-damage":
            target_slot, hp_field = parts[2], parts[3]
            target_key = _nick_of(target_slot)
            from_tag = parts[4] if len(parts) > 4 else ""
            mon = mons.get(target_key)
            if mon is None:
                continue
            delta = apply_hp(mon, hp_field)

            attacker_key = None
            if not from_tag.startswith("[from]") and last_move and last_move[2] == target_key:
                attacker_key = last_move[0]

            if attacker_key and attacker_key in mons and mons[attacker_key].side != mon.side:
                if delta and delta > 0:
                    mons[attacker_key].stats["damage_dealt"] += delta
                last_damage_source[target_key] = attacker_key
            else:
                if delta and delta > 0:
                    mon.stats["indirect_damage"] += delta
                # Residual status damage (poison/burn) is credited to
                # whoever inflicted the status, for kill-attribution
                # purposes only - not counted as that mon's dealt damage.
                if from_tag in STATUS_DAMAGE_TAGS:
                    last_damage_source[target_key] = status_source.get(target_key)
                elif (
                    weather[0] and from_tag == f"[from] {weather[0]}"
                    and weather[1] in mons and mons[weather[1]].side != mon.side
                ):
                    # Weather hits both sides - only counts as a "kill" for
                    # the setter when it faints an opposing mon.
                    last_damage_source[target_key] = weather[1]
                else:
                    last_damage_source[target_key] = None

            if delta and delta > 0:
                mon.stats["damage_taken"] += delta

        elif cmd == "-heal":
            slot, hp_field = parts[2], parts[3]
            mon = mons.get(_nick_of(slot))
            if mon:
                apply_hp(mon, hp_field)

        elif cmd == "-miss":
            attacker_slot = parts[2]
            target_slot = parts[3] if len(parts) > 3 and parts[3] else None
            attacker = mons.get(_nick_of(attacker_slot))
            if attacker:
                attacker.stats["missed_moves"] += 1
            if target_slot:
                target = mons.get(_nick_of(target_slot))
                if target:
                    target.stats["dodged_moves"] += 1

        elif cmd == "-resisted":
            target = mons.get(_nick_of(parts[2]))
            if target:
                target.stats["resisted_hits_taken"] += 1

        elif cmd == "-supereffective":
            target = mons.get(_nick_of(parts[2]))
            if target:
                target.stats["super_effective_hits_taken"] += 1

        elif cmd == "-status":
            target_slot = parts[2]
            status_name = parts[3] if len(parts) > 3 else ""
            target_key = _nick_of(target_slot)
            target = mons.get(target_key)
            if target is None:
                continue
            if last_move and last_move[2] == target_key:
                attacker = mons.get(last_move[0])
                if attacker and attacker.side != target.side:
                    attacker.stats["statuses_inflicted"] += 1
                    status_source[target_key] = attacker.key
            elif status_name in ("psn", "tox"):
                # No move caused this - likely Toxic Spikes poisoning a
                # switch-in. Credit whoever set that side's hazard.
                setter_key = hazard_setter.get((target.side, "Toxic Spikes"))
                if setter_key:
                    status_source[target_key] = setter_key

        elif cmd == "-weather":
            weather_name = parts[2] if len(parts) > 2 else ""
            of_slot = next((p for p in parts[3:] if p.startswith("[of] ")), None)
            if weather_name == "none":
                weather[0], weather[1] = None, None
            elif of_slot:
                setter = mons.get(_nick_of(of_slot[len("[of] "):]))
                if setter:
                    weather[0], weather[1] = weather_name, setter.key
            # "[upkeep]" lines just confirm the same weather is still
            # active - nothing to update.

        elif cmd == "-sidestart":
            side_field = parts[2].split(":")[0].strip()[:2]
            hazard_name = parts[3] if len(parts) > 3 else ""
            hazard_name = hazard_name[len("move: "):] if hazard_name.startswith("move: ") else hazard_name
            if last_move:
                attacker = mons.get(last_move[0])
                if attacker and attacker.side != side_field:
                    attacker.stats["hazards_set"] += 1
                    hazard_setter[(side_field, hazard_name)] = attacker.key

        elif cmd == "faint":
            target_key = _nick_of(parts[2])
            mon = mons.get(target_key)
            if mon is None:
                continue
            mon.died = True
            killer_key = last_damage_source.get(target_key)
            if killer_key and killer_key in mons:
                mons[killer_key].kills += 1

        elif cmd == "player":
            side, username = parts[2], parts[3] if len(parts) > 3 else ""
            if username:
                usernames[side] = username

        elif cmd == "win":
            winner_username = parts[2] if len(parts) > 2 else ""
            for side, username in usernames.items():
                if username == winner_username:
                    winner_side = side

    result = {
        "p1": [],
        "p2": [],
        "usernames": usernames,
        "winner_side": winner_side,
    }
    for mon in mons.values():
        result[mon.side].append({
            "pokemon": mon.species,
            "kills": mon.kills,
            "died": mon.died,
            "max_hp": mon.max_hp or 0,
            **{f: round(mon.stats[f], 1) if isinstance(mon.stats[f], float) else mon.stats[f] for f in STAT_FIELDS},
        })
    return result
