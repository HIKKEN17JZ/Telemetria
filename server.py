"""
Servidor Asíncrono Concurrente de Telemetría (Issue #2, Issue #5 e Issue #8).
Asignado a: Charango (Dev 2 - @Charango21)

Implementa:
- Servidor TCP concurrente de alto rendimiento basado en asyncio (I/O no bloqueante).
- Manejo estricto de conexiones simultáneas mediante StreamReader y StreamWriter.
- Protocolo delimitado por fin de línea ('\\n') con validación robusta y acuses de recibo ACK/NACK.
- Registro en memoria de clientes conectados activamente.
- Despacho asíncrono no bloqueante a tareas distribuidas de Celery (Issue #8).
- Mecanismos de Comunicación Entre Procesos (IPC) mediante señales UNIX:
    * SIGHUP: Recarga dinámica de configuraciones en caliente (hot-reload).
    * SIGUSR1: Volcado de métricas operativas y estadísticas en tiempo real.
"""

import asyncio
import argparse
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, asdict
from typing import Dict, Tuple, Optional, Any, Set

from src.protocol import ProtocolValidator, ProtocolResponse, ProtocolError, TelemetryFrame
try:
    from src.tasks import process_telemetry
except ImportError:
    process_telemetry = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    """Configuración dinámica del servidor con soporte para recarga en caliente (SIGHUP)."""
    log_level: str = "INFO"
    enable_celery_dispatch: bool = True

    @classmethod
    def load_from_env(cls) -> "ServerConfig":
        return cls(
            log_level=os.getenv("TELEMETRY_LOG_LEVEL", "INFO").upper(),
            enable_celery_dispatch=os.getenv("TELEMETRY_ENABLE_CELERY", "true").lower() in ("true", "1", "yes")
        )


class ServerMetrics:
    """Métricas y estadísticas operativas del servidor en tiempo real (consultadas vía SIGUSR1)."""
    def __init__(self) -> None:
        self.start_time: float = time.time()
        self.total_received: int = 0
        self.total_processed: int = 0
        self.total_errors: int = 0

    def record_message_received(self) -> None:
        self.total_received += 1

    def record_message_processed(self) -> None:
        self.total_processed += 1

    def record_message_error(self) -> None:
        self.total_errors += 1

    def get_stats(self, active_client_count: int = 0) -> Dict[str, Any]:
        uptime = round(time.time() - self.start_time, 2)
        rate = round(self.total_processed / uptime, 2) if uptime > 0 else 0.0
        return {
            "uptime_seconds": uptime,
            "active_clients": active_client_count,
            "total_received": self.total_received,
            "total_processed": self.total_processed,
            "total_errors": self.total_errors,
            "processed_per_second": rate
        }


# Instancias globales del servidor
server_config = ServerConfig.load_from_env()
server_metrics = ServerMetrics()

# Registro en memoria de sesiones activas: client_id -> (peername, vehicle_id)
active_clients: Dict[int, Tuple[str, str]] = {}

# Suscriptores en tiempo real del Dashboard (modo socket directo)
dashboard_subscribers: Set[asyncio.StreamWriter] = set()


async def dispatch_telemetry_task(frame: TelemetryFrame) -> Optional[str]:
    """
    Despacha la telemetría a Celery sin bloquear el event loop de asyncio.
    Ejecuta el .delay() de Celery en un thread del pool del ejecutor por defecto.
    """
    if process_telemetry is None:
        logger.warning("Celery task module not available. Telemetry not dispatched.")
        return None

    loop = asyncio.get_running_loop()

    try:
        # loop.run_in_executor para garantizar que la llamada sincrónica al broker no bloquee asyncio
        async_result = await loop.run_in_executor(None, process_telemetry.delay, frame.to_payload().to_dict())
        task_id = async_result.id if async_result else None
        logger.debug(f"Telemetry dispatched to Celery worker (task_id={task_id})")
        return task_id
    except Exception as exc:
        logger.error(f"Failed to dispatch telemetry to Celery: {exc}")
        return None


