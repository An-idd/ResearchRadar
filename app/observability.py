"""Small JSON event logger; callers pass identifiers, never provider payloads."""

import json
import logging
from typing import Any

logger = logging.getLogger("researchradar")


def event(name: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": name, **fields}, default=str, ensure_ascii=False))
