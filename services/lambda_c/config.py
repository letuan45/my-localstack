import logging
from common.log_handler import get_otel_log_handler
from opentelemetry.sdk._logs import LoggingHandler


SERVICE_NAME = "lambda_c"

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

has_otel_handler = any(isinstance(h, LoggingHandler) for h in logger.handlers)

if not has_otel_handler:
    logger.addHandler(get_otel_log_handler(SERVICE_NAME))
