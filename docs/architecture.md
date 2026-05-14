# Architecture — my-localstack

## Overview

This project is a **LocalStack-based proof of concept** demonstrating an **event-driven AWS Lambda workflow** with:

- **SQS** for queued message delivery (single and batch)
- **SNS** for fan-out event broadcasting
- **OpenTelemetry (OTLP)** for distributed tracing and structured log export
- **AWS Lambda Powertools** for batch processing and structured logging
- **W3C Trace Context** propagation across asynchronous boundaries

The system simulates a **device registration pipeline**: `lambda_a` ingests device events and forwards them to downstream consumers (`lambda_b`, `lambda_c`) via SQS or SNS, with full trace observability from producer to consumer.

---

## High-Level Architecture Diagram

```
                          ┌─────────────────────────────────────────────────────────────┐
                          │                    Invocation Scripts                        │
                          │   sqs_a_to_b.ps1 │ sqs_a_to_b_with_batch.ps1 │ sns_a_to_b_c.ps1 │
                          └───────────┬─────────────────────────────────────────────────┘
                                      │ awslocal lambda invoke
                                      ▼
                          ┌──────────────────────┐
                          │      lambda_a         │  Producer — Python 3.10
                          │   (services/lambda_a)  │
                          └──────────┬───────────┘
                                     │
                    ┌────────────────┼────────────────────┐
                    │ SQS            │ SQS (batch)         │ SNS (fan-out)
                    ▼                ▼                     ▼
           ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
           │  my_queue     │  │  my_queue     │  │   my_topic        │
           │  (batch: 5)   │  │  (batch: 5)   │  │   (SNS Topic)     │
           └──────┬───────┘  └──────┬───────┘  └─────┬──────────┬──┘
                  │                 │               │          │
                  │ Event Source    │ Event Source  │ SNS Sub  │ SNS Sub
                  │ Mapping         │ Mapping       │          │
                  ▼                 ▼               ▼          ▼
          ┌──────────────┐  ┌──────────────┐  ┌──────────┐  ┌──────────┐
          │   lambda_b    │  │   lambda_b    │  │ lambda_b  │  │ lambda_c  │
          │  Consumer     │  │  Consumer     │  │ Consumer  │  │ Consumer  │
          │               │  │ (BatchProc)   │  │           │  │           │
          └──────────────┘  └──────────────┘  └──────────┘  └──────────┘
```

---

## Infrastructure & Deployment

### Local Development (`docker-compose.local.yml`)

| Service           | Image                                       | Port(s)                                     | Purpose                              |
|-------------------|---------------------------------------------|---------------------------------------------|--------------------------------------|
| **localstack**    | localstack/localstack:3.4.0                 | `4566`                                      | Mock AWS services (SQS, SNS, Lambda, Logs, S3, DynamoDB) |
| **otel-collector**| otel/opentelemetry-collector-contrib:0.90.0 | `4318` (OTLP HTTP)                          | OpenTelemetry Collector for batch/buffer/log forwarding |
| **tempo**         | grafana/tempo:2.3.0                         | `3200` (Tempo API)                          | Trace storage |
| **loki**          | grafana/loki:2.9.2                          | `3100`                                      | Log aggregation |
| **grafana**       | grafana/grafana:10.2.2                      | `3000`                                      | Grafana dashboards (Tempo + Loki datasources pre-configured) |

### Cloud Mode (`docker-compose.cloud.yml`)

Same LocalStack container but passes Grafana Cloud OTLP credentials via `LAMBDA_DOCKER_FLAGS`:

| Environment Variable       | Description                        |
|----------------------------|------------------------------------|
| `GRAFANA_INSTANCE_ID`      | Grafana Cloud instance ID          |
| `GRAFANA_API_TOKEN`        | Grafana Cloud API token            |
| `GRAFANA_OTLP_ENDPOINT`    | OTLP HTTP endpoint for traces/logs |

### Init Script (`localstack/init/init.sh`)

Runs automatically when LocalStack starts. Performs:

