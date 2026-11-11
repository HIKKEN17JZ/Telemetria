"""
Capa de red para el agente de telemetría (TCP Socket Client) - Issue #6.
Implementa conexión resiliente, reintentos con exponential backoff y buffer offline FIFO.
"""

from __future__ import annotations

import json
import logging
import socket
from dataclasses import dataclass
from typing import Optional, Dict, Any

from src.models import TelemetryPayload
from src.buffer import TelemetryBuffer
from src.backoff import ExponentialBackoff

logger = logging.getLogger("TelemetryClient")


@dataclass(frozen=True)
class NetworkResponse:
    """Resultado de la operación de envío y recepción de respuesta del servidor."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    raw_text: str = ""
    error_message: Optional[str] = None
    buffered: bool = False
    queue_size: int = 0


class TelemetryClient:
    """
    Cliente TCP resiliente para transmisión de telemetría vehicular.
    Soporta reconexión automática, buffer offline en memoria y reintentos exponenciales.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        timeout: float = 3.0,
        buffer: Optional[TelemetryBuffer] = None,
        backoff: Optional[ExponentialBackoff] = None
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._buffer: TelemetryBuffer = buffer if buffer is not None else TelemetryBuffer()
        self._backoff: ExponentialBackoff = backoff if backoff is not None else ExponentialBackoff()

    @property
    def is_connected(self) -> bool:
        """Indica si el socket se encuentra activo."""
        return self._socket is not None

    @property
    def buffer(self) -> TelemetryBuffer:
        """Acceso al buffer offline en memoria."""
        return self._buffer

    @property
    def backoff(self) -> ExponentialBackoff:
        """Estrategia de retroceso exponencial configurada."""
        return self._backoff

    def connect(self) -> bool:
        """
        Establece la conexión con el servidor TCP.
        Retorna True si fue exitosa, o False si falló (sin arrojar excepciones no controladas).
        """
        self.disconnect()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))
            self._socket = sock
            self._backoff.reset()
            logger.info(f"Conexión establecida con el servidor {self.host}:{self.port}")
            return True
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            delay = self._backoff.next_delay()
            logger.warning(
                f"No se pudo conectar a {self.host}:{self.port} ({e}). "
                f"Próximo reintento calculado: {delay:.2f}s (Intento #{self._backoff.current_attempt})"
            )
            try:
                sock.close()
            except Exception:
                pass
            self._socket = None
            return False

    def disconnect(self) -> None:
        """Cierra el socket y libera recursos de forma segura (Graceful close)."""
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                try:
                    self._socket.close()
                except OSError:
                    pass
                self._socket = None

    def send(self, payload: TelemetryPayload) -> NetworkResponse:
        """
        Envío directo a través del socket (método base).
        Si no hay conexión activa, intenta conectar una vez.
        """
        if not self.is_connected and not self.connect():
            return NetworkResponse(
                success=False,
                error_message="El cliente no se encuentra conectado al servidor."
            )
        return self._send_raw(payload)

    def send_or_buffer(self, payload: TelemetryPayload) -> NetworkResponse:
        """
        Envío resiliente de telemetría.
        Si no hay conexión o falla el socket:
          - Encola el payload en el buffer local (FIFO).
          - Retorna NetworkResponse con buffered=True.
        Si la conexión se restablece:
          - Vacía secuencialmente el buffer acumulado antes de enviar la medición actual.
        """
        if not self.is_connected:
            if not self.connect():
                self._buffer.push(payload)
                return NetworkResponse(
                    success=False,
                    buffered=True,
                    queue_size=len(self._buffer),
                    error_message=f"Servidor no disponible. Encolado en buffer local (Total: {len(self._buffer)})"
                )

        if not self._buffer.is_empty:
            flushed = self.flush_buffer()
            if flushed > 0:
                logger.info(f"🔄 Retransmitidos exitosamente {flushed} paquetes acumulados desde el buffer local.")

        if not self.is_connected:
            self._buffer.push(payload)
            return NetworkResponse(
                success=False,
                buffered=True,
                queue_size=len(self._buffer),
                error_message=f"Conexión interrumpida al vaciar buffer. Encolado (Total: {len(self._buffer)})"
            )

        response = self._send_raw(payload)
        if not response.success:
            self._buffer.push(payload)
            return NetworkResponse(
                success=False,
                buffered=True,
                queue_size=len(self._buffer),
                error_message=f"Fallo en transmisión: {response.error_message}. Encolado (Total: {len(self._buffer)})"
            )

        return response

    def flush_buffer(self) -> int:
        """
        Transmite en estricto orden FIFO todas las mediciones acumuladas en el buffer offline.
        Retorna la cantidad de mensajes transmitidos con éxito.
        """
        sent_count = 0
        while not self._buffer.is_empty:
            item = self._buffer.peek()
            if item is None:
                break

            response = self._send_raw(item)
            if response.success:
                self._buffer.pop()
                sent_count += 1
            else:
                logger.warning(f"Error vaciando buffer en elemento {item.timestamp}: {response.error_message}")
                break

        return sent_count

    def _send_raw(self, payload: TelemetryPayload) -> NetworkResponse:
        """Envía un payload serializado a JSON terminado en \\n y procesa el acuse de recibo."""
        if not self._socket:
            return NetworkResponse(success=False, error_message="Socket no inicializado.")

        try:
            raw_bytes = payload.to_json().encode("utf-8")
            self._socket.sendall(raw_bytes)

            response_data = self._read_response_line()
            if not response_data:
                self.disconnect()
                return NetworkResponse(
                    success=False,
                    error_message="El servidor cerró la conexión inesperadamente (EOF)."
                )

            parsed_json = json.loads(response_data)
            return NetworkResponse(
                success=True,
                data=parsed_json,
                raw_text=response_data
            )

        except (socket.timeout, TimeoutError):
            logger.warning("Timeout esperando acuse de recibo del servidor.")
            return NetworkResponse(
                success=False,
                error_message="Timeout esperando acuse de recibo (ACK)."
            )
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            logger.error(f"Error de conexión durante el envío: {e}")
            self.disconnect()
            return NetworkResponse(
                success=False,
                error_message=f"Conexión perdida: {e}"
            )
        except json.JSONDecodeError as e:
            logger.warning(f"Respuesta no válida del servidor: {e}")
            return NetworkResponse(
                success=False,
                error_message=f"Formato de respuesta no reconocido: {e}"
            )

    def _read_response_line(self) -> str:
        """Lee del socket hasta encontrar el delimitador de línea \\n o EOF."""
        buffer = []
        while True:
            chunk = self._socket.recv(1024)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            buffer.append(text)
            if "\n" in text:
                break
        return "".join(buffer).strip()
