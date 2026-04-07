from opentelemetry import trace
import logging

class OtelLogHandler(logging.Handler):
    def emit(self, record):
        span = trace.get_current_span()
        if span.is_recording():
            span.add_event(
                name=record.getMessage(),
                attributes={
                    "level": record.levelname,
                    "logger": record.name,
                }
            )