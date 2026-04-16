from opentelemetry import trace
from common.inject import inject_trace

from services.lambda_a.config import logger, sns, sqs
import json
tracer = trace.get_tracer(__name__)

def get_queue_type(queue_url):
    assert queue_url is not None
    if ':sns:' in queue_url or queue_url.startswith('arn:aws:sns:'):
        return 'sns'
    else:
        return 'sqs'


def send_message(message: dict, queue_url: str):
    with tracer.start_as_current_span("send_message", kind=trace.SpanKind.PRODUCER) as span:
        # Get context and inject traceparent into message attributes
        carrier = inject_trace()
        traceparent = carrier.get('traceparent')

        span.set_attribute("messaging.destination", queue_url)
        span.set_attribute("messaging.system", get_queue_type(queue_url))

        device_id = message.get("device_id")
        if device_id:
            span.set_attribute("device_id", device_id)

        device_imeis = message.get("device_imeis")
        if device_imeis:
            span.set_attribute("device_imeis", json.dumps(device_imeis))

        message_attributes = {}
        if traceparent:
            message_attributes['traceparent'] = {
                'DataType': 'String',
                'StringValue': traceparent
            }

        queue_type = get_queue_type(queue_url)

        try:
            if queue_type == 'sns':
                response = sns.publish(
                    TopicArn=queue_url,
                    Message=json.dumps(message),
                    MessageAttributes=message_attributes
                )
                logger.info(f"Event sent to SNS: {queue_url} - Trace: {carrier.get('traceparent')}")
            else:
                response = sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps(message),
                    MessageAttributes=message_attributes
                )
                logger.info(f"Event sent to SQS: {queue_url} - Trace: {carrier.get('traceparent')}")

            return response
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            logger.error(f"Failed to send message: {e}")
            raise e
