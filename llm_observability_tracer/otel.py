"""OpenTelemetry export with the GenAI semantic conventions.

Every span the tracer opens is mirrored, live, as an OpenTelemetry span (same parent/child
structure, same start and end times), so traces can be sent with OTLP to Jaeger, Grafana Tempo or
any collector. Spans that describe model calls carry the attributes of the OpenTelemetry
*GenAI semantic conventions* (``gen_ai.*``):

====================================  =======================================================
Span metadata key (this tracer)       OpenTelemetry attribute
====================================  =======================================================
``operation`` (chat, embeddings…)     ``gen_ai.operation.name``
``provider`` / ``system``             ``gen_ai.provider.name`` (and legacy ``gen_ai.system``)
``model`` / ``request_model``         ``gen_ai.request.model``
``response_model``                    ``gen_ai.response.model``
``response_id``                       ``gen_ai.response.id``
``temperature``, ``top_p``,           ``gen_ai.request.temperature``, ``.top_p``, ``.top_k``,
``top_k``, ``max_tokens``, ``seed``   ``.max_tokens``, ``.seed``
``input_tokens`` / ``output_tokens``  ``gen_ai.usage.input_tokens`` / ``gen_ai.usage.output_tokens``
``finish_reason``                     ``gen_ai.response.finish_reasons``
``tool`` / ``tool_call_id``           ``gen_ai.tool.name`` / ``gen_ai.tool.call.id``
``agent``                             ``gen_ai.agent.name``
``server_address``, ``server_port``   ``server.address``, ``server.port``
``cost``                              ``gen_ai.usage.cost`` (not standard; documented here)
====================================  =======================================================

As the conventions ask, a model-call span is named ``"{operation} {model}"`` and has kind
``CLIENT``; other spans keep their name and are ``INTERNAL``. An error sets the span status to
``ERROR`` and ``error.type``.

**Content is not exported by default.** Prompts and completions (span ``inputs``/``outputs``) are
personal data in most deployments; they are attached (as ``gen_ai.input.messages`` /
``gen_ai.output.messages`` JSON) only with ``capture_content=True``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

GENAI_KEYS: Dict[str, str] = {
    "operation": "gen_ai.operation.name",
    "provider": "gen_ai.provider.name",
    "model": "gen_ai.request.model",
    "request_model": "gen_ai.request.model",
    "response_model": "gen_ai.response.model",
    "response_id": "gen_ai.response.id",
    "temperature": "gen_ai.request.temperature",
    "top_p": "gen_ai.request.top_p",
    "top_k": "gen_ai.request.top_k",
    "max_tokens": "gen_ai.request.max_tokens",
    "seed": "gen_ai.request.seed",
    "input_tokens": "gen_ai.usage.input_tokens",
    "output_tokens": "gen_ai.usage.output_tokens",
    "tool": "gen_ai.tool.name",
    "tool_call_id": "gen_ai.tool.call.id",
    "agent": "gen_ai.agent.name",
    "conversation_id": "gen_ai.conversation.id",
    "server_address": "server.address",
    "server_port": "server.port",
    "cost": "gen_ai.usage.cost",
}
MODEL_OPERATIONS = {"chat", "text_completion", "generate_content", "embeddings"}
# Keys that describe a model request/response: only meaningful on model-call spans (a retriever's
# ``top_k`` is not ``gen_ai.request.top_k``).
MODEL_ONLY = {
    "model", "request_model", "response_model", "response_id", "temperature", "top_p", "top_k",
    "max_tokens", "seed", "input_tokens", "output_tokens",
}  # fmt: skip


def genai_attributes(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Translate the tracer's metadata into OpenTelemetry attributes (GenAI conventions first;
    any other scalar is kept under ``ai_core.<key>``)."""
    attrs: Dict[str, Any] = {}
    is_model_call = metadata.get("operation") in MODEL_OPERATIONS
    for key, value in metadata.items():
        if value is None:
            continue
        if key in MODEL_ONLY and not is_model_call:
            if isinstance(value, (str, bool, int, float)):
                attrs[f"ai_core.{key}"] = value
            continue
        if key == "system":
            attrs.setdefault("gen_ai.provider.name", value)
            attrs["gen_ai.system"] = value
            continue
        if key == "provider":
            attrs["gen_ai.system"] = value  # still read by many backends
        if key == "finish_reason":
            attrs["gen_ai.response.finish_reasons"] = [value] if isinstance(value, str) else list(value)
            continue
        target = GENAI_KEYS.get(key)
        if target:
            attrs[target] = value
        elif isinstance(value, (str, bool, int, float)):
            attrs[f"ai_core.{key}"] = value
    return attrs


