from services.lambda_a.config import logger, sns, sqs
import json


def get_queue_type(queue_url):
    assert queue_url is not None
    if ':sns:' in queue_url or queue_url.startswith('arn:aws:sns:'):
        return 'sns'
    else:
        return 'sqs'


def send_message(message: dict, queue_url: str):
    # Get context and inject traceparent into message attributes
    from common.inject import inject_trace
    carrier = inject_trace()

    attributes = {
        'traceparent': {
            'Type': 'String',
            'Value': carrier.get('traceparent', '')
        }
    }

    queue_type = get_queue_type(queue_url)

    if queue_type == 'sns':
        _attributes = {}
        for key, val in attributes.items():
            _attributes[key] = {
                'DataType': val['Type'],
                'StringValue': val['Value']
            }

        response = sns.publish(
            TopicArn=queue_url,
            Message=json.dumps(message),
            MessageAttributes=_attributes
        )
        logger.info(f"Event sent to SNS: {queue_url} - Trace: {carrier.get('traceparent')}")
    else:
        _attributes = {}
        for key, val in attributes.items():
            _attributes[key] = {
                'DataType': val['Type'],
                'StringValue': val['Value']
            }

        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message),
            MessageAttributes=_attributes
        )
        logger.info(f"Event sent to SQS: {queue_url} - Trace: {carrier.get('traceparent')}")

    return response