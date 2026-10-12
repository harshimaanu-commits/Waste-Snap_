
from app import app
from db_helpers import get_user_by_email, create_user
from getpass import getpass


# Create an admin account for local testing
with app.app_context():

    print("Create WASTE SNAP Admin Account")

    # Collect admin details
    name = input("Enter admin name: ").strip()
    email = input("Enter admin email: ").strip().lower()

    # getpass hides the password as you type
    password = getpass("Enter admin password: ")

    # Check that details are valid
    if not name or not email or "@" not in email:
        print("Please enter a valid name and email.")

    elif len(password) < 8:
        print("Password must have at least 8 characters.")

    elif get_user_by_email(email):
        print("An account with this email already exists.")

    else:
        # Create the admin user and save it in MongoDB
        create_user(name, email, password, "admin")

        print("Admin account created successfully!")
