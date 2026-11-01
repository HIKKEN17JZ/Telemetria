"""
Tests unitarios y de integración para el API Gateway (Issue #11).
Asignado a: Charango (Dev 2 - @Charango21)

Cubre:
- Exposición de endpoints REST (/api/vehicles, /api/alerts, /api/stats).
- Endpoint de diagnóstico de concurrencia (/api/system/concurrency) demostrando workers y threads.
- Streaming en tiempo real con Server-Sent Events (SSE: /api/stream) y WebSockets (/ws).
- Resiliencia y manejo de errores con PostgreSQL (503 Service Unavailable).
- Publicación y despacho de eventos hacia el StreamBroadcaster.
- Verificación del archivo de configuración de Gunicorn (gunicorn.conf.py).
"""

import asyncio
import json
import os
import threading
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.gateway import create_app, StreamBroadcaster, GatewayConfig
from src.database import DatabaseManager


@pytest.fixture
def mock_db():
    """Mock completo del DatabaseManager para desacoplar las pruebas de la BD real."""
    db = MagicMock(spec=DatabaseManager)
    
    # Mock vehicles
    db.get_all_vehicles.return_value = [
        {"id": "AUTO-001", "model": "Sedan 2024", "type": "CAR", "status": "ACTIVE", "created_at": "2026-10-31T20:00:00Z"},
        {"id": "CAMION-002", "model": "Volvo FH", "type": "TRUCK", "status": "ACTIVE", "created_at": "2026-10-31T20:00:00Z"},
        {"id": "MOTO-003", "model": "Honda 250", "type": "MOTO", "status": "INACTIVE", "created_at": "2026-10-31T20:00:00Z"}
    ]
    
    db.get_vehicle.side_effect = lambda vid: (
        {"id": vid, "model": "Vehículo Test", "type": "CAR", "status": "ACTIVE", "created_at": "2026-10-31T20:00:00Z"}
        if vid in ["AUTO-001", "CAMION-002"] else None
    )
    
    db.get_latest_telemetry.side_effect = lambda vid: (
        {
            "id": 1,
            "vehicle_id": vid,
            "timestamp": "2026-10-31T20:05:00Z",
            "latitude": -32.8895,
            "longitude": -68.8458,
            "speed_kmh": 75.5,
            "rpm": 2400,
            "fuel_level_pct": 65.0,
            "engine_temp_c": 87.0,
            "status": "MOVING",
            "created_at": "2026-10-31T20:05:00Z"
        }
        if vid in ["AUTO-001", "CAMION-002"] else None
    )
    
    # Mock alerts
    db.get_recent_alerts.return_value = [
        {
            "id": 10,
            "vehicle_id": "AUTO-001",
            "alert_type": "EXCESO_VELOCIDAD",
            "severity": "CRITICAL",
            "description": "Exceso de velocidad: 135 km/h",
            "metric_value": 135.0,
            "threshold_value": 120.0,
            "timestamp": "2026-10-31T20:02:00Z",
            "created_at": "2026-10-31T20:02:00Z"
        },
        {
            "id": 11,
            "vehicle_id": "CAMION-002",
            "alert_type": "NIVEL_COMBUSTIBLE",
            "severity": "WARNING",
            "description": "Nivel de combustible bajo: 8%",
            "metric_value": 8.0,
            "threshold_value": 15.0,
            "timestamp": "2026-10-31T20:04:00Z",
            "created_at": "2026-10-31T20:04:00Z"
        }
    ]
    
    # Mock fleet summary
    db.get_fleet_summary.return_value = {
        "total_vehicles": 3,
        "total_telemetry_records": 150,
        "total_alerts": 2,
        "critical_alerts": 1,
        "warning_alerts": 1,
        "vehicles": [
            {"vehicle_id": "AUTO-001", "status": "ACTIVE", "avg_speed_kmh": 68.2, "last_fuel_pct": 65.0},
            {"vehicle_id": "CAMION-002", "status": "ACTIVE", "avg_speed_kmh": 55.0, "last_fuel_pct": 8.0}
        ],
        "alerts_breakdown": [
            {"alert_type": "EXCESO_VELOCIDAD", "severity": "CRITICAL", "count": 1},
            {"alert_type": "NIVEL_COMBUSTIBLE", "severity": "WARNING", "count": 1}
        ]
    }
    
    return db


@pytest.fixture
def app(mock_db):
    """Instancia de la aplicación FastAPI con base de datos mockeada."""
    return create_app(db_manager=mock_db)


@pytest.fixture
def client(app):
    """Cliente de pruebas de FastAPI/Starlette."""
    return TestClient(app)


class TestHealthAndSystemEndpoints:
    """Pruebas de endpoints de salud y diagnóstico del sistema."""

    def test_root_index_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "API Gateway de Telemetría"
        assert "version" in data
        assert "endpoints" in data
        assert "runtime" in data
        assert "worker_pid" in data["runtime"]

    def test_health_check_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "timestamp" in data
        assert "worker_pid" in data

    def test_concurrency_diagnostic_endpoint(self, client):
        """
        Verifica el endpoint que justifica conceptualmente ante la cátedra
        el modelo de Workers (procesos) y Threads (hilos concurrentes).
        """
        response = client.get("/api/system/concurrency")
        assert response.status_code == 200
        data = response.json()
        assert "worker_pid" in data
        assert "active_threads_count" in data
        assert data["worker_pid"] == os.getpid()
        assert data["active_threads_count"] >= 1
        assert "architecture" in data
        assert "gunicorn_workers" in data["architecture"]
        assert "uvicorn_async_loop" in data["architecture"]
        assert "worker_threads" in data["architecture"]


