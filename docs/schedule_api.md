# Schedule API

A read-only JSON endpoint for fetching a season's match schedule, for use by
external servers/services.

## Endpoint

```
GET /api/schedule/
```

No authentication required.

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

## Response

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

## Errors

`400 Bad Request` for an unrecognized `season`:

```json
{ "error": "Invalid season" }
```

## Implementation

- View: [`home/views.py`](../home/views.py) — `schedule_api`
- URL: [`home/urls.py`](../home/urls.py) — `path('api/schedule/', ...)`
- Data source: `home/data_access.py` — `get_schedule(season)` (same function
  the schedule page itself uses)