async def forward_to_gateway(frame: TelemetryFrame, gateway_url: Optional[str] = None) -> None:
    """
    Reenvía asíncronamente la telemetría al API Gateway (Issue #11 / #12).
    Permite que el Dashboard Tkinter reciba los datos en tiempo real vía SSE.
    """
    target_url = gateway_url or os.getenv("GATEWAY_URL", "http://127.0.0.1:8000")
    loop = asyncio.get_running_loop()

    def _post() -> None:
        try:
            import urllib.request
            import json
            payload_data = json.dumps(frame.to_payload().to_dict()).encode("utf-8")
            req = urllib.request.Request(
                f"{target_url}/api/telemetry/publish",
                data=payload_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=0.8):
                pass
        except Exception:
            pass

    try:
        await loop.run_in_executor(None, _post)
    except Exception:
        pass


def handle_sighup(config: Optional[ServerConfig] = None) -> None:
    """
    Manejador de la señal SIGHUP (IPC):
    Recarga configuraciones dinámicas en caliente sin interrumpir el servicio.
    """
    target_config = config if config is not None else server_config
    new_config = ServerConfig.load_from_env()
    target_config.log_level = new_config.log_level
    target_config.enable_celery_dispatch = new_config.enable_celery_dispatch

    numeric_level = getattr(logging, target_config.log_level, logging.INFO)
    logging.getLogger().setLevel(numeric_level)
    logger.setLevel(numeric_level)
    logger.info(f"[IPC SIGHUP] Configuración recargada dinámicamente: {asdict(target_config)}")


def handle_sigusr1(metrics: Optional[ServerMetrics] = None, active_client_count: Optional[int] = None) -> None:
    """
    Manejador de la señal SIGUSR1 (IPC):
    Vuelca las métricas operativas del servidor en consola/logs.
    """
    target_metrics = metrics if metrics is not None else server_metrics
    clients_count = active_client_count if active_client_count is not None else len(active_clients)
    stats = target_metrics.get_stats(active_client_count=clients_count)
    
    logger.info(
        f"[IPC SIGUSR1 METRICS] Estadísticas operativas: "
        f"Clientes={stats['active_clients']} | Recibidos={stats['total_received']} | "
        f"Procesados={stats['total_processed']} | Errores={stats['total_errors']} | "
        f"Uptime={stats['uptime_seconds']}s ({stats['processed_per_second']} msg/s)"
    )


