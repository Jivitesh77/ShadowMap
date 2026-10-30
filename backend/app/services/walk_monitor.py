"""Background clock for Walk With Me: every 2 seconds it applies the time rules to running walks, so alerts happen
even when the walker's phone stops sending anything."""

import logging
import threading

from app.db import SessionLocal, utcnow
from app.services.walks import evaluate_all

log = logging.getLogger("shadowmap.walks")


class WalkMonitor:
    def __init__(self, every_s: float = 2.0) -> None:
        self.every_s = every_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="walk-monitor", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.every_s):
            try:
                with SessionLocal() as db:
                    evaluate_all(db, utcnow())
            except Exception:  # keep the clock running even if one round fails
                log.exception("walk monitor round failed")


monitor = WalkMonitor()
