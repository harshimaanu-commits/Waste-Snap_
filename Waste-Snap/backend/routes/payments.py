
from flask import (
    Blueprint,
    render_template,
    abort,
    jsonify,
    flash,
    redirect,
    url_for
)
from flask_login import login_required, current_user

from db_helpers import get_payment
from payment_gateway import payment_status


# Pages shared by the admin and the company that is being paid:
# the live payment screen, its status feed, and the receipt
payments_bp = Blueprint("payments", __name__)


# Load a payment the current user is allowed to see
def _load_payment(payment_id):

    payment = get_payment(payment_id)

    if payment is None:
        abort(404)

    # The admin sees every payment. A company sees only its own.
    if current_user.role == "admin":
        return payment

    if (
        current_user.role == "company"
        and payment["company_id"] == current_user.id
    ):
        return payment

    abort(403)


# -----------------------------------------
# LIVE PAYMENT SCREEN
# -----------------------------------------

@payments_bp.route("/payments/<payment_id>/live")
@login_required
def live(payment_id):

    payment = _load_payment(payment_id)

    return render_template("payment_live.html", payment=payment)


# -----------------------------------------
# STATUS FEED (the live screen asks for this every second)
# -----------------------------------------

@payments_bp.route("/payments/<payment_id>/status")
@login_required
def status(payment_id):

    _load_payment(payment_id)

    return jsonify(payment_status(payment_id))


# -----------------------------------------
# RECEIPT (printable)
# -----------------------------------------

@payments_bp.route("/payments/<payment_id>/receipt")
@login_required
def receipt(payment_id):

    payment = _load_payment(payment_id)

    if payment["status"] != "paid":
        flash("A receipt is available once the payment is paid.", "warning")

        return redirect(url_for("payments.live", payment_id=payment_id))

    return render_template("payment_receipt.html", payment=payment)
