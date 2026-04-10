from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor

def init_tracer(service_name: str):
    resource = Resource.create({
        "service.name": service_name,
        "deployment.environment": "localstack"
    })

    provider = TracerProvider(resource=resource)

    # Jaeger OTLP HTTP endpoint
    exporter = OTLPSpanExporter(
        endpoint="http://host.docker.internal:4318/v1/traces"
    )

    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)

    BotocoreInstrumentor().instrument()

    return trace.get_tracer(service_name)