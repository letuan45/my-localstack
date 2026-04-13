import logging
from common.log_handler import get_otel_log_handler

SERVICE_NAME = "lambda_b"

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    logger.addHandler(get_otel_log_handler(SERVICE_NAME))
