Act as an expert Enterprise Solutions Architect. Based **strictly** on the OpenTelemetry project plan phases provided below, generate a **Mermaid high-level architecture diagram** showing the end-to-end telemetry data flow.

### Provided Project Plan (CONTEXT):
* **Foundation:** Build a common observability library, define data schema, and set up a **Central OTel Proxy (Gateway)**.
* **Data Sources (Inputs):** Trace Injection starts at **Upstream Services**; message flow goes **SNS -> SQS**; hybrid sources include **ECS services (with Sidecars)** and selective **Databases (Auto-instrumented)**.
* **Processing (Consumers):** **"Generic Compute/Services"** consume from SQS, performing **Manual OTLP** integration, extracting **SQS Span Links**, and handling Partial Batch Failures.
* **Routing & Storage:** The **Central OTel Proxy** performs **Tail-Based Sampling** and routes data to **"Storage Backend (Clickhouse/Tempo)"** managed by a **Backend Collector pipeline**.

### Strategic Constraint (CRITICAL):
* **DO NOT focus on AWS Lambda internal architecture.**
* In the diagram, represent Lambda functions simply as generic, abstract nodes (e.g., call them **"Python Consumer Service"** or **"Compute Component"**). Focus entirely on the **data flow relationships** between OTel components, messaging queues, DBs, and the central proxy, rather than the internal serverless runtime details.

### Diagram Requirements:
1.  Use the **Mermaid Flowchart (graph TD or graph LR)** syntax.
2.  Show clear logical groupings (Subgraphs/Boundary lines) for:
    * **Upstream & Messaging:** (Upstream Apps, SNS, SQS).
    * **Application/Compute Layer:** (The generic services/ECS, DBs).
    * **Telemetry Infrastructure:** (OTel collectors/proxies, Tail-sampling logic).
    * **Storage Backend:** (Collectors, DB storage).
3.  Clearly denote the protocol (e.g., "OTLP/gRPC", "Message Payload w/ trace context", "Span Links") on the relationship connection lines.

### Expected Output:
Provide **ONLY** valid, renderable Mermaid diagram syntax. Do not include introductory text.