
# Fill the database with demo accounts and a few complaints
# so the whole workflow can be shown straight away.
#
#   python seed_demo.py
#
# Safe to run again: accounts that already exist are skipped.
# These accounts use a simple shared password - demo use only!

from datetime import datetime, timedelta

from app import app
from models import get_db, to_object_id
from db_helpers import get_user_by_email, create_user, create_complaint


DEMO_PASSWORD = "Demo@1234"

DEMO_USERS = [
    ("Demo Admin", "admin@wastesnap.test", "admin"),
    ("Demo Worker", "worker@wastesnap.test", "worker"),
    ("Demo Company", "company@wastesnap.test", "company"),
    ("Demo Citizen", "citizen@wastesnap.test", "citizen"),
]


with app.app_context():

    # Create the demo accounts
    for name, email, role in DEMO_USERS:

        if get_user_by_email(email):
            print(f"Skipped (already exists): {email}")

        else:
            create_user(name, email, DEMO_PASSWORD, role)
            print(f"Created {role}: {email}")

    citizen = get_user_by_email("citizen@wastesnap.test")

    # Add sample complaints only if the citizen has none yet
    if get_db().complaints.count_documents(
        {"user_id": to_object_id(citizen.id)}
    ) == 0:

        # (type, location, description, days it had existed when reported)
        samples = [
            ("Garbage accumulation", "Market Road, near the bus stop",
             "Garbage has not been collected for a week.", 7),
            ("Overflowing bin", "Lake View Park entrance",
             "The bin is overflowing and attracting stray dogs.", 3),
            ("Illegal dumping", "Sector 4, behind the school",
             "Construction debris dumped on the roadside.", 14),
        ]

        for index, (issue_type, location, description, days) in enumerate(samples):

            complaint = create_complaint(
                citizen.id, issue_type, description, location, None, days
            )

            # Spread the dates out a little
            created = datetime.now() - timedelta(days=index)

            get_db().complaints.update_one(
                {"_id": to_object_id(complaint["id"])},
                {"$set": {"created_at": created, "updated_at": created}}
            )

        print("Created 3 sample complaints.")

    print()
    print("Demo logins (password for all: " + DEMO_PASSWORD + ")")

    for name, email, role in DEMO_USERS:
        print(f"  {role:<8} {email}")
