import logging
from common.log_handler import get_otel_log_handler
import boto3
import os
from opentelemetry.sdk._logs import LoggingHandler


SERVICE_NAME = "lambda_a"

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

has_otel_handler = any(isinstance(h, LoggingHandler) for h in logger.handlers)

if not has_otel_handler:
    logger.addHandler(get_otel_log_handler(SERVICE_NAME))

localstack_host = os.environ.get(
    'LOCALSTACK_HOSTNAME', 'localhost.localstack.cloud')
endpoint = f"http://{localstack_host}:4566"

sqs = boto3.client("sqs", endpoint_url=endpoint, region_name="us-east-1")
sns = boto3.client("sns", endpoint_url=endpoint, region_name="us-east-1")

