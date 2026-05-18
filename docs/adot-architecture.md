# ADOT Integration Architecture — my-localstack

## Overview

This document describes the target production-grade observability architecture for integrating AWS Distro for OpenTelemetry (ADOT) into the existing LocalStack-based event-driven Lambda tracing system.

The current architecture already implements:

- Manual OpenTelemetry instrumentation
- W3C trace context propagation
- Span Links for SQS batching
- Structured log correlation
- OTLP export to Grafana stack

This ADOT integration architecture evolves the system into a scalable enterprise-grade telemetry platform while preserving full control over asynchronous tracing semantics.

The architecture intentionally adopts a **Hybrid ADOT Model**:

- Use ADOT for infrastructure/runtime telemetry plumbing
- Keep manual instrumentation for business tracing and async context propagation

The system explicitly avoids full auto-instrumentation because event-driven SQS/SNS architectures require precise manual trace propagation and span modeling.

---

# Goals

## Primary Goals

- Integrate AWS-managed ADOT components
- Preserve existing manual tracing architecture
- Support enterprise-scale Lambda fleets (100+ Lambdas)
- Enable centralized telemetry governance
- Reduce telemetry ingestion cost
- Support intelligent tail-based sampling
- Maintain complete async trace continuity across SQS/SNS boundaries

---

# Non-Goals

The following are intentionally NOT part of this architecture:

- Replacing manual span creation with auto-instrumentation
- Removing W3C trace propagation logic
- Removing Span Links
- Replacing Powertools batch processing
- Direct vendor-specific instrumentation inside Lambda code
- Using AWS X-Ray SDK

---

# High-Level Production Architecture

```text
┌──────────────────────────────────────────────────────┐
│                    AWS Lambda                        │
│                                                      │
│  lambda_a / lambda_b / lambda_c                      │
│                                                      │
│  - Manual OpenTelemetry spans                        │
│  - W3C trace propagation                             │
│  - Span Links                                        │
│  - Powertools structured logging                     │
│  - Partial batch failure handling                    │
│                                                      │
│  + ADOT Lambda Layer                                 │
│  + Embedded ADOT Collector Extension                 │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ OTLP HTTP/gRPC
                       ▼
┌──────────────────────────────────────────────────────┐
│      Centralized OpenTelemetry Gateway              │
│               ECS/Fargate Deployment                 │
│                                                      │
│ Responsibilities:                                    │
│                                                      │
│ - batching                                            │
│ - compression                                         │
│ - retry                                               │
│ - centralized authentication                          │
│ - telemetry routing                                   │
│ - tail-based sampling                                 │
│ - vendor abstraction                                  │
│ - telemetry governance                                │
│                                                      │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│                 Telemetry Backends                   │
│                                                      │
│  - Grafana Cloud                                     │
│  - Tempo                                             │
│  - Loki                                              │
│  - Datadog                                           │
│  - AWS X-Ray (optional)                              │
└──────────────────────────────────────────────────────┘
```

# ADOT Lambda Layer Responsibilities

Each Lambda attaches an AWS-managed ADOT Lambda Layer.

The ADOT layer provides:

- embedded OpenTelemetry Collector
- OTLP export runtime
- telemetry buffering
- retry handling
- batching support
- AWS-managed collector lifecycle

The ADOT layer DOES NOT:

- create business spans
- understand SQS batching semantics
- implement Span Links
- manage trace propagation
- replace manual instrumentation

---

# Lambda Architecture

## Existing Manual Instrumentation Remains

The following existing components remain unchanged:

| Module | Status |
|---|---|
| common/tracing.py | KEEP |
| common/inject.py | KEEP |
| common/log_handler.py | KEEP |
| Span Links | KEEP |
| W3C traceparent propagation | KEEP |
| Powertools BatchProcessor | KEEP |

The system continues to manually:

- inject traceparent into SQS/SNS message attributes
- extract trace context from incoming records
- create root Lambda spans
- create Span Links for batch records
- create business spans
- force_flush traces before Lambda freeze

---

# Embedded Collector Flow

## Lambda Runtime

