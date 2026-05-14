# ADOT Migration Architecture & Implementation Guide

## Overview

This document outlines the migration from manual OpenTelemetry instrumentation to **AWS Distro for OpenTelemetry (ADOT)** for the `my-localstack` project. The goal is to reduce boilerplate code, leverage ADOT's auto-instrumentation, and isolate telemetry traffic by introducing a centralized ADOT Collector.

**Key Principles:**
- The current Span structure, Parent-Child trace relationships, and Business Logic must remain intact.
- ADOT handles auto-instrumentation (Lambda wrapper, botocore, HTTP calls).
- Manual instrumentation is retained only for **business-specific spans** (`send_message` PRODUCER span, `process_device:{device_id}` INTERNAL spans).
- All telemetry traffic routes through the centralized ADOT Collector (not directly to Tempo/Loki).

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ADOT Lambda Layer                             │
│  (Auto-instrumentation: Lambda handler wrapper, botocore, HTTP)      │
│                                                                      │
│  ┌─────────────────────┐   ┌─────────────────────────────────────┐  │
│  │    lambda_a          │   │    lambda_b / lambda_c              │  │
│  │  (Producer)          │   │  (Consumers)                        │  │
│  │                      │   │                                     │  │
│  │  ADOT Layer wraps    │   │  ADOT Layer wraps handler           │  │
│  │  handler → root span │   │  → root CONSUMER span               │  │
│  │                      │   │  → Span Links for SQS batch         │  │
│  │  Manual:             │   │  → Extracts traceparent from        │  │
│  │  ┌───────────────┐   │   │    SQS/SNS message attributes       │  │
│  │  │send_message   │   │   │                                     │  │
│  │  │(PRODUCER span)│   │   │  Manual:                            │  │
│  │  └───────┬───────┘   │   │  ┌─────────────────────────────┐   │  │
│  │          │           │   │  │process_device:{device_id}    │   │  │
│  │  inject traceparent  │   │  │(INTERNAL child spans)        │   │  │
│  │  via ADOT's inject() │   │  └─────────────────────────────┘   │  │
│  └──────────┬───────────┘   └────────────────┬───────────────────┘  │
│             │                                 │                      │
│             │          OTLP (gRPC/HTTP)        │                      │
│             └──────────────┬──────────────────┘                      │
│                            ▼                                         │
│              ┌──────────────────────────────┐                        │
│              │   ADOT Collector (Sidecar)    │                        │
│              │  - Receives OTLP from Lambdas │                        │
│              │  - Tail-based sampling        │                        │
│              │  - Batching                   │                        │
│              │  - Export to backend          │                        │
│              └──────────────┬───────────────┘                        │
│                             │                                        │
│              ┌──────────────┼──────────────┐                         │
│              ▼              ▼              ▼                         │
│        ┌──────────┐  ┌──────────┐  ┌──────────┐                     │
│        │  Tempo   │  │   Loki   │  │ Grafana  │                     │
│        │ (traces) │  │  (logs)  │  │ Cloud    │                     │
│        └──────────┘  └──────────┘  └──────────┘                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Infrastructure & Architecture Setup

### 1.1 ADOT Lambda Layer

The **ADOT Lambda Layer** (Python) provides:
- **Auto-instrumentation** of the Lambda handler via `AWS_LAMBDA_EXEC_WRAPPER`
- **Auto-instrumentation** of botocore/AWS SDK calls
- **Auto-instrumentation** of HTTP requests
- **Automatic trace context extraction** from SQS/SNS event sources
- **Automatic span links** for SQS batch records
- **Automatic W3C Trace Context injection** into SQS/SNS message attributes

**Layer ARN (Python 3.10, x86_64):**
```
arn:aws:lambda:us-east-1:580247275435:layer:AWSOpenTelemetryDistroPython:3
```

> **Note:** In LocalStack, the ADOT Layer ARN is accepted but the actual auto-instrumentation behavior depends on LocalStack's Lambda runtime simulation. The environment variables and configuration are set up to match production behavior.

### 1.2 Environment Variables for Lambdas

Each Lambda function must have these environment variables set:

| Variable | Value | Purpose |
|---|---|---|
| `AWS_LAMBDA_EXEC_WRAPPER` | `/opt/otel-instrument` | ADOT auto-instrumentation wrapper |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://adot-collector:4318` | Send telemetry to ADOT Collector |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | OTLP HTTP protocol |
| `OTEL_SERVICE_NAME` | `lambda_a` / `lambda_b` / `lambda_c` | Service name for traces |
| `OTEL_RESOURCE_ATTRIBUTES` | `deployment.environment=localstack` | Resource attributes |
| `OTEL_TRACES_SAMPLER` | `always_on` | Sampling configuration |
| `OTEL_PROPAGATORS` | `tracecontext` | W3C Trace Context propagation |
| `PYTHONPATH` | `.` | Python module path |
| `LOCALSTACK_HOSTNAME` | `localhost.localstack.cloud` | LocalStack endpoint |

