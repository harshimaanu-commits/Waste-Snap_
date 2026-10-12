
from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user

from db_helpers import get_payments


# Create the Company Blueprint
company_bp = Blueprint("company", __name__)


# -----------------------------------------
# COMPANY DASHBOARD
# -----------------------------------------

@company_bp.route("/company")
@login_required
def dashboard():

    # Only companies can access this page
    if current_user.role != "company":
        abort(403)

    # Payments for work assigned to this company
    payments = get_payments(current_user.id)

    pending_total = sum(
        payment["net_amount"] for payment in payments
        if payment["status"] == "pending"
    )

    penalty_total = sum(
        payment["penalty"] for payment in payments
    )

    paid_total = sum(
        payment["net_amount"] for payment in payments
        if payment["status"] == "paid"
    )

    return render_template(
        "company_dashboard.html",
        payments=payments,
        pending_total=pending_total,
        paid_total=paid_total,
        penalty_total=penalty_total
    )
