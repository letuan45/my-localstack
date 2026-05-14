# Enterprise Observability Migration using ADOT Layer & ADOT Collector

Act as an expert Enterprise Software Engineer. Implement apply ADOT to my project, generate your plan and save with path docs/adot-architecture.md

Read docs/architecture.md to undertand the codebase concept

Objective: I want to refactor this entire system to adopt an Enterprise-grade Observability.Architecture using AWS Distro for OpenTelemetry (ADOT). The goal is to reduce boilerplate code, leverage ADOT's auto-instrumentation, and isolate telemetry traffic by introducing a centralized ADOT Collector. Crucially, the current Span structure, Parent-Child trace relationships, and Business Logic must remain intact.

Detailed Technical Requirements:

## 1. Infrastructure & Architecture Setup (ADOT Layer + ADOT Collector):

Attach the ADOT Lambda Layer (Python version) to all 3 functions (lambda_a, lambda_b, lambda_c) for auto-instrumentation.

Introduce a centralized ADOT Collector running as a separate service (simulated in docker-compose.local.yml alongside LocalStack, representing a future ECS Fargate deployment).

Configure the Lambdas' Environment Variables (e.g., AWS_LAMBDA_EXEC_WRAPPER, OTEL_EXPORTER_OTLP_ENDPOINT) so the ADOT Layer inside Lambda exports telemetry NOT directly to the backend, but to the internal ADOT Collector.

Configure the standalone ADOT Collector (otel-collector-config.yaml) to receive this OTLP data, optionally perform tail-based sampling/batching, and then export it to the final backend (Jaeger/Grafana Cloud).

## 2. Refactoring the Producer (lambda_a):

Remove the manual OTel initialization code (common/otel.py).

Since the ADOT Layer automatically wraps the Lambda handler, how do I access the auto-generated current_span to append custom business attributes (like device_id)?

Does ADOT automatically inject the W3C Trace Context into SQS/SNS Message Attributes when making boto3 calls? If yes, explain the required environment variables/config. If no, provide the manual injection code compatible with ADOT.

I strictly need to retain a specific Child Span named send_message with the PRODUCER span kind.

## 3. Refactoring the Consumers (lambda_b, lambda_c):

SQS Batch Processing (Critical): How does ADOT wrap a Lambda triggered by SQS? How does ADOT extract the traceparent from multiple SQS records in a batch and create Span Links attached to the Root Span?

I am using process_partial_response from AWS Lambda Powertools. How do I create Internal Spans for each process_device:{device_id} inside the record processing loop while maintaining the correct Parent-Child relationship with ADOT's auto-generated Root Span?

SNS Envelope Problem: When an SNS message is routed to SQS (Fanout), does ADOT automatically unwrap the Notification envelope to find the traceparent inside? If not, provide the manual extractor code compatible with ADOT.


## 4. Expected Output:

Provide a step-by-step implementation guide.

Provide fully refactored code snippets for:

docker-compose.local.yml (Adding the ADOT Collector).

otel-collector-config.yaml (The Collector's pipeline configuration).

LocalStack init script modifications for attaching the ADOT Layer.

The refactored lambda_a/handler.py and lambda_a/utils.py.

The refactored lambda_b/handler.py (handling both SQS Batching and SNS un-enveloping).

Clearly differentiate between what ADOT will handle automatically (Auto-instrumentation) versus what I will still need to handle manually to maintain my business logic tracing.