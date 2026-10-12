
from bson import ObjectId
from bson.errors import InvalidId
from flask_login import UserMixin
from pymongo import MongoClient


# -----------------------------------------
# MONGODB CONNECTION
# -----------------------------------------

# These are filled in by init_db_connection() when the app starts
client = None
db = None


def init_db_connection(app):

    global client, db

    uri = app.config["MONGODB_URI"]

    if not uri:
        raise RuntimeError(
            "MONGODB_URI is missing. Copy .env.example to .env "
            "and add the Atlas connection string."
        )

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)

    db = client[app.config["MONGODB_DATABASE"]]


def get_db():

    if db is None:
        raise RuntimeError("Database is not connected yet.")

    return db


# Convert text into a MongoDB ObjectId (None if it is not valid)
def to_object_id(value):

    try:
        return ObjectId(str(value))

    except (InvalidId, TypeError):
        return None


# -----------------------------------------
# DATABASE COLLECTIONS
# -----------------------------------------
#
# users
#   name, email (unique), password_hash,
#   role (citizen / worker / admin / company), created_at
#
# complaints
#   user_id, type, description, location,
#   image_filename, status, worker_done,
#   resolution_image_filename, assigned_worker_id,
#   created_at, updated_at
#
# status flow:
#   Submitted -> Verified -> Assigned -> In Progress -> Resolved
#
# payments (added with the company feature)
#   company_id, worker_id, amount, status,
#   reference, note, created_at


# -----------------------------------------
# USER CLASS (needed by Flask-Login)
# -----------------------------------------

class User(UserMixin):

    def __init__(self, document):

        # MongoDB _id becomes a text id such as "65f1..."
        self.id = str(document["_id"])

        self.name = document.get("name", "")
        self.email = document.get("email", "")
        self.password_hash = document.get("password_hash", "")
        self.role = document.get("role", "citizen")
        self.created_at = document.get("created_at")