1. **Creates CloudWatch log groups** for each Lambda
2. **Creates SQS queue** `my_queue`
3. **Creates SNS topic** `my_topic`
4. **Packages and deploys each Lambda** — installs dependencies from `requirements.txt`, bundles `common/` module, creates Python 3.10 functions
5. **Wires event sources**:
   - SQS → Lambda B event source mapping (batch size: 5, max retries: 10)
   - SNS → Lambda B subscription
   - SNS → Lambda C subscription
   - SNS invoke permissions granted to both consumers

---

## Lambdas

### lambda_a — Producer

| Attribute     | Value                                  |
|---------------|----------------------------------------|
| Runtime       | Python 3.10                            |
| Handler       | `services.lambda_a.handler.handler`    |
| Dependencies  | boto3, opentelemetry, powertools       |
| Trigger       | Direct invocation via AWS CLI          |

**Logic:**
- Accepts a JSON payload with `target_destination` (SQS URL or SNS ARN), device data, and a `simulate_batch` flag
- **Single mode**: Sends one message containing `device_id` and `device_imeis` to the target
- **Batch mode**: Iterates over a `devices` array and sends individual messages (each with a unique `batch_id`)
- **Tracing**: Creates a `send_message` span (PRODUCER kind), injects W3C `traceparent` into message attributes for downstream context propagation

### lambda_b — Consumer (SQS + SNS)

| Attribute     | Value                                  |
|---------------|----------------------------------------|
| Runtime       | Python 3.10                            |
| Handler       | `services.lambda_b.handler.handler`    |
| Dependencies  | boto3, opentelemetry, powertools       |
| Triggers      | SQS event source mapping, SNS subscription |

**Logic:**
- Routes based on event source type (`aws:sqs` vs `aws:sns`)
- **SQS path**: Uses Powertools `BatchProcessor` and `process_partial_response` for partial batch failure handling
- **SNS path**: Iterates records directly, extracts SNS message body
- **Device processing**: For each device, creates a child span `process_device:{device_id}`. Simulated error on `DEV_002`.
- **Span linking**: For SQS batches, creates span links to maintain parent-child trace relationships across messages

### lambda_c — Consumer (SNS only)

| Attribute     | Value                                  |
|---------------|----------------------------------------|
| Runtime       | Python 3.10                            |
| Handler       | `services.lambda_c.handler.handler`    |
| Dependencies  | boto3, opentelemetry, powertools       |
| Trigger       | SNS subscription                       |

**Logic:**
- Identical processing logic to lambda_b (aligned `const.py` and `utils.py`)
- Currently responds only to SNS events
- Includes SQS batch handling code for future extensibility (identical pattern to lambda_b)

---

## Observability Architecture

### OpenTelemetry Stack

```
Lambda A (PRODUCER)         Lambda B/C (CONSUMERS)
┌─────────────────┐        ┌─────────────────────────┐
│  common.otel     │        │  common.otel             │
│  init_tracer()   │        │  init_tracer()           │
│  ┌───────────┐   │        │  ┌───────────────────┐   │
│  │send_msg  │   │        │  │lambda_handler     │   │
│  │span      │   │        │  │root span          │   │
│  │(PRODUCER)│   │        │  │(CONSUMER)         │   │
│  └─────┬─────┘   │        │  ├───────────────────┤   │
│        │         │        │  │process_device     │   │
│  inject traceparent──►message──►child spans       │   │
│        │         │        │  │(span links for    │   │
│        │         │        │  │ batch records)    │   │
│        │         │        │  └───────────────────┘   │
│  OTLP Exporter   │        │  OTLP Exporter           │
└────────┬─────────┘        └──────────┬──────────────┘
         │                             │
         └───────────┬─────────────────┘
                     ▼
        ┌─────────────────────────┐
        │     OTLP HTTP (port 4318)      │
        │  http://host.docker.internal:4318│
        └──────────┬────────────────┘
                   ▼
        ┌──────────────────────┐
        │   OTel Collector     │
        │  (batch/buffer)      │
        └──────┬───────┬──────┘
               │       │
               ▼       ▼
        ┌────────┐ ┌────────┐
        │ Tempo  │ │  Loki  │
        │(traces)│ │ (logs) │
        └────┬───┘ └───┬────┘
             │         │
             ▼         ▼
        ┌──────────────────────┐
        │      Grafana          │
        │   http://localhost:3000│
        └──────────────────────┘
```

