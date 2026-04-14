import base64
import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor

def init_tracer(service_name: str):
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

    trace_endpoint = f"{endpoint_base}/v1/traces" if endpoint_base else "http://host.docker.internal:4318/v1/traces"

    resource = Resource.create({
        "service.name": service_name,
        "deployment.environment": "localstack"
    })

    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(
        endpoint=trace_endpoint,
        headers=headers
    )

    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)

    BotocoreInstrumentor().instrument()

    return trace.get_tracer(service_name)