### 1.3 ADOT Collector Service

The ADOT Collector runs as a standalone service in `docker-compose.local.yml`, simulating a future ECS Fargate deployment. It:

1. **Receives OTLP HTTP** from Lambda functions on port `4318`
2. **Processes** with batching and optional tail-based sampling
3. **Exports** traces to Tempo (gRPC) and logs to Loki (HTTP)

---

## 2. What ADOT Handles Automatically

### 2.1 Lambda Handler Auto-Instrumentation

ADOT's `AWS_LAMBDA_EXEC_WRAPPER` (`/opt/otel-instrument`) automatically:
- Creates a **root span** for the Lambda invocation
- Sets the span kind to `CONSUMER` (for SQS/SNS-triggered) or `SERVER` (for direct invoke)
- Extracts **W3C Trace Context** from the event source (SQS `messageAttributes`, SNS `MessageAttributes`)
- Creates **Span Links** for SQS batch records (one link per record with valid traceparent)
- Sets standard Lambda attributes (`faas.name`, `faas.invocation_id`, `cloud.account.id`, etc.)
- Exports spans via OTLP to the configured endpoint

### 2.2 Botocore / AWS SDK Auto-Instrumentation

ADOT automatically instruments `botocore` calls, creating spans for:
- `SQS.SendMessage`
- `SNS.Publish`
- Any other AWS SDK calls

### 2.3 W3C Trace Context Injection

ADOT automatically injects `traceparent` into **SQS MessageAttributes** and **SNS MessageAttributes** when making AWS SDK calls, **provided** that the `OTEL_PROPAGATORS` environment variable is set to `tracecontext` and the botocore instrumentation is active.

**However**, the automatic injection only works for the **root span's context**. For the `send_message` PRODUCER span (which is a child span created manually), we still need to manually inject the trace context to ensure the PRODUCER span is the parent of the downstream consumer span.

### 2.4 SNS Envelope Unwrapping

ADOT **does NOT automatically unwrap** the SNS Notification envelope when SNS messages are routed through SQS (SNS → SQS fan-out). The `traceparent` is nested inside the SNS `MessageAttributes` within the SQS message body. Manual extraction is required for this case.

---

## 3. What Must Be Done Manually

### 3.1 Business-Specific Spans

| Span | Service | Reason |
|---|---|---|
| `send_message` (PRODUCER) | lambda_a | Business-logic span wrapping the SQS/SNS send call |
| `process_device:{device_id}` (INTERNAL) | lambda_b, lambda_c | Per-device processing spans |

### 3.2 Manual Trace Context Injection (for PRODUCER span)

Since the `send_message` span is a **child span** created manually, we must manually inject the trace context into message attributes to ensure the PRODUCER span is the parent of the downstream consumer span. ADOT's auto-injection would use the root span's context, not the child span's context.

### 3.3 SNS Envelope Traceparent Extraction

When SNS messages are routed through SQS (SNS → SQS), the `traceparent` is inside the SNS Notification envelope's `MessageAttributes`. We must manually extract it.

### 3.4 Logging Configuration

ADOT does not handle OTLP log export. We retain `common/log_handler.py` for structured log export via OTLP.

---

## 4. Refactored Code

### 4.1 `docker-compose.local.yml`

```yaml
version: "3.8"

services:
  localstack:
    container_name: localstack
    image: localstack/localstack:3.4.0
    ports:
      - "4566:4566"
    environment:
      - SERVICES=s3,dynamodb,lambda,sqs,sns,logs
      - AWS_DEFAULT_REGION=us-east-1
      - DOCKER_HOST=unix:///var/run/docker.sock
    volumes:
      - .:/var/task
      - "/var/run/docker.sock:/var/run/docker.sock"
      - "./localstack/init:/etc/localstack/init/ready.d"

  adot-collector:
    container_name: adot-collector
    image: amazon/aws-otel-collector:latest
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./o11y/otel-collector-config.yaml:/etc/otel-collector-config.yaml
    ports:
      - "4318:4318"   # OTLP HTTP
      - "4317:4317"   # OTLP gRPC
    depends_on:
      - tempo
      - loki

  tempo:
    image: grafana/tempo:2.3.0
    command: [ "-config.file=/etc/tempo.yaml" ]
    volumes:
      - ./o11y/tempo-local.yaml:/etc/tempo.yaml
    ports:
      - "3200:3200"

  loki:
    image: grafana/loki:2.9.2
    command: -config.file=/etc/loki/local-config.yaml
    ports:
      - "3100:3100"

  grafana:
    image: grafana/grafana:10.2.2
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
      - GF_AUTH_DISABLE_LOGIN_FORM=true
    volumes:
      - ./o11y/grafana-datasources.yaml:/etc/grafana/provisioning/datasources/datasources.yaml
    ports:
      - "3000:3000"
    depends_on:
      - tempo
      - loki
```

