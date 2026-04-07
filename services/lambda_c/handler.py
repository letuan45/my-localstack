import json

from common.otel import init_tracer
from common.tracing import traced_lambda, traced_record

from services.lambda_c.config import logger

tracer = init_tracer("lambda_c")


@traced_lambda
def handler(event, context):
    logger.info(f"Lambda c received event: {json.dumps(event)}")
    records = event.get("Records", [])

    for record in records:
        with traced_record(record):
            if 'Sns' in record:
                raw_data = record['Sns'].get('Message', '{}')
            else:
                raw_data = record.get('body', '{}')

            body = json.loads(raw_data)
            logger.info(f"Processing message: {body}")

    return {
        "statusCode": 200
    }
