"""
Capa de red para el agente de telemetría (TCP Socket Client).
Implementa conexión resiliente, delimitación por fin de línea y manejo de errores.
"""

import json
import logging
import socket
from dataclasses import dataclass
from typing import Optional, Dict, Any

from src.models import TelemetryPayload

logger = logging.getLogger("TelemetryClient")


@dataclass(frozen=True)
class NetworkResponse:
    """Resultado de la operación de envío y recepción de respuesta del servidor."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    raw_text: str = ""
    error_message: Optional[str] = None


class TelemetryClient:
    """Cliente TCP resiliente para transmisión de telemetría."""

    def __init__(self, host: str = "127.0.0.1", port: int = 5000, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None

    @property
    def is_connected(self) -> bool:
        """Indica si el socket está instanciado."""
        return self._socket is not None

    def connect(self) -> bool:
        """
        Establece la conexión con el servidor TCP.
        Retorna True si fue exitosa, o False si falló (sin arrojar excepción no controlada).
        """
        self.disconnect()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))
            self._socket = sock
            logger.info(f"Conexión establecida con el servidor {self.host}:{self.port}")
            return True
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            logger.warning(f"No se pudo conectar a {self.host}:{self.port} - {e}")
            try:
                sock.close()
            except Exception:
                pass
            self._socket = None
            return False

    def disconnect(self) -> None:
        """Cierra el socket y libera recursos de forma segura."""
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
        Envía un payload serializado a JSON terminado en \\n y espera la respuesta ACK/NACK.
        Si la conexión se interrumpe, marca el socket como desconectado.
        """
        if not self.is_connected and not self.connect():
            return NetworkResponse(
                success=False,
                error_message="El cliente no se encuentra conectado al servidor."
            )

        try:
            # Serialización y envío asegurando el delimitador \n
            raw_bytes = payload.to_json().encode("utf-8")
            self._socket.sendall(raw_bytes)

            # Recepción de acuse de recibo delimitado
            response_data = self._read_response_line()
            if not response_data:
                self.disconnect()
                return NetworkResponse(
                    success=False,
                    error_message="El servidor cerró la conexión inesperadamente."
                )

            # Parseo JSON de la respuesta
            parsed_json = json.loads(response_data)
            return NetworkResponse(
                success=True,
                data=parsed_json,
                raw_text=response_data
            )

        except (socket.timeout, TimeoutError):
            logger.warning("Timeout esperando respuesta del servidor.")
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
            text = chunk.decode("utf-8")
            buffer.append(text)
            if "\n" in text:
                break
        full_text = "".join(buffer).strip()
        return full_text
