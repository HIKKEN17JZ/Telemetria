"""
Pruebas Unitarias para la Capa de Red Multithreading del Dashboard (Issue #12).
Asignado a: Ale (Dev 1 - @HIKKEN17JZ)

Valida:
- Estados de conexión (ConnectionState) y eventos thread-safe (NetworkEvent).
- Parser de Server-Sent Events (SSE) y deserialización de telemetría/alertas.
- Hilo secundario (daemon thread) con entrega segura en queue.Queue.
- Estrategia de reconexión con retroceso exponencial ante caídas del servidor.
- Consulta de endpoints REST (/api/vehicles, /api/alerts) e inicialización de estado.
- Apagado ordenado y liberación de recursos en stop().
"""

import json
import queue
import time
import unittest
from unittest.mock import MagicMock, patch

from src.dashboard_network import (
    ConnectionState,
    NetworkEvent,
    EventType,
    SSEParser,
    DashboardNetworkReceiver,
    NetworkReceiverConfig
)
from src.models import TelemetryPayload


class TestSSEParser(unittest.TestCase):
    """Pruebas del parser de eventos Server-Sent Events (SSE)."""

    def test_parse_single_telemetry_event(self):
        raw_lines = [
            "event: telemetry\n",
            'data: {"type": "telemetry", "vehicle_id": "AUTO-001", "metrics": {"speed_kmh": 85.5}}\n',
            "\n"
        ]
        events = SSEParser.parse_chunk("".join(raw_lines))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "telemetry")
        self.assertEqual(events[0]["data"]["vehicle_id"], "AUTO-001")
        self.assertEqual(events[0]["data"]["metrics"]["speed_kmh"], 85.5)

    def test_parse_multiple_events_in_single_chunk(self):
        chunk = (
            "event: connect\n"
            'data: {"status": "ok"}\n\n'
            "event: alert\n"
            'data: {"vehicle_id": "CAMION-002", "severity": "CRITICAL", "description": "Overheat"}\n\n'
        )
        events = SSEParser.parse_chunk(chunk)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event"], "connect")
        self.assertEqual(events[1]["event"], "alert")
        self.assertEqual(events[1]["data"]["severity"], "CRITICAL")

    def test_parse_keepalive_comment(self):
        chunk = ": keepalive\n\n"
        events = SSEParser.parse_chunk(chunk)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "keepalive")

    def test_parse_incomplete_chunk_buffers_remainder(self):
        parser = SSEParser()
        # Primer fragmento incompleto
        events_1 = parser.feed("event: telemetry\ndata: {\"vehicle_id\": ")
        self.assertEqual(len(events_1), 0)

        # Segundo fragmento completando el mensaje
        events_2 = parser.feed("\"AUTO-001\"}\n\n")
        self.assertEqual(len(events_2), 1)
        self.assertEqual(events_2[0]["data"]["vehicle_id"], "AUTO-001")


