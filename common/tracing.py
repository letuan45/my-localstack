from opentelemetry import trace, propagate
# from opentelemetry.propagate import extract
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
from opentelemetry._logs import get_logger_provider
from opentelemetry.sdk._logs import LoggerProvider as SDKLoggerProvider

tracer = trace.get_tracer(__name__)


def extract_carrier(event):
    try:
        if "Records" in event:
            record = event["Records"][0]
            attrs = record.get("messageAttributes", {})

            if "traceparent" in attrs:
                return {"traceparent": attrs["traceparent"]["stringValue"]}
    except Exception as e:
        print(f"No trace context found in event: {e}")
    return {}


def get_context_from_record(record):
    try:
        if 'Sns' in record:
            attrs = record['Sns'].get('MessageAttributes', {})
            traceparent = attrs.get('traceparent', {}).get('Value')
            return propagate.extract({'traceparent': traceparent})

        elif 'messageAttributes' in record:
            attrs = record.get("messageAttributes", {})
            traceparent = attrs.get("traceparent", {}).get("stringValue")
            return propagate.extract({'traceparent': traceparent})
    except Exception as e:
        print(f"Tracing extraction failed: {e}")
    return None


def traced_lambda(handler_func):
    def wrapper(event, context):
        # Create a new span for the Lambda invocation
        with tracer.start_as_current_span(
            name=f"lambda_handler:{handler_func.__name__}"
        ) as span:
            span.set_attribute("faas.name", getattr(context, 'function_name', 'unknown_function'))
            span.set_attribute("faas.invocation_id", getattr(context, 'aws_request_id', 'unknown_id'))

            result = handler_func(event, context)

            # 1. Force flush TRACE data
            trace_provider = trace.get_tracer_provider()
            if isinstance(trace_provider, SDKTracerProvider):
                trace_provider.force_flush()

            log_provider = get_logger_provider()
            if isinstance(log_provider, SDKLoggerProvider):
                log_provider.force_flush()

            return result
    return wrapper


def traced_record(record):
    """
    Context Manager to create a span for processing a single SQS record
    extracting trace context from the record's attributes.
    """
    parent_ctx = get_context_from_record(record)
    tracer = trace.get_tracer(__name__)

    return tracer.start_as_current_span("process_record", context=parent_ctx)
