import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict

from pythonjsonlogger import jsonlogger

from app.core.correlation import get_correlation_id


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging"""

    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = datetime.utcnow().isoformat()
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        
        correlation_id = get_correlation_id()
        if correlation_id:
            log_record["correlation_id"] = correlation_id
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id
        if hasattr(record, "user_id"):
            log_record["user_id"] = record.user_id


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Setup structured logging"""
    logger = logging.getLogger("axiar")
    logger.setLevel(getattr(logging, log_level.upper()))

    handler = logging.StreamHandler(sys.stdout)
    formatter = CustomJsonFormatter("%(timestamp)s %(level)s %(name)s %(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger


# Global logger instance
logger = setup_logging()
