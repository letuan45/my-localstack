import json
import uuid
from opentelemetry import trace

from common.otel import init_tracer
from common.tracing import traced_lambda

from services.lambda_a.utils import send_message
from services.lambda_a.config import logger

tracer = init_tracer("lambda_a")

@traced_lambda(logger=logger)
def handler(event, context):
    logger.debug(f"lambda_a triggered with event: {json.dumps(event)}")
    target_destination = event.get("target_destination", "arn:aws:sns:us-east-1:000000000000:my_topic")
    is_batch_test = event.get("simulate_batch", False)

    # Simulate processing the event and sending a message to the next service
    # Business Logic: Retrieve IMEIs and tag the span
    current_span = trace.get_current_span()

    if is_batch_test:
        logger.info(f"Simulating Batch Send to: {target_destination}")
        devices = event.get("devices", [])
        for dev in devices:
            device_id = dev.get("device_id")
            device_imeis = dev.get("device_imeis", [])

            payload = {
                "action": "register",
                "device_id": device_id,
                "device_imeis": device_imeis,
                "batch_id": str(uuid.uuid4())
            }

            send_message(payload, target_destination)
    else:
        logger.info(f"Sending Single Message to: {target_destination}")
        device_id = event.get("device_id", "SINGLE_TEST_DEV")
        device_imeis = event.get("device_imeis", ["351756051523999", "351756051523998"])

        current_span.set_attribute("device_id", device_id)
        current_span.set_attribute("device_imeis", json.dumps(device_imeis))

        payload = {
            "action": "register",
            "device_id": device_id,
            "device_imeis": device_imeis
        }
        send_message(payload, target_destination)

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Dispatched successfully", "target": target_destination})
    }
