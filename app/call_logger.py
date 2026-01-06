# app/call_logger.py
from pathlib import Path
import os

# Default to /app/logs inside the container; override with env if desired
LOGS_DIR = Path(os.getenv("BOBA_LOG_DIR", "/app/logs"))
LOGS_DIR.mkdir(parents=True, exist_ok=True)

def log_file_for(phone_digits: str, suffix: str = "") -> Path:
    """
    Optional helper if you ever want to open a specific call log.
    We only export LOGS_DIR for now since http_routes.py uses globbing.
    """
    name = f"{phone_digits}{suffix}.log"
    return LOGS_DIR / name