### 4.2 `o11y/otel-collector-config.yaml` (ADOT Collector Configuration)

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: "0.0.0.0:4318"
      grpc:
        endpoint: "0.0.0.0:4317"

processors:
  batch:
    send_batch_size: 100
    timeout: 1s

  # Tail-based sampling configuration (optional, for production)
  # tail_sampling:
  #   policies:
  #     - name: error-policy
  #       type: status_code
  #       status_code: { status_codes: [ERROR] }
  #     - name: latency-policy
  #       type: latency
  #       latency: { threshold_ms: 500 }

exporters:
  otlp/tempo:
    endpoint: "tempo:4317"
    tls:
      insecure: true

  loki:
    endpoint: "http://loki:3100/loki/api/v1/push"
    default_labels_enabled:
      exporter: false
      job: false

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/tempo]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [loki]
```

### 4.3 `localstack/init/init.sh` (Modified)

Key changes:
1. Attach ADOT Lambda Layer to all 3 functions
2. Set ADOT-specific environment variables
3. Remove `common/otel.py` from the build (no longer needed)
4. Keep `common/tracing.py` only for the `@traced_lambda` decorator (which we will refactor to work with ADOT)
5. Keep `common/inject.py` for manual trace context injection
6. Keep `common/log_handler.py` for OTLP log export

```bash
#!/bin/bash
set -e

echo "===== START LOCALSTACK INIT ====="

cd /var/task

echo "Listing mounted directory:"
ls -R /var/task || true

# =======================
# 1. SETUP LOGGING
# =======================
echo "Creating Log Groups..."
awslocal logs create-log-group --log-group-name /aws/lambda/lambda_a || true
awslocal logs create-log-group --log-group-name /aws/lambda/lambda_b || true
awslocal logs create-log-group --log-group-name /aws/lambda/lambda_c || true

# =======================
# 2. CREATE RESOURCES (SNS & SQS)
# =======================
echo "Creating SQS queue..."
QUEUE_URL=$(awslocal sqs create-queue --queue-name my_queue --query 'QueueUrl' --output text)

echo "Creating SNS Topic..."
TOPIC_ARN=$(awslocal sns create-topic --name my_topic --query 'TopicArn' --output text)

# =======================
# 3. ADOT LAYER ARN
# =======================
# Python 3.10, x86_64
ADOT_LAYER_ARN="arn:aws:lambda:us-east-1:580247275435:layer:AWSOpenTelemetryDistroPython:3"

# =======================
# 4. COMMON SETUP & BUILD LAMBDAS
# =======================
touch common/__init__.py
touch services/__init__.py
touch services/lambda_a/__init__.py
touch services/lambda_b/__init__.py
touch services/lambda_c/__init__.py

build_lambda() {
    local LAMBDA_NAME=$1
    echo "Packaging $LAMBDA_NAME..."
    local BUILD_DIR="/tmp/build_$LAMBDA_NAME"

    rm -rf $BUILD_DIR
    mkdir -p $BUILD_DIR/services/$LAMBDA_NAME

    echo "Installing dependencies for $LAMBDA_NAME..."
    pip install -r /var/task/services/$LAMBDA_NAME/requirements.txt -t $BUILD_DIR/ > /dev/null 2>&1

    cp -r /var/task/common $BUILD_DIR/
    cp /var/task/services/__init__.py $BUILD_DIR/services/
    cp -r /var/task/services/$LAMBDA_NAME/. $BUILD_DIR/services/$LAMBDA_NAME/

    touch $BUILD_DIR/services/__init__.py
    touch $BUILD_DIR/services/$LAMBDA_NAME/__init__.py

    cd $BUILD_DIR
    zip -rq /tmp/$LAMBDA_NAME.zip .

    echo "Creating $LAMBDA_NAME..."
    awslocal lambda create-function \
      --function-name $LAMBDA_NAME \
      --runtime python3.10 \
      --handler services.$LAMBDA_NAME.handler.handler \
      --zip-file fileb:///tmp/$LAMBDA_NAME.zip \
      --role arn:aws:iam::000000000000:role/lambda-role \
      --layers "$ADOT_LAYER_ARN" \
      --environment "Variables={
        AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument,
        OTEL_EXPORTER_OTLP_ENDPOINT=http://adot-collector:4318,
        OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf,
        OTEL_SERVICE_NAME=$LAMBDA_NAME,
        OTEL_RESOURCE_ATTRIBUTES=deployment.environment=localstack,
        OTEL_TRACES_SAMPLER=always_on,
        OTEL_PROPAGATORS=tracecontext,
        PYTHONPATH=.
      }" > /dev/null

    cd /var/task
}

