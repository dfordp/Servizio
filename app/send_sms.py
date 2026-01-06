# app/send_sms.py
import os
import re
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

SID  = os.environ.get("MSG_TWILIO_ACCOUNT_SID")
TOK  = os.environ.get("MSG_TWILIO_AUTH_TOKEN")
FROM = os.environ.get("MSG_TWILIO_FROM_E164")

_client = Client(SID, TOK) if SID and TOK else None
E164_RE = re.compile(r"^\+\d{10,15}$")

def _ok_e164(p: str | None) -> bool:
    return bool(p and E164_RE.fullmatch(p))

def send_received_sms(order_no: str, to_phone_no: str):
    """Confirmation SMS (sent right after order is placed)."""
    if not _client:
        print("❌ Twilio client not configured"); return None
    if not _ok_e164(to_phone_no):
        print(f"❌ Invalid E.164 phone for SMS: {to_phone_no}"); return None
    print(f"📱 SMS (received) to {to_phone_no}: order {order_no}")
    return _client.messages.create(
        from_=FROM, to=to_phone_no,
        body=(
            f"Thanks for your order with Servizio! 🍹 "
            f"Your order number is {order_no}. "
            "We’ll text you again when it’s ready for pickup.\n"
            "Reply STOP to opt out."
        )
    )

def send_ready_sms(order_no: str, to_phone_no: str):
    """Notify order is ready (triggered by /barista Done)."""
    if not _client:
        print("❌ Twilio client not configured"); return None
    if not _ok_e164(to_phone_no):
        print(f"❌ Invalid E.164 phone for SMS: {to_phone_no}"); return None
    print(f"📱 SMS (ready) to {to_phone_no}: order {order_no}")
    return _client.messages.create(
        from_=FROM, to=to_phone_no,
        body=(
            f"Hi! Your boba order #{order_no} is now ready for pickup at Servizio. 🧋 "
            "See you soon!\n"
            "Reply STOP to opt out."
        )
    )
