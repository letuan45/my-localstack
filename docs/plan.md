# Python OTLP Migration Project Plan

## Overview

This project focuses on migrating and standardizing observability across the platform using OpenTelemetry (OTLP). The implementation includes tracing propagation, Lambda instrumentation, centralized telemetry routing, backend collector deployment, and storage validation.

---

# Phase 1: Foundation

## 1.1 Common Observability Library

* Build shared observability utilities and abstractions
* Standardize tracing and logging integration
* Prepare reusable instrumentation components

Duration: 5 days

## 1.2 Data Schema Design

* Design telemetry payload structure
* Define trace/span/log field conventions
* Align schema between services and backend storage

Duration: 3 days

## 1.3 Central OpenTelemetry Proxy

* Build centralized OTLP forwarding layer
* Configure telemetry routing
* Support scalable ingestion pipeline

Duration: 4 days

---

# Phase 2: Upstream Context Propagation

## 2.1 Trace Injection Logic

* Inject trace context into upstream events/messages
* Ensure propagation across asynchronous boundaries

Duration: 3 days

## 2.2 SNS-to-SQS Trace Continuity

* Preserve tracing metadata through SNS and SQS flow
* Validate parent-child span continuity

Duration: 2 days

---

# Phase 3: Lambda Consumers

## 3.1 Manual OTLP Integration

* Integrate OpenTelemetry manually into Lambda consumers
* Configure exporters and tracing lifecycle

Duration: 8 days

## 3.2 SQS Span Link Extraction

* Extract and reconstruct trace/span links from SQS payloads
* Maintain distributed tracing relationships

Duration: 5 days

## 3.3 Partial Batch Failure Logic

* Handle tracing consistency during partial batch retries/failures
* Prevent duplicated or broken trace trees

Duration: 5 days

---

# Phase 4: Hybrid Infrastructure / Databases

## 4.1 Selective Database Auto Instrumentation

* Enable targeted DB auto-instrumentation
* Avoid unnecessary tracing overhead

Duration: 2 days

## 4.2 ECS OpenTelemetry Sidecar Setup

* Configure ECS sidecar collector architecture
* Enable centralized telemetry forwarding from containers

Duration: 3 days

---

# Phase 5: Backend Routing

## 5.1 Final Backend Integration

* Connect telemetry pipeline to final observability backend
* Validate end-to-end ingestion

Duration: 2 days

## 5.2 Tail-Based Sampling Configuration

* Configure tail-based sampling policies
* Optimize telemetry volume and trace quality

Duration: 3 days

---

# Phase 6: Backend Deployment

## 6.1 Provision Storage (ClickHouse)

* Provision telemetry storage backend
* Configure infrastructure and persistence

Duration: 4 days

## 6.2 Backend Collector

* Deploy centralized telemetry collector
* Configure exporters and routing rules

Duration: 3 days

## 6.3 Data Retention Policies

* Define telemetry retention lifecycle
* Configure cleanup and storage optimization policies

Duration: 2 days

## 6.4 Validate Storage End-to-End

* Validate ingestion pipeline end-to-end
* Verify trace/search/query functionality

Duration: 3 days

---

# Expected Outcomes

* Unified OpenTelemetry tracing architecture
* Cross-service distributed tracing support
* Reliable asynchronous trace propagation
* Centralized telemetry collection and routing
* Scalable backend observability infrastructure
* Improved debugging and monitoring capabilities
