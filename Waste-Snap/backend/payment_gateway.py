
# A SIMULATED payment gateway for the demo.
#
# No real money moves and no real bank is contacted. It behaves like the
# test mode of a real gateway (Razorpay, Stripe): you choose a payment
# method, enter details, and watch the payment move through stages in
# real time. Special test values make a payment fail on purpose.
#
# How it works:
#   1. start_payment() checks the details and changes the payment from
#      "pending" (or "failed") to "processing" in ONE database step, so a
#      double click cannot pay twice.
#   2. A background thread then moves the payment through the stages,
#      pausing a little at each one and saving a timeline event.
#   3. The live page asks payment_status() every second and draws it.
#
# Card numbers, PINs and CVVs are NEVER saved. Only a masked label such as
# "Visa card ending 1111" is stored.

import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta

from models import get_db, to_object_id
from db_helpers import payment_event, money


# -----------------------------------------
# THE STAGES OF A PAYMENT
# -----------------------------------------

# (key, label while it is happening, text saved when it is done)
STAGES = [
    ("initiate", "Initiating the payment", "Payment initiated"),
    ("verify", "Verifying the payee's details", "Payee details verified"),
    ("authorise", "Authorising with the bank", "Bank authorised the payment"),
    ("transfer", "Transferring the money", "Money transferred to the payee"),
    ("confirm", "Confirming the payment", "Payment successful"),
]

# Seconds spent on each stage (multiplied by PAYMENT_SPEED)
STAGE_SECONDS = [0.8, 1.6, 2.2, 2.2, 0.8]

# A payment stuck in "processing" longer than this (for example the server
# restarted) is marked as failed so it can be retried
STUCK_SECONDS = 45

METHODS = ("upi", "card", "bank")


def _speed():

    try:
        return float(os.getenv("PAYMENT_SPEED", "1"))

    except ValueError:
        return 1.0


# -----------------------------------------
# CHECK THE PAYMENT METHOD DETAILS
# -----------------------------------------
#
# Returns {"ok": False, "error": "..."} when something is typed wrongly
# (the payment is NOT started), or
# {"ok": True, "label": "...", "fail_stage": None or a stage key,
#  "fail_reason": "..."}.
# fail_stage is set for the special TEST values that make the payment fail.

def _luhn_ok(number):

    total = 0

    for position, digit in enumerate(reversed(number)):

        value = int(digit)

        if position % 2 == 1:
            value *= 2

            if value > 9:
                value -= 9

        total += value

    return total % 10 == 0


def _card_brand(number):

    return {
        "4": "Visa", "5": "Mastercard", "3": "Amex", "6": "RuPay"
    }.get(number[:1], "Card")


