import base64
import os

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor

ADOT_EXTENSION_ENDPOINT = "http://localhost:4318"

_global_meter_provider = None


def _build_endpoint(base: str, path: str) -> str:
    if base.endswith("/"):
        return f"{base.rstrip('/')}{path}"
    return f"{base}{path}"


def _resolve_endpoint(path: str) -> str:
    instance_id = os.environ.get("GRAFANA_INSTANCE_ID", "")
    api_token = os.environ.get("GRAFANA_API_TOKEN", "")
    endpoint_base = os.environ.get("GRAFANA_OTLP_ENDPOINT", "")
    local_otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    if endpoint_base:
        return _build_endpoint(endpoint_base, path)
    elif local_otlp_endpoint:
        return _build_endpoint(local_otlp_endpoint, path)
    else:
        return _build_endpoint(ADOT_EXTENSION_ENDPOINT, path)


def _resolve_headers() -> dict:
    instance_id = os.environ.get("GRAFANA_INSTANCE_ID", "")
    api_token = os.environ.get("GRAFANA_API_TOKEN", "")
    if instance_id and api_token:
        auth_string = f"{instance_id}:{api_token}"
        encoded_auth = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
        return {"Authorization": f"Basic {encoded_auth}"}
    return {}


def init_tracer(service_name: str):
    headers = _resolve_headers()
    trace_endpoint = _resolve_endpoint("/v1/traces")

    resource = Resource.create({
        "service.name": service_name,
        "deployment.environment": "localstack"
    })

    sampling_ratio = float(os.environ.get("OTEL_TRACES_SAMPLER_RATIO", "1.0"))
    sampler = ParentBased(TraceIdRatioBased(sampling_ratio))

    provider = TracerProvider(resource=resource, sampler=sampler)

    exporter = OTLPSpanExporter(
        endpoint=trace_endpoint,
        headers=headers
    )

    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)

    BotocoreInstrumentor().instrument()

    _init_metrics(resource, headers, service_name)

    return trace.get_tracer(service_name)


def _init_metrics(resource: Resource, headers: dict, service_name: str): # type: ignore
    global _global_meter_provider

    metrics_endpoint = _resolve_endpoint("/v1/metrics")

    metric_exporter = OTLPMetricExporter(
        endpoint=metrics_endpoint,
        headers=headers
    )

    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=30_000
    )

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader]
    )

    metrics.set_meter_provider(meter_provider)
    _global_meter_provider = meter_provider

    _create_instrumentation_metrics(meter_provider.get_meter(service_name, "1.0"))


def _create_instrumentation_metrics(meter): # type: ignore
    meter.create_counter(
        name="lambda.invocations",
        description="Number of Lambda invocations",
        unit="1"
    )

    meter.create_counter(
        name="lambda.errors",
        description="Number of Lambda invocation errors",
        unit="1"
    )

    meter.create_histogram(
        name="lambda.duration",
        description="Lambda invocation duration in milliseconds",
        unit="ms"
    )

    meter.create_counter(
        name="messaging.messages_sent",
        description="Number of messages sent to SQS/SNS",
        unit="1"
    )

    meter.create_histogram(
        name="messaging.publish_duration",
        description="Duration of message publish operations in milliseconds",
        unit="ms"
    )


def flush_otel_metrics(timeout_millis: int = 30_000): # type: ignore
    if _global_meter_provider and hasattr(_global_meter_provider, "force_flush"):
        _global_meter_provider.force_flush(timeout_millis=timeout_millis)


def _init_metrics(resource: Resource, headers: dict, service_name: str):
    global _global_meter_provider

    metrics_endpoint = _resolve_endpoint("/v1/metrics")

    metric_exporter = OTLPMetricExporter(
        endpoint=metrics_endpoint,
        headers=headers
    )

    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=30_000
    )

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader]
    )

    metrics.set_meter_provider(meter_provider)
    _global_meter_provider = meter_provider

    _create_instrumentation_metrics(meter_provider.get_meter(service_name, "1.0"))


def _create_instrumentation_metrics(meter):
    meter.create_counter(
        name="lambda.invocations",
        description="Number of Lambda invocations",
        unit="1"
    )

    meter.create_counter(
        name="lambda.errors",
        description="Number of Lambda invocation errors",
        unit="1"
    )

    meter.create_histogram(
        name="lambda.duration",
        description="Lambda invocation duration in milliseconds",
        unit="ms"
    )

    meter.create_counter(
        name="messaging.messages_sent",
        description="Number of messages sent to SQS/SNS",
        unit="1"
    )

    meter.create_histogram(
        name="messaging.publish_duration",
        description="Duration of message publish operations in milliseconds",
        unit="ms"
    )


def flush_otel_metrics(timeout_millis: int = 30_000):
    if _global_meter_provider and hasattr(_global_meter_provider, "force_flush"):
        _global_meter_provider.force_flush(timeout_millis=timeout_millis)