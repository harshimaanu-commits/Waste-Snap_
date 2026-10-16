WasteSnap data copy
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
