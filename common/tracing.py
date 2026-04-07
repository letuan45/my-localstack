from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider

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


def traced_lambda(handler_func):

    def wrapper(event, context):
        carrier = extract_carrier(event)
        parent_context = extract(carrier)

        with tracer.start_as_current_span(
            name=f"lambda_handler:{handler_func.__name__}",
            context=parent_context
        ) as span:
            span.set_attribute("faas.name", context.function_name)
            span.set_attribute("faas.invocation_id", context.aws_request_id)

            result = handler_func(event, context)

            provider = trace.get_tracer_provider()
            if isinstance(provider, SDKTracerProvider):
                provider.force_flush()

            return result
    return wrapper