def validate_method(method, form):

    if method == "upi":

        upi_id = str(form.get("upi_id", "")).strip().lower()
        pin = str(form.get("upi_pin", "")).strip()

        if not re.fullmatch(r"[a-z0-9._\-]{2,}@[a-z]{2,}", upi_id):
            return {"ok": False,
                    "error": "Enter a valid UPI ID, for example name@bank."}

        if not re.fullmatch(r"\d{4}|\d{6}", pin):
            return {"ok": False,
                    "error": "The UPI PIN must be 4 or 6 digits."}

        result = {"ok": True, "label": f"UPI: {upi_id}",
                  "fail_stage": None, "fail_reason": ""}

        # TEST VALUE: PIN 0000 / 000000 is rejected by the "bank"
        if pin in ("0000", "000000"):
            result["fail_stage"] = "authorise"
            result["fail_reason"] = "Incorrect UPI PIN. The bank declined the payment."

        return result

    if method == "card":

        number = re.sub(r"\D", "", str(form.get("card_number", "")))
        name = str(form.get("card_name", "")).strip()
        expiry = str(form.get("card_expiry", "")).strip()
        cvv = str(form.get("card_cvv", "")).strip()

        if not 13 <= len(number) <= 19 or not _luhn_ok(number):
            return {"ok": False,
                    "error": "That card number is not valid."}

        if not name or len(name) > 60:
            return {"ok": False,
                    "error": "Enter the name on the card."}

        match = re.fullmatch(r"(\d{2})\s*/\s*(\d{2})", expiry)

        if not match or not 1 <= int(match.group(1)) <= 12:
            return {"ok": False,
                    "error": "Enter the expiry as MM/YY."}

        month, year = int(match.group(1)), 2000 + int(match.group(2))
        now = datetime.now()

        if (year, month) < (now.year, now.month):
            return {"ok": False, "error": "This card has expired."}

        if not re.fullmatch(r"\d{3,4}", cvv):
            return {"ok": False, "error": "The CVV must be 3 or 4 digits."}

        result = {
            "ok": True,
            "label": f"{_card_brand(number)} card ending {number[-4:]}",
            "fail_stage": None, "fail_reason": ""
        }

        # TEST CARDS (the same ones Stripe uses in test mode)
        declined = {
            "4000000000000002": "Card declined: insufficient funds.",
            "4000000000000069": "Card declined: the card has expired.",
            "4000000000000127": "Card declined: the CVV check failed.",
        }

        if number in declined:
            result["fail_stage"] = "authorise"
            result["fail_reason"] = declined[number]

        return result

    if method == "bank":

        account = re.sub(r"\D", "", str(form.get("bank_account", "")))
        ifsc = str(form.get("bank_ifsc", "")).strip().upper()
        holder = str(form.get("bank_holder", "")).strip()

        if not 9 <= len(account) <= 18:
            return {"ok": False,
                    "error": "The account number must have 9 to 18 digits."}

        if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", ifsc):
            return {"ok": False,
                    "error": "Enter a valid IFSC code, for example HDFC0001234."}

        if not holder or len(holder) > 80:
            return {"ok": False,
                    "error": "Enter the account holder's name."}

        result = {
            "ok": True,
            "label": f"Bank transfer: a/c ending {account[-4:]} ({ifsc})",
            "fail_stage": None, "fail_reason": ""
        }

        # TEST VALUE: an account number ending in 0000 does not exist
        if account.endswith("0000"):
            result["fail_stage"] = "verify"
            result["fail_reason"] = "Beneficiary account is closed or does not exist."

        return result

    return {"ok": False, "error": "Choose a payment method."}


# -----------------------------------------
# START PAYING (the admin pressed "Confirm and pay")
# -----------------------------------------
#
# Returns (True/False, message)

def start_payment(payment_id, method, form):

    object_id = to_object_id(payment_id)

    if object_id is None:
        return False, "Payment not found."

    payment = get_db().payments.find_one({"_id": object_id})

    if payment is None:
        return False, "Payment not found."

    if payment["status"] not in ("pending", "failed"):
        return False, (
            f"This payment cannot be paid now (it is {payment['status']})."
        )

    complaint = get_db().complaints.find_one(
        {"_id": payment["complaint_id"]}
    ) or {}

    if complaint.get("rating_penalty") == "pending":
        return False, (
            "A low-rating review is waiting for your decision. "
            "Decide it on the Reviews page first."
        )

    if complaint.get("status") != "Resolved":
        return False, "The complaint is not resolved, so it cannot be paid."

    checked = validate_method(method, form)

    if not checked["ok"]:
        return False, checked["error"]

    attempt = payment.get("attempts", 0) + 1
    now = datetime.now()

    # pending/failed -> processing in ONE step (no double payment)
    result = get_db().payments.update_one(
        {"_id": object_id, "status": {"$in": ["pending", "failed"]}},
        {"$set": {"status": "processing",
                  "attempts": attempt,
                  "method": method,
                  "method_label": checked["label"],
                  "stage": 0,
                  "failure_reason": None,
                  "started_at": now,
                  "progress_at": now},
         "$push": {"events": payment_event(
             f"Attempt {attempt}: paying Rs. {money(payment['net_amount'])} "
             f"by {checked['label']}"
         )}}
    )

    if result.modified_count != 1:
        return False, "This payment is already being processed."

    thread = threading.Thread(
        target=_run,
        args=(object_id, checked["fail_stage"], checked["fail_reason"]),
        daemon=True
    )

    thread.start()

    return True, "Payment started."


# -----------------------------------------
# THE BACKGROUND WORKER: MOVES THE PAYMENT THROUGH THE STAGES
# -----------------------------------------

