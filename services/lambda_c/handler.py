import json
from typing import Any

from opentelemetry import trace
from common.otel import init_tracer
from common.tracing import traced_lambda
from services.lambda_c.const import (
    HTTP_BAD_REQUEST,
    HTTP_OK,
    SIMULATED_ERROR_DEVICE_ID,
    SNS_SUCCESS_BODY,
    UNKNOWN_ACTION,
    UNKNOWN_DEVICE_ID,
)
from services.lambda_c.config import logger
from services.lambda_c.utils import (
    get_record_body,
    is_sns_record,
    is_sqs_record,
    normalize_imeis,
    parse_payload,
    tag_root_span,
)

from aws_lambda_powertools.utilities.batch import (
    BatchProcessor,
    EventType,
    process_partial_response
)
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord

tracer = init_tracer("lambda_c")
processor = BatchProcessor(event_type=EventType.SQS)


def process_device_logic(payload: dict[str, Any]) -> None:
    """Run device processing inside an item-level child span."""
    device_id = payload.get('device_id', UNKNOWN_DEVICE_ID)
    device_imeis = normalize_imeis(payload.get('device_imeis'))
    action = payload.get('action', UNKNOWN_ACTION)

    with tracer.start_as_current_span(f"process_device:{device_id}") as item_span:
        item_span.set_attribute("device_id", device_id)
        item_span.set_attribute("device_imeis", json.dumps(device_imeis))
        item_span.set_attribute("action", action)

        try:
            logger.debug(f"Processing device {device_id} | IMEIs: {device_imeis}")

            if device_id == SIMULATED_ERROR_DEVICE_ID:
                raise ValueError(f"Simulated error for device {device_id}")

            logger.info(f"Successfully processed device: {device_id}")

        except Exception as e:
            logger.error(f"Failed to process device {device_id}: {e}")
            item_span.record_exception(e)
            item_span.set_status(trace.StatusCode.ERROR, str(e))
            raise


def sqs_record_handler(record: SQSRecord) -> None:
    """Adapt Powertools SQS records to the device processor."""
    payload = parse_payload(record.body)
    process_device_logic(payload)


@traced_lambda(logger=logger)
def handler(event, context):
    """Route supported event sources to the appropriate processor."""
    records = event.get('Records', [])
    if not records:
        logger.debug("Received empty event")
        return {"statusCode": HTTP_OK}

    tag_root_span(records)

    logger.debug(f"Processing {len(records)} records.")
    first_record = records[0]

    if is_sqs_record(first_record):
        logger.info("Routing to SQS Batch Processor")
        return process_partial_response(
            event=event,
            record_handler=sqs_record_handler,
            processor=processor,
            context=context
        )

    if is_sns_record(first_record):
        logger.info("Routing to SNS Direct Processor")
        for record in records:
            payload = parse_payload(get_record_body(record))
            process_device_logic(payload)

        return {"statusCode": HTTP_OK, "body": SNS_SUCCESS_BODY}

    logger.warning("Unrecognized event source structure")
    return {"statusCode": HTTP_BAD_REQUEST}
