# Schedule API

Read-only JSON endpoints for fetching a season's match schedule, for use by
external servers/services. No authentication required.

## `GET /api/schedule/`

Full schedule for a season, grouped by week.

### Query parameters

| Param    | Required | Default | Notes                              |
|----------|----------|---------|-------------------------------------|
| `season` | No       | `4`     | One of `1`, `2`, `3`, `4`.          |

An invalid `season` value returns a `400` with an error body (see below).

### Example requests

```bash
curl "http://147.5.114.148:8000/api/schedule/"
curl "http://147.5.114.148:8000/api/schedule/?season=3"
```

### Response

`200 OK` with a JSON array, one entry per week:

```json
[
  {
    "week": 1,
    "label": "Week 1",
    "matches": [
      {
        "player1": "CoachA",
        "player2": "CoachB",
        "replay_url": "https://replay.pokemonshowdown.com/...",
        "winner": "CoachA",
        "margin": 2,
        "stats": {
          "player1": [ { "pokemon": "...", "...": "..." } ],
          "player2": [ { "pokemon": "...", "...": "..." } ]
        },
        "scheduled_day": "2026-09-10"
      }
    ]
  }
]
```

### Field notes

- `week` — integer week number.
- `label` — display label for the week (e.g. `"Week 1"`).
- `matches` — list of matches scheduled for that week, in match order.
  - `player1` / `player2` — coach names.
  - `replay_url` — link to the submitted replay, or `null` if none yet.
  - `winner` — `player1`'s or `player2`'s name (whichever value matches),
    or `null` if the match hasn't been played.
  - `margin` — Pokémon-remaining margin of victory, or `null` if unplayed.
  - `stats` — per-Pokémon battle stats parsed from the replay
    (`{"player1": [...], "player2": [...]}`), or `null` if unplayed/unparsed.
    Pokémon names are canonicalized to the draft board's naming convention.
  - `scheduled_day` — ISO `YYYY-MM-DD` coach-proposed play date, or `null`.

An unplayed match has `replay_url`, `winner`, `margin`, and `stats` all `null`
(unless a game day has been proposed, in which case `scheduled_day` is set).

## `GET /api/upcoming-games/`

Matches that have a coach-proposed day to play but no replay submitted yet,
across all weeks, soonest first. This is a filtered/flattened view of the
same data `/api/schedule/` returns.

### Query parameters

Same as `/api/schedule/` — `season` (default `4`), validated the same way.

### Example requests

```bash
curl "http://147.5.114.148:8000/api/upcoming-games/"
curl "http://147.5.114.148:8000/api/upcoming-games/?season=3"
```

### Response

`200 OK` with a JSON array, soonest game first:

```json
[
  {
    "week": 2,
    "week_label": "Week 2",
    "match_index": 0,
    "player1": "CoachA",
    "player2": "CoachB",
    "scheduled_day": "2026-09-10"
  }
]
```

- `week` / `week_label` — which week the match belongs to.
- `match_index` — position of the match within that week's `matches` list
  (useful for cross-referencing against `/api/schedule/`).
- `player1` / `player2` — coach names.
- `scheduled_day` — ISO `YYYY-MM-DD` proposed play date.

Only matches with a proposed `scheduled_day` and no `replay_url` yet appear
here — once a replay is submitted the match drops out of this list (it still
shows up in `/api/schedule/`).

## `GET /api/rosters/`

Every coach's team name and full drafted roster for a season. Pass `coach`
to get a single team instead of the whole list.

### Query parameters

| Param    | Required | Default | Notes                                          |
|----------|----------|---------|--------------------------------------------------|
| `season` | No       | `4`     | One of `1`, `2`, `3`, `4`.                      |
| `coach`  | No       | —       | Case-insensitive exact match on `coach_name`.   |

### Example requests

```bash
curl "http://147.5.114.148:8000/api/rosters/"
curl "http://147.5.114.148:8000/api/rosters/?season=3"
curl "http://147.5.114.148:8000/api/rosters/?coach=Harsh"
```

### Response

Without `coach` — `200 OK` with a JSON array, one entry per team:

```json
[
  {
    "coach_name": "Harsh",
    "team_name": "Some Team Name",
    "logo": "https://.../logo.png",
    "pokemon": [ { "name": "Landorus-Therian", "points": 20 } ],
    "free_agents_used": 1
  }
]
```

With `coach` — `200 OK` with a single team object (same shape as above, not
wrapped in an array).

- `coach_name` — the coach's name (matches `player1`/`player2` in the
  schedule endpoints).
- `team_name` — display name for the team, or `null` if unset.
- `logo` — logo URL/path, or `""` if unset.
- `pokemon` — the coach's full drafted roster, each entry `{name, points}`.
- `free_agents_used` — count of free-agency pickups made this season.

## Errors

`400 Bad Request` for an unrecognized `season`, from any endpoint:

```json
{ "error": "Invalid season" }
```

`404 Not Found` from `/api/rosters/?coach=...` when no team matches:

```json
{ "error": "Coach not found" }
```

## Implementation

- Views: [`home/views.py`](../home/views.py) — `schedule_api`,
  `upcoming_games_api`, `rosters_api`
- URLs: [`home/urls.py`](../home/urls.py) — `api/schedule/`,
  `api/upcoming-games/`, `api/rosters/`
- Data source: `home/data_access.py` — `get_schedule(season)`,
  `get_upcoming_games(season)`, `get_rosters(season)` (same functions the
  site's own pages use)
