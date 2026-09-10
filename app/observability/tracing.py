from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import settings

_configured = False


def configure_tracing() -> None:
    global _configured
    if _configured:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": settings.otel_service_name}))
    if settings.otel_exporter_otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured = True


@contextmanager
def span(name: str, **attributes: object) -> Iterator[trace.Span]:
    tracer = trace.get_tracer(settings.otel_service_name)
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None and isinstance(value, (str, int, float, bool)):
                current.set_attribute(key, value)
        yield current