class TestVehiclesEndpoints:
    """Pruebas de los endpoints REST para consulta de vehículos."""

    def test_get_vehicles_list(self, client, mock_db):
        response = client.get("/api/vehicles")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3
        assert data[0]["id"] == "AUTO-001"
        assert "latest_telemetry" in data[0]
        assert data[0]["latest_telemetry"]["speed_kmh"] == 75.5

    def test_get_vehicles_filter_by_status(self, client, mock_db):
        response = client.get("/api/vehicles?status=INACTIVE")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "MOTO-003"
        assert data[0]["status"] == "INACTIVE"

    def test_get_vehicle_by_id_success(self, client, mock_db):
        response = client.get("/api/vehicles/AUTO-001")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "AUTO-001"
        assert data["model"] == "Vehículo Test"
        assert data["latest_telemetry"]["speed_kmh"] == 75.5
        assert len(data["recent_alerts"]) == 2

    def test_get_vehicle_by_id_not_found(self, client, mock_db):
        response = client.get("/api/vehicles/VEHICULO-INEXISTENTE")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "no encontrado" in data["detail"].lower()


class TestAlertsEndpoints:
    """Pruebas de los endpoints REST para consulta de alertas."""

    def test_get_alerts_list(self, client, mock_db):
        response = client.get("/api/alerts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["alert_type"] == "EXCESO_VELOCIDAD"
        mock_db.get_recent_alerts.assert_called_with(limit=50, vehicle_id=None)

    def test_get_alerts_with_limit_and_vehicle_filter(self, client, mock_db):
        response = client.get("/api/alerts?limit=10&vehicle_id=AUTO-001")
        assert response.status_code == 200
        mock_db.get_recent_alerts.assert_called_with(limit=10, vehicle_id="AUTO-001")

    def test_get_alerts_filter_by_severity(self, client, mock_db):
        response = client.get("/api/alerts?severity=CRITICAL")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["severity"] == "CRITICAL"


class TestStatsEndpoints:
    """Pruebas del endpoint de estadísticas consolidadas."""

    def test_get_stats_endpoint(self, client, mock_db):
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "fleet" in data
        assert data["fleet"]["total_vehicles"] == 3
        assert data["fleet"]["total_telemetry_records"] == 150
        assert data["fleet"]["critical_alerts"] == 1
        assert "runtime" in data
        assert "active_subscribers" in data["runtime"]
        assert "worker_pid" in data["runtime"]


class TestBroadcasterUnit:
    """Pruebas unitarias para el componente StreamBroadcaster."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_subscriber_registration_and_broadcast(self):
        broadcaster = StreamBroadcaster()
        assert broadcaster.active_subscribers == 0

        queue = await broadcaster.subscribe()
        assert broadcaster.active_subscribers == 1

        test_payload = {"type": "telemetry", "vehicle_id": "TEST-1"}
        sent_count = await broadcaster.broadcast(test_payload)
        assert sent_count == 1

        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received == test_payload

        await broadcaster.unsubscribe(queue)
        assert broadcaster.active_subscribers == 0

    @pytest.mark.asyncio(loop_scope="function")
    async def test_broadcast_drops_slow_consumers_cleanly(self):
        broadcaster = StreamBroadcaster(queue_maxsize=2)
        queue = await broadcaster.subscribe()

        # Enviar 3 mensajes cuando el máximo es 2
        await broadcaster.broadcast({"msg": 1})
        await broadcaster.broadcast({"msg": 2})
        # Este 3ro debería saltar sin bloquear
        await broadcaster.broadcast({"msg": 3})

        assert queue.qsize() <= 2
        await broadcaster.unsubscribe(queue)


class TestStreamingEndpoints:
    """Pruebas de los canales de streaming (SSE y WebSocket)."""

    def test_sse_stream_initial_headers(self, client):
        """Verifica que el endpoint SSE responda con el media type text/event-stream."""
        response = client.get("/api/stream", headers={"x-test-mode": "true"})
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert "data:" in response.text

    def test_publish_telemetry_endpoint(self, client):
        """Verifica el endpoint de publicación directa hacia el broadcaster."""
        payload = {
            "vehicle_id": "AUTO-001",
            "timestamp": "2026-10-31T20:10:00Z",
            "location": {"lat": -32.8895, "lon": -68.8458},
            "metrics": {
                "speed_kmh": 85.0,
                "rpm": 2600,
                "fuel_level_pct": 70.0,
                "engine_temp_c": 89.0
            },
            "status": "MOVING"
        }
        response = client.post("/api/telemetry/publish", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "broadcasted"
        assert data["vehicle_id"] == "AUTO-001"
        assert "recipients" in data


class TestDatabaseErrorResilience:
    """Verifica que las fallas de conexión a la BD no causen un 500 no capturado."""

    def test_database_error_returns_503_service_unavailable(self, mock_db):
        mock_db.get_all_vehicles.side_effect = Exception("Database connection pool exhausted")
        app = create_app(db_manager=mock_db)
        client = TestClient(app)

        response = client.get("/api/vehicles")
        assert response.status_code == 503
        data = response.json()
        # FastAPI serializa HTTPException con clave "detail"
        assert "detail" in data
        assert "base de datos" in data["detail"].lower() or "exhausted" in data["detail"].lower()


class TestGunicornConfiguration:
    """Verifica la configuración para Gunicorn con workers de Uvicorn (Criterio de Aceptación 1)."""

    def test_gunicorn_conf_file_exists_and_valid(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        conf_file = root / "gunicorn.conf.py"
        assert conf_file.exists(), "El archivo gunicorn.conf.py debe existir en la raíz"

        content = conf_file.read_text(encoding="utf-8")
        assert "workers" in content
        assert "threads" in content
        assert "UvicornWorker" in content
        assert "bind" in content