def span_name(name: str, metadata: Dict[str, Any]) -> str:
    op = metadata.get("operation")
    model = metadata.get("model") or metadata.get("request_model")
    if op in MODEL_OPERATIONS and model:
        return f"{op} {model}"
    if op == "execute_tool" and metadata.get("tool"):
        return f"execute_tool {metadata['tool']}"
    if op == "invoke_agent" and metadata.get("agent"):
        return f"invoke_agent {metadata['agent']}"
    return name


class OTelBridge:
    """Mirrors tracer spans into OpenTelemetry spans.

    Args:
        tracer_provider: an OpenTelemetry ``TracerProvider``; by default one is built with an OTLP
            HTTP exporter to ``endpoint`` and a batch processor.
        endpoint: OTLP/HTTP traces endpoint (Jaeger and Tempo both listen on
            ``http://localhost:4318/v1/traces``).
        service_name: ``service.name`` resource attribute (how the service shows up in Jaeger).
        capture_content: also export span inputs/outputs (prompts and completions).
    """

    def __init__(
        self,
        tracer_provider: Any = None,
        endpoint: str = "http://localhost:4318/v1/traces",
        service_name: str = "ai-core",
        capture_content: bool = False,
    ) -> None:
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as exc:  # pragma: no cover
            raise ImportError('OpenTelemetry export needs: pip install "llm-observability-tracer[otel]"') from exc
        self._trace = trace
        if tracer_provider is None:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            tracer_provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
            tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        self.provider = tracer_provider
        self.otel_tracer = tracer_provider.get_tracer("llm-observability-tracer")
        self.capture_content = capture_content
        self._live: Dict[str, Any] = {}

    def on_start(self, span: Any, parent: Any) -> None:
        kind = self._trace.SpanKind.CLIENT if span.metadata.get("operation") in MODEL_OPERATIONS else self._trace.SpanKind.INTERNAL
        parent_otel = self._live.get(parent.id) if parent is not None else None
        ctx = self._trace.set_span_in_context(parent_otel) if parent_otel is not None else None
        otel_span = self.otel_tracer.start_span(
            span_name(span.name, span.metadata),
            context=ctx,
            kind=kind,
            start_time=int(span.start_time * 1e9),
        )
        self._live[span.id] = otel_span

    def on_end(self, span: Any) -> None:
        otel_span = self._live.pop(span.id, None)
        if otel_span is None:
            return
        name = span_name(span.name, span.metadata)
        if name != span.name:
            otel_span.update_name(name)
        otel_span.set_attributes(genai_attributes(span.metadata))
        if span.name != name:
            otel_span.set_attribute("ai_core.span", span.name)
        if self.capture_content:
            if span.inputs:
                otel_span.set_attribute("gen_ai.input.messages", _json(span.inputs))
            if span.outputs:
                otel_span.set_attribute("gen_ai.output.messages", _json(span.outputs))
        if span.error:
            from opentelemetry.trace import Status, StatusCode

            otel_span.set_attribute("error.type", span.error.split(":", 1)[0])
            otel_span.set_status(Status(StatusCode.ERROR, span.error))
        end = span.end_time if span.end_time is not None else span.start_time
        otel_span.end(end_time=int(end * 1e9))

    def flush(self, timeout_ms: int = 5000) -> bool:
        flush = getattr(self.provider, "force_flush", None)
        return bool(flush(timeout_ms)) if callable(flush) else True

    def shutdown(self) -> None:
        shutdown = getattr(self.provider, "shutdown", None)
        if callable(shutdown):
            shutdown()


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:8192]
    except (TypeError, ValueError):
        return str(value)[:8192]