class TestNetworkReceiverUnit(unittest.TestCase):
    """Pruebas unitarias de DashboardNetworkReceiver y manejo de hilos."""

    def setUp(self):
        self.event_queue = queue.Queue()
        self.config = NetworkReceiverConfig(
            gateway_url="http://127.0.0.1:8000",
            poll_interval=0.1,
            reconnect_backoff_base=0.05,
            reconnect_backoff_max=0.2
        )
        self.receiver = DashboardNetworkReceiver(
            config=self.config,
            event_queue=self.event_queue
        )

    def tearDown(self):
        if self.receiver.is_alive():
            self.receiver.stop()
            self.receiver.join(timeout=1.0)

    def test_thread_is_daemon_and_initially_disconnected(self):
        self.assertTrue(self.receiver.daemon)
        self.assertEqual(self.receiver.state, ConnectionState.DISCONNECTED)
        self.assertFalse(self.receiver.is_alive())

    def test_state_change_pushes_status_event_to_queue(self):
        self.receiver.set_state(ConnectionState.CONNECTING, message="Conectando al Gateway...")
        self.assertEqual(self.receiver.state, ConnectionState.CONNECTING)

        event: NetworkEvent = self.event_queue.get_nowait()
        self.assertEqual(event.event_type, EventType.STATUS)
        self.assertEqual(event.data["state"], ConnectionState.CONNECTING.value)
        self.assertEqual(event.data["message"], "Conectando al Gateway...")

    def test_enqueue_telemetry_event(self):
        raw_telemetry = {
            "type": "telemetry",
            "vehicle_id": "AUTO-001",
            "timestamp": "2026-11-10T20:00:00Z",
            "location": {"lat": -32.8895, "lon": -68.8458},
            "metrics": {
                "speed_kmh": 65.2,
                "rpm": 2200,
                "fuel_level_pct": 80.0,
                "engine_temp_c": 85.0
            },
            "status": "MOVING"
        }
        self.receiver.dispatch_telemetry(raw_telemetry)

        event: NetworkEvent = self.event_queue.get_nowait()
        self.assertEqual(event.event_type, EventType.TELEMETRY)
        self.assertIsInstance(event.data, TelemetryPayload)
        self.assertEqual(event.data.vehicle_id, "AUTO-001")
        self.assertEqual(event.data.metrics.speed_kmh, 65.2)

    def test_enqueue_alert_event(self):
        alert_dict = {
            "vehicle_id": "CAMION-002",
            "severity": "CRITICAL",
            "alert_type": "EXCESS_SPEED",
            "description": "Velocidad 135 km/h detectada",
            "timestamp": "2026-11-10T20:00:00Z"
        }
        self.receiver.dispatch_alert(alert_dict)

        event: NetworkEvent = self.event_queue.get_nowait()
        self.assertEqual(event.event_type, EventType.ALERT)
        self.assertEqual(event.data["vehicle_id"], "CAMION-002")
        self.assertEqual(event.data["severity"], "CRITICAL")

    @patch("urllib.request.urlopen")
    def test_fetch_initial_state_success(self, mock_urlopen):
        # Mock para /api/vehicles
        vehicles_response = MagicMock()
        vehicles_response.read.return_value = json.dumps([
            {
                "id": "AUTO-001",
                "status": "ACTIVE",
                "latest_telemetry": {
                    "vehicle_id": "AUTO-001",
                    "latitude": -32.89,
                    "longitude": -68.84,
                    "speed": 50.0,
                    "rpm": 2000,
                    "fuel_level": 75.0,
                    "engine_temp": 82.0,
                    "status": "MOVING",
                    "timestamp": "2026-11-10T20:00:00Z"
                }
            }
        ]).encode("utf-8")

        mock_urlopen.return_value.__enter__.return_value = vehicles_response

        vehicles = self.receiver.fetch_vehicles()
        self.assertEqual(len(vehicles), 1)
        self.assertEqual(vehicles[0]["id"], "AUTO-001")

    @patch("urllib.request.urlopen")
    def test_fetch_alerts_success(self, mock_urlopen):
        alerts_response = MagicMock()
        alerts_response.read.return_value = json.dumps([
            {
                "vehicle_id": "CAMION-002",
                "severity": "WARNING",
                "alert_type": "LOW_FUEL",
                "description": "Combustible 8% restante",
                "timestamp": "2026-11-10T20:00:00Z"
            }
        ]).encode("utf-8")

        mock_urlopen.return_value.__enter__.return_value = alerts_response

        alerts = self.receiver.fetch_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["vehicle_id"], "CAMION-002")

    def test_graceful_stop_terminates_loop(self):
        self.receiver.config.request_timeout = 0.1
        self.receiver.config.reconnect_backoff_base = 0.05
        self.receiver.start()
        self.assertTrue(self.receiver.is_alive())
        time.sleep(0.05)

        self.receiver.stop()
        self.receiver.join(timeout=2.0)
        self.assertFalse(self.receiver.is_alive())
        self.assertEqual(self.receiver.state, ConnectionState.DISCONNECTED)


if __name__ == "__main__":
    unittest.main()
