import json
import logging
import os
import sys

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("url", "stage", "domain", "duration_ms", "cache_hit"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

_configured = False

def get_logger(name: str) -> logging.Logger:
    global _configured
    root = logging.getLogger()
    if not _configured:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(JsonFormatter())
        has_json = any(isinstance(existing.formatter, JsonFormatter) for existing in root.handlers)
        if not has_json:
            root.addHandler(h)
        root.setLevel(os.getenv("LOG_LEVEL", "INFO"))
        _configured = True
    return logging.getLogger(name)
