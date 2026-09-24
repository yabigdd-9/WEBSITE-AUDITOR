#!/usr/bin/env python3
"""Create a verified backup of the money_machine database."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'money-machine'))

from mm_core import backup

if __name__ == "__main__":
    backup_folder = backup()
    print(f"Verified backup created at: {backup_folder}")

    # Verify the backup exists and has manifest
    manifest_path = os.path.join(backup_folder, 'manifest.json')
    if os.path.exists(manifest_path):
        print("Backup manifest verified")
    else:
        print("ERROR: Backup manifest missing")
        sys.exit(1)

    # Verify the database file exists in backup
    db_backup_path = os.path.join(backup_folder, 'money_machine.db')
    if os.path.exists(db_backup_path):
        print("Backup database file verified")
    else:
        print("ERROR: Backup database file missing")
        sys.exit(1)