"""
Bulk-parses every match in a season's schedule that has a replay_url but
no stats yet, and persists the parsed per-Pokemon stats via
data_access.set_match_from_replay -- the same path the per-match "parse
replay" button in the UI uses, just looped over the whole schedule.
"""
import time

from django.core.management.base import BaseCommand, CommandError

from home import data_access, replay_parser


class Command(BaseCommand):
    help = "Backfill match stats for every replay in a season's schedule that doesn't have stats yet."

    def add_arguments(self, parser):
        parser.add_argument("season", choices=["1", "2", "3", "4"])
        parser.add_argument("--redo", action="store_true",
                             help="Also re-parse matches that already have stats.")

    def handle(self, *args, **options):
        season = options["season"]
        redo = options["redo"]

        weeks = data_access.get_schedule(season)
        if not weeks:
            raise CommandError(f"No schedule found for season {season}.")

        targets = []
        for week in weeks:
            for i, match in enumerate(week["matches"]):
                if not match.get("replay_url"):
                    continue
                if match.get("stats") and not redo:
                    continue
                targets.append((week["week"], i, match["player1"], match["player2"], match["replay_url"]))

        self.stdout.write(f"{len(targets)} match(es) to parse for season {season}.")

        ok, failed = 0, []
        for week_num, idx, p1, p2, url in targets:
            label = f"week {week_num} #{idx} ({p1} vs {p2})"
            try:
                success, err = data_access.set_match_from_replay(season, week_num, idx, url)
                if success:
                    ok += 1
                    self.stdout.write(self.style.SUCCESS(f"  OK  {label}"))
                else:
                    failed.append((label, err))
                    self.stdout.write(self.style.WARNING(f"  SKIP {label}: {err}"))
            except replay_parser.ReplayParseError as e:
                failed.append((label, str(e)))
                self.stdout.write(self.style.ERROR(f"  FAIL {label}: {e}"))
            except Exception as e:
                failed.append((label, str(e)))
                self.stdout.write(self.style.ERROR(f"  FAIL {label}: {e!r}"))
            time.sleep(0.3)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Parsed {ok}/{len(targets)} match(es)."))
        if failed:
            self.stdout.write(self.style.ERROR(f"{len(failed)} failure(s):"))
            for label, err in failed:
                self.stdout.write(f"  - {label}: {err}")
