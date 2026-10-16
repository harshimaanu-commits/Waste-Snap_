
# Keeps a COPY of the MongoDB data in ordinary files:
#
#   data/json/users.json, complaints.json, payments.json, violations.json
#       readable in any text editor
#   data/wastesnap_backup.db
#       one SQLite database file (open it with "DB Browser for SQLite")
#
# MongoDB stays the real database. These files are a read-only copy that
# is rewritten when the app starts and a moment after every change.
# Password hashes are never written to the files.

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from bson import ObjectId

from models import get_db


COLLECTIONS = ["users", "complaints", "payments", "violations"]

# Fields that must never be copied into the files
HIDDEN_FIELDS = {"password_hash"}

# Seconds to wait after a change before writing the files, so a burst
# of changes is written once
EXPORT_DELAY_SECONDS = 2.0

DB_FILE_NAME = "wastesnap_backup.db"

_lock = threading.Lock()
_timer = None


# -----------------------------------------
# WHERE THE FILES GO
# -----------------------------------------

def export_dir():

    custom = os.getenv("DATA_EXPORT_DIR")

    if custom:
        return Path(custom)

    # <project root>/data
    return Path(__file__).resolve().parent.parent / "data"


# -----------------------------------------
# CONVERT MONGODB DOCUMENTS INTO PLAIN DATA
# -----------------------------------------

def _plain(value):

    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")

    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]

    return value


def read_collection(name):

    documents = []

    for record in get_db()[name].find():

        document = _plain(record)

        # _id becomes a normal "id" column, listed first
        cleaned = {"id": document.pop("_id")}
        cleaned.update(document)

        for field in HIDDEN_FIELDS:
            if field in cleaned:
                cleaned[field] = "[hidden]"

        documents.append(cleaned)

    documents.sort(key=lambda d: str(d.get("created_at") or ""))

    return documents


# -----------------------------------------
# WRITE THE JSON FILES
# -----------------------------------------

