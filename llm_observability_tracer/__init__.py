"""LLM observability: hierarchical spans, token costs and an HTML flame graph."""

from .tracer import SpanModel, GlobalTracer, trace_span, tracer

__version__ = "0.1.0"

__all__ = ['SpanModel', 'GlobalTracer', 'trace_span', 'tracer']
