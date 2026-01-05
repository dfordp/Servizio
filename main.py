import os
from fastapi import FastAPI, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from dotenv import load_dotenv

load_dotenv()

RESTAURANT_STAFF_PHONE = os.getenv("RESTAURANT_STAFF_PHONE")

app = FastAPI(title="Servizio Backend", version="0.3")


@app.get("/health")
def health_check():
    return {"status": "ok"}


# -------------------------
# STEP 4 ENTRY POINT
# -------------------------
@app.post("/twilio/inbound")
async def inbound_call(_: Request):
    """
    Step 4:
    - Greeting
    - Recording consent
    - Ask for first word to detect language
    """

    response = VoiceResponse()

    response.say(
        "Hello. This call may be recorded to help manage reservations."
    )

    gather = Gather(
        input="speech",
        action="/twilio/language",
        method="POST",
        timeout=4,
        speech_timeout="auto"
    )

    gather.say(
        "Please say hello for English, or ciao for Italian."
    )

    response.append(gather)

    # Fail-open if nothing captured
    response.say("Connecting you to the restaurant.")
    if RESTAURANT_STAFF_PHONE:
        response.dial(RESTAURANT_STAFF_PHONE)

    return Response(str(response), media_type="text/xml")


# -------------------------
# LANGUAGE GATE
# -------------------------
@app.post("/twilio/language")
async def language_gate(request: Request):
    """
    Step 4:
    - Decide language from first spoken word
    - Lock language for remainder of call
    """

    form = await request.form()
    speech = (form.get("SpeechResult") or "").lower().strip()

    response = VoiceResponse()

    # Deterministic language decision
    if speech.startswith("ciao"):
        response.redirect("/twilio/it")
        return Response(str(response), media_type="text/xml")

    if speech.startswith("hello"):
        response.redirect("/twilio/en")
        return Response(str(response), media_type="text/xml")

    # Configurable fallback: default Italian or escalate
    response.say(
        "I could not understand the language. Connecting you to the restaurant."
    )
    if RESTAURANT_STAFF_PHONE:
        response.dial(RESTAURANT_STAFF_PHONE)

    return Response(str(response), media_type="text/xml")


# -------------------------
# ITALIAN FLOW (PLACEHOLDER)
# -------------------------
@app.post("/twilio/it")
async def italian_entry():
    response = VoiceResponse()

    response.say(
        "Ciao. Continuiamo in italiano. Dimmi come posso aiutarti."
    )

    gather = Gather(
        input="speech",
        action="/twilio/it/next",
        method="POST",
        timeout=5,
        speech_timeout="auto"
    )

    response.append(gather)
    return Response(str(response), media_type="text/xml")


# -------------------------
# ENGLISH FLOW (PLACEHOLDER)
# -------------------------
@app.post("/twilio/en")
async def english_entry():
    response = VoiceResponse()

    response.say(
        "Hello. We will continue in English. Please tell me how I can help you."
    )

    gather = Gather(
        input="speech",
        action="/twilio/en/next",
        method="POST",
        timeout=5,
        speech_timeout="auto"
    )

    response.append(gather)
    return Response(str(response), media_type="text/xml")