Each Lambda exports OTLP telemetry locally:

```text
http://localhost:4318
```

This endpoint belongs to the embedded ADOT Collector Extension.

The collector extension then forwards telemetry to the centralized OTEL Gateway.

---

# Centralized Gateway Architecture

## Purpose

The ECS/Fargate Gateway Collector becomes the central observability control plane.

Without a gateway:

```text
100+ Lambdas
 -> directly connect to vendor
```

This creates:

- excessive outbound connections
- duplicated authentication
- increased NAT Gateway cost
- no centralized sampling
- poor governance
- vendor lock-in

---

# Gateway Responsibilities

## Telemetry Batching

Aggregates spans/logs before export to reduce network overhead.

---

## Compression

Compresses OTLP payloads before external transmission.

---

## Retry Handling

Handles transient backend failures without burdening Lambda execution duration.

---

## Centralized Authentication

Vendor API tokens are stored only in the gateway layer.

Lambda functions never directly manage vendor credentials.

---

## Vendor Routing

Telemetry can be routed to:

- Grafana Cloud
- Tempo
- Loki
- Datadog
- X-Ray
- multiple destinations simultaneously

without modifying Lambda source code.

---

# Sampling Strategy

## Philosophy

The architecture intentionally does NOT retain 100% of traces.

Distributed tracing is used for:

- execution path visualization
- latency analysis
- async debugging
- dependency correlation
- incident investigation

not for complete transaction archival.

---

# Sampling Layers

## Lambda-Level Sampling

Lambda uses lightweight head sampling:

```text
ParentBased(TraceIdRatioBased)
```

Recommended default:

```text
20%
```

Purpose:

- reduce OTLP volume
- reduce Lambda overhead
- reduce network traffic
- reduce collector load

Parent-based sampling ensures trace continuity across async boundaries.

---

# Gateway-Level Tail Sampling

The ECS Gateway performs intelligent tail-based sampling.

The gateway buffers complete traces and decides whether to retain or drop telemetry after evaluating the full trace outcome.

---

# Tail Sampling Rules

## Always Keep

- exceptions
- Lambda failures
- SQS retries
- DLQ flows
- partial batch failures
- high latency traces
- timeout traces
- fan-out anomalies

---

## Aggressively Sample

Healthy successful traces are sampled at low retention percentages.

Recommended:

```text
5%–10%
```

---

# Async Trace Propagation

## W3C Trace Context

The system continues using:

```text
traceparent
tracestate
```

via SQS/SNS message attributes.

This remains entirely manual.

ADOT does not automatically solve async propagation across SQS/SNS.

---

# SQS Batch Processing

## Span Links

A Lambda execution processing an SQS batch may receive messages from multiple independent upstream traces.

A single span cannot have multiple parents.

Therefore:

- one root CONSUMER span is created
- all upstream contexts are attached as Span Links

This architecture remains mandatory after ADOT integration.

---

# Logging Architecture

## Structured Logging

AWS Lambda Powertools remains the primary structured logger.

Each log record includes:

- trace_id
- span_id
- device_id
- batch_id
- retry metadata

---

# Log Correlation

The current span context is manually extracted and appended to the Powertools logger context.

This behavior remains unchanged after ADOT integration.

---

# Partial Batch Failure Strategy

The architecture continues using:

- Powertools BatchProcessor
- process_partial_response
- ReportBatchItemFailures

This prevents successful messages from being retried when only partial batch failures occur.

This behavior is critical for:

- telemetry accuracy
- retry isolation
- preventing duplicate traces

# Final Architectural Principles

## Core Principle #1

ADOT is infrastructure plumbing, not tracing intelligence.

---

## Core Principle #2

Manual instrumentation remains mandatory for async event-driven tracing.

---

## Core Principle #3

The Gateway Collector becomes the observability control plane.

---

## Core Principle #4

Tail sampling is essential for scalable event-driven observability.

---

## Core Principle #5

Telemetry quality is more important than telemetry quantity.

The architecture prioritizes:

- high-value traces
- anomalous flows
- retry visibility
- async continuity

over retaining every successful execution trace.