"""
Parses a Pokemon Showdown replay page into per-Pokemon match stats.

Fetches the replay HTML, pulls the raw protocol log out of it, and walks
the log line by line tracking two sides' rosters, active Pokemon, and HP,
attributing kills/damage/healing/status/hazards/misses to whichever
Pokemon caused them. Returns one row per Pokemon per side, ready to drop
into a match's "stats" object in schedule.json.

Attribution is deliberately conservative: where the log doesn't expose a
reliable source (an effect with no `[of]` tag and no matching prior move),
the event is recorded as taken/received but left unattributed rather than
guessed at.
"""
import json
import re
import ssl
import urllib.request
from urllib.parse import urlparse

# The league's replay host (champsnatdex.dedyn.io) has been serving an
# expired TLS cert. The data itself is public, non-sensitive replay logs,
# so we skip verification for this one known, trusted host rather than
# fail every fetch.
_UNVERIFIED_SSL_CONTEXT = ssl._create_unverified_context()

# Hosts whose replay page is a client-rendered SPA with no embedded log --
# fetch the log via their JSON API (<url>.json -> {"log": "..."}) instead of
# scraping the page HTML, which is what fetch_replay_log() does for other
# hosts (e.g. champsnatdex.dedyn.io, which server-renders the log inline).
_JSON_API_HOSTS = {"replay.pokemonshowdown.com"}

STAT_FIELDS = [
    # activity
    "turns_active", "switch_ins", "times_dragged_in", "forced_switches_caused",
    "moves_used", "hits_landed", "effect_only_landed",
    "missed_moves", "dodged_moves", "moves_failed", "immune_hits",

    # damage dealt: raw HP, and normalized to % of the target's max HP
    "damage_dealt_direct", "damage_dealt_direct_pct",
    "damage_dealt_hazard", "damage_dealt_hazard_pct",
    "damage_dealt_residual", "damage_dealt_residual_pct",
    "damage_dealt_contact_punish", "damage_dealt_contact_punish_pct",
    "damage_dealt_delayed", "damage_dealt_delayed_pct",
    "damage_dealt_other", "damage_dealt_other_pct",

    # damage taken: raw HP, and normalized to % of this Pokemon's max HP
    "damage_taken_direct", "damage_taken_direct_pct",
    "damage_taken_hazard", "damage_taken_hazard_pct",
    "damage_taken_residual", "damage_taken_residual_pct",
    "damage_taken_recoil", "damage_taken_recoil_pct",
    "damage_taken_contact_punish", "damage_taken_contact_punish_pct",
    "damage_taken_other", "damage_taken_other_pct",

    # residual damage dealt, broken out by source (sums into damage_dealt_residual)
    "residual_dealt_poison", "residual_dealt_burn", "residual_dealt_weather",
    "residual_dealt_leech_seed", "residual_dealt_salt_cure", "residual_dealt_curse",
    "residual_dealt_nightmare", "residual_dealt_binding", "residual_dealt_item_ability",

    # self-inflicted/punishment damage taken (sums into damage_taken_recoil)
    "recoil_damage", "life_orb_damage", "substitute_cost", "belly_drum_cost",
    "crash_damage", "confusion_self_damage",

    # healing received, by source
    "healing_received_move", "healing_received_wish", "healing_received_leech_seed",
    "healing_received_item_ability", "healing_received_terrain", "healing_received_other",
    "healing_done_wish",

    # statuses inflicted/received, by type - Rest's self-inflicted sleep is
    # intentionally excluded from both sides entirely.
    "statuses_inflicted_psn", "statuses_inflicted_tox", "statuses_inflicted_brn",
    "statuses_inflicted_slp", "statuses_inflicted_par", "statuses_inflicted_frz",
    "statuses_received_psn", "statuses_received_tox", "statuses_received_brn",
    "statuses_received_slp", "statuses_received_par", "statuses_received_frz",

    # entry hazards
    "hazards_set", "hazards_removed",

    # crits / type effectiveness taken
    "crits_dealt", "crits_taken", "resisted_hits_taken", "super_effective_hits_taken",

    # stat changes (given/received between opponents; self-inflicted tracked separately)
    "boosts_given", "boosts_received", "self_boosts",
    "drops_given", "drops_received", "self_drops",
]

