"""
Discord webhook URLs and message text, kept separate from data_access.py so
they can be edited without touching app logic. Every send here is
best-effort - a webhook outage should never block an action that already
saved successfully.
"""
import requests

# Base URL for links back to the site in Discord messages. Update this once
# the app has a real production domain.
SITE_BASE_URL = "http://127.0.0.1:8001"

# Free agency tracker: posts every drop/pickup move.
FREE_AGENCY_WEBHOOK_URL = "https://discord.com/api/webhooks/1542556245486075995/UaKu_0Lu6hDDWbLDqMiYaOZFhRkl3T2tP7Ybbj8_q1YuM9sewVFwc1m_Fb8OSEq6h8Dn"

# Schedule page: posts when a coach proposes a day to play an unplayed match.
# Point this at a different webhook URL if game-time pings should go to a
# different channel than free agency moves.
GAME_TIME_WEBHOOK_URL = "https://discord.com/api/webhooks/1542556245486075995/UaKu_0Lu6hDDWbLDqMiYaOZFhRkl3T2tP7Ybbj8_q1YuM9sewVFwc1m_Fb8OSEq6h8Dn"


def _post(webhook_url, payload):
    try:
        requests.post(webhook_url, json=payload, timeout=5)
    except requests.RequestException:
        pass


def notify_free_agency(season, coach_name, team_name, drop_names, pickup_names):
    dropping = "\n".join(drop_names) if drop_names else "(none)"
    picking_up = "\n".join(pickup_names) if pickup_names else "(none)"
    payload = {
        "embeds": [
            {
                "title": "Pokemon Traded",
                "fields": [
                    {"name": "Team", "value": team_name, "inline": True},
                    {"name": "Coach", "value": coach_name, "inline": True},
                    {"name": "​", "value": "​", "inline": False},
                    {"name": "Dropping", "value": dropping, "inline": True},
                    {"name": "Picking up", "value": picking_up, "inline": True},
                ],
            }
        ]
    }
    _post(FREE_AGENCY_WEBHOOK_URL, payload)


def notify_battle_concluded(season, team1_name, coach1_name, team2_name, coach2_name, replay_url, match_url):
    payload = {
        "embeds": [
            {
                "title": "Pokemon Battle Concluded",
                "fields": [
                    {"name": team1_name or coach1_name, "value": coach1_name, "inline": True},
                    {"name": team2_name or coach2_name, "value": coach2_name, "inline": True},
                    {"name": "Replay", "value": replay_url, "inline": False},
                    {"name": "Match Page", "value": match_url, "inline": False},
                ],
            }
        ]
    }
    _post(GAME_TIME_WEBHOOK_URL, payload)


def notify_todays_battles(matches):
    lines = [f"{m['player1']} vs {m['player2']}" for m in matches]
    payload = {
        "embeds": [
            {
                "title": "Today's Scheduled Battles",
                "description": "\n".join(lines),
            }
        ]
    }
    _post(GAME_TIME_WEBHOOK_URL, payload)


def notify_game_time(season, week_label, player1, player2, day):
    payload = {
        "embeds": [
            {
                "fields": [
                    {"name": "Date", "value": f"{week_label} — {day}", "inline": False},
                    {"name": "Team 2", "value": player2, "inline": True},
                    {"name": "Team 1", "value": player1, "inline": True},
                ],
                "title": "Pokemon Battle Scheduled",
            }
        ]
    }
    _post(GAME_TIME_WEBHOOK_URL, payload)
