import json
import boto3
import os
import logging

from common.otel import init_tracer
from common.tracing import traced_lambda
from common import local_http
from common.log_handler import OtelLogHandler

logger = logging.getLogger()
logger.setLevel(logging.INFO)

logger.addHandler(OtelLogHandler())

localstack_host = os.environ.get(
    'LOCALSTACK_HOSTNAME', 'localhost.localstack.cloud')
endpoint = f"http://{localstack_host}:4566"

sqs = boto3.client("sqs", endpoint_url=endpoint, region_name="us-east-1")

tracer = init_tracer("lambda_a")


def send_message(queue_url: str, message_body: dict):
    """
    Helper function to send message to SQS queue.
    """
    from common.inject import inject_trace
    carrier = inject_trace()

    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(message_body),
        MessageAttributes={
            'traceparent': {
                'DataType': 'String',
                'StringValue': carrier.get('traceparent', '')
            }
        }
    )


@traced_lambda
def handler(event, context):
    logger.info(f"lambda_a triggered with event: {json.dumps(event)}")

    response = sqs.get_queue_url(QueueName="my_queue")
    queue_url = response['QueueUrl']

    message_payload = event if event else {"info": "no data received"}

    send_message(queue_url, message_payload)

    logger.info("message sent")

    logger.error("This is a test error log")
    return {
        "statusCode": 200
    }