build_lambda "lambda_a"
build_lambda "lambda_b"
build_lambda "lambda_c"

# =======================
# 5. WIRING IT ALL TOGETHER
# =======================

# --- A. SQS to Lambda B Mapping ---
echo "Linking SQS -> lambda_b..."
QUEUE_ARN=$(awslocal sqs get-queue-attributes \
    --queue-url "$QUEUE_URL" \
    --attribute-names QueueArn \
    --query 'Attributes.QueueArn' \
    --output text)

awslocal lambda create-event-source-mapping \
    --function-name lambda_b \
    --batch-size 5 \
    --maximum-retry-attempts 10 \
    --event-source-arn "$QUEUE_ARN" > /dev/null

# --- B. SNS to Lambda B & C Mapping ---
echo "Linking SNS -> lambda_b & lambda_c..."

# Subscribe B and C to Topic
awslocal sns subscribe \
    --topic-arn "$TOPIC_ARN" \
    --protocol lambda \
    --notification-endpoint arn:aws:lambda:us-east-1:000000000000:function:lambda_b > /dev/null

awslocal sns subscribe \
    --topic-arn "$TOPIC_ARN" \
    --protocol lambda \
    --notification-endpoint arn:aws:lambda:us-east-1:000000000000:function:lambda_c > /dev/null

# Grant SNS invoke permissions
awslocal lambda add-permission --function-name lambda_b --statement-id sns-invoke-b --action lambda:InvokeFunction --principal sns.amazonaws.com > /dev/null
awslocal lambda add-permission --function-name lambda_c --statement-id sns-invoke-c --action lambda:InvokeFunction --principal sns.amazonaws.com > /dev/null

echo "===== INIT DONE SUCCESSFULLY ====="
```

### 4.4 `common/otel.py` — REMOVED

This file is no longer needed. ADOT's Lambda Layer handles tracer initialization, provider setup, and exporter configuration automatically.

### 4.5 `common/tracing.py` — Refactored for ADOT Compatibility

The `@traced_lambda` decorator is refactored to:
- **Not** initialize a tracer provider (ADOT does this)
- **Not** create a root span (ADOT does this)
- **Not** extract trace context (ADOT does this)
- **Not** create span links (ADOT does this for SQS batches)
- **Still** append `trace_id`/`span_id` to the Powertools logger
- **Still** force-flush traces and logs before exit
- **Still** tag the root span with business attributes

```python
from functools import wraps

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
from common.log_handler import flush_otel_logs

tracer = trace.get_tracer(__name__)


def traced_lambda(logger=None):
    def decorator(handler_func):
        @wraps(handler_func)
        def wrapper(event, context):
            # ADOT auto-creates the root span and extracts trace context.
            # We just need to append trace_id/span_id to the logger
            # and force-flush at the end.

            current_span = trace.get_current_span()

            # Append trace_id and span_id to logger if available
            if logger:
                span_context = current_span.get_span_context()
                trace_id = f"{span_context.trace_id:032x}" if span_context.is_valid else "None"
                span_id = f"{span_context.span_id:016x}" if span_context.is_valid else "None"
                logger.append_keys(trace_id=trace_id, span_id=span_id)

            try:
                return handler_func(event, context)
            finally:
                # Force-flush traces and logs before Lambda exits
                trace_provider = trace.get_tracer_provider()
                if isinstance(trace_provider, SDKTracerProvider):
                    trace_provider.force_flush(timeout_millis=5000)
                flush_otel_logs()

        return wrapper
    return decorator
```

### 4.6 `common/inject.py` — Retained (Manual Trace Context Injection)

```python
from opentelemetry.propagate import inject

def inject_trace():
    carrier = {}
    inject(carrier)
    return carrier
