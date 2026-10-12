
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from flask_login import (
    login_user,
    logout_user,
    login_required,
    current_user
)

from werkzeug.security import check_password_hash

from db_helpers import (
    get_user_by_email,
    create_citizen
)


# Blueprint for authentication
auth_bp = Blueprint("auth", __name__)


# -----------------------------------------
# CITIZEN REGISTRATION
# -----------------------------------------

@auth_bp.route("/register", methods=["GET", "POST"])
def register():

    # Already logged-in users go to their dashboard
    if current_user.is_authenticated:
        return redirect(
            url_for("dashboard", role=current_user.role)
        )

    if request.method == "GET":
        return render_template("register.html")

    # Get form information
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    # Check required fields
    if not name or not email or not password:
        flash("Please fill in all fields.", "danger")
        return render_template("register.html")

    # Validate email
    if "@" not in email or "." not in email.split("@")[-1]:
        flash("Please enter a valid email.", "danger")
        return render_template("register.html")

    # Validate password
    if len(password) < 8:
        flash("Password must contain at least 8 characters.", "danger")
        return render_template("register.html")

    # Check for duplicate email
    if get_user_by_email(email):
        flash("Email already registered.", "danger")
        return render_template("register.html")

    # Create a new citizen
    create_citizen(name, email, password)

    flash("Registration successful! Please log in.", "success")

    return redirect(url_for("auth.login"))


# -----------------------------------------
# USER LOGIN
# -----------------------------------------

@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    # Redirect users who are already logged in
    if current_user.is_authenticated:
        return redirect(
            url_for("dashboard", role=current_user.role)
        )

    if request.method == "GET":
        return render_template("login.html")

    # Get login information
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    # Find the user in the database
    user = get_user_by_email(email)

    # Check whether the user exists and
    # whether the password matches its hash
    if not user or not check_password_hash(
        user.password_hash, password
    ):
        flash("Invalid email or password.", "danger")
        return render_template("login.html")

    # Create the user's login session
    login_user(user)

    flash("Login successful!", "success")

    # Redirect based on the user's role
    return redirect(
        url_for("dashboard", role=user.role)
    )


# -----------------------------------------
# USER LOGOUT
# -----------------------------------------

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():

    # End the current user's login session
    logout_user()

    flash("You have been logged out.", "success")

    return redirect(url_for("auth.login"))
