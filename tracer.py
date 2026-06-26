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
