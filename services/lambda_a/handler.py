import json
import boto3

sqs = boto3.client(
    "sqs",
    endpoint_url="http://localstack:4566",
    region_name="us-east-1",
    aws_access_key_id="test",
    aws_secret_access_key="test"
)

QUEUE_URL = "http://localstack:4566/000000000000/my_queue"

def handler(event, context):
    print("lambda_a triggered")

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({"msg": "hello from lambda_a"})
    )

    return {"status": "sent"}