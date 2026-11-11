"""
Prueba de Integración End-to-End Multithreading para el Dashboard (Issue #12).
Asignado a: Ale (Dev 1 - @HIKKEN17JZ)

Valida el ciclo de vida completo:
- Servidor HTTP mock (simula el API Gateway con SSE y REST).
- Hilo secundario DashboardNetworkReceiver consumiendo SSE y entregando en queue.Queue.
- Bucle de Tkinter consumiendo de la cola y actualizando Treeviews y KPIs.
- Apagado limpio y coordinado de ambos hilos.
"""

import http.server
import json
import queue
import socketserver
import threading
import time
import tkinter as tk
import unittest

from src.dashboard_model import FleetDashboardState
from src.dashboard_gui import FleetDashboardView
from src.dashboard_network import (
    ConnectionState,
    DashboardNetworkReceiver,
    NetworkReceiverConfig
)


class MockGatewayHandler(http.server.BaseHTTPRequestHandler):
    """Manejador HTTP ligero para simular el API Gateway."""

    def log_message(self, format, *args):
        pass  # Silenciar logs en consola de pruebas

    def do_GET(self):
        if self.path.startswith("/api/vehicles"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = [
                {
                    "id": "MOCK-001",
                    "status": "ACTIVE",
                    "latest_telemetry": {
                        "vehicle_id": "MOCK-001",
                        "latitude": -32.8895,
                        "longitude": -68.8458,
                        "speed": 72.5,
                        "rpm": 2400,
                        "fuel_level": 88.0,
                        "engine_temp": 84.0,
                        "status": "MOVING",
                        "timestamp": "2026-11-10T22:00:00Z"
                    }
                }
            ]
            self.wfile.write(json.dumps(data).encode("utf-8"))
        elif self.path.startswith("/api/alerts"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = [
                {
                    "vehicle_id": "MOCK-001",
                    "severity": "CRITICAL",
                    "alert_type": "EXCESS_SPEED",
                    "description": "Velocidad 125 km/h detectada",
                    "timestamp": "2026-11-10T22:00:01Z",
                    "metric_value": 125.0,
                    "threshold_value": 120.0
                }
            ]
            self.wfile.write(json.dumps(data).encode("utf-8"))
        elif self.path.startswith("/api/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            # Enviar evento connect y una telemetría en streaming
            event_1 = "event: connect\ndata: {\"status\": \"ok\"}\n\n"
            self.wfile.write(event_1.encode("utf-8"))
            self.wfile.flush()

            time.sleep(0.05)
            telemetry_data = {
                "type": "telemetry",
                "vehicle_id": "STREAM-99",
                "timestamp": "2026-11-10T22:00:02Z",
                "location": {"lat": -32.90, "lon": -68.85},
                "metrics": {
                    "speed_kmh": 95.0,
                    "rpm": 2800,
                    "fuel_level_pct": 65.0,
                    "engine_temp_c": 89.0
                },
                "status": "MOVING"
            }
            event_2 = f"event: telemetry\ndata: {json.dumps(telemetry_data)}\n\n"
            self.wfile.write(event_2.encode("utf-8"))
            self.wfile.flush()

            # Mantener conexión brevemente
            time.sleep(0.1)
        else:
            self.send_response(404)
            self.end_headers()


class TestDashboardE2EMultithreading(unittest.TestCase):
    """Prueba de integración end-to-end con servidor HTTP mock y multithreading real."""

    @classmethod
    def setUpClass(cls):
        # Iniciar servidor mock en un puerto efímero del SO (port 0)
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), MockGatewayHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except tk.TclError:
            self.skipTest("Entorno gráfico no disponible (TclError)")

        self.event_queue = queue.Queue()
        self.state = FleetDashboardState(speed_limit_kmh=120.0, temp_critical_c=100.0)

        self.config = NetworkReceiverConfig(
            gateway_url=f"http://127.0.0.1:{self.port}",
            poll_interval=0.1,
            reconnect_backoff_base=0.05,
            reconnect_backoff_max=0.2,
            request_timeout=0.5,
            stream_mode="stream"
        )
        self.receiver = DashboardNetworkReceiver(config=self.config, event_queue=self.event_queue)

        self.view = FleetDashboardView(
            root=self.root,
            state=self.state,
            network_receiver=self.receiver,
            event_queue=self.event_queue,
            auto_poll_queue=False
        )

    def tearDown(self):
        if self.receiver.is_alive():
            self.receiver.stop()
            self.receiver.join(timeout=1.0)
        try:
            self.view.destroy()
        except Exception:
            pass

    def test_e2e_stream_and_gui_consumption(self):
        """El hilo de red consume del servidor mock y la GUI procesa los eventos reactivamente."""
        self.receiver.start()

        # Dar tiempo al hilo para conectar y transmitir los eventos mock
        time.sleep(0.25)

        # Procesar los eventos acumulados en la cola de la interfaz
        processed = self.view.process_queue_events()
        self.assertGreater(processed, 0)

        # Verificar que la conexión pasó a EN LÍNEA
        badge_text = self.view.lbl_connection_badge.cget("text")
        self.assertIn("EN LÍNEA", badge_text)

        # Verificar que los vehículos (inicial y streaming) fueron cargados
        vehicles = self.state.get_vehicles()
        vehicle_ids = [v.vehicle_id for v in vehicles]
        self.assertIn("MOCK-001", vehicle_ids)
        self.assertIn("STREAM-99", vehicle_ids)

        # Verificar que la alerta crítica fue agregada al estado
        alerts = self.state.get_alerts()
        self.assertTrue(any(a.vehicle_id == "MOCK-001" and a.severity.value == "CRITICAL" for a in alerts))

        # Verificar actualización en Treeviews de la vista
        vehicle_items = self.view.vehicle_tree.get_children()
        self.assertEqual(len(vehicle_items), len(vehicles))

        alert_items = self.view.alerts_tree.get_children()
        self.assertGreaterEqual(len(alert_items), 1)


if __name__ == "__main__":
    unittest.main()

