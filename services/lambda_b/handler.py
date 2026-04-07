import json
import logging

from common.otel import init_tracer
from common.tracing import traced_lambda
from common import local_http
from common.log_handler import OtelLogHandler


logger = logging.getLogger()
logger.setLevel(logging.INFO)

logger.addHandler(OtelLogHandler())

tracer = init_tracer("lambda_b")


@traced_lambda
def handler(event, context):
    logger.info(f"Lambda b received event: {json.dumps(event)}")

    for record in event.get("Records", []):
        body = json.loads(record.get("body", "{}"))

        logger.info(f"Processing message: {body}")

    return {
        "statusCode": 200
    }
