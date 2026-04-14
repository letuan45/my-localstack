import json
from opentelemetry import trace

from common.otel import init_tracer
from common.tracing import traced_lambda

# from utils import send_message
# from config import logger, sqs
from services.lambda_a.utils import send_message
from services.lambda_a.config import logger, sqs, sns

tracer = init_tracer("lambda_a")

@traced_lambda
def handler(event, context):
    logger.debug(f"lambda_a triggered with event: {json.dumps(event)}")

    # response = sqs.get_queue_url(QueueName="my_queue")
    # queue_url = response['QueueUrl']
    target_arn = "arn:aws:sns:us-east-1:000000000000:my_topic"

    # Simulate processing the event and sending a message to the next service
    device_imeis = ["351756051523999", "351756051523998"]
    current_span = trace.get_current_span()
    current_span.set_attribute("device_imeis", json.dumps(device_imeis))

    if not event:
        logger.warning("Received empty event, sending default message")
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "No event data received"})
        }

    message_payload = {
        "original_event": event,
        "device_imeis": device_imeis,
        "action": "process_device"
    }

    # send_message(message_payload, queue_url)
    send_message(message_payload, target_arn)

    logger.debug(f"message sent to target successfully {target_arn}")
    # logger.info(f"message sent to target successfully {queue_url}")
    logger.error("This is a test error log")

    return {
        "statusCode": 200
    }
