# app/main.py
import logging, sys
from .app_factory import create_app

logging.basicConfig(
    level=logging.INFO,             # <- show INFO+
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = create_app()
