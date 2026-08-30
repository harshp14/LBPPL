"""
Copies db.sqlite3 into a timestamped file under BACKUP_DIR.

The database is the app's source of truth now (rosters, schedule/battle
stats, free agency log, accolades), so backing it up means copying that
one file -- see the changelog for how it originally backed up
home/data/*.json instead. This is the local half of data backup: it
produces a self-contained file on disk that can then be shipped off the
VM by whatever means gets picked later (git push, object storage, email,
etc.). Run manually, or wire up to cron for a recurring backup.
"""
import shutil
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand

BASE_DIR = Path(__file__).resolve().parents[3]
BACKUP_DIR = BASE_DIR / "backups"


class Command(BaseCommand):
    help = "Back up db.sqlite3 into a timestamped copy under backups/."

    def handle(self, *args, **options):
        BACKUP_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = BACKUP_DIR / f"db_backup_{timestamp}.sqlite3"

        shutil.copy2(BASE_DIR / "db.sqlite3", backup_path)

        self.stdout.write(self.style.SUCCESS(f"Backed up db.sqlite3 to {backup_path}"))
