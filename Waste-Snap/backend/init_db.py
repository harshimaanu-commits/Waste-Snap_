
# Import our Flask application
from app import app

from models import get_db


# Connect to the Flask application
with app.app_context():

    database = get_db()

    # Two accounts cannot share the same email
    database.users.create_index("email", unique=True)

    # Speed up the dashboard searches
    database.complaints.create_index("user_id")
    database.complaints.create_index("assigned_worker_id")
    database.complaints.create_index("status")

    # One payment per complaint
    database.payments.create_index("complaint_id", unique=True)
    database.payments.create_index("company_id")

    # Violation log (strikes, warnings)
    database.violations.create_index("user_id")
    database.violations.create_index("kind")

    print("WASTE SNAP database indexes created!")
