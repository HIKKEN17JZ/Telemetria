"""
Capa de Red Asíncrona con Multithreading para el Dashboard de Tkinter.

Implementa:
- Hilo secundario independiente (daemon thread) dedicado al consumo continuo de datos.
- Comunicación bidireccional y desacoplada mediante una cola thread-safe (queue.Queue).
- Soporte para streaming de Server-Sent Events (SSE: /api/stream) y sondeo REST (/api/vehicles, /api/alerts).
- Reconexión resiliente automática con algoritmo de retroceso exponencial y jitter.
- Estados de conectividad (DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING).
- Cero dependencias externas requeridas (biblioteca estándar: urllib, threading, queue, json).
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import queue

from src.models import TelemetryPayload, Location, VehicleMetrics

logger = logging.getLogger("DashboardNetwork")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class ConnectionState(str, Enum):
    """Estados del ciclo de vida de la conexión del Dashboard con el backend."""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"


class EventType(str, Enum):
    """Tipos de eventos entregados a la cola thread-safe de la interfaz gráfica."""
    STATUS = "STATUS"
    TELEMETRY = "TELEMETRY"
    ALERT = "ALERT"
    STATS = "STATS"
    ERROR = "ERROR"


@dataclass
class NetworkEvent:
    """Evento atómico y seguro para paso de mensajes entre hilos."""
    event_type: EventType
    data: Any
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class NetworkReceiverConfig:
    """Configuración de red y tolerancia a fallos del receptor del dashboard."""
    gateway_url: str = "http://127.0.0.1:8000"
    poll_interval: float = 2.0
    reconnect_backoff_base: float = 1.0
    reconnect_backoff_max: float = 30.0
    request_timeout: float = 2.0
    stream_mode: str = "auto"  # "auto", "stream", "poll"


class SSEParser:
    """
    Parser con búfer de memoria para Server-Sent Events (SSE).
    Gestiona mensajes fragmentados entre paquetes TCP contiguos.
    """

    def __init__(self) -> None:
        self._buffer: str = ""

    def feed(self, chunk: str) -> List[Dict[str, Any]]:
        """Recibe un bloque de texto arbitrario y extrae eventos completos."""
        self._buffer += chunk
        events: List[Dict[str, Any]] = []

        while "\n\n" in self._buffer:
            raw_event, self._buffer = self._buffer.split("\n\n", 1)
            parsed = self._parse_event_block(raw_event)
            if parsed:
                events.append(parsed)

        return events

    @classmethod
    def parse_chunk(cls, text: str) -> List[Dict[str, Any]]:
        """Método estático de conveniencia para procesar bloques independientes."""
        parser = cls()
        return parser.feed(text)

    def _parse_event_block(self, block: str) -> Optional[Dict[str, Any]]:
        lines = block.splitlines()
        event_name = "message"
        data_parts: List[str] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith(":"):
                return {"event": line[1:].strip() or "keepalive", "data": {}}
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_parts.append(line[5:].strip())

        if not data_parts and event_name != "keepalive":
            return None

        raw_data = "\n".join(data_parts)
        try:
            parsed_data = json.loads(raw_data) if raw_data else {}
        except json.JSONDecodeError:
            parsed_data = {"raw": raw_data}

        return {
            "event": event_name,
            "data": parsed_data
        }


class DashboardNetworkReceiver(threading.Thread):
    """
    Hilo secundario dedicado a la sincronización de telemetría en tiempo real.
    Consume la API REST y/o el streaming SSE del API Gateway sin bloquear el loop de Tkinter.
    """

    def __init__(
        self,
        config: Optional[NetworkReceiverConfig] = None,
        event_queue: Optional[queue.Queue] = None
    ) -> None:
        super().__init__(name="DashboardNetworkThread", daemon=True)
        self.config = config or NetworkReceiverConfig()
        self.event_queue: queue.Queue = event_queue if event_queue is not None else queue.Queue()

        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._current_response: Optional[Any] = None

    @property
    def state(self) -> ConnectionState:
        with self._state_lock:
            return self._state

    def set_state(self, new_state: ConnectionState, message: str = "") -> None:
        """Actualiza el estado interno y envía una notificación thread-safe a la GUI."""
        with self._state_lock:
            self._state = new_state

        event = NetworkEvent(
            event_type=EventType.STATUS,
            data={
                "state": new_state.value,
                "message": message,
                "url": self.config.gateway_url
            }
        )
        self.event_queue.put(event)
        logger.info(f"[DashboardNetwork] Estado: {new_state.value} - {message}")

    def stop(self) -> None:
        """Señala la detención inmediata del hilo y cierra conexiones activas."""
        self._stop_event.set()
        if self._current_response:
            try:
                self._current_response.close()
            except Exception:
                pass
        self.set_state(ConnectionState.DISCONNECTED, message="Detenido por el usuario.")

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def dispatch_telemetry(self, raw_telemetry: Dict[str, Any]) -> None:
        """Transforma un diccionario entrante a TelemetryPayload y lo encola."""
        try:
            if isinstance(raw_telemetry, TelemetryPayload):
                payload = raw_telemetry
            else:
                loc = raw_telemetry.get("location", {})
                met = raw_telemetry.get("metrics", {})
                payload = TelemetryPayload(
                    vehicle_id=raw_telemetry.get("vehicle_id", "UNKNOWN"),
                    timestamp=raw_telemetry.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                    location=Location(
                        lat=float(loc.get("lat", loc.get("latitude", 0.0))),
                        lon=float(loc.get("lon", loc.get("longitude", 0.0)))
                    ),
                    metrics=VehicleMetrics(
                        speed_kmh=float(met.get("speed_kmh", met.get("speed", 0.0))),
                        rpm=int(met.get("rpm", 0)),
                        fuel_level_pct=float(met.get("fuel_level_pct", met.get("fuel_level", 0.0))),
                        engine_temp_c=float(met.get("engine_temp_c", met.get("engine_temp", 0.0)))
                    ),
                    status=raw_telemetry.get("status", "MOVING")
                )

            self.event_queue.put(NetworkEvent(event_type=EventType.TELEMETRY, data=payload))
        except Exception as e:
            logger.warning(f"Error parseando telemetría entrante: {e}")

    def dispatch_alert(self, alert_data: Dict[str, Any]) -> None:
        """Encola una alerta para su despliegue visual en la GUI."""
        self.event_queue.put(NetworkEvent(event_type=EventType.ALERT, data=alert_data))

    def _http_get_json(self, endpoint: str) -> Any:
        url = urllib.parse.urljoin(self.config.gateway_url, endpoint)
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "TkinterFleetDashboard/1.0"}
        )
        with urllib.request.urlopen(req, timeout=self.config.request_timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)

    def fetch_vehicles(self) -> List[Dict[str, Any]]:
        """Consulta la lista de vehículos y su última telemetría desde /api/vehicles."""
        try:
            return self._http_get_json("/api/vehicles")
        except Exception as e:
            logger.warning(f"Error consultando /api/vehicles: {e}")
            return []

    def fetch_alerts(self) -> List[Dict[str, Any]]:
        """Consulta las alertas recientes desde /api/alerts."""
        try:
            return self._http_get_json("/api/alerts?limit=50")
        except Exception as e:
            logger.warning(f"Error consultando /api/alerts: {e}")
            return []

    def fetch_stats(self) -> Dict[str, Any]:
        """Consulta las estadísticas de flota desde /api/stats."""
        try:
            return self._http_get_json("/api/stats")
        except Exception as e:
            logger.warning(f"Error consultando /api/stats: {e}")
            return {}

    def sync_initial_state(self) -> bool:
        """Sincroniza la instantánea inicial completa (vehículos y alertas existentes)."""
        vehicles = self.fetch_vehicles()
        for v in vehicles:
            latest = v.get("latest_telemetry")
            if latest:
                loc = {
                    "lat": latest.get("lat") or latest.get("latitude") or 0.0,
                    "lon": latest.get("lon") or latest.get("longitude") or 0.0
                }
                met = {
                    "speed_kmh": latest.get("speed_kmh") or latest.get("speed") or 0.0,
                    "rpm": latest.get("rpm") or 0,
                    "fuel_level_pct": latest.get("fuel_level_pct") or latest.get("fuel_level") or 0.0,
                    "engine_temp_c": latest.get("engine_temp_c") or latest.get("engine_temp") or 0.0
                }
                telemetry_dict = {
                    "vehicle_id": v.get("id", latest.get("vehicle_id")),
                    "timestamp": latest.get("timestamp"),
                    "location": loc,
                    "metrics": met,
                    "status": latest.get("status") or v.get("status") or "ACTIVE"
                }
                self.dispatch_telemetry(telemetry_dict)

        alerts = self.fetch_alerts()
        for a in alerts:
            self.dispatch_alert(a)

        return len(vehicles) > 0 or len(alerts) > 0

    def _stream_sse(self) -> None:
        """Abre un canal continuo Server-Sent Events hacia /api/stream."""
        stream_url = urllib.parse.urljoin(self.config.gateway_url, "/api/stream")
        req = urllib.request.Request(
            stream_url,
            headers={
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache",
                "User-Agent": "TkinterFleetDashboard/1.0"
            }
        )

        with urllib.request.urlopen(req, timeout=self.config.request_timeout) as resp:
            self._current_response = resp
            self.set_state(ConnectionState.CONNECTED, message="Conectado vía SSE en tiempo real.")

            try:
                self.sync_initial_state()
            except Exception as e:
                logger.debug(f"Sincronización inicial parcial: {e}")

            parser = SSEParser()
            while not self.is_stopped():
                line = resp.readline()
                if not line:
                    break

                text = line.decode("utf-8")
                events = parser.feed(text)
                for ev in events:
                    self._process_sse_event(ev)

    def _process_sse_event(self, sse_event: Dict[str, Any]) -> None:
        event_name = sse_event.get("event", "message")
        data = sse_event.get("data", {})

        if event_name == "connect":
            logger.info(f"Handshake SSE confirmado por el Gateway: {data}")
        elif event_name == "keepalive":
            pass
        elif event_name == "telemetry" or data.get("type") == "telemetry":
            self.dispatch_telemetry(data)
        elif event_name == "alert" or data.get("type") == "alert":
            self.dispatch_alert(data)
        elif "vehicle_id" in data and "metrics" in data:
            self.dispatch_telemetry(data)

    def _poll_fallback(self) -> None:
        """Modo de sondeo continuo (fallback cuando SSE no está disponible)."""
        self.set_state(ConnectionState.CONNECTED, message="Conectado vía Sondeo REST (Polling).")
        while not self.is_stopped():
            self.sync_initial_state()
            for _ in range(int(self.config.poll_interval * 10)):
                if self.is_stopped():
                    return
                time.sleep(0.1)

    def _stream_tcp_server(self, host: str = "127.0.0.1", port: int = 5000) -> None:
        """Conexión TCP directa con el servidor de telemetría (fallback sin Docker/Gateway)."""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.config.request_timeout)
        try:
            sock.connect((host, port))
        except Exception as e:
            sock.close()
            raise e

        self._current_response = sock
        sock.sendall(b'{"action": "subscribe", "role": "dashboard"}\n')
        self.set_state(ConnectionState.CONNECTED, message=f"Conectado a Servidor TCP directo ({host}:{port})")

        sock.settimeout(None)
        sock_file = sock.makefile("r", encoding="utf-8")
        try:
            while not self.is_stopped():
                line = sock_file.readline()
                if not line:
                    break
                line = line.strip()
                if not line or "SUBSCRIBED" in line:
                    continue
                try:
                    data = json.loads(line)
                    if "vehicle_id" in data:
                        self.dispatch_telemetry(data)
                except Exception:
                    pass
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def run(self) -> None:
        """Bucle principal del hilo de red con reconexión automática y retroceso exponencial."""
        attempt = 0
        backoff = self.config.reconnect_backoff_base

        while not self.is_stopped():
            try:
                attempt += 1
                state_msg = "Conectando al API Gateway..." if attempt == 1 else f"Reconectando (Intento #{attempt})..."
                self.set_state(
                    ConnectionState.CONNECTING if attempt == 1 else ConnectionState.RECONNECTING,
                    message=state_msg
                )

                connected = False
                if self.config.stream_mode in ("stream", "auto"):
                    try:
                        self._stream_sse()
                        connected = True
                    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as sse_err:
                        logger.debug(f"API Gateway no disponible ({sse_err}).")

                if not connected and not self.is_stopped() and self.config.stream_mode in ("auto", "poll"):
                    try:
                        self._stream_tcp_server(host="127.0.0.1", port=5000)
                        connected = True
                    except Exception as tcp_err:
                        logger.debug(f"Servidor TCP directo no disponible ({tcp_err}).")
                        raise tcp_err
                elif not connected and not self.is_stopped():
                    self._poll_fallback()

                attempt = 0
                backoff = self.config.reconnect_backoff_base

            except Exception as exc:
                if self.is_stopped():
                    break

                jitter = random.uniform(0.8, 1.2)
                wait_time = min(backoff * jitter, self.config.reconnect_backoff_max)
                backoff = min(backoff * 2.0, self.config.reconnect_backoff_max)

                err_msg = f"Falla de conexión ({exc}). Reintentando en {wait_time:.1f}s..."
                self.set_state(ConnectionState.RECONNECTING, message=err_msg)

                step = 0.1
                waited = 0.0
                while waited < wait_time and not self.is_stopped():
                    time.sleep(step)
                    waited += step

        self.set_state(ConnectionState.DISCONNECTED, message="Desconectado.")
