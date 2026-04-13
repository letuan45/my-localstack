import logging
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk.resources import Resource

def get_otel_log_handler(service_name: str) -> logging.Handler:
    resource = Resource.create({
        "service.name": service_name,
        "deployment.environment": "localstack"
    })

    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)

    log_exporter = OTLPLogExporter(
        endpoint="http://host.docker.internal:4318/v1/logs"
    )

    log_processor = BatchLogRecordProcessor(
        log_exporter,
        schedule_delay_millis=1000,
        max_export_batch_size=512
    )

    logger_provider.add_log_record_processor(log_processor)

    return LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)