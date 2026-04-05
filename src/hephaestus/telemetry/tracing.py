"""OpenTelemetry tracing integration."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Lazy-loaded OTLP components
_tracer: Any = None
_tracer_provider: Any = None
_configured = False


def configure_tracing(
    *,
    service_name: str = "hephaestus",
    otlp_endpoint: str = "",
    enabled: bool = True,
) -> None:
    """Configure OpenTelemetry tracing with OTLP export.

    If opentelemetry packages are not installed, tracing is silently disabled.
    """
    global _tracer, _tracer_provider, _configured

    if not enabled:
        logger.info("OTLP tracing disabled by configuration")
        _configured = True
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.info("OpenTelemetry SDK not installed — tracing disabled")
        _configured = True
        return

    resource = Resource.create({"service.name": service_name})
    _tracer_provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OTLP trace export configured: %s", otlp_endpoint)
        except ImportError:
            logger.warning(
                "opentelemetry-exporter-otlp-proto-grpc not installed — OTLP export disabled"
            )

    trace.set_tracer_provider(_tracer_provider)
    _tracer = trace.get_tracer("hephaestus")
    _configured = True
    logger.info("OpenTelemetry tracing configured for service: %s", service_name)


def get_tracer() -> Any:
    """Return the configured tracer, or a no-op tracer if OTLP is unavailable."""
    global _tracer, _configured

    if _tracer is not None:
        return _tracer

    if not _configured:
        configure_tracing()

    if _tracer is None:
        # Return a no-op tracer
        try:
            from opentelemetry import trace

            _tracer = trace.get_tracer("hephaestus")
        except ImportError:
            _tracer = _NoOpTracer()

    return _tracer


class _NoOpSpan:
    """No-op span for when OTLP is not available."""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass


class _NoOpTracer:
    """No-op tracer for when OpenTelemetry is not installed."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    def start_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()


async def shutdown_tracing() -> None:
    """Flush and shut down the tracer provider."""
    global _tracer_provider
    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
        except Exception:
            logger.exception("Error shutting down tracer provider")
        _tracer_provider = None


__all__ = [
    "configure_tracing",
    "get_tracer",
    "shutdown_tracing",
]