def setup_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    config: Optional[ServerConfig] = None,
    metrics: Optional[ServerMetrics] = None
) -> None:
    """
    Registra los manejadores de señales UNIX (SIGHUP, SIGUSR1) en el event loop.
    Degrada limpiamente en entornos donde estas señales no existen (ej. Windows nativo).
    """
    cfg = config if config is not None else server_config
    met = metrics if metrics is not None else server_metrics

    # Verificar si el sistema operativo y el loop soportan add_signal_handler
    if not hasattr(loop, "add_signal_handler"):
        logger.debug("Event loop does not support add_signal_handler.")
        return

    # SIGHUP: Hot-reload de configuración
    if hasattr(signal, "SIGHUP"):
        try:
            loop.add_signal_handler(signal.SIGHUP, lambda: handle_sighup(cfg))
            logger.info("Signal handler registered for SIGHUP (Dynamic hot-reload)")
        except (ValueError, NotImplementedError) as e:
            logger.debug(f"Could not register SIGHUP handler: {e}")

    # SIGUSR1: Dump de métricas operativas
    if hasattr(signal, "SIGUSR1"):
        try:
            loop.add_signal_handler(signal.SIGUSR1, lambda: handle_sigusr1(met, len(active_clients)))
            logger.info("Signal handler registered for SIGUSR1 (Metrics dump)")
        except (ValueError, NotImplementedError) as e:
            logger.debug(f"Could not register SIGUSR1 handler: {e}")


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Maneja la conexión TCP individual de un cliente de telemetría de forma no bloqueante."""
    peername = writer.get_extra_info('peername')
    client_id = id(writer)
    active_clients[client_id] = (str(peername), "UNKNOWN")
    logger.info(f"New connection from {peername} (Active: {len(active_clients)})")
    
    try:
        while True:
            line = await reader.readline()
            if not line:
                logger.info(f"Client {peername} disconnected (EOF)")
                break
                
            message_str = line.decode("utf-8").strip()
            if not message_str:
                continue

            # Detectar registro de Dashboard como suscriptor de telemetría en vivo
            if "dashboard" in message_str.lower() or "subscribe" in message_str.lower():
                dashboard_subscribers.add(writer)
                active_clients[client_id] = (str(peername), "DASHBOARD_MONITOR")
                logger.info(f"Dashboard monitor registrado desde {peername} (Total monitores: {len(dashboard_subscribers)})")
                writer.write(b'{"status": "SUBSCRIBED", "role": "dashboard"}\n')
                await writer.drain()
                continue

            server_metrics.record_message_received()
                
            try:
                # Validar paquete mediante la capa de aplicación de protocolo (Issue #5)
                frame = ProtocolValidator.validate_raw(message_str)
                active_clients[client_id] = (str(peername), frame.vehicle_id)
                logger.info(
                    f"Received valid telemetry from {frame.vehicle_id}: "
                    f"speed={frame.metrics.speed_kmh}km/h, rpm={frame.metrics.rpm}, "
                    f"fuel={frame.metrics.fuel_level_pct}%, temp={frame.metrics.engine_temp_c}°C"
                )

                # Despacho no bloqueante a Celery (Issue #8)
                if server_config.enable_celery_dispatch:
                    asyncio.create_task(dispatch_telemetry_task(frame))

                # Reenvío no bloqueante al API Gateway para el Dashboard en tiempo real (Issue #11 / #12)
                asyncio.create_task(forward_to_gateway(frame))

                # Difundir a todos los dashboards conectados directamente por socket
                for sub_writer in list(dashboard_subscribers):
                    try:
                        sub_writer.write(message_str.encode("utf-8") + b"\n")
                        asyncio.create_task(sub_writer.drain())
                    except Exception:
                        dashboard_subscribers.discard(sub_writer)

                server_metrics.record_message_processed()
                response = ProtocolResponse.ack(frame.vehicle_id)

            except ProtocolError as e:
                server_metrics.record_message_error()
                logger.warning(f"Protocol validation error from {peername}: {e}")
                response = ProtocolResponse.nack(str(e))
            except Exception as e:
                server_metrics.record_message_error()
                logger.error(f"Unexpected error processing message from {peername}: {e}")
                response = ProtocolResponse.nack(f"Server error: {e}")
                
            response_bytes = ProtocolResponse.to_bytes(response)
            writer.write(response_bytes)
            await writer.drain()
            
    except ConnectionResetError:
        logger.warning(f"Connection reset by peer {peername}")
    except Exception as e:
        logger.error(f"Unexpected error with {peername}: {e}")
    finally:
        dashboard_subscribers.discard(writer)
        active_clients.pop(client_id, None)
        logger.info(f"Closing connection for {peername} (Active: {len(active_clients)})")
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def run_server(host: str, port: int) -> None:
    """Arranca el bucle de eventos del servidor TCP concurrente y registra señales IPC."""
    loop = asyncio.get_running_loop()
    setup_signal_handlers(loop)

    server = await asyncio.start_server(handle_client, host, port)
    addr = server.sockets[0].getsockname()
    logger.info(f"Telemetry server serving on {addr}")
    
    async with server:
        await server.serve_forever()


def main() -> None:
    """Punto de entrada CLI para el servidor de telemetría."""
    parser = argparse.ArgumentParser(description="Concurrent Asyncio Telemetry Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind server to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind server to")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(run_server(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Server stopped by user (KeyboardInterrupt)")


if __name__ == "__main__":
    main()
