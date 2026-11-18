"""Encrypted database backups (SEC-20).

``python manage.py encrypted_backup --output-dir /var/backups/bookstore`` runs
``pg_dump`` and writes the dump encrypted with ``BACKUP_ENCRYPTION_KEY``
(Fernet: AES-128-CBC + HMAC-SHA256). The plain dump never touches the disk,
the file is created with mode 0600 inside a 0700 directory so only the backup
operator account can read it, and there is no fallback key: without
``BACKUP_ENCRYPTION_KEY`` the command refuses to run.

``--decrypt FILE --to OUT.sql`` turns a backup back into SQL for a restore.
"""

import os
import subprocess
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


def _fernet():
    key = getattr(settings, "BACKUP_ENCRYPTION_KEY", "")
    if not key:
        raise CommandError("BACKUP_ENCRYPTION_KEY is not set; refusing to write an unencrypted backup.")
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except ValueError as error:
        raise CommandError("BACKUP_ENCRYPTION_KEY is not a valid Fernet key.") from error


def _write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


class Command(BaseCommand):
    help = "Write an encrypted pg_dump of the database, or decrypt one for a restore."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default="backups")
        parser.add_argument("--decrypt", metavar="FILE")
        parser.add_argument("--to", metavar="OUT")

    def handle(self, *args, **options):
        fernet = _fernet()
        if options["decrypt"]:
            if not options["to"]:
                raise CommandError("--decrypt needs --to OUT.sql")
            try:
                plain = fernet.decrypt(Path(options["decrypt"]).read_bytes())
            except InvalidToken as error:
                raise CommandError("Wrong key or damaged backup file.") from error
            _write_private(options["to"], plain)
            self.stdout.write(f"Decrypted {len(plain)} bytes to {options['to']}")
            return

        if connection.vendor != "postgresql":
            raise CommandError("encrypted_backup supports PostgreSQL only.")
        db = connection.settings_dict
        env = {**os.environ, "PGPASSWORD": db.get("PASSWORD") or ""}
        command = ["pg_dump", "--no-owner", "--format=plain", "-h", db.get("HOST") or "localhost",
                   "-p", str(db.get("PORT") or 5432), "-U", db["USER"], db["NAME"]]
        result = subprocess.run(command, env=env, capture_output=True, check=False)  # noqa: S603 (fixed argv)
        if result.returncode != 0:
            # pg_dump's stderr can echo connection details; report the exit code only.
            raise CommandError(f"pg_dump failed with exit code {result.returncode}.")

        out_dir = Path(options["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(out_dir, 0o700)
        path = out_dir / f"bookstore-{timezone.now():%Y%m%dT%H%M%S}.sql.enc"
        _write_private(path, fernet.encrypt(result.stdout))
        self.stdout.write(f"Encrypted backup written to {path} ({len(result.stdout)} bytes before encryption)")