### Common Modules (`common/`)

| Module            | Responsibility                                                       |
|-------------------|----------------------------------------------------------------------|
| `common/otel.py`  | Initializes `TracerProvider`, `OTLPSpanExporter`, `BatchSpanProcessor`, botocore auto-instrumentation. Supports both local (on-prem Grafana stack via OTel Collector) and cloud (Grafana Cloud with HTTP Basic auth) modes. |
| `common/tracing.py` | `@traced_lambda` decorator: creates root Lambda span, extracts upstream `traceparent`, creates span links for SQS batch records, appends `trace_id`/`span_id` to Powertools logger, force-flushes traces and logs before exit. |
| `common/inject.py` | Injects W3C `traceparent` into a carrier dict for SQS/SNS message attributes. |
| `common/log_handler.py` | Configures OpenTelemetry `LoggingHandler` with OTLP export, custom `JsonFormatter` that includes `trace_id` and `span_id` in log records. |

### Trace Context Flow

1. **Producer (lambda_a)**: `common.inject.inject_trace()` extracts the current `traceparent` and stores it in the message attributes
2. **SQS**: `traceparent` stored in `messageAttributes.traceparent.stringValue`
3. **SNS**: `traceparent` stored in `MessageAttributes.traceparent.StringValue` (or nested inside the SNS envelope's `MessageAttributes`)
4. **Consumer (lambda_b/c)**: `common.tracing.extract_trace_context()` reads `traceparent` from the appropriate location depending on event type (SQS direct, SNS direct, or SNS-via-SQS)
5. **Single message**: extracted context becomes the parent of the root Lambda span
6. **Batch messages**: each record's context is converted into a `Link` object, attached to the root span

### Logging

- Uses **AWS Lambda Powertools Logger** for structured JSON logging
- OTel `LoggingHandler` added via `common.log_handler.get_otel_log_handler()`
- Custom `JsonFormatter` enriches each log record with `trace_id` and `span_id`
- Logs exported via OTLP HTTP alongside traces

---

## Data Flows (Detailed)

### Flow 1: SQS Single Message

```
lambda_a payload:
{
  "target_destination": "http://localhost:4566/000000000000/my_queue",
  "simulate_batch": false,
  "device_id": "123123123123",
  "device_imeis": ["111111111", "222222222"]
}

1. awslocal lambda invoke lambda_a
2. lambda_a creates PRODUCER span, injects traceparent
3. lambda_a sends single SQS message to my_queue
4. SQS event source mapping triggers lambda_b
5. lambda_b extracts traceparent → sets as parent of root CONSUMER span
6. lambda_b processes device in child span process_device:123123123123
7. Traces/logs exported to OTel Collector → Tempo + Loki → Grafana
```

### Flow 2: SQS Batch Message

```
lambda_a payload:
{
  "target_destination": "http://localhost:4566/000000000000/my_queue",
  "simulate_batch": true,
  "devices": [
    { "device_id": "DEV_001", "device_imeis": ["111", "222"] },
    { "device_id": "DEV_002", "device_imeis": ["333"] },  ← simulated error
    { "device_id": "DEV_003", "device_imeis": ["444", "555"] }
  ]
}

1. awslocal lambda invoke lambda_a
2. lambda_a sends 3 separate SQS messages (each with unique batch_id)
3. SQS batches them (batch size: 5) → invokes lambda_b
4. lambda_b creates root span with 3 span links (one per message traceparent)
5. Uses Powertools process_partial_response with BatchProcessor
6. DEV_001, DEV_003 succeed; DEV_002 raises ValueError
7. Partial batch failure: failed messages reported back to SQS for retry
```

### Flow 3: SNS Fan-Out

```
lambda_a payload:
{
  "target_destination": "arn:aws:sns:us-east-1:000000000000:my_topic",
  "simulate_batch": false,
  "device_id": "000001",
  "device_imeis": ["999999", "888888"]
}

1. awslocal lambda invoke lambda_a
2. lambda_a creates PRODUCER span, injects traceparent into SNS message attributes
3. SNS topic my_topic fans out to subscribers:
   ├── lambda_b (SNS subscription)
   └── lambda_c (SNS subscription)
4. Each consumer extracts traceparent from Sns.MessageAttributes
5. Each consumer sets it as parent of its root CONSUMER span
6. Both lambdas process the device independently
```

---

## Batch Error Handling Strategy

The project demonstrates **partial batch failure** handling using AWS Lambda Powertools:

| Component               | Behavior                                                |
|-------------------------|--------------------------------------------------------|
| SQS Event Source Mapping | Batch size: 5, Max retries: 10                         |
| Powertools `BatchProcessor` | Processes each SQS record individually                 |
| `process_partial_response` | Returns batch response with `batchItemFailures` list    |
| Simulated error         | `DEV_002` raises `ValueError` in both lambda_b and lambda_c |
| SQS retry behavior      | Failed messages remain in queue and are retried         |

---

## Test Scripts (`powershell/`)

| Script                       | Flow                    | Wait Time | Logs Fetched           |
|------------------------------|-------------------------|-----------|------------------------|
| `sqs_a_to_b.ps1`             | SQS single message      | 5s        | lambda_a, lambda_b     |
| `sqs_a_to_b_with_batch.ps1`  | SQS batch (3 devices)   | 12s       | lambda_a, lambda_b     |
| `sns_a_to_b_c.ps1`           | SNS fan-out             | 20s       | lambda_a, lambda_b, lambda_c |

Each script:
1. Cleans old logs from `logs/` folder
2. Writes invocation payload to `input.json`
3. Invokes lambda_a via `awslocal lambda invoke`
4. Waits for downstream processing
5. Fetches and saves CloudWatch log events to `logs/*.log`

---

## Project Structure

```
my-localstack/
│
├── common/                          # Shared observability library
│   ├── __init__.py
│   ├── inject.py                    # W3C traceparent injection
│   ├── log_handler.py               # OTLP log exporter + JsonFormatter
│   ├── otel.py                      # Tracer provider & exporter init
│   └── tracing.py                   # @traced_lambda decorator
│
├── services/
│   ├── __init__.py
│   ├── lambda_a/                    # Producer Lambda
│   │   ├── __init__.py
│   │   ├── config.py                # Logger, boto3 clients
│   │   ├── handler.py               # Event handler
│   │   ├── requirements.txt         # Dependencies
│   │   └── utils.py                 # SQS/SNS message sender
│   ├── lambda_b/                    # Consumer Lambda (SQS + SNS)
│   │   ├── __init__.py
│   │   ├── config.py                # Logger
│   │   ├── const.py                 # Constants & error device ID
│   │   ├── handler.py               # Event handler with BatchProcessor
│   │   ├── requirements.txt
│   │   └── utils.py                 # Payload parsing, span tagging
│   └── lambda_c/                    # Consumer Lambda (SNS)
│       ├── __init__.py
│       ├── config.py
│       ├── const.py
│       ├── handler.py
│       ├── requirements.txt
│       └── utils.py
│
├── localstack/
│   └── init/
│       └── init.sh                  # Infrastructure provisioning script
│
├── o11y/                            # Observability configs
│   ├── grafana-datasources.yaml     # Tempo + Loki datasource setup
│   ├── otel-collector.yaml          # OTel Collector pipeline config
│   └── tempo-local.yaml            # Tempo local storage config
│
├── powershell/                      # Demo/test scripts
│   ├── sns_a_to_b_c.ps1            # SNS fan-out test
│   ├── sqs_a_to_b.ps1              # SQS single message test
│   └── sqs_a_to_b_with_batch.ps1   # SQS batch test
│
├── docker-compose.local.yml         # Local stack (LocalStack + OTel Collector + Tempo + Loki + Grafana)
├── docker-compose.cloud.yml         # Cloud stack (LocalStack + Grafana Cloud)
├── input.json                       # Last invocation payload
├── out.json                         # Last invocation response
├── logs/                            # Fetched CloudWatch log files
│   ├── lambda_a.log
│   ├── lambda_b.log
│   └── lambda_c.log
├── .env                             # Environment overrides
├── .gitattributes
├── .gitignore
└── README.md
```

---

## Configuration & Environment Variables

| Variable                | Default / Example                        | Description                              |
|-------------------------|------------------------------------------|------------------------------------------|
| `LOCALSTACK_HOSTNAME`   | `localhost.localstack.cloud`             | LocalStack endpoint hostname             |
| `GRAFANA_INSTANCE_ID`   | *(empty)*                                | Grafana Cloud instance ID (cloud mode)   |
| `GRAFANA_API_TOKEN`     | *(empty)*                                | Grafana Cloud API token (cloud mode)     |
| `GRAFANA_OTLP_ENDPOINT` | *(empty)* → `http://host.docker.internal:4318` | OTLP HTTP endpoint                  |
| `PYTHONPATH`            | `.`                                      | Set in Lambda environment                |

---

## Key AWS Resources Created

| Resource             | Name/Action                                      | Used By                   |
|----------------------|--------------------------------------------------|---------------------------|
| SQS Queue            | `my_queue`                                       | lambda_a → lambda_b       |
| SNS Topic            | `my_topic`                                       | lambda_a → lambda_b, lambda_c |
| Lambda Function      | `lambda_a`                                       | Direct invocation         |
| Lambda Function      | `lambda_b`                                       | SQS + SNS triggers        |
| Lambda Function      | `lambda_c`                                       | SNS trigger               |
| CloudWatch Log Group | `/aws/lambda/lambda_a`                           | lambda_a logs             |
| CloudWatch Log Group | `/aws/lambda/lambda_b`                           | lambda_b logs             |
| CloudWatch Log Group | `/aws/lambda/lambda_c`                           | lambda_c logs             |
| SQS → Lambda mapping | Event source mapping (batch 5, retries 10)       | lambda_b consumer         |
| SNS → Lambda sub     | Lambda protocol subscription                     | lambda_b, lambda_c        |
| SNS invoke permission| `lambda:InvokeFunction` from `sns.amazonaws.com`  | lambda_b, lambda_c        |

---

## Span Naming Convention

| Span Name                       | Service    | Kind     | Description                             |
|---------------------------------|------------|----------|-----------------------------------------|
| `lambda_handler:handler`        | lambda_a/b/c | SERVER / CONSUMER | Root Lambda span (CONSUMER if from event source, SERVER if direct invoke) |
| `send_message`                  | lambda_a   | PRODUCER | Sending message to SQS or SNS           |
| `process_device:{device_id}`    | lambda_b/c | INTERNAL | Individual device processing            |

---

## Notes & Known Behaviors

- **lambda_b** and **lambda_c** contain intentionally duplicated `const.py` and `utils.py` for independent evolution
- `DEV_002` is the reserved device ID for simulating processing errors
- SQS retries are expected when `DEV_002` fails; Lambda Powertools `batchItemFailures` prevents committed messages from being retried
- Grafana UI available at `http://localhost:3000` in local mode with anonymous access (no login required)
- Tempo and Loki datasources are pre-provisioned in Grafana with `tracesToLogsV2` linking
- CloudWatch log groups are created during init but also auto-created by LocalStack on first invocation
- OTel Collector receives OTLP HTTP on port 4318 and forwards traces to Tempo (gRPC) and logs to Loki (HTTP)