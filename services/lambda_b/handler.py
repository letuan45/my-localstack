import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    logger.info(f"Lambda b received event: {json.dumps(event)}")

    for record in event.get("Records", []):
        body = json.loads(record.get("body", "{}"))

        logger.info(f"Processing message: {body}")

    return {
        "statusCode": 200
    }