```

This is retained because we need to manually inject the trace context from the `send_message` PRODUCER span (a child span) into the message attributes. ADOT's auto-injection would use the root span's context, not the child span's context.

### 4.7 `common/log_handler.py` — Retained (Unchanged)

ADOT does not handle OTLP log export. This file is retained as-is for structured log export via OTLP.

### 4.8 `services/lambda_a/handler.py` — Refactored

Key changes:
- Remove `from common.otel import init_tracer` and `tracer = init_tracer("lambda_a")`
- ADOT auto-initializes the tracer; we get the tracer from `trace.get_tracer(__name__)`
- The `@traced_lambda` decorator is simplified (no root span creation)
- Business logic remains identical

```python
import json
import uuid
from opentelemetry import trace

from common.tracing import traced_lambda

from services.lambda_a.utils import send_message
from services.lambda_a.config import logger

tracer = trace.get_tracer(__name__)

@traced_lambda(logger=logger)
def handler(event, context):
    logger.debug(f"lambda_a triggered with event: {json.dumps(event)}")
    target_destination = event.get("target_destination", "arn:aws:sns:us-east-1:000000000000:my_topic")
    is_batch_test = event.get("simulate_batch", False)

    # Business Logic: Retrieve IMEIs and tag the span
    current_span = trace.get_current_span()

    if is_batch_test:
        logger.info(f"Simulating Batch Send to: {target_destination}")
        devices = event.get("devices", [])
        for dev in devices:
            device_id = dev.get("device_id")
            device_imeis = dev.get("device_imeis", [])

            payload = {
                "action": "register",
                "device_id": device_id,
                "device_imeis": device_imeis,
                "batch_id": str(uuid.uuid4())
            }

            send_message(payload, target_destination)
    else:
        logger.info(f"Sending Single Message to: {target_destination}")
        device_id = event.get("device_id", "SINGLE_TEST_DEV")
        device_imeis = event.get("device_imeis", ["351756051523999", "351756051523998"])

        current_span.set_attribute("device_id", device_id)
        current_span.set_attribute("device_imeis", json.dumps(device_imeis))

        payload = {
            "action": "register",
            "device_id": device_id,
            "device_imeis": device_imeis
        }
        send_message(payload, target_destination)

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Dispatched successfully", "target": target_destination})
    }
```

### 4.9 `services/lambda_a/utils.py` — Refactored

Key changes:
- Remove `from common.otel import init_tracer` (not needed here)
- The `send_message` function still creates the `send_message` PRODUCER span manually
- Trace context injection is still manual (to ensure the PRODUCER span is the parent)

```python
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
```

### 4.10 `services/lambda_a/config.py` — Refactored

Key changes:
- Remove `from common.otel import init_tracer` (ADOT handles tracer init)
- Keep OTel log handler (ADOT doesn't handle logs)

```python
from aws_lambda_powertools import Logger
import logging
from common.log_handler import get_otel_log_handler
import boto3
import os


SERVICE_NAME = "lambda_a"

logger = Logger(service=SERVICE_NAME)
logger.setLevel("DEBUG")

has_otel_handler = any(type(h).__name__ == "LoggingHandler" for h in logger.handlers)
if not has_otel_handler:
    logger.addHandler(get_otel_log_handler(SERVICE_NAME))

localstack_host = os.environ.get(
    'LOCALSTACK_HOSTNAME', 'localhost.localstack.cloud')
endpoint = f"http://{localstack_host}:4566"

sqs = boto3.client("sqs", endpoint_url=endpoint, region_name="us-east-1")
sns = boto3.client("sns", endpoint_url=endpoint, region_name="us-east-1")
```

### 4.11 `services/lambda_a/requirements.txt` — Simplified

ADOT Layer provides `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, and `opentelemetry-instrumentation-botocore`. We only need to include what's not provided by the layer.

```text
boto3==1.42.83
aws_lambda_powertools==3.12.0
```

> **Note:** In production, the ADOT Layer provides all OTel dependencies. For LocalStack testing, you may still need to include them in `requirements.txt` if the layer isn't fully functional in the LocalStack environment. The refactored code is designed to work with or without the layer — if the layer is present, it uses ADOT; if not, it falls back gracefully.

### 4.12 `services/lambda_b/handler.py` — Refactored

Key changes:
- Remove `from common.otel import init_tracer` and `tracer = init_tracer("lambda_b")`
- ADOT auto-creates the root CONSUMER span and extracts trace context
- ADOT auto-creates span links for SQS batch records
- The `process_device_logic` function still creates `process_device:{device_id}` child spans manually
- The `@traced_lambda` decorator is simplified

