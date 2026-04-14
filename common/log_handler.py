import base64
import logging
import os
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk.resources import Resource

def get_otel_log_handler(service_name: str) -> logging.Handler:
    instance_id = os.environ.get("GRAFANA_INSTANCE_ID", "")
    api_token = os.environ.get("GRAFANA_API_TOKEN", "")
    endpoint_base = os.environ.get("GRAFANA_OTLP_ENDPOINT", "")

    if instance_id and api_token and endpoint_base:
        print("Using Grafana Cloud OTLP endpoint for tracing")

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

    return LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)