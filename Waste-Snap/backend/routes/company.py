
from flask import (
    Blueprint,
    render_template,
    abort,
    request,
    flash,
    redirect,
    url_for
)
from flask_login import login_required, current_user

from db_helpers import (
    get_payments,
    get_requestable_complaints,
    request_payment
)


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

    # Money still to come: approved, being paid, or failed (to retry)
    pending_total = sum(
        payment["net_amount"] for payment in payments
        if payment["status"] in ("pending", "processing", "failed")
    )

    # Asked for, waiting for the admin
    requested_total = sum(
        payment["net_amount"] for payment in payments
        if payment["status"] == "requested"
    )

    penalty_total = sum(
        payment["penalty"] for payment in payments
        if payment["status"] not in ("rejected", "requested")
    )

    paid_total = sum(
        payment["net_amount"] for payment in payments
        if payment["status"] == "paid"
    )

    return render_template(
        "company_dashboard.html",
        payments=payments,
        pending_total=pending_total,
        requested_total=requested_total,
        paid_total=paid_total,
        penalty_total=penalty_total,
        requestable=get_requestable_complaints(current_user.id)
    )


# -----------------------------------------
# COMPANY ASKS TO BE PAID FOR A RESOLVED JOB
# -----------------------------------------

@company_bp.route(
    "/company/request/<complaint_id>",
    methods=["POST"]
)
@login_required
def request_money(complaint_id):

    if current_user.role != "company":
        abort(403)

    success, message = request_payment(
        complaint_id,
        current_user.id,
        request.form.get("amount"),
        request.form.get("note", "")
    )

    flash(message, "success" if success else "danger")

    return redirect(url_for("company.dashboard"))
