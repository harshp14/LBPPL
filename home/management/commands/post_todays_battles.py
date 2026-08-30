"""Posts today's scheduled, unplayed battles to Discord. Meant to run once
daily around game time, triggered by an external scheduler (e.g. Windows
Task Scheduler)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand

from home import data_access, discord_webhooks

EASTERN = ZoneInfo("America/New_York")


class Command(BaseCommand):
    help = "Post today's scheduled, unplayed battles to Discord."

    def handle(self, *args, **options):
        today = datetime.now(EASTERN).strftime("%Y-%m-%d")

        weeks = data_access.get_schedule("4")

        todays_matches = [
            match
            for week in weeks
            for match in week["matches"]
            if match.get("scheduled_day") == today and not match.get("winner")
        ]

        if not todays_matches:
            self.stdout.write("No battles scheduled for today.")
            return

        discord_webhooks.notify_todays_battles(todays_matches)
        self.stdout.write(self.style.SUCCESS(f"Posted {len(todays_matches)} battle(s) to Discord."))
