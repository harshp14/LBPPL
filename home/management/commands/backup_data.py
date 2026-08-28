"""
Zips home/data/*.json into a timestamped archive under BACKUP_DIR.

This is the local half of data backup: it produces a self-contained
archive on disk that can then be shipped off the VM by whatever means
gets picked later (git push, object storage, email, etc. -- see the
changelog). Run manually, or wire up to cron for a recurring backup.
"""
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand

from home.data_access import DATA_DIR

BACKUP_DIR = Path(__file__).resolve().parents[3] / "backups"


class Command(BaseCommand):
    help = "Back up home/data/*.json into a timestamped zip under backups/."

    def handle(self, *args, **options):
        BACKUP_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_path = BACKUP_DIR / f"data_backup_{timestamp}.zip"

        json_files = sorted(DATA_DIR.glob("*.json"))
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in json_files:
                zf.write(f, arcname=f.name)

        self.stdout.write(self.style.SUCCESS(
            f"Backed up {len(json_files)} file(s) to {archive_path}"
        ))
