def detect_intent(text: str, language: str) -> str:
    """
    Allowed intents:
    - reservation
    - availability
    - staff

    Everything else is unknown.
    """

    text = text.lower()

    if language == "it":
        if any(k in text for k in ["prenot", "tavolo"]):
            return "reservation"
        if any(k in text for k in ["disponibil", "posti", "avete"]):
            return "availability"
        if any(k in text for k in ["staff", "persona", "parlare"]):
            return "staff"

    if language == "en":
        if any(k in text for k in ["reserve", "booking", "table"]):
            return "reservation"
        if any(k in text for k in ["available", "availability"]):
            return "availability"
        if any(k in text for k in ["staff", "person", "someone"]):
            return "staff"

    return "unknown"
