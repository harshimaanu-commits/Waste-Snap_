
from app import app
from db_helpers import get_user_by_email, create_user
from getpass import getpass


# Create a company account (a contractor the admin pays)
with app.app_context():

    print("Create WASTE SNAP Company Account")

    # Collect company details
    name = input("Enter company name: ").strip()
    email = input("Enter company email: ").strip().lower()
    password = getpass("Enter company password: ")

    # Validate the information
    if not name or not email or "@" not in email:
        print("Please enter a valid name and email.")

    elif len(password) < 8:
        print("Password must contain at least 8 characters.")

    elif get_user_by_email(email):
        print("This email is already registered.")

    else:
        # Create the company and save it in MongoDB
        create_user(name, email, password, "company")

        print("Company account created successfully!")