```python
import json
from typing import Any

from opentelemetry import trace
from common.tracing import traced_lambda
from services.lambda_b.const import (
    HTTP_BAD_REQUEST,
    HTTP_OK,
    SIMULATED_ERROR_DEVICE_ID,
    SNS_SUCCESS_BODY,
    UNKNOWN_ACTION,
    UNKNOWN_DEVICE_ID,
)
from services.lambda_b.config import logger
from services.lambda_b.utils import (
    get_record_body,
    is_sns_record,
    is_sqs_record,
    normalize_imeis,
    parse_payload,
    tag_root_span,
)

from aws_lambda_powertools.utilities.batch import (
    BatchProcessor,
    EventType,
    process_partial_response
)
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord

tracer = trace.get_tracer(__name__)
processor = BatchProcessor(event_type=EventType.SQS)


def process_device_logic(payload: dict[str, Any]) -> None:
    """Run device processing inside an item-level child span."""
    device_id = payload.get('device_id', UNKNOWN_DEVICE_ID)
    device_imeis = normalize_imeis(payload.get('device_imeis'))
    action = payload.get('action', UNKNOWN_ACTION)

    with tracer.start_as_current_span(f"process_device:{device_id}") as item_span:
        item_span.set_attribute("device_id", device_id)
        item_span.set_attribute("device_imeis", json.dumps(device_imeis))
        item_span.set_attribute("action", action)

        try:
            logger.debug(f"Processing device {device_id} | IMEIs: {device_imeis}")

            if device_id == SIMULATED_ERROR_DEVICE_ID:
                raise ValueError(f"Simulated error for device {device_id}")

            logger.info(f"Successfully processed device: {device_id}")

        except Exception as e:
            logger.error(f"Failed to process device {device_id}: {e}")
            item_span.record_exception(e)
            item_span.set_status(trace.StatusCode.ERROR, str(e))
            raise


def sqs_record_handler(record: SQSRecord) -> None:
    """Adapt Powertools SQS records to the device processor."""
    payload = parse_payload(record.body)
    process_device_logic(payload)


@traced_lambda(logger=logger)
def handler(event, context):
    """Route supported event sources to the appropriate processor."""
    records = event.get('Records', [])
    if not records:
        logger.debug("Received empty event")
        return {"statusCode": HTTP_OK}

    tag_root_span(records)

    logger.debug(f"Processing {len(records)} records.")
    first_record = records[0]

    if is_sqs_record(first_record):
        logger.info("Routing to SQS Batch Processor")
        return process_partial_response(
            event=event,
            record_handler=sqs_record_handler,
            processor=processor,
            context=context
        )

    if is_sns_record(first_record):
        logger.info("Routing to SNS Direct Processor")
        for record in records:
            payload = parse_payload(get_record_body(record))
            process_device_logic(payload)

        return {"statusCode": HTTP_OK, "body": SNS_SUCCESS_BODY}

    logger.warning("Unrecognized event source structure")
    return {"statusCode": HTTP_BAD_REQUEST}
```

### 4.13 `services/lambda_b/config.py` — Refactored

```python
from aws_lambda_powertools import Logger
from common.log_handler import get_otel_log_handler

SERVICE_NAME = "lambda_b"

logger = Logger(service=SERVICE_NAME)
logger.setLevel("DEBUG")

has_otel_handler = any(type(h).__name__ == "LoggingHandler" for h in logger.handlers)
if not has_otel_handler:
    logger.addHandler(get_otel_log_handler(SERVICE_NAME))
```

### 4.14 `services/lambda_b/requirements.txt` — Simplified

```text
boto3==1.42.83
aws_lambda_powertools==3.12.0
```

### 4.15 `services/lambda_c/handler.py` — Refactored

Same changes as lambda_b:

