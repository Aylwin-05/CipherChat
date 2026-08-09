import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """
    Structured (JSON-lines) formatter: machine-readable logs for
    collection pipelines, with the human detail still present.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(level: str = "INFO", json_output: bool = True):
    root = logging.getLogger()
    root.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if json_output else logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
    )

    root.handlers[:] = [handler]

    for noisy in (
        "uvicorn.access",
        "httpx",
        "multipart",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return root