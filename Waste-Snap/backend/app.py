
from flask import (
    Flask,
    render_template,
    abort,
    redirect,
    url_for,
    request
)
from flask_login import (
    LoginManager,
    login_required,
    current_user
)

# Import database configuration and connection
from config import Config
from models import init_db_connection, get_db
from data_export import schedule_export

# Import database helper
from db_helpers import (
    get_user_by_id,
    get_complaints_by_user,
    get_resolved_complaints_by_user,
    count_strikes,
    STRIKE_LIMIT,
    STRIKE_DAYS
)

# Import our route Blueprints
from routes.auth import auth_bp
from routes.complaints import complaints_bp

from routes.admin import admin_bp
from routes.workers import workers_bp
from routes.company import company_bp
from routes.payments import payments_bp

# -----------------------------------------
# 1. CREATE FLASK APPLICATION
# -----------------------------------------

app = Flask(__name__)

# Load configuration from config.py
app.config.from_object(Config)

# Limit image uploads to 5 MB
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


# -----------------------------------------
# 2. CONNECT MONGODB ATLAS
# -----------------------------------------

init_db_connection(app)


# -----------------------------------------
# KEEP A COPY OF THE DATABASE IN FILES
# -----------------------------------------
#
# After every change (a POST request that worked) the data/ folder
# (JSON files + a .db file) is rewritten a moment later.

@app.after_request
def keep_data_files_up_to_date(response):

    if (
        app.config["AUTO_EXPORT"]
        and request.method == "POST"
        and response.status_code < 400
        and request.endpoint not in ("auth.login", "auth.logout")
    ):
        schedule_export()

    return response


# Write the files once when the app starts
if app.config["AUTO_EXPORT"]:
    schedule_export(delay=1)


# -----------------------------------------
# 3. CONFIGURE FLASK-LOGIN
# -----------------------------------------

login_manager = LoginManager()

login_manager.init_app(app)

# Redirect users to login if not authenticated
login_manager.login_view = "auth.login"


# Load logged-in user from MongoDB
@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)


# -----------------------------------------
# 4. REGISTER BLUEPRINTS
# -----------------------------------------

# Registration, login and logout
app.register_blueprint(auth_bp)

# Complaint reporting
app.register_blueprint(complaints_bp)

# Register Admin routes
app.register_blueprint(admin_bp)

# Register Worker routes
app.register_blueprint(workers_bp)

# Register Company routes
app.register_blueprint(company_bp)

# Register the live payment / receipt pages
app.register_blueprint(payments_bp)


# -----------------------------------------
# 5. HOME PAGE
# -----------------------------------------

@app.route("/")
def home():
    return render_template("home.html")



# -----------------------------------------
# ROLE-BASED DASHBOARD REDIRECT
# -----------------------------------------

@app.route("/dashboard/<role>")
@login_required
def dashboard(role):

    # Prevent access to another role's dashboard
    if role != current_user.role:
        abort(403)

    # Redirect admin
    if role == "admin":
        return redirect(url_for("admin.dashboard"))

    # Redirect worker
    if role == "worker":
        return redirect(url_for("workers.dashboard"))

    # Redirect company
    if role == "company":
        return redirect(url_for("company.dashboard"))

    # Citizen dashboard
    complaints = get_complaints_by_user(current_user.id)

    # Get this citizen's recently resolved complaints
    resolved_complaints = get_resolved_complaints_by_user(
        current_user.id
    )

    return render_template(
        "dashboard.html",
        complaints=complaints,
        resolved_complaints=resolved_complaints,
        strikes=count_strikes(current_user.id),
        strike_limit=STRIKE_LIMIT,
        strike_days=STRIKE_DAYS
    )



# -----------------------------------------
# 7. TEST MONGODB CONNECTION (admins only)
# -----------------------------------------

@app.route("/db-check")
@login_required
def check_database():

    if current_user.role != "admin":
        abort(403)

    try:
        get_db().command("ping")

        return (
            "Successfully connected to MongoDB: "
            f"{get_db().name}"
        )

    except Exception as error:
        app.logger.error("Database error: %s", error)
        return "Database connection failed.", 500


# -----------------------------------------
# 8. RUN FLASK APPLICATION
# -----------------------------------------

if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"])