def _write_json(folder, name, documents):

    path = folder / f"{name}.json"
    temp = folder / f"{name}.json.tmp"

    temp.write_text(
        json.dumps(documents, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    os.replace(temp, path)


# -----------------------------------------
# WRITE THE SQLITE .db FILE
# -----------------------------------------

def _column_type(values):

    values = [v for v in values if v is not None]

    if values and all(isinstance(v, bool) for v in values):
        return "INTEGER"

    if values and all(
        isinstance(v, int) and not isinstance(v, bool) for v in values
    ):
        return "INTEGER"

    if values and all(
        isinstance(v, (int, float)) and not isinstance(v, bool)
        for v in values
    ):
        return "REAL"

    return "TEXT"


def _cell(value):

    if isinstance(value, bool):
        return int(value)

    # lists and nested objects are stored as JSON text
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    return value


def _write_sqlite(path, data, exported_at):

    temp = Path(str(path) + ".tmp")

    if temp.exists():
        temp.unlink()

    connection = sqlite3.connect(temp)

    try:
        for name, documents in data.items():

            # Every field that appears in any document becomes a column
            columns = []

            for document in documents:
                for key in document:
                    if key not in columns:
                        columns.append(key)

            if not columns:
                columns = ["id"]

            types = {
                column: _column_type(
                    [d.get(column) for d in documents]
                )
                for column in columns
            }

            definition = ", ".join(
                f'"{column}" {types[column]}'
                + (" PRIMARY KEY" if column == "id" else "")
                for column in columns
            )

            connection.execute(f'CREATE TABLE "{name}" ({definition})')

            marks = ", ".join("?" for _ in columns)
            names = ", ".join(f'"{column}"' for column in columns)

            connection.executemany(
                f'INSERT INTO "{name}" ({names}) VALUES ({marks})',
                [
                    [_cell(d.get(column)) for column in columns]
                    for d in documents
                ]
            )

        connection.execute(
            "CREATE TABLE export_info (exported_at TEXT, note TEXT)"
        )

        connection.execute(
            "INSERT INTO export_info VALUES (?, ?)",
            (exported_at,
             "Read-only copy of the WasteSnap MongoDB data. "
             "Password hashes are not included.")
        )

        connection.commit()

    except Exception:
        connection.close()
        temp.unlink(missing_ok=True)
        raise

    connection.close()

    # Swap in the finished file. If it is open in another program the
    # swap fails: remove the temporary file so nothing is left behind.
    try:
        os.replace(temp, path)

    except OSError:
        temp.unlink(missing_ok=True)
        raise


# -----------------------------------------
# NOTE FOR WHOEVER OPENS THE FOLDER
# -----------------------------------------

README_TEXT = """WasteSnap data copy
===================

This folder is a read-only COPY of the MongoDB database used by the app.
It is rewritten automatically every time the app starts and a moment after
every change (and when an admin presses "Export now" on the Data page).
The real database is MongoDB Atlas; do not edit these files.

json/users.json        the user accounts (password hashes are hidden)
json/complaints.json   every complaint with its status and history
json/payments.json     payments to companies
json/violations.json   strikes and warnings
wastesnap_backup.db    the same data in ONE SQLite database file.
                       Open it with "DB Browser for SQLite"
                       (https://sqlitebrowser.org), or with the sqlite3
                       command:  sqlite3 wastesnap_backup.db "SELECT * FROM complaints;"

Dates are written as "YYYY-MM-DD HH:MM:SS". Lists and nested values inside
the .db file are stored as JSON text.
"""


# -----------------------------------------
# EXPORT EVERYTHING NOW
# -----------------------------------------
#
# Returns a short result dictionary (never raises: a problem only means
# the copy is a little out of date).

def export_all():

    with _lock:

        try:
            folder = export_dir()
            json_folder = folder / "json"

            json_folder.mkdir(parents=True, exist_ok=True)

            data = {name: read_collection(name) for name in COLLECTIONS}

            exported_at = datetime.now().isoformat(
                sep=" ", timespec="seconds"
            )

            for name, documents in data.items():
                _write_json(json_folder, name, documents)

            (folder / "README.txt").write_text(
                README_TEXT, encoding="utf-8"
            )

            try:
                _write_sqlite(folder / DB_FILE_NAME, data, exported_at)
                db_ok = True

            except (OSError, sqlite3.Error):
                # for example the .db file is open in another program
                db_ok = False

            return {
                "ok": True,
                "db_file_updated": db_ok,
                "exported_at": exported_at,
                "counts": {n: len(d) for n, d in data.items()}
            }

        except Exception as error:
            return {"ok": False, "error": str(error)}


# -----------------------------------------
# EXPORT A MOMENT AFTER A CHANGE (waits, so many changes = one export)
# -----------------------------------------

def schedule_export(delay=None):

    global _timer

    if delay is None:
        delay = EXPORT_DELAY_SECONDS

    with _lock:

        if _timer is not None:
            _timer.cancel()

        _timer = threading.Timer(delay, export_all)
        _timer.daemon = True
        _timer.start()


# -----------------------------------------
# LIST THE FILES (for the admin Data page)
# -----------------------------------------

def list_files():

    folder = export_dir()

    files = []

    candidates = [folder / DB_FILE_NAME, folder / "README.txt"] + [
        folder / "json" / f"{name}.json" for name in COLLECTIONS
    ]

    for path in candidates:

        if path.exists():

            stat = path.stat()

            files.append({
                "name": str(path.relative_to(folder)).replace("\\", "/"),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(
                    stat.st_mtime
                ).isoformat(sep=" ", timespec="seconds")
            })

    return files


# Files an admin is allowed to download
def downloadable_names():

    return (
        [DB_FILE_NAME, "README.txt"]
        + [f"json/{name}.json" for name in COLLECTIONS]
    )
