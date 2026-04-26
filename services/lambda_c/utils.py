import json
from typing import Any, Mapping

from opentelemetry import trace
from services.lambda_c.config import logger
from services.lambda_c.const import (
    EVENT_SOURCE_SNS,
    EVENT_SOURCE_SQS,
    UNKNOWN_DEVICE_ID,
)


def parse_payload(raw_msg: str | None) -> dict[str, Any]:
    """Parse JSON payloads, including SNS envelopes and double-serialized bodies."""
    if not raw_msg:
        return {}

    try:
        payload = json.loads(raw_msg)

        if isinstance(payload, dict) and payload.get("Type") == "Notification":
            payload = json.loads(payload.get("Message", "{}"))

        if isinstance(payload, str):
            payload = json.loads(payload)

        return payload if isinstance(payload, dict) else {}
    except (TypeError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to parse payload: {e}")
        return {}


def normalize_imeis(value: Any) -> list[Any]:
    """Return IMEIs as a list so tracing attributes stay consistent."""
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return value
    return []


def get_record_body(record: Mapping[str, Any]) -> str | None:
    return record.get("body") or record.get("Sns", {}).get("Message")


def tag_root_span(records: list[dict[str, Any]]) -> None:
    """Copy business identifiers onto the root span for trace search."""
    root_span = trace.get_current_span()
    if not root_span or not root_span.is_recording():
        return

    primary_device_id = None
    all_imeis = []

    for record in records:
        payload = parse_payload(get_record_body(record))

        device_id = payload.get("device_id")
        if device_id and device_id != UNKNOWN_DEVICE_ID and not primary_device_id:
            primary_device_id = device_id

        all_imeis.extend(normalize_imeis(payload.get("device_imeis")))

    if primary_device_id:
        root_span.set_attribute("device_id", primary_device_id)

    root_span.set_attribute("device_imeis", json.dumps(all_imeis))


def get_event_source(record: Mapping[str, Any]) -> str | None:
    return record.get("eventSource") or record.get("EventSource")


def is_sqs_record(record: Mapping[str, Any]) -> bool:
    return get_event_source(record) == EVENT_SOURCE_SQS


def is_sns_record(record: Mapping[str, Any]) -> bool:
    return get_event_source(record) == EVENT_SOURCE_SNS
