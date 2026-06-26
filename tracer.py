import os
import json
import time
import uuid
import logging
import functools
from contextvars import ContextVar
from typing import Dict, List, Any, Tuple, Optional, Callable
from pydantic import BaseModel, Field

# Logger para auditoría telemetral
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SpanModel(BaseModel):
    """Representación de datos estructurados para un Span de telemetría."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None
    name: str
    start_time: float
    end_time: Optional[float] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    children: List["SpanModel"] = Field(default_factory=list)

    @property
    def duration(self) -> float:
        """Devuelve la latencia de ejecución en segundos."""
        if self.end_time is None:
            return 0.0
        return self.end_time - self.start_time


# ContextVar para rastrear el Span activo de forma segura en entornos async e hilos
_active_span_var: ContextVar[Optional[SpanModel]] = ContextVar("active_span", default=None)


class GlobalTracer:
    """
    Motor de Observabilidad central (Tracer).
    
    Gestiona el ciclo de vida de los Spans en una estructura de árbol jerárquica,
    acumula estadísticas agregadas (tokens, coste) y exporta trazas en ASCII e HTML.
    """

    def __init__(self) -> None:
        self.root_spans: List[SpanModel] = []
        # Mapa plano para accesos rápidos por ID
        self.span_map: Dict[str, SpanModel] = {}

    def start_span(
        self,
        name: str,
        inputs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SpanModel:
        """Inicializa un nuevo span jerárquico bajo el span activo actual."""
        parent = _active_span_var.get()
        
        span = SpanModel(
            name=name,
            parent_id=parent.id if parent else None,
            start_time=time.time(),
            inputs=inputs or {},
            metadata=metadata or {}
        )
        
        self.span_map[span.id] = span
        
        if parent:
            parent.children.append(span)
        else:
            self.root_spans.append(span)
            
        _active_span_var.set(span)
        return span

    def end_span(
        self,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
        metadata_update: Optional[Dict[str, Any]] = None
    ) -> None:
        """Finaliza el span activo actual, registrando salidas, errores y duraciones."""
        span = _active_span_var.get()
        if not span:
            logger.warning("Intento de finalizar un span sin ningún span activo en el contexto.")
            return
            
        span.end_time = time.time()
        if outputs:
            span.outputs.update(outputs)
        if error:
            span.error = f"{type(error).__name__}: {str(error)}"
        if metadata_update:
            span.metadata.update(metadata_update)
            
        # Retornamos al span padre en el contexto actual
        if span.parent_id:
            parent = self.span_map.get(span.parent_id)
            _active_span_var.set(parent)
        else:
            _active_span_var.set(None)

    def clear(self) -> None:
        """Reinicia el historial de trazas acumulado."""
        self.root_spans = []
        self.span_map = {}
        _active_span_var.set(None)

    def get_trace_tree(self) -> List[Dict[str, Any]]:
        """Devuelve el árbol completo de trazas serializado en diccionarios."""
        return [span.model_dump() for span in self.root_spans]

