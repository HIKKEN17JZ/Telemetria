"""
Pruebas de Integración y Multithreading para la GUI de Tkinter (Issue #12).
Asignado a: Ale (Dev 1 - @HIKKEN17JZ)

Valida:
- Consumo seguro de eventos de red en queue.Queue mediante root.after().
- Actualización reactiva del indicador visual de conectividad (🟢 Conectado / 🔴 Desconectado / 🟡 Reconectando).
- Inyección asíncrona de telemetría y actualización fluida de Treeviews y KPIs sin race conditions.
- Manejo de alertas críticas en el Treeview de eventos sin congelar la interfaz.
- Detención y limpieza de hilos secundarios al cerrar la ventana principal.
"""

import queue
import time
import tkinter as tk
import unittest
from unittest.mock import MagicMock

from src.dashboard_model import FleetDashboardState
from src.dashboard_gui import FleetDashboardView
from src.dashboard_network import (
    ConnectionState,
    EventType,
    NetworkEvent,
    DashboardNetworkReceiver
)
from src.models import TelemetryPayload


class TestDashboardMultithreadingGUI(unittest.TestCase):
    """Pruebas del consumidor multithreading en FleetDashboardView."""

    def setUp(self):
        try:
            self.root = tk.Tk()
            self.root.withdraw()  # Ocultar ventana física durante pruebas
        except tk.TclError:
            self.skipTest("Entorno gráfico sin display disponible (TclError)")

        self.event_queue = queue.Queue()
        self.state = FleetDashboardState(speed_limit_kmh=120.0, temp_critical_c=100.0)

        # Mock del receptor de red
        self.mock_receiver = MagicMock(spec=DashboardNetworkReceiver)
        self.mock_receiver.is_alive.return_value = True

        self.view = FleetDashboardView(
            root=self.root,
            state=self.state,
            network_receiver=self.mock_receiver,
            event_queue=self.event_queue,
            auto_poll_queue=False  # Control manual del polling en pruebas
        )

    def tearDown(self):
        try:
            self.view.destroy()
        except Exception:
            pass

    def test_connection_status_indicator_initial_state(self):
        """Verifica que el componente visual de estado de conexión existe y tiene valores iniciales."""
        self.assertIsNotNone(self.view.lbl_connection_badge)
        self.assertIsNotNone(self.view.lbl_connection_detail)

    def test_status_event_updates_connection_badge(self):
        """Un evento STATUS debe actualizar la etiqueta visual a verde, amarillo o rojo."""
        # 1. Simular evento CONECTADO
        self.event_queue.put(NetworkEvent(
            event_type=EventType.STATUS,
            data={
                "state": ConnectionState.CONNECTED.value,
                "message": "Conectado vía SSE en tiempo real",
                "url": "http://127.0.0.1:8000"
            }
        ))
        self.view.process_queue_events()

        badge_text = self.view.lbl_connection_badge.cget("text")
        self.assertIn("EN LÍNEA", badge_text)

        # 2. Simular evento RECONECTANDO
        self.event_queue.put(NetworkEvent(
            event_type=EventType.STATUS,
            data={
                "state": ConnectionState.RECONNECTING.value,
                "message": "Reintentando conexión...",
                "url": "http://127.0.0.1:8000"
            }
        ))
        self.view.process_queue_events()

        badge_text = self.view.lbl_connection_badge.cget("text")
        self.assertIn("RECONECTANDO", badge_text)

        # 3. Simular evento DESCONECTADO
        self.event_queue.put(NetworkEvent(
            event_type=EventType.STATUS,
            data={
                "state": ConnectionState.DISCONNECTED.value,
                "message": "Servidor fuera de línea",
                "url": "http://127.0.0.1:8000"
            }
        ))
        self.view.process_queue_events()

        badge_text = self.view.lbl_connection_badge.cget("text")
        self.assertIn("DESCONECTADO", badge_text)

    def test_telemetry_event_from_queue_updates_model_and_table(self):
        """Un evento TELEMETRY encolado desde el hilo de red actualiza la tabla de vehículos."""
        payload = TelemetryPayload.create(
            vehicle_id="AUTO-001",
            lat=-32.8895,
            lon=-68.8458,
            speed_kmh=80.0,
            rpm=2300,
            fuel_level_pct=90.0,
            engine_temp_c=86.0,
            status="MOVING"
        )
        self.event_queue.put(NetworkEvent(
            event_type=EventType.TELEMETRY,
            data=payload
        ))

        # Procesar cola en el hilo principal de Tkinter
        self.view.process_queue_events()

        # Verificar que el modelo contiene el vehículo
        vehicle = self.state.get_vehicle("AUTO-001")
        self.assertIsNotNone(vehicle)
        self.assertEqual(vehicle.speed_kmh, 80.0)

        # Verificar que la fila en el Treeview fue creada
        items = self.view.vehicle_tree.get_children()
        self.assertEqual(len(items), 1)
        row_values = self.view.vehicle_tree.item(items[0], "values")
        self.assertEqual(row_values[0], "AUTO-001")
        self.assertEqual(row_values[2], "80.0")

    def test_alert_event_from_queue_updates_alerts_table(self):
        """Un evento ALERT encolado actualiza la tabla de eventos críticos."""
        alert_dict = {
            "vehicle_id": "CAMION-002",
            "severity": "CRITICAL",
            "alert_type": "HIGH_ENGINE_TEMP",
            "description": "Temperatura de motor crítica: 108.5°C",
            "timestamp": "2026-11-10T21:00:00Z"
        }
        self.event_queue.put(NetworkEvent(
            event_type=EventType.ALERT,
            data=alert_dict
        ))

        self.view.process_queue_events()

        # Verificar que el Treeview de alertas contiene el registro
        items = self.view.alerts_tree.get_children()
        self.assertEqual(len(items), 1)
        row_values = self.view.alerts_tree.item(items[0], "values")
        self.assertEqual(row_values[1], "CAMION-002")
        self.assertEqual(row_values[2], "CRITICAL")
        self.assertEqual(row_values[3], "HIGH_ENGINE_TEMP")

    def test_window_close_stops_network_receiver(self):
        """Cerrar la ventana debe invocar stop() sobre el receptor de red secundario."""
        self.view.on_close()
        self.mock_receiver.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()

