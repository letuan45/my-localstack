import json
import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

localstack_host = os.environ.get(
    'LOCALSTACK_HOSTNAME', 'localhost.localstack.cloud')
endpoint = f"http://{localstack_host}:4566"

sqs = boto3.client("sqs", endpoint_url=endpoint, region_name="us-east-1")


def handler(event, context):
    logger.info("lambda_a triggered")

    response = sqs.get_queue_url(QueueName="my_queue")
    queue_url = response['QueueUrl']

    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({"msg": "hello from lambda_a"})
    )

    logger.info("message sent")
    return {
        "statusCode": 200
    }