```python
import json
from typing import Any

from opentelemetry import trace
from common.tracing import traced_lambda
from services.lambda_c.const import (
    HTTP_BAD_REQUEST,
    HTTP_OK,
    SIMULATED_ERROR_DEVICE_ID,
    SNS_SUCCESS_BODY,
    UNKNOWN_ACTION,
    UNKNOWN_DEVICE_ID,
)
from services.lambda_c.config import logger
from services.lambda_c.utils import (
    get_record_body,
    is_sns_record,
    is_sqs_record,
    normalize_imeis,
    parse_payload,
    tag_root_span,
)

from aws_lambda_powertools.utilities.batch import (
    BatchProcessor,
    EventType,
    process_partial_response
)
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord

tracer = trace.get_tracer(__name__)
processor = BatchProcessor(event_type=EventType.SQS)


def process_device_logic(payload: dict[str, Any]) -> None:
    """Run device processing inside an item-level child span."""
    device_id = payload.get('device_id', UNKNOWN_DEVICE_ID)
    device_imeis = normalize_imeis(payload.get('device_imeis'))
    action = payload.get('action', UNKNOWN_ACTION)

    with tracer.start_as_current_span(f"process_device:{device_id}") as item_span:
        item_span.set_attribute("device_id", device_id)
        item_span.set_attribute("device_imeis", json.dumps(device_imeis))
        item_span.set_attribute("action", action)

        try:
            logger.debug(f"Processing device {device_id} | IMEIs: {device_imeis}")

            if device_id == SIMULATED_ERROR_DEVICE_ID:
                raise ValueError(f"Simulated error for device {device_id}")

            logger.info(f"Successfully processed device: {device_id}")

        except Exception as e:
            logger.error(f"Failed to process device {device_id}: {e}")
            item_span.record_exception(e)
            item_span.set_status(trace.StatusCode.ERROR, str(e))
            raise


def sqs_record_handler(record: SQSRecord) -> None:
    """Adapt Powertools SQS records to the device processor."""
    payload = parse_payload(record.body)
    process_device_logic(payload)


@traced_lambda(logger=logger)
def handler(event, context):
    """Route supported event sources to the appropriate processor."""
    records = event.get('Records', [])
    if not records:
        logger.debug("Received empty event")
        return {"statusCode": HTTP_OK}

    tag_root_span(records)

    logger.debug(f"Processing {len(records)} records.")
    first_record = records[0]

    if is_sqs_record(first_record):
        logger.info("Routing to SQS Batch Processor")
        return process_partial_response(
            event=event,
            record_handler=sqs_record_handler,
            processor=processor,
            context=context
        )

    if is_sns_record(first_record):
        logger.info("Routing to SNS Direct Processor")
        for record in records:
            payload = parse_payload(get_record_body(record))
            process_device_logic(payload)

        return {"statusCode": HTTP_OK, "body": SNS_SUCCESS_BODY}

    logger.warning("Unrecognized event source structure")
    return {"statusCode": HTTP_BAD_REQUEST}
```

### 4.16 `services/lambda_c/config.py` — Refactored

```python
from aws_lambda_powertools import Logger
from common.log_handler import get_otel_log_handler

SERVICE_NAME = "lambda_c"

logger = Logger(service=SERVICE_NAME)
logger.setLevel("DEBUG")

has_otel_handler = any(type(h).__name__ == "LoggingHandler" for h in logger.handlers)
if not has_otel_handler:
    logger.addHandler(get_otel_log_handler(SERVICE_NAME))
```

### 4.17 `services/lambda_c/requirements.txt` — Simplified

```text
boto3==1.42.83
aws_lambda_powertools==3.12.0
```

### 4.18 `docker-compose.cloud.yml` — Updated

```yaml
version: "3.8"

services:
  localstack:
    container_name: localstack
    image: localstack/localstack:3.4.0
    ports:
      - "4566:4566"
    environment:
      - SERVICES=s3,dynamodb,lambda,sqs,sns,logs
      - AWS_DEFAULT_REGION=us-east-1
      - DOCKER_HOST=unix:///var/run/docker.sock
      - LAMBDA_DOCKER_FLAGS=-e GRAFANA_INSTANCE_ID=${GRAFANA_INSTANCE_ID} -e GRAFANA_API_TOKEN=${GRAFANA_API_TOKEN} -e GRAFANA_OTLP_ENDPOINT=${GRAFANA_OTLP_ENDPOINT}
    volumes:
      - .:/var/task
      - "/var/run/docker.sock:/var/run/docker.sock"
      - "./localstack/init:/etc/localstack/init/ready.d"
```

---

## 5. ADOT vs Manual: Responsibility Matrix

| Concern | ADOT Auto | Manual | File |
|---|---|---|---|
| TracerProvider initialization | ✅ | — | `common/otel.py` (removed) |
| Root Lambda span creation | ✅ | — | ADOT Layer |
| Trace context extraction (SQS/SNS) | ✅ | — | ADOT Layer |
| Span Links for SQS batch | ✅ | — | ADOT Layer |
| Botocore instrumentation | ✅ | — | ADOT Layer |
| W3C Traceparent injection (root span) | ✅ | — | ADOT Layer |
| `send_message` PRODUCER span | — | ✅ | `lambda_a/utils.py` |
| Traceparent injection (child span) | — | ✅ | `common/inject.py` |
| `process_device:{device_id}` spans | — | ✅ | `lambda_b/handler.py`, `lambda_c/handler.py` |
| Root span business attributes | — | ✅ | `lambda_b/utils.py`, `lambda_c/utils.py` |
| OTLP Log export | — | ✅ | `common/log_handler.py` |
| Trace ID / Span ID in logs | — | ✅ | `common/tracing.py` |
| Force-flush on Lambda exit | — | ✅ | `common/tracing.py` |
| SNS envelope unwrapping (SNS→SQS) | — | ✅ | `lambda_b/utils.py`, `lambda_c/utils.py` |

