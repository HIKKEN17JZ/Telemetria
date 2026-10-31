"""
Tests unitarios TDD para el Issue #8:
- Despacho asíncrono a Celery (non-blocking para asyncio).
- IPC mediante Señales UNIX (SIGHUP para hot-reload de config y SIGUSR1 para dump de métricas).
- Robustez y compatibilidad multiplataforma.
"""

import asyncio
import os
import signal
from unittest.mock import MagicMock, patch
import pytest

from server import (
    ServerConfig,
    ServerMetrics,
    dispatch_telemetry_task,
    handle_sighup,
    handle_sigusr1,
    setup_signal_handlers,
    active_clients
)
from src.protocol import TelemetryFrame
from src.models import Location, VehicleMetrics


@pytest.fixture
def sample_frame():
    return TelemetryFrame(
        vehicle_id="AUTO-001",
        timestamp="2026-10-31T20:00:00Z",
        location=Location(lat=-32.8895, lon=-68.8458),
        metrics=VehicleMetrics(
            speed_kmh=80.0,
            rpm=2500,
            fuel_level_pct=75.0,
            engine_temp_c=90.0
        ),
        status="MOVING"
    )


class TestCeleryAsyncDispatch:
    """Pruebas para el despacho no bloqueante hacia Celery."""

    @pytest.mark.asyncio
    async def test_dispatch_telemetry_task_calls_celery_in_executor(self, sample_frame):
        """Verifica que el despacho a Celery use el executor del loop sin bloquear."""
        mock_task = MagicMock()
        mock_task.delay.return_value = MagicMock(id="celery-job-123")

        with patch("server.process_telemetry", mock_task):
            task_id = await dispatch_telemetry_task(sample_frame)
            assert task_id == "celery-job-123"
            mock_task.delay.assert_called_once()
            called_arg = mock_task.delay.call_args[0][0]
            assert called_arg["vehicle_id"] == "AUTO-001"
            assert called_arg["metrics"]["speed_kmh"] == 80.0

    @pytest.mark.asyncio
    async def test_dispatch_telemetry_task_handles_celery_error_gracefully(self, sample_frame):
        """Si Celery/Redis falla o no está disponible, no debe tumbar el servidor ni corromper el flujo."""
        mock_task = MagicMock()
        mock_task.delay.side_effect = ConnectionError("Redis broker unreachable")

        with patch("server.process_telemetry", mock_task):
            task_id = await dispatch_telemetry_task(sample_frame)
            assert task_id is None  # Error capturado limpiamente


class TestServerMetrics:
    """Pruebas para la recopilación de métricas de telemetría."""

    def test_metrics_increment_and_dump(self):
        metrics = ServerMetrics()
        metrics.record_message_received()
        metrics.record_message_processed()
        metrics.record_message_error()

        stats = metrics.get_stats(active_client_count=2)
        assert stats["total_received"] == 1
        assert stats["total_processed"] == 1
        assert stats["total_errors"] == 1
        assert stats["active_clients"] == 2
        assert "uptime_seconds" in stats


class TestIPCSignals:
    """Pruebas para el manejo de señales UNIX (SIGHUP y SIGUSR1)."""

    def test_handle_sighup_reloads_config(self):
        """Verifica que SIGHUP recargue configuraciones dinámicas (hot-reload)."""
        config = ServerConfig()
        config.log_level = "INFO"

        with patch.dict(os.environ, {"TELEMETRY_LOG_LEVEL": "DEBUG"}):
            handle_sighup(config)
            assert config.log_level == "DEBUG"

    def test_handle_sigusr1_dumps_metrics(self):
        """Verifica que SIGUSR1 obtenga y loguee las métricas del servidor."""
        metrics = ServerMetrics()
        metrics.record_message_received()
        metrics.record_message_processed()

        with patch("server.logger.info") as mock_log:
            handle_sigusr1(metrics, active_client_count=3)
            mock_log.assert_called()
            log_text = " ".join([call.args[0] for call in mock_log.call_args_list if call.args])
            assert "Estadísticas operativas" in log_text or "total_processed" in log_text

    def test_setup_signal_handlers_registers_on_posix(self):
        """Verifica el registro de señales en event loop si el sistema operativo soporta señales UNIX."""
        loop = asyncio.new_event_loop()
        config = ServerConfig()
        metrics = ServerMetrics()

        if hasattr(signal, "SIGHUP") and hasattr(signal, "SIGUSR1") and hasattr(loop, "add_signal_handler"):
            with patch.object(loop, "add_signal_handler") as mock_add_handler:
                setup_signal_handlers(loop, config, metrics)
                assert mock_add_handler.call_count >= 2
        else:
            setup_signal_handlers(loop, config, metrics)
        loop.close()
