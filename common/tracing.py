from functools import wraps
import json

from opentelemetry import trace, propagate
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
from common.log_handler import flush_otel_logs

tracer = trace.get_tracer(__name__)


def extract_trace_context(record):
    try:
        traceparent = None

        if 'Sns' in record:
            traceparent = record['Sns'].get('MessageAttributes', {}).get('traceparent', {}).get('Value')
        elif 'messageAttributes' in record:
            traceparent = record.get("messageAttributes", {}).get("traceparent", {}).get("stringValue")

            if not traceparent and 'body' in record:
                try:
                    body = json.loads(record['body'])
                    if isinstance(body, dict) and body.get('Type') == 'Notification':
                        traceparent = body.get('MessageAttributes', {}).get('traceparent', {}).get('Value')
                except json.JSONDecodeError:
                    pass

        if traceparent:
            return propagate.extract({'traceparent': traceparent})
    except Exception as e:
        print(f"Tracing extraction failed: {e}")
    return None


def traced_lambda(logger=None):
    def decorator(handler_func):
        @wraps(handler_func)
        def wrapper(event, context):
            # 1. Create the Root Span
            parent_ctx = None
            links = []
            records = event.get("Records", [])

            if logger:
                logger.debug(f"[Tracing] Received event with {len(records)} records.")

            if records:
                if len(records) == 1:
                    parent_ctx = extract_trace_context(records[0])
                    if logger:
                        status = "Success" if parent_ctx else "Failed (Traceparent not found)"
                        logger.debug(f"[Tracing] Single-Record Strategy. Extracting Parent Context: {status}")
                else:
                    for record in records:
                        ctx = extract_trace_context(record)
                        if ctx:
                            span_ctx = trace.get_current_span(ctx).get_span_context()
                            if span_ctx.is_valid:
                                links.append(trace.Link(span_ctx))

                    if logger:
                        logger.debug(f"[Tracing] Batch-Records Strategy. Successfully extracted {len(links)}/{len(records)} Span Links.")
            else:
                if logger:
                    logger.debug("[Tracing] No records found in event. Starting span without parent context.")

            with tracer.start_as_current_span(
                name=f"lambda_handler:{handler_func.__name__}",
                context=parent_ctx,
                links=links if links else None,
                kind=trace.SpanKind.CONSUMER if records else trace.SpanKind.SERVER
            ) as span:
                span.set_attribute("faas.name", getattr(context, 'function_name', 'unknown_function'))
                span.set_attribute("faas.invocation_id", getattr(context, 'aws_request_id', 'unknown_id'))
                if records:
                    span.set_attribute("messaging.batch.message_count", len(records))

                # Append trace_id and span_id to logger if available
                if logger:
                    span_context = span.get_span_context()
                    trace_id = f"{span_context.trace_id:032x}" if span_context.is_valid else "None"
                    span_id = f"{span_context.span_id:016x}" if span_context.is_valid else "None"
                    logger.append_keys(trace_id=trace_id, span_id=span_id)
                    logger.debug(f"[Tracing] Starting handler with trace_id: {trace_id}")
                try:
                    return handler_func(event, context)
                finally:
                    # This ensures traces are exported even if the handler raises an Exception.
                    trace_provider = trace.get_tracer_provider()
                    if isinstance(trace_provider, SDKTracerProvider):
                        trace_provider.force_flush(timeout_millis=5000)
                    flush_otel_logs()

        return wrapper
    return decorator

