import logging
from common.log_handler import OtelLogHandler
import boto3
import os

localstack_host = os.environ.get(
    'LOCALSTACK_HOSTNAME', 'localhost.localstack.cloud')
endpoint = f"http://{localstack_host}:4566"

sqs = boto3.client("sqs", endpoint_url=endpoint, region_name="us-east-1")
sns = boto3.client("sns", endpoint_url=endpoint, region_name="us-east-1")

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(OtelLogHandler())
