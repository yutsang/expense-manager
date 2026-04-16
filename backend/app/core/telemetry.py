"""OpenTelemetry setup — auto-instruments FastAPI, SQLAlchemy, httpx.

Call configure_telemetry() once at app startup (before routes are registered).
When OTEL_EXPORTER_OTLP_ENDPOINT is empty, traces are exported to stdout (dev).
"""

from __future__ import annotations

from app.core.logging import get_logger

log = get_logger(__name__)


def configure_telemetry(app_name: str, environment: str, otlp_endpoint: str = "") -> None:
    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": app_name,
                "deployment.environment": environment,
            }
        )
        provider = TracerProvider(resource=resource)

        if otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        else:
            # Dev: log spans to stdout (no-op if console exporter not installed)
            try:
                from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
                    InMemorySpanExporter,
                )

                exporter = InMemorySpanExporter()  # type: ignore[assignment]
            except ImportError:
                from opentelemetry.sdk.trace.export import ConsoleSpanExporter

                exporter = ConsoleSpanExporter()  # type: ignore[assignment]

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument()

        log.info("telemetry_configured", endpoint=otlp_endpoint or "stdout")

    except Exception as exc:
        log.warning("telemetry_setup_failed", error=str(exc))