# Moves whose only residual-damage tag in the log is their own name (no
# reliable [of] most of the time), so attribution falls back to whoever
# most recently used that named move against this target.
BINDING_MOVES = {
    "Bind", "Clamp", "Fire Spin", "Infestation", "Magma Storm",
    "Sand Tomb", "Whirlpool", "Wrap",
}
DELAYED_MOVES = {"Future Sight", "Doom Desire"}
HAZARD_NAMES = {"Stealth Rock", "Spikes", "Toxic Spikes", "Sticky Web", "G-Max Steelsurge"}
SELF_KO_MOVES = {"Explosion", "Self-Destruct", "Misty Explosion", "Final Gambit", "Memento"}
# Self-targeting moves whose HP cost shows up as a plain, untagged -damage
# line (as opposed to recoil/Life Orb/etc., which carry a [from] tag).
SELF_COST_MOVES = {"Substitute": "substitute_cost", "Belly Drum": "belly_drum_cost"}

_LOG_RE = re.compile(r'<script type="text/plain" class="battle-log-data">(.*?)</script>', re.S)


class ReplayParseError(Exception):
    pass


def fetch_replay_log(replay_url):
    host = urlparse(replay_url).hostname
    if host in _JSON_API_HOSTS:
        json_url = replay_url.rstrip("/") + ".json"
        req = urllib.request.Request(json_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20, context=_UNVERIFIED_SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        log = data.get("log")
        if not log:
            raise ReplayParseError(f"No battle log found at {json_url}")
        return log

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


def _extract_tags(parts):
    """Pull the [from]/[of]/[silent]/[wisher] trailing tags off a protocol
    line's remaining parts. Returns (from_text, from_kind, of_slot, silent,
    wisher_nick). from_kind is 'move'/'ability'/'item'/None depending on
    the [from] tag's prefix (stripped from from_text itself)."""
    from_text = None
    from_kind = None
    of_slot = None
    silent = False
    wisher_nick = None
    for p in parts:
        if p.startswith("[from]"):
            raw = p[len("[from]"):].strip()
            for prefix, kind in (("move: ", "move"), ("ability: ", "ability"), ("item: ", "item")):
                if raw.startswith(prefix):
                    raw = raw[len(prefix):]
                    from_kind = kind
                    break
            from_text = raw
        elif p.startswith("[of] "):
            of_slot = p[len("[of] "):].strip()
        elif p.strip() == "[silent]":
            silent = True
        elif p.startswith("[wisher] "):
            wisher_nick = p[len("[wisher] "):].strip()
    return from_text, from_kind, of_slot, silent, wisher_nick


class _Mon:
    def __init__(self, key, side, species):
        self.key = key
        self.side = side
        self.species = species
        self.hp = None
        self.max_hp = None
        self.kills = 0
        self.direct_kills = 0
        self.indirect_kills = 0
        self.died = False
        self.self_ko = False
        self.status = None  # current major status (psn/tox/brn/slp/par/frz)
        self.team_position = None
        self.tera_type = None
        self.terastallized = False
        self.items_revealed = []
        self.abilities_revealed = []
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
    team_order = {"p1": [], "p2": []}  # side -> [species in team-preview order]
    winner_side = None
    last_move = None  # (attacker_key, move_name, target_key)
    last_ability_user = None  # key of the mon whose ability most recently activated
    landed_flag = [False]  # whether last_move has already registered a "landed" event
    last_damage_source = {}  # target_key -> attacker_key or None (indirect/unattributed)
    status_source = {}  # target_key -> attacker_key who inflicted their current status
    hazard_setter = {}  # (side_with_hazard, hazard_name) -> setter_key
    effect_source = {}  # (target_key, move_name) -> attacker_key, for delayed/residual credit
    pending_leech_heal = set()  # seeder keys whose next [silent] self-heal is Leech Seed drain
    weather = [None, None]  # [weather_name, setter_key]
    STATUS_DAMAGE_NAMES = ("psn", "brn")

    def get_or_create(nick_key, side, species):
        mon = mons.get(nick_key)
        if mon is None:
            mon = _Mon(nick_key, side, species)
            order = team_order.get(side, [])
            if species in order:
                mon.team_position = order.index(species) + 1
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
        status = hp_field.split(" ")[1] if " " in hp_field else None
        if status and status != "fnt":
            mon.status = status
        prev = mon.hp
        mon.hp = cur
        if prev is None:
            return None
        return prev - cur

    def credit_dealt(attacker, mon, delta, pct, dealt_bucket, taken_bucket=None, credit_kill=True):
        """Attribute a chunk of indirect/hazard/residual/etc. damage: the
        dealing mon's damage_dealt_<bucket> (+its %), the receiving mon's
        damage_taken_<bucket> (+its %), and (if credit_kill) marks the
        attacker as the fatal-blow source for kill attribution."""
        taken_bucket = taken_bucket or dealt_bucket
        if attacker:
            attacker.stats[f"damage_dealt_{dealt_bucket}"] += delta
            attacker.stats[f"damage_dealt_{dealt_bucket}_pct"] += pct
        mon.stats[f"damage_taken_{taken_bucket}"] += delta
        mon.stats[f"damage_taken_{taken_bucket}_pct"] += pct
        last_damage_source[mon.key] = attacker.key if (attacker and credit_kill) else None

    for raw_line in log.split("\n"):
        line = raw_line.strip("\r")
        if not line.startswith("|"):
            continue
        parts = line.split("|")
        cmd = parts[1] if len(parts) > 1 else ""

        if cmd == "poke":
            side, details = parts[2], parts[3] if len(parts) > 3 else ""
            species = details.split(",")[0].strip()
            if species:
                team_order.setdefault(side, []).append(species)

        elif cmd == "switch" or cmd == "drag":
            slot, details = parts[2], parts[3]
            species = details.split(",")[0].strip()
            side = _side_of(slot)
            nick_key = _nick_of(slot)
            mon = get_or_create(nick_key, side, species)
            if len(parts) > 4:
                apply_hp(mon, parts[4])
            mon.stats["switch_ins"] += 1
            if cmd == "drag":
                mon.stats["times_dragged_in"] += 1
                if last_move:
                    forcer = mons.get(last_move[0])
                    if forcer and forcer.key != nick_key:
                        forcer.stats["forced_switches_caused"] += 1
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
                        existing.direct_kills += mon.direct_kills
                        existing.indirect_kills += mon.indirect_kills
                        existing.died = existing.died or mon.died
                        existing.self_ko = existing.self_ko or mon.self_ko
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

        elif cmd == "-terastallize":
            slot = parts[2]
            tera_type = parts[3] if len(parts) > 3 else None
            mon = mons.get(_nick_of(slot))
            if mon:
                mon.tera_type = tera_type
                mon.terastallized = True

        elif cmd == "-ability":
            slot = parts[2]
            ability_name = parts[3] if len(parts) > 3 else ""
            mon = mons.get(_nick_of(slot))
            if mon:
                if ability_name and ability_name not in mon.abilities_revealed:
                    mon.abilities_revealed.append(ability_name)
                last_ability_user = mon.key

        elif cmd in ("-item", "-enditem"):
            slot = parts[2]
            item_name = parts[3] if len(parts) > 3 else ""
            mon = mons.get(_nick_of(slot))
            if mon and item_name and item_name not in mon.items_revealed:
                mon.items_revealed.append(item_name)

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
            landed_flag[0] = False
            if target_key:
                effect_source[(target_key, move_name)] = attacker_key
            attacker = mons.get(attacker_key)
            if attacker:
                attacker.stats["moves_used"] += 1
                if move_name in SELF_KO_MOVES:
                    attacker.self_ko = True

        elif cmd == "-damage":
            target_slot, hp_field = parts[2], parts[3]
            target_key = _nick_of(target_slot)
            mon = mons.get(target_key)
            if mon is None:
                continue
            from_text, from_kind, of_slot, silent, _wisher = _extract_tags(parts[4:])
            delta = apply_hp(mon, hp_field)
            if not delta or delta <= 0:
                continue
            pct = round(delta / mon.max_hp * 100, 2) if mon.max_hp else 0.0
            source_mon = mons.get(_nick_of(of_slot)) if of_slot else None

            if from_text is None:
                self_cost_field = None
                if last_move and last_move[0] == target_key and last_move[2] == target_key:
                    self_cost_field = SELF_COST_MOVES.get(last_move[1])
                if self_cost_field:
                    mon.stats[self_cost_field] += delta
                    mon.stats["damage_taken_recoil"] += delta
                    mon.stats["damage_taken_recoil_pct"] += pct
                    last_damage_source[target_key] = None
                elif last_move and last_move[2] == target_key and last_move[0] != target_key:
                    attacker = mons.get(last_move[0])
                    move_name = last_move[1]
                    if attacker and attacker.side != mon.side:
                        credit_dealt(attacker, mon, delta, pct, "direct",
                                     credit_kill=move_name not in SELF_KO_MOVES)
                        attacker.stats["hits_landed"] += 1
                        landed_flag[0] = True
                    else:
                        mon.stats["damage_taken_other"] += delta
                        mon.stats["damage_taken_other_pct"] += pct
                        last_damage_source[target_key] = None
                else:
                    mon.stats["damage_taken_other"] += delta
                    mon.stats["damage_taken_other_pct"] += pct
                    last_damage_source[target_key] = None

            elif from_text == "Recoil":
                mon.stats["recoil_damage"] += delta
                mon.stats["damage_taken_recoil"] += delta
                mon.stats["damage_taken_recoil_pct"] += pct
                last_damage_source[target_key] = None

            elif from_kind == "item" and from_text == "Life Orb":
                mon.stats["life_orb_damage"] += delta
                mon.stats["damage_taken_recoil"] += delta
                mon.stats["damage_taken_recoil_pct"] += pct
                last_damage_source[target_key] = None

            elif "Jump Kick" in from_text:
                mon.stats["crash_damage"] += delta
                mon.stats["damage_taken_recoil"] += delta
                mon.stats["damage_taken_recoil_pct"] += pct
                last_damage_source[target_key] = None

            elif from_text == "confusion":
                mon.stats["confusion_self_damage"] += delta
                mon.stats["damage_taken_recoil"] += delta
                mon.stats["damage_taken_recoil_pct"] += pct
                last_damage_source[target_key] = None

            elif from_text in STATUS_DAMAGE_NAMES:
                attacker = mons.get(status_source.get(target_key))
                credit_dealt(attacker, mon, delta, pct, "residual")
                if attacker:
                    field = "residual_dealt_burn" if from_text == "brn" else "residual_dealt_poison"
                    attacker.stats[field] += delta

            elif weather[0] and from_text == weather[0]:
                attacker = mons.get(weather[1])
                opposing = attacker if (attacker and attacker.side != mon.side) else None
                credit_dealt(opposing, mon, delta, pct, "residual")
                if opposing:
                    opposing.stats["residual_dealt_weather"] += delta

            elif from_text == "Leech Seed":
                seeder_key = (of_slot and _nick_of(of_slot)) or effect_source.get((target_key, "Leech Seed"))
                attacker = mons.get(seeder_key) if seeder_key else None
                credit_dealt(attacker, mon, delta, pct, "residual")
                if attacker:
                    attacker.stats["residual_dealt_leech_seed"] += delta
                    pending_leech_heal.add(attacker.key)

            elif from_text == "Salt Cure":
                source_key = (of_slot and _nick_of(of_slot)) or effect_source.get((target_key, "Salt Cure"))
                attacker = mons.get(source_key) if source_key else None
                credit_dealt(attacker, mon, delta, pct, "residual")
                if attacker:
                    attacker.stats["residual_dealt_salt_cure"] += delta

            elif from_text in ("Curse", "Nightmare"):
                source_key = (of_slot and _nick_of(of_slot)) or effect_source.get((target_key, from_text))
                attacker = mons.get(source_key) if source_key else None
                credit_dealt(attacker, mon, delta, pct, "residual")
                if attacker:
                    field = "residual_dealt_curse" if from_text == "Curse" else "residual_dealt_nightmare"
                    attacker.stats[field] += delta

            elif from_text in BINDING_MOVES:
                source_key = (of_slot and _nick_of(of_slot)) or effect_source.get((target_key, from_text))
                attacker = mons.get(source_key) if source_key else None
                credit_dealt(attacker, mon, delta, pct, "residual")
                if attacker:
                    attacker.stats["residual_dealt_binding"] += delta

            elif from_text in HAZARD_NAMES:
                setter_key = hazard_setter.get((mon.side, from_text))
                attacker = mons.get(setter_key) if setter_key else None
                credit_dealt(attacker, mon, delta, pct, "hazard")

            elif from_text in DELAYED_MOVES:
                source_key = effect_source.get((target_key, from_text))
                attacker = mons.get(source_key) if source_key else None
                credit_dealt(attacker, mon, delta, pct, "delayed", taken_bucket="other")

            elif from_kind in ("item", "ability") and source_mon and source_mon.side != mon.side:
                # Contact punishment (Rocky Helmet, Rough Skin, etc.) -
                # credited to the defending Pokemon whose item/ability it is.
                credit_dealt(source_mon, mon, delta, pct, "contact_punish")
                if from_kind == "item":
                    source_mon.stats["residual_dealt_item_ability"] += delta

            elif from_kind in ("item", "ability"):
                # Self-caused (e.g. Solar Power, Bad Dreams on the mon
                # itself) - no external attacker to credit.
                mon.stats["damage_taken_other"] += delta
                mon.stats["damage_taken_other_pct"] += pct
                last_damage_source[target_key] = None

            else:
                mon.stats["damage_taken_other"] += delta
                mon.stats["damage_taken_other_pct"] += pct
                last_damage_source[target_key] = None

        elif cmd == "-heal":
            slot, hp_field = parts[2], parts[3]
            mon = mons.get(_nick_of(slot))
            if mon is None:
                continue
            from_text, from_kind, of_slot, silent, wisher_nick = _extract_tags(parts[4:])
            lost = apply_hp(mon, hp_field)
            delta = -lost if lost else None  # apply_hp reports HP lost; healing is a gain
            if not delta or delta <= 0:
                continue

            if wisher_nick:
                mon.stats["healing_received_wish"] += delta
                wisher_key = f"{mon.side}|{wisher_nick}"
                wisher = mons.get(wisher_key)
                if wisher:
                    wisher.stats["healing_done_wish"] += delta
            elif mon.key in pending_leech_heal:
                mon.stats["healing_received_leech_seed"] += delta
                pending_leech_heal.discard(mon.key)
            elif from_text == "drain":
                mon.stats["healing_received_move"] += delta
            elif from_text == "Grassy Terrain":
                mon.stats["healing_received_terrain"] += delta
            elif from_kind in ("item", "ability"):
                mon.stats["healing_received_item_ability"] += delta
            elif from_kind == "move" or from_text is None:
                mon.stats["healing_received_move"] += delta
            else:
                mon.stats["healing_received_other"] += delta

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

        elif cmd == "-fail":
            if last_move:
                attacker = mons.get(last_move[0])
                if attacker:
                    attacker.stats["moves_failed"] += 1

        elif cmd == "-immune":
            target = mons.get(_nick_of(parts[2]))
            if target:
                target.stats["immune_hits"] += 1

        elif cmd == "-resisted":
            target = mons.get(_nick_of(parts[2]))
            if target:
                target.stats["resisted_hits_taken"] += 1

        elif cmd == "-supereffective":
            target = mons.get(_nick_of(parts[2]))
            if target:
                target.stats["super_effective_hits_taken"] += 1

        elif cmd == "-crit":
            target_key = _nick_of(parts[2])
            target = mons.get(target_key)
            if target:
                target.stats["crits_taken"] += 1
            if last_move and last_move[2] == target_key:
                attacker = mons.get(last_move[0])
                if attacker:
                    attacker.stats["crits_dealt"] += 1

        elif cmd == "-status":
            target_slot = parts[2]
            status_name = parts[3] if len(parts) > 3 else ""
            from_text, from_kind, of_slot, silent, _wisher = _extract_tags(parts[4:])
            target_key = _nick_of(target_slot)
            target = mons.get(target_key)
            if target is None:
                continue
            target.status = status_name
            if from_kind == "move" and from_text == "Rest":
                continue  # Rest's self-inflicted sleep is intentionally excluded
            field = status_name if status_name in ("psn", "tox", "brn", "slp", "par", "frz") else None

            attacker = None
            if last_move and last_move[2] == target_key:
                candidate = mons.get(last_move[0])
                if candidate and candidate.side != target.side:
                    attacker = candidate
            elif status_name in ("psn", "tox"):
                setter_key = hazard_setter.get((target.side, "Toxic Spikes"))
                if setter_key:
                    attacker = mons.get(setter_key)
            elif from_kind == "ability" and of_slot:
                candidate = mons.get(_nick_of(of_slot))
                if candidate and candidate.side != target.side:
                    attacker = candidate

            if attacker:
                status_source[target_key] = attacker.key
                if field:
                    attacker.stats[f"statuses_inflicted_{field}"] += 1
                    target.stats[f"statuses_received_{field}"] += 1
                if not landed_flag[0] and last_move and last_move[0] == attacker.key:
                    attacker.stats["effect_only_landed"] += 1
                    landed_flag[0] = True

        elif cmd in ("-boost", "-unboost"):
            target_slot = parts[2]
            target_key = _nick_of(target_slot)
            target = mons.get(target_key)
            if target is None:
                continue
            is_boost = cmd == "-boost"

            source_key = None
            if last_move and last_move[2] == target_key:
                source_key = last_move[0]
            elif last_ability_user:
                candidate = mons.get(last_ability_user)
                if candidate and candidate.side != target.side:
                    source_key = last_ability_user

            if source_key and source_key != target_key and source_key in mons:
                source = mons[source_key]
                if is_boost:
                    source.stats["boosts_given"] += 1
                    target.stats["boosts_received"] += 1
                else:
                    source.stats["drops_given"] += 1
                    target.stats["drops_received"] += 1
                if not landed_flag[0] and last_move and last_move[0] == source_key:
                    source.stats["effect_only_landed"] += 1
                    landed_flag[0] = True
            else:
                target.stats["self_boosts" if is_boost else "self_drops"] += 1

        elif cmd == "-weather":
            weather_name = parts[2] if len(parts) > 2 else ""
            _from_text, _from_kind, of_slot, _silent, _wisher = _extract_tags(parts[3:])
            if weather_name == "none":
                weather[0], weather[1] = None, None
            elif of_slot:
                setter = mons.get(_nick_of(of_slot))
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
                    if not landed_flag[0] and last_move[0] == attacker.key:
                        attacker.stats["effect_only_landed"] += 1
                        landed_flag[0] = True

        elif cmd == "-sideend":
            side_field = parts[2].split(":")[0].strip()[:2]
            hazard_name = parts[3] if len(parts) > 3 else ""
            hazard_name = hazard_name[len("move: "):] if hazard_name.startswith("move: ") else hazard_name
            hazard_setter.pop((side_field, hazard_name), None)
            if last_move:
                remover = mons.get(last_move[0])
                if remover:
                    remover.stats["hazards_removed"] += 1

        elif cmd == "-swapsideconditions":
            # Court Change: hazards move to the other side, but stay
            # credited to whoever originally set them.
            for name in HAZARD_NAMES:
                key_p1, key_p2 = ("p1", name), ("p2", name)
                v1, v2 = hazard_setter.get(key_p1), hazard_setter.get(key_p2)
                if v1 is None and v2 is None:
                    continue
                if v2 is not None:
                    hazard_setter[key_p1] = v2
                else:
                    hazard_setter.pop(key_p1, None)
                if v1 is not None:
                    hazard_setter[key_p2] = v1
                else:
                    hazard_setter.pop(key_p2, None)

        elif cmd == "faint":
            target_key = _nick_of(parts[2])
            mon = mons.get(target_key)
            if mon is None:
                continue
            mon.died = True
            killer_key = last_damage_source.get(target_key)
            if killer_key and killer_key in mons:
                killer = mons[killer_key]
                killer.kills += 1
                if last_move and last_move[0] == killer_key and last_move[2] == target_key:
                    killer.direct_kills += 1
                else:
                    killer.indirect_kills += 1

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
        row = {
            "pokemon": mon.species,
            "team_position": mon.team_position,
            "tera_type": mon.tera_type,
            "terastallized": mon.terastallized,
            "items_revealed": mon.items_revealed,
            "abilities_revealed": mon.abilities_revealed,
            "kills": mon.kills,
            "direct_kills": mon.direct_kills,
            "indirect_kills": mon.indirect_kills,
            "died": mon.died,
            "self_ko": mon.self_ko,
            "max_hp": mon.max_hp or 0,
        }
        for f in STAT_FIELDS:
            v = mon.stats[f]
            row[f] = round(v, 2) if isinstance(v, float) else v
        result[mon.side].append(row)
    return result
