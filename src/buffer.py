"""
Módulo de búfer de telemetría en memoria (Issue #6).
Almacena mediciones offline en orden FIFO con capacidad acotada para evitar fugas de memoria.
"""

from collections import deque
from typing import Optional, List
from src.models import TelemetryPayload


class TelemetryBuffer:
    """
    Búfer en memoria circular/acotado para acumular telemetría ante pérdidas de conectividad.
    Asegura transmisión secuencial estricta (FIFO) una vez restablecida la red.
    """

    DEFAULT_MAX_SIZE = 1000

    def __init__(self, max_size: int = DEFAULT_MAX_SIZE):
        if max_size <= 0:
            raise ValueError(f"El tamaño máximo del buffer debe ser mayor a 0. Recibido: {max_size}")
        self._max_size = max_size
        self._queue: deque[TelemetryPayload] = deque(maxlen=max_size)

    @property
    def max_size(self) -> int:
        """Capacidad máxima del búfer."""
        return self._max_size

    @property
    def is_empty(self) -> bool:
        """Indica si el búfer está vacío."""
        return len(self._queue) == 0

    def push(self, payload: TelemetryPayload) -> None:
        """
        Inserta un nuevo payload en el búfer.
        Si se alcanza max_size, deque descarta automáticamente el más antiguo (FIFO).
        """
        self._queue.append(payload)

    def pop(self) -> Optional[TelemetryPayload]:
        """
        Extrae y retorna el payload más antiguo en el búfer.
        Retorna None si el búfer está vacío.
        """
        if self._queue:
            return self._queue.popleft()
        return None

    def peek(self) -> Optional[TelemetryPayload]:
        """
        Inspecciona el payload más antiguo sin extraerlo.
        Retorna None si el búfer está vacío.
        """
        if self._queue:
            return self._queue[0]
        return None

    def clear(self) -> None:
        """Vacía todos los elementos del búfer."""
        self._queue.clear()

    def __len__(self) -> int:
        return len(self._queue)

    def __repr__(self) -> str:
        return f"TelemetryBuffer(items={len(self._queue)}/{self._max_size})"

