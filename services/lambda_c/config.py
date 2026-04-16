from aws_lambda_powertools import Logger
from common.log_handler import get_otel_log_handler

SERVICE_NAME = "lambda_c"

logger = Logger(service=SERVICE_NAME)
logger.setLevel("DEBUG")

has_otel_handler = any(type(h).__name__ == "LoggingHandler" for h in logger.handlers)
if not has_otel_handler:
    logger.addHandler(get_otel_log_handler(SERVICE_NAME))