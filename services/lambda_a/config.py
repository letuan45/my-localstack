from aws_lambda_powertools import Logger
import logging
from common.log_handler import get_otel_log_handler
import boto3
import os


SERVICE_NAME = "lambda_a"

logger = Logger(service=SERVICE_NAME)
logger.setLevel("DEBUG")

has_otel_handler = any(type(h).__name__ == "LoggingHandler" for h in logger.handlers)
if not has_otel_handler:
    logger.addHandler(get_otel_log_handler(SERVICE_NAME))

localstack_host = os.environ.get(
    'LOCALSTACK_HOSTNAME', 'localhost.localstack.cloud')
endpoint = f"http://{localstack_host}:4566"

sqs = boto3.client("sqs", endpoint_url=endpoint, region_name="us-east-1")
sns = boto3.client("sns", endpoint_url=endpoint, region_name="us-east-1")
