import base64
import json
import logging
import os

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk.resources import Resource

_global_logger_provider = None

class JsonFormatter(logging.Formatter):
    def format(self, record):
        span_context = trace.get_current_span().get_span_context()

        trace_id = None
        span_id = None

        if span_context.is_valid:
            trace_id = f"{span_context.trace_id:032x}"
            span_id = f"{span_context.span_id:016x}"

        log_obj = {
            "level": record.levelname,
            "message": record.getMessage(),
            "name": record.name,
            "trace_id": trace_id,
            "span_id": span_id,
        }

        log_obj = {k: v for k, v in log_obj.items() if v is not None}
        return json.dumps(log_obj)

def get_otel_log_handler(service_name: str) -> logging.Handler:
    global _global_logger_provider

    instance_id = os.environ.get("GRAFANA_INSTANCE_ID", "")
    api_token = os.environ.get("GRAFANA_API_TOKEN", "")
    endpoint_base = os.environ.get("GRAFANA_OTLP_ENDPOINT", "")

    if instance_id and api_token:
        auth_string = f"{instance_id}:{api_token}"
        encoded_auth = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
        headers = {"Authorization": f"Basic {encoded_auth}"}
    else:
        headers = {}

    log_endpoint = f"{endpoint_base}/v1/logs" if endpoint_base else "http://host.docker.internal:4318/v1/logs"

    resource = Resource.create({
        "service.name": service_name,
        "deployment.environment": "localstack"
    })

    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)

    _global_logger_provider = logger_provider

    log_exporter = OTLPLogExporter(
        endpoint=log_endpoint,
        headers=headers
    )

    log_processor = BatchLogRecordProcessor(
        log_exporter,
        schedule_delay_millis=1000,
        max_export_batch_size=512
    )

    logger_provider.add_log_record_processor(log_processor)
    otel_handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    otel_handler.setFormatter(JsonFormatter())
    return otel_handler

def flush_otel_logs():
    """Forces the batch processor to send remaining logs to Grafana immediately."""
    if _global_logger_provider and hasattr(_global_logger_provider, "force_flush"):
        _global_logger_provider.force_flush(timeout_millis=5000)