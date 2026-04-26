import json
from opentelemetry import trace
from common.otel import init_tracer
from common.tracing import traced_lambda
from services.lambda_b.config import logger

from aws_lambda_powertools.utilities.batch import (
    BatchProcessor,
    EventType,
    process_partial_response
)
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord

tracer = init_tracer("lambda_b")
processor = BatchProcessor(event_type=EventType.SQS)


def parse_payload(raw_msg: str) -> dict:
    """
    Safely parses JSON, handling SNS envelopes and accidental double-serialization.
    """
    try:
        payload = json.loads(raw_msg)

        # Unwrap SNS Envelope if present
        if isinstance(payload, dict) and payload.get('Type') == 'Notification':
            payload = json.loads(payload.get('Message', '{}'))

        # Unwrap double-serialized JSON strings
        if isinstance(payload, str):
            payload = json.loads(payload)

        return payload if isinstance(payload, dict) else {}
    except (TypeError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to parse payload: {e}")
        return {}


def tag_root_span(records: list):
    """
    Aggressively extracts business data to tag the Root Span for Grafana visibility.
    """
    root_span = trace.get_current_span()
    if not root_span or not root_span.is_recording():
        return

    primary_device_id = None
    all_imeis = []

    for record in records:
        raw_msg = record.get('body') or record.get('Sns', {}).get('Message')
        if not raw_msg:
            continue

        payload = parse_payload(raw_msg)

        # Capture the first valid device_id as a flat string
        p_device_id = payload.get('device_id')
        if p_device_id and p_device_id != 'unknown_device' and not primary_device_id:
            primary_device_id = p_device_id

        if imeis := payload.get('device_imeis'):
            all_imeis.extend(imeis)

    # Set as a single string, exactly matching your requested format
    if primary_device_id:
        root_span.set_attribute("device_id", primary_device_id)

    root_span.set_attribute("device_imeis", json.dumps(all_imeis))


def process_device_logic(payload: dict):
    """
    Core business logic wrapped in a dedicated Child Span.
    """
    device_id = payload.get('device_id', 'unknown_device')
    device_imeis = payload.get('device_imeis', [])
    action = payload.get('action', 'unknown')

    with tracer.start_as_current_span(f"process_device:{device_id}") as item_span:
        item_span.set_attribute("device_id", device_id)
        item_span.set_attribute("device_imeis", json.dumps(device_imeis))
        item_span.set_attribute("action", action)

        try:
            logger.debug(f"Processing device {device_id} | IMEIs: {device_imeis}")

            if device_id == 'DEV_002':
                raise ValueError(f"Simulated error for device {device_id}")

            logger.info(f"Successfully processed device: {device_id}")

        except Exception as e:
            logger.error(f"Failed to process device {device_id}: {e}")
            item_span.record_exception(e)
            item_span.set_status(trace.StatusCode.ERROR, str(e))
            raise e


def sqs_record_handler(record: SQSRecord):
    """
    Adapter for SQS records (BatchProcessor uses SQSRecord objects).
    """
    payload = parse_payload(record.body)
    process_device_logic(payload)


@traced_lambda(logger=logger)
def handler(event, context):
    """
    Main Lambda entry point. Handles Root Span tagging and Event Routing.
    """
    records = event.get('Records', [])
    if not records:
        logger.debug("Received empty event")
        return {"statusCode": 200}

    # 1. Pre-process for tracing visibility
    tag_root_span(records)

    logger.debug(f"Processing {len(records)} records.")
    first_record = records[0]

    # 2. Route based on Event Source
    if first_record.get('eventSource') == 'aws:sqs':
        logger.info("Routing to SQS Batch Processor")
        return process_partial_response(
            event=event,
            record_handler=sqs_record_handler,
            processor=processor,
            context=context
        )

    elif first_record.get('EventSource') == 'aws:sns':
        logger.info("Routing to SNS Direct Processor")
        for record in records:
            raw_msg = record.get('Sns', {}).get('Message', '')
            payload = parse_payload(raw_msg)
            process_device_logic(payload)

        return {"statusCode": 200, "body": "SNS Processed successfully"}

    logger.warning("Unrecognized event source structure")
    return {"statusCode": 400}
