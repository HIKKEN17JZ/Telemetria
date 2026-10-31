"""
Estrategia de retroceso exponencial con jitter (Exponential Backoff with Jitter).
Evita tormentas de reconexión (Thundering Herd) y gestiona los reintentos de forma resiliente.
"""

import random
from typing import Optional


class ExponentialBackoff:
    """
    Calculador de retrasos progresivos para reintentos de conexión.
    Formula: delay = min(max_delay, initial_delay * (multiplier ** attempt)) + jitter
    """

    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        multiplier: float = 2.0,
        jitter: bool = True,
        jitter_ratio: float = 0.5
    ):
        if initial_delay <= 0:
            raise ValueError("initial_delay debe ser mayor a 0.")
        if max_delay < initial_delay:
            raise ValueError("max_delay no puede ser menor a initial_delay.")
        if multiplier < 1.0:
            raise ValueError("multiplier debe ser al menos 1.0.")

        self._initial_delay = initial_delay
        self._max_delay = max_delay
        self._multiplier = multiplier
        self._jitter = jitter
        self._jitter_ratio = jitter_ratio
        self._attempt = 0
        self._last_delay = 0.0

    @property
    def current_attempt(self) -> int:
        """Cantidad de intentos fallidos registrados."""
        return self._attempt

    @property
    def last_delay(self) -> float:
        """Último retraso calculado."""
        return self._last_delay

    def next_delay(self) -> float:
        """
        Calcula el próximo tiempo de espera en segundos e incrementa el contador de intentos.
        """
        base_delay = min(self._max_delay, self._initial_delay * (self._multiplier ** self._attempt))
        self._attempt += 1

        if self._jitter:
            added_jitter = random.uniform(0, base_delay * self._jitter_ratio)
            delay = base_delay + added_jitter
        else:
            delay = base_delay

        self._last_delay = delay
        return delay

    def reset(self) -> None:
        """Restablece el contador de intentos a cero al restablecerse la conexión."""
        self._attempt = 0
        self._last_delay = 0.0

    def __repr__(self) -> str:
        return (
            f"ExponentialBackoff(attempt={self._attempt}, initial={self._initial_delay}s, "
            f"max={self._max_delay}s, last={self._last_delay:.2f}s)"
        )
