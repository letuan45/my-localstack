# Enterprise Observability Migration using ADOT Layer & ADOT Collector

Read docs/architecture.md to understand current project architecture, then read adot-architecture.md to understand how AWS ADOT will be migrated and combined with current project. Then read the code base, your task is implement ADOT to current project, update the code and infrastructure code if needed.

---

The system intentionally avoids:

```text
AWS_LAMBDA_EXEC_WRAPPER
```

because full auto-instrumentation creates major problems in asynchronous event-driven systems:

- broken SQS trace continuity
- incomplete batch visibility
- missing span links
- poor business span modeling
- limited control over trace lifecycle

Instead, this architecture combines:

| Component | Responsibility |
|---|---|
| Manual instrumentation | business tracing |
| Manual propagation | W3C context continuity |
| Span Links | SQS batch relationships |
| ADOT Layer | collector runtime |
| ADOT Collector | telemetry buffering/export |
| Gateway Collector | sampling/routing/governance |

# Mandatory Technical Constraints (THE "RULES")

## DO NOT (Strict Prohibitions)
- DO NOT use AWS_LAMBDA_EXEC_WRAPPER. We are intentionally avoiding ADOT Auto-Instrumentation to maintain control over SQS batch semantics.
- DO NOT remove existing Span Links logic. This is required for many-to-one SQS batch tracing.
- DO NOT use the AWS X-Ray SDK. All telemetry must be OTLP-native.
- DO NOT let the AI simplify the common/otel.py module to the point where force_flush() is removed.

# DO (Mandatory Requirements):
- Infrastructure: Attach the ADOT Lambda Layer in Terraform/LocalStack, but leave the instrumentation to the Python code.
- SDK Initialization: Refactor common/otel.py to export to http://localhost:4318 via OTLP HTTP/gRPC (the local ADOT Extension endpoint).
- Trace Continuity: Preserve the manual extraction of traceparent from SQS/SNS messageAttributes.
- Log Correlation: Ensure AWS Lambda Powertools continues to receive the trace_id and span_id from the manual OTel Span Context.
- Batch Strategy: Keep the BatchProcessor and process_partial_response to handle SQS partial failures.