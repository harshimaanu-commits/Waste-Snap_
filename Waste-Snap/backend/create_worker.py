
from app import app
from db_helpers import get_user_by_email, create_user
from getpass import getpass


# Create a worker account for testing
with app.app_context():

    print("Create WASTE SNAP Worker Account")

    # Collect worker information
    name = input("Enter worker name: ").strip()
    email = input("Enter worker email: ").strip().lower()
    password = getpass("Enter worker password: ")

    # Validate the information
    if not name or not email or "@" not in email:
        print("Please enter a valid name and email.")

    elif len(password) < 8:
        print("Password must contain at least 8 characters.")

    elif get_user_by_email(email):
        print("This email is already registered.")

    else:
        # Create the worker and save it in MongoDB
        create_user(name, email, password, "worker")

        print("Worker account created successfully!")
