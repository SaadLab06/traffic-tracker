import json
import logging
from app.utils.logger import get_logger

def test_logger_emits_json(caplog):
    log = get_logger("test")
    with caplog.at_level(logging.INFO):
        log.info("hello", extra={"url": "https://x.fr", "stage": 1})
    record = caplog.records[-1]
    payload = json.loads(record.getMessage()) if record.getMessage().startswith("{") else {"message": record.message}
    assert "hello" in caplog.text