---

## 6. SQS Batch Processing with ADOT

### How ADOT Handles SQS Batch

When a Lambda is triggered by an SQS event source mapping with batch size > 1:

1. ADOT's `AWS_LAMBDA_EXEC_WRAPPER` intercepts the invocation
2. It iterates over `event.Records`
3. For each record, it checks `messageAttributes.traceparent.stringValue`
4. If a valid `traceparent` exists, it creates a **Span Link** from that context
5. All span links are attached to the auto-generated root CONSUMER span
6. The root span's `messaging.batch.message_count` attribute is set

### Manual Process Device Spans

Inside the batch processing loop, we still create `process_device:{device_id}` child spans manually. These become children of the ADOT-created root span.

### SNS Envelope Problem (SNS → SQS)

When SNS messages are routed through SQS (fan-out pattern), the SNS Notification envelope is serialized into the SQS message body. The `traceparent` is nested inside:

```json
{
  "Type": "Notification",
  "MessageId": "...",
  "Message": "{\"device_id\": \"DEV_001\", ...}",
  "MessageAttributes": {
    "traceparent": {
      "Type": "String",
      "Value": "00-abc123-def456-01"
    }
  }
}
```

ADOT **does NOT** automatically unwrap this. The `parse_payload` function in `lambda_b/utils.py` and `lambda_c/utils.py` handles this by:
1. Parsing the SQS message body as JSON
2. Checking if it's an SNS Notification (`Type == "Notification"`)
3. Extracting the `traceparent` from `MessageAttributes`
4. Extracting the actual message from `Message`

---

## 7. Step-by-Step Implementation Guide

### Step 1: Create ADOT Collector Configuration
- Create `o11y/otel-collector-config.yaml` with OTLP receiver, batch processor, and exporters for Tempo (traces) and Loki (logs)

### Step 2: Update Docker Compose
- Replace `otel-collector` service with `adot-collector` using `amazon/aws-otel-collector` image
- Update the config file path

### Step 3: Update Init Script
- Add ADOT Layer ARN to all 3 Lambda functions
- Set ADOT-specific environment variables (`AWS_LAMBDA_EXEC_WRAPPER`, `OTEL_EXPORTER_OTLP_ENDPOINT`, etc.)

### Step 4: Remove `common/otel.py`
- ADOT handles tracer initialization, provider setup, and exporter configuration

### Step 5: Refactor `common/tracing.py`
- Remove root span creation (ADOT does this)
- Remove trace context extraction (ADOT does this)
- Remove span link creation (ADOT does this for SQS batches)
- Keep logger enrichment and force-flush logic

### Step 6: Refactor Lambda Handlers
- Remove `from common.otel import init_tracer` and `tracer = init_tracer(...)`
- Use `trace.get_tracer(__name__)` instead
- Business logic remains identical

### Step 7: Simplify Requirements
- Remove OTel dependencies from `requirements.txt` (provided by ADOT Layer)

### Step 8: Test
- Start the stack: `docker compose -f docker-compose.local.yml up -d`
- Run all 3 test flows (SQS single, SQS batch, SNS fan-out)
- Verify traces in Grafana/Tempo
- Verify logs in Grafana/Loki

---

## 8. ADOT Collector vs OTel Collector

| Feature | ADOT Collector (`amazon/aws-otel-collector`) | OTel Collector (`otel/opentelemetry-collector-contrib`) |
|---|---|---|
| Base | AWS-distributed OTel Collector | Upstream OTel Collector Contrib |
| AWS integrations | Built-in (X-Ray, CloudWatch, S3) | Via contrib exporters |
| Security patches | AWS-managed | Community-managed |
| License | AWS EULA | Apache 2.0 |
| Use case | AWS-native workloads | Multi-cloud / generic |

For this project, we use the ADOT Collector to align with the AWS-native architecture. The configuration is compatible with both.

---

## 9. Production Considerations

### Tail-Based Sampling
For production, enable tail-based sampling in the ADOT Collector to:
- Keep all traces with errors
- Sample a percentage of successful traces
- Keep all traces above a latency threshold

### ECS Fargate Deployment
The ADOT Collector can run as a sidecar container in ECS Fargate:
- One collector per task definition
- Lambdas export to the local collector via `http://localhost:4318`
- The collector batches and forwards to the central backend

### Security
- Use IAM roles for Lambda execution
- Use AWS X-Ray integration if needed
- Encrypt OTLP traffic with TLS in production