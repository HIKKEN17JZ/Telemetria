"""
API Gateway de Telemetría con FastAPI, Gunicorn y Uvicorn (Issue #11).
Asignado a: Charango (Dev 2 - @Charango21)

Implementa:
- Capa de exposición REST de alto rendimiento (/api/vehicles, /api/alerts, /api/stats).
- Endpoint diagnóstico de concurrencia (/api/system/concurrency) que evidencia la
  combinación de multiprocesamiento (Workers Gunicorn) y multihilo (Threads concurrentes).
- Canales de streaming en tiempo real:
    * Server-Sent Events (SSE: /api/stream) para clientes HTTP reactivos.
    * WebSockets (/ws y /api/stream/ws) para comunicación bidireccional de baja latencia.
- Despacho y difusión de telemetría hacia observadores del dashboard (Tkinter).
- Integración resiliente con PostgreSQL (psycopg_pool) ejecutando consultas en
  hilos secundarios (asyncio.to_thread) para preservar el event loop sin bloqueos.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.database import DatabaseConfig, DatabaseManager

logger = logging.getLogger("APIGateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ============================================================================
# Modelos de Configuración y Esquemas Pydantic
# ============================================================================

@dataclass
class GatewayConfig:
    """Parámetros de configuración del API Gateway."""
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 2
    threads: int = 2
    cors_origins: tuple[str, ...] = ("*",)

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        return cls(
            host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
            port=int(os.getenv("GATEWAY_PORT", "8000")),
            workers=int(os.getenv("GATEWAY_WORKERS", "2")),
            threads=int(os.getenv("GATEWAY_THREADS", "2"))
        )


class TelemetryMetricsSchema(BaseModel):
    speed_kmh: float = Field(..., description="Velocidad en km/h", ge=0.0)
    rpm: int = Field(..., description="Revoluciones por minuto del motor", ge=0)
    fuel_level_pct: float = Field(..., description="Nivel de combustible (0-100%)", ge=0.0, le=100.0)
    engine_temp_c: float = Field(..., description="Temperatura del motor en °C")


class LocationSchema(BaseModel):
    lat: float = Field(..., description="Latitud GPS")
    lon: float = Field(..., description="Longitud GPS")


class TelemetryIngestSchema(BaseModel):
    vehicle_id: str = Field(..., description="Identificador único del vehículo")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    location: LocationSchema
    metrics: TelemetryMetricsSchema
    status: str = Field(default="MOVING")


# ============================================================================
# Componente de Difusión en Tiempo Real (StreamBroadcaster)
# ============================================================================

class StreamBroadcaster:
    """
    Gestor de suscripciones y difusión en tiempo real (Pub/Sub en memoria).
    Mantiene colas asíncronas independientes por suscriptor para streaming
    mediante Server-Sent Events (SSE) y WebSockets sin bloquear el servidor.
    """

    def __init__(self, queue_maxsize: int = 100):
        self.queue_maxsize = queue_maxsize
        self._subscribers: Set[asyncio.Queue[Dict[str, Any]]] = set()
        self._lock = asyncio.Lock()
        self._total_broadcasted: int = 0

    @property
    def active_subscribers(self) -> int:
        return len(self._subscribers)

    async def subscribe(self) -> asyncio.Queue[Dict[str, Any]]:
        """Registra un nuevo canal suscriptor y retorna su cola FIFO asíncrona."""
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=self.queue_maxsize)
        async with self._lock:
            self._subscribers.add(queue)
            logger.info(f"Nuevo suscriptor de streaming conectado (Total: {len(self._subscribers)})")
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        """Remueve un suscriptor desconectado liberando sus recursos."""
        async with self._lock:
            self._subscribers.discard(queue)
            logger.info(f"Suscriptor desconectado (Restantes: {len(self._subscribers)})")

    async def broadcast(self, message: Dict[str, Any]) -> int:
        """
        Transmite un payload a todas las conexiones activas.
        Si una cola se encuentra llena (consumidor lento), descarta el paquete
        más antiguo para evitar backpressure y starvation de recursos.
        """
        async with self._lock:
            subscribers = list(self._subscribers)

        sent_count = 0
        for queue in subscribers:
            try:
                queue.put_nowait(message)
                sent_count += 1
            except asyncio.QueueFull:
                try:
                    # Descartar paquete antiguo e insertar el más reciente
                    _ = queue.get_nowait()
                    queue.put_nowait(message)
                    sent_count += 1
                except Exception:
                    pass

        self._total_broadcasted += 1
        return sent_count


# ============================================================================
# Factory de la Aplicación FastAPI
# ============================================================================

def create_app(
    db_manager: Optional[DatabaseManager] = None,
    broadcaster: Optional[StreamBroadcaster] = None,
    config: Optional[GatewayConfig] = None
) -> FastAPI:
    """
    Crea y configura la instancia de la aplicación FastAPI.
    Permite inyección de dependencias para tests unitarios y desacoplamiento limpio.
    """
    cfg = config or GatewayConfig.from_env()
    db = db_manager or DatabaseManager()
    stream_hub = broadcaster or StreamBroadcaster()

    start_time = time.time()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        logger.info(
            f"Iniciando API Gateway en PID {os.getpid()} (Hilos activos: {threading.active_count()})"
        )
        yield
        logger.info(f"Deteniendo API Gateway en PID {os.getpid()}...")
        # Cerrar pool de base de datos si fue instanciado internamente
        try:
            db.close()
        except Exception:
            pass

    app = FastAPI(
        title="API Gateway - Sistema de Telemetría de Flota Distribuido",
        description=(
            "Capa de exposición de datos y streaming en tiempo real servida mediante "
            "Gunicorn + Uvicorn Workers e hilos concurrentes para alimentar el Dashboard Tkinter."
        ),
        version="1.0.0",
        lifespan=lifespan
    )

    # Middleware CORS para permitir consultas desde frontend web o clientes externos
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ========================================================================
    # Rutas Base, Salud y Diagnóstico de Concurrencia
    # ========================================================================

    @app.get("/", summary="Índice del API Gateway")
    async def index() -> Dict[str, Any]:
        """Metadatos del servicio, documentación interactiva y estado de runtime."""
        return {
            "service": "API Gateway de Telemetría",
            "version": "1.0.0",
            "status": "online",
            "docs_url": "/docs",
            "runtime": {
                "worker_pid": os.getpid(),
                "active_threads": threading.active_count(),
                "uptime_seconds": round(time.time() - start_time, 2),
            },
            "endpoints": {
                "vehicles": "/api/vehicles",
                "alerts": "/api/alerts",
                "stats": "/api/stats",
                "concurrency": "/api/system/concurrency",
                "sse_stream": "/api/stream",
                "websocket": "/ws",
                "health": "/health"
            }
        }

    @app.get("/health", summary="Healthcheck del Gateway")
    @app.get("/api/health", summary="Healthcheck del Gateway (Alias)")
    async def health_check() -> Dict[str, Any]:
        """Verifica la conectividad con la base de datos PostgreSQL y el estado operativo."""
        db_status = "connected"
        try:
            # Consulta liviana ejecutada en thread para no bloquear el loop
            await asyncio.to_thread(db.get_vehicle, "__healthcheck__")
        except Exception as e:
            logger.warning(f"Falla de conectividad en healthcheck con PostgreSQL: {e}")
            db_status = f"degraded: {e}"

        return {
            "status": "healthy" if "degraded" not in db_status else "degraded",
            "database": db_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "worker_pid": os.getpid(),
            "active_threads": threading.active_count(),
            "active_subscribers": stream_hub.active_subscribers
        }

    @app.get("/api/system/concurrency", summary="Diagnóstico de Concurrencia (Workers vs Threads)")
    async def get_concurrency_diagnostic() -> Dict[str, Any]:
        """
        Justificación conceptual y evidencia técnica del modelo de concurrencia:
        - Workers: Procesos independientes aislados en memoria creados por Gunicorn con fork().
        - Threads: Hilos concurrentes por worker para atender I/O bloqueante (PostgreSQL/Disco).
        - Async I/O: Event loop de Uvicorn multiplexando miles de conexiones (SSE/WebSockets).
        """
        current_thread = threading.current_thread()
        return {
            "worker_pid": os.getpid(),
            "parent_pid": os.getppid(),
            "active_threads_count": threading.active_count(),
            "current_thread_name": current_thread.name,
            "current_thread_ident": current_thread.ident,
            "python_version": sys.version,
            "architecture": {
                "gunicorn_workers": (
                    "Múltiples procesos independientes con memoria aislada y GIL separado. "
                    "Garantizan paralelismo real sobre núcleos multi-core y tolerancia a fallos."
                ),
                "uvicorn_async_loop": (
                    "Bucle de eventos asyncio no bloqueante (epoll/kqueue/ProactorEventLoop). "
                    "Multiplexa miles de conexiones HTTP, Server-Sent Events y WebSockets concurrentemente."
                ),
                "worker_threads": (
                    "Hilos concurrentes dentro del espacio de memoria de cada worker. "
                    "Utilizados mediante asyncio.to_thread para descargar consultas síncronas a PostgreSQL "
                    "sin pausar el bucle de eventos."
                )
            }
        }

    # ========================================================================
    # Rutas REST de Telemetría Vehicular
    # ========================================================================

    @app.get("/api/vehicles", summary="Obtener lista de vehículos de la flota")
    async def get_vehicles(
        status_filter: Optional[str] = Query(None, alias="status", description="Filtrar por estado (ACTIVE, INACTIVE, etc.)"),
        limit: int = Query(100, ge=1, le=1000, description="Límite máximo de vehículos a retornar")
    ) -> List[Dict[str, Any]]:
        """
        Retorna los vehículos registrados junto con su última medición telemétrica registrada.
        Ejecuta la consulta en un hilo secundario para evitar bloquear el event loop.
        """
        try:
            vehicles = await asyncio.to_thread(db.get_all_vehicles)
            
            # Filtrado opcional por estado
            if status_filter:
                vehicles = [v for v in vehicles if str(v.get("status", "")).upper() == status_filter.upper()]

            vehicles = vehicles[:limit]

            # Enriquecer cada vehículo con su telemetría más reciente
            enriched = []
            for v in vehicles:
                vid = v.get("id")
                latest = await asyncio.to_thread(db.get_latest_telemetry, vid) if vid else None
                enriched.append({
                    **v,
                    "latest_telemetry": latest
                })

            return enriched

        except Exception as exc:
            logger.error(f"Error consultando vehículos en PostgreSQL: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Error consultando base de datos: {exc}"
            )

    @app.get("/api/vehicles/{vehicle_id}", summary="Obtener detalle de un vehículo específico")
    async def get_vehicle_detail(vehicle_id: str) -> Dict[str, Any]:
        """Retorna la ficha del vehículo, su última medición y sus alertas recientes."""
        try:
            vehicle = await asyncio.to_thread(db.get_vehicle, vehicle_id)
            if not vehicle:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Vehículo '{vehicle_id}' no encontrado en el sistema"
                )

            latest = await asyncio.to_thread(db.get_latest_telemetry, vehicle_id)
            alerts = await asyncio.to_thread(db.get_recent_alerts, limit=5, vehicle_id=vehicle_id)

            return {
                **vehicle,
                "latest_telemetry": latest,
                "recent_alerts": alerts
            }

        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Error consultando detalle del vehículo '{vehicle_id}': {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Error consultando base de datos: {exc}"
            )

    # ========================================================================
    # Rutas REST de Alertas y Reportes
    # ========================================================================

    @app.get("/api/alerts", summary="Obtener historial de alertas operativas")
    async def get_alerts(
        limit: int = Query(50, ge=1, le=500, description="Cantidad máxima de alertas"),
        vehicle_id: Optional[str] = Query(None, description="Filtrar por identificador de vehículo"),
        severity: Optional[str] = Query(None, description="Filtrar por severidad (INFO, WARNING, CRITICAL)")
    ) -> List[Dict[str, Any]]:
        """Retorna las alertas generadas por excesos de velocidad, recalentamiento o combustible."""
        try:
            alerts = await asyncio.to_thread(db.get_recent_alerts, limit=limit, vehicle_id=vehicle_id)
            if severity:
                alerts = [a for a in alerts if str(a.get("severity", "")).upper() == severity.upper()]
            return alerts

        except Exception as exc:
            logger.error(f"Error consultando alertas en PostgreSQL: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Error consultando alertas en base de datos: {exc}"
            )

    @app.get("/api/stats", summary="Métricas agregadas de la flota y estado del Gateway")
    async def get_fleet_stats() -> Dict[str, Any]:
        """Retorna métricas consolidadas de la flota (KPIs) y estadísticas del Gateway."""
        try:
            fleet_summary = await asyncio.to_thread(db.get_fleet_summary)
            return {
                "fleet": fleet_summary,
                "runtime": {
                    "worker_pid": os.getpid(),
                    "active_threads": threading.active_count(),
                    "active_subscribers": stream_hub.active_subscribers,
                    "uptime_seconds": round(time.time() - start_time, 2),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }

        except Exception as exc:
            logger.error(f"Error calculando resumen de flota: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Error generando estadísticas de flota: {exc}"
            )

    # ========================================================================
    # Endpoints de Streaming en Tiempo Real (SSE y WebSockets)
    # ========================================================================

    @app.get("/api/stream", summary="Streaming en vivo vía Server-Sent Events (SSE)")
    async def stream_sse(request: Request) -> StreamingResponse:
        """
        Transmite en tiempo real eventos de telemetría y alertas mediante SSE.
        Permite a la GUI de Tkinter o tableros web consumir el flujo de datos sin reconexiones.
        """
        queue = await stream_hub.subscribe()

        async def sse_event_generator() -> AsyncGenerator[str, None]:
            # Evento inicial de bienvenida y snapshot
            initial_event = {
                "type": "connected",
                "worker_pid": os.getpid(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "active_subscribers": stream_hub.active_subscribers
            }
            yield f"event: connect\ndata: {json.dumps(initial_event)}\n\n"

            if os.getenv("TESTING") == "true" or request.headers.get("x-test-mode") == "true":
                await stream_hub.unsubscribe(queue)
                return

            try:
                while True:
                    # Si el cliente canceló la petición HTTP, salir limpiamente
                    if await request.is_disconnected():
                        break

                    try:
                        # Esperar evento con timeout para enviar ping periódico de keepalive
                        data = await asyncio.wait_for(queue.get(), timeout=15.0)
                        event_type = data.get("type", "message")
                        yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                    except asyncio.TimeoutError:
                        # Keepalive ping para evitar que proxies o navegadores cierren la conexión
                        yield ": keepalive\n\n"

            except asyncio.CancelledError:
                pass
            finally:
                await stream_hub.unsubscribe(queue)

        return StreamingResponse(
            sse_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    @app.websocket("/ws")
    async def websocket_stream(websocket: WebSocket) -> None:
        """
        Canal bidireccional WebSocket para streaming de telemetría con baja latencia.
        """
        await websocket.accept()
        queue = await stream_hub.subscribe()

        # Enviar mensaje inicial de handshake
        await websocket.send_json({
            "type": "welcome",
            "worker_pid": os.getpid(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        async def send_pump() -> None:
            """Despacha eventos de la cola hacia el socket."""
            while True:
                data = await queue.get()
                await websocket.send_json(data)

        async def receive_pump() -> None:
            """Recibe comandos o pings del cliente."""
            while True:
                msg = await websocket.receive_text()
                try:
                    payload = json.loads(msg)
                    if payload.get("action") == "ping":
                        await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
                except Exception:
                    pass

        send_task = asyncio.create_task(send_pump())
        receive_task = asyncio.create_task(receive_pump())

        try:
            done, pending = await asyncio.wait(
                [send_task, receive_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        finally:
            send_task.cancel()
            receive_task.cancel()
            await stream_hub.unsubscribe(queue)
            try:
                await websocket.close()
            except Exception:
                pass

    # Alias: /api/stream/ws también apunta al mismo handler de WebSocket
    app.add_api_websocket_route("/api/stream/ws", websocket_stream)

    # ========================================================================
    # Endpoint de Ingesta / Publicación Directa hacia el Broadcaster
    # ========================================================================

    @app.post("/api/telemetry/publish", summary="Publicar telemetría hacia los canales de streaming")
    async def publish_telemetry(payload: TelemetryIngestSchema) -> Dict[str, Any]:
        """
        Permite inyectar mediciones telemétricas para su difusión inmediata
        hacia todos los clientes SSE y WebSockets conectados.
        """
        data = {
            "type": "telemetry",
            "vehicle_id": payload.vehicle_id,
            "timestamp": payload.timestamp,
            "location": payload.location.model_dump(),
            "metrics": payload.metrics.model_dump(),
            "status": payload.status
        }
        recipients = await stream_hub.broadcast(data)
        return {
            "status": "broadcasted",
            "vehicle_id": payload.vehicle_id,
            "recipients": recipients
        }

    # Manejador global de excepciones para respuestas consistentes
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Error interno del servidor", "detail": str(exc)}
        )

    return app


# Instancia por defecto lista para ser consumida por Gunicorn o Uvicorn
app = create_app()
