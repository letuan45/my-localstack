import json
from opentelemetry import trace
from common.otel import init_tracer
from common.tracing import traced_lambda
from services.lambda_c.config import logger

from aws_lambda_powertools.utilities.batch import (
    BatchProcessor,
    EventType,
    process_partial_response
)
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord

tracer = init_tracer("lambda_c")
processor = BatchProcessor(event_type=EventType.SQS)


def process_device_logic(body: dict):
    device_id = body.get('device_id', 'unknown_device')
    device_imeis = body.get('device_imeis', [])
    action = body.get('action', 'unknown')

    with tracer.start_as_current_span(f"process_device:{device_id}") as item_span:
        item_span.set_attribute("device_id", device_id)
        item_span.set_attribute("device_imeis", json.dumps(device_imeis))
        item_span.set_attribute("action", action)

        try:
            logger.debug(f"Processing device id {device_id} with IMEIs: {device_imeis}")

            if device_id == 'DEV_002':
                logger.error(f"Error with device {device_id}")
                raise ValueError(f"Error with device {device_id}")

            logger.info(f"Processing completed for device: {device_id}")

        except Exception as e:
            item_span.record_exception(e)
            item_span.set_status(trace.StatusCode.ERROR, str(e))
            raise e

def sqs_record_handler(record: SQSRecord):
    body = json.loads(record.body)
    process_device_logic(body)

@traced_lambda(logger=logger)
def handler(event, context):
    records = event.get('Records', [])
    if not records:
        logger.debug("Received empty event")
        return {"statusCode": 200}

    logger.debug(f"EVENT {len(records)} records.")
    first_record = records[0]

    if 'eventSource' in first_record and first_record['eventSource'] == 'aws:sqs':
        logger.info("Routing to SQS Batch Processor")
        return process_partial_response(
            event=event,
            record_handler=sqs_record_handler,
            processor=processor,
            context=context
        )

    elif 'EventSource' in first_record and first_record['EventSource'] == 'aws:sns':
        logger.info("Routing to SNS Direct Processor")
        for record in records:
            raw_message = record['Sns']['Message']
            body = json.loads(raw_message)
            process_device_logic(body)
        return {"statusCode": 200, "body": "SNS Processed"}

    else:
        logger.warning("Unrecognized event source structure")
        return {"statusCode": 400}
