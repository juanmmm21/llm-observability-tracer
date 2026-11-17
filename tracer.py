"""Compatibilidad: el código vive en el paquete `llm_observability_tracer`. Este módulo se
conserva para quien añade esta carpeta a `sys.path` e importa `tracer`
directamente."""

from llm_observability_tracer.tracer import *  # noqa: F401,F403
from llm_observability_tracer.tracer import SpanModel, GlobalTracer, trace_span, tracer  # noqa: F401
