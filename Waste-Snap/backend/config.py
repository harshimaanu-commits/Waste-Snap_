
import os
from pathlib import Path

from dotenv import load_dotenv


# Load private settings from the .env file in the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


class Config:

    # Flask secret key (used to sign login sessions)
    SECRET_KEY = os.getenv("SECRET_KEY", "")

    # MongoDB Atlas connection
    MONGODB_URI = os.getenv("MONGODB_URI", "")
    MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "wastesnap_db")

    # Keep a copy of the database in files (data/ folder).
    # Set AUTO_EXPORT=false in .env to switch it off.
    AUTO_EXPORT = os.getenv("AUTO_EXPORT", "true").lower() == "true"

    # Set FLASK_DEBUG=true in .env while developing
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
