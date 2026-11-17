"""LLM observability: hierarchical spans, token costs, an HTML flame graph and OpenTelemetry
export with the GenAI semantic conventions."""

from .otel import OTelBridge, genai_attributes
from .tracer import GlobalTracer, SpanModel, trace_span, tracer

__version__ = "0.1.0"

__all__ = ["GlobalTracer", "OTelBridge", "SpanModel", "genai_attributes", "trace_span", "tracer"]