def _run(object_id, fail_stage, fail_reason):

    try:
        database = get_db()

        for index, (key, active_text, done_text) in enumerate(STAGES):

            time.sleep(STAGE_SECONDS[index] * _speed())

            now = datetime.now()

            if key == fail_stage:

                database.payments.update_one(
                    {"_id": object_id, "status": "processing"},
                    {"$set": {"status": "failed",
                              "failure_reason": fail_reason,
                              "progress_at": now},
                     "$push": {"events": payment_event(
                         f"{active_text} failed. {fail_reason}", "error"
                     )}}
                )

                break

            if index == len(STAGES) - 1:

                txn_id = "TXN" + "".join(
                    secrets.choice("0123456789") for _ in range(12)
                )

                receipt_no = (
                    "RCPT-" + now.strftime("%Y%m%d") + "-"
                    + secrets.token_hex(3).upper()
                )

                database.payments.update_one(
                    {"_id": object_id, "status": "processing"},
                    {"$set": {"status": "paid",
                              "stage": len(STAGES),
                              "txn_id": txn_id,
                              "receipt_no": receipt_no,
                              "paid_at": now,
                              "progress_at": now},
                     "$push": {"events": payment_event(
                         f"{done_text}. Transaction ID {txn_id}", "success"
                     )}}
                )

                break

            result = database.payments.update_one(
                {"_id": object_id, "status": "processing"},
                {"$set": {"stage": index + 1, "progress_at": now},
                 "$push": {"events": payment_event(done_text)}}
            )

            # Someone else changed the payment: stop quietly
            if result.matched_count != 1:
                return

    except Exception as error:

        try:
            get_db().payments.update_one(
                {"_id": object_id, "status": "processing"},
                {"$set": {"status": "failed",
                          "failure_reason": "Unexpected error. Please retry.",
                          "progress_at": datetime.now()},
                 "$push": {"events": payment_event(
                     f"Unexpected error: {error}", "error"
                 )}}
            )

        except Exception:
            pass

    _after_change()


# The data/ copy of the database should show the new status too
def _after_change():

    if os.getenv("AUTO_EXPORT", "true").lower() != "true":
        return

    try:
        from data_export import schedule_export
        schedule_export()

    except Exception:
        pass


# -----------------------------------------
# THE CURRENT STATE (the live page asks for this every second)
# -----------------------------------------

def payment_status(payment_id):

    object_id = to_object_id(payment_id)

    if object_id is None:
        return None

    payment = get_db().payments.find_one({"_id": object_id})

    if payment is None:
        return None

    now = datetime.now()

    # Recovery: the worker thread is gone (for example the server restarted)
    progress_at = payment.get("progress_at")

    if (
        payment["status"] == "processing"
        and progress_at
        and now - progress_at > timedelta(seconds=STUCK_SECONDS)
    ):
        get_db().payments.update_one(
            {"_id": object_id, "status": "processing"},
            {"$set": {"status": "failed",
                      "failure_reason": "The payment was interrupted. Please retry.",
                      "progress_at": now},
             "$push": {"events": payment_event(
                 "The payment was interrupted. Please retry.", "error"
             )}}
        )

        payment = get_db().payments.find_one({"_id": object_id})

    return {
        "status": payment["status"],
        "stage": payment.get("stage", 0),
        "total_stages": len(STAGES),
        "steps": [
            {"key": key, "label": active, "done": done}
            for key, active, done in STAGES
        ],
        "events": [
            {"time": event["at"].strftime("%H:%M:%S"),
             "text": event["text"],
             "kind": event.get("kind", "info")}
            for event in payment.get("events", [])
        ],
        "failure_reason": payment.get("failure_reason"),
        "txn_id": payment.get("txn_id"),
        "receipt_no": payment.get("receipt_no"),
        "attempts": payment.get("attempts", 0),
        "method_label": payment.get("method_label"),
        "amount": payment["amount"],
        "net_amount": payment.get("net_amount", payment["amount"]),
        "paid_at": (
            payment["paid_at"].strftime("%d %b %Y, %H:%M:%S")
            if payment.get("paid_at") else None
        )
    }
