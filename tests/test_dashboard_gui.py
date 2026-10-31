"""
Tests unitarios y de integración para la interfaz gráfica Tkinter (TDD - Issue #10).
Verifica renderizado de componentes, inserción de filas en Treeview y manejo de tags de color.
"""

import unittest
import tkinter as tk
from src.dashboard_model import FleetDashboardState, AlertSeverity
from src.dashboard_gui import FleetDashboardView
from src.models import TelemetryPayload


class TestFleetDashboardGUI(unittest.TestCase):

    def setUp(self):
        # Crear ventana oculta para testing sin abrir ventana gráfica en pantalla
        self.root = tk.Tk()
        self.root.withdraw()
        self.state = FleetDashboardState()
        self.view = FleetDashboardView(root=self.root, state=self.state)

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_gui_initialization_structure(self):
        """Verifica que los paneles y widgets principales se inicialicen correctamente."""
        self.assertIsNotNone(self.view.header_frame)
        self.assertIsNotNone(self.view.vehicle_tree)
        self.assertIsNotNone(self.view.alerts_tree)
        self.assertEqual(len(self.view.vehicle_tree.get_children()), 0)
        self.assertEqual(len(self.view.alerts_tree.get_children()), 0)

    def test_vehicle_tree_update_and_styling(self):
        """Verifica que al actualizar telemetría la tabla refleje la fila y asigne tags adecuados."""
        payload = TelemetryPayload.create(
            vehicle_id="AUTO-001",
            lat=-32.8895,
            lon=-68.8458,
            speed_kmh=135.0,  # Exceso de velocidad (>120)
            rpm=3200,
            fuel_level_pct=85.0,
            engine_temp_c=88.0,
            status="MOVING"
        )
        self.state.update_telemetry(payload)
        self.view.refresh_views()

        # Debe existir 1 vehículo en la tabla
        children = self.view.vehicle_tree.get_children()
        self.assertEqual(len(children), 1)

        item = self.view.vehicle_tree.item(children[0])
        self.assertEqual(item["values"][0], "AUTO-001")
        self.assertIn("135.0", str(item["values"][2]))
        # Tag de alerta crítica por velocidad
        self.assertIn("critical", item["tags"])

    def test_alerts_tree_update(self):
        """Verifica que las alertas se listen con su severidad y formato."""
        payload = TelemetryPayload.create(
            vehicle_id="AUTO-HOT",
            lat=-32.88,
            lon=-68.84,
            speed_kmh=50.0,
            rpm=2000,
            fuel_level_pct=90.0,
            engine_temp_c=106.0,  # Recalentamiento crítico
            status="MOVING"
        )
        self.state.update_telemetry(payload)
        self.view.refresh_views()

        alerts = self.view.alerts_tree.get_children()
        self.assertGreaterEqual(len(alerts), 1)

        first_alert = self.view.alerts_tree.item(alerts[0])
        self.assertEqual(first_alert["values"][1], "AUTO-HOT")
        self.assertEqual(first_alert["values"][2], "CRITICAL")
        self.assertIn("CRITICAL", first_alert["tags"])

    def test_summary_kpi_cards_update(self):
        """Verifica que las tarjetas KPI del encabezado muestren los totales correctos."""
        self.state.update_telemetry(
            TelemetryPayload.create("AUTO-1", -32.8, -68.8, 60.0, 2000, 80.0, 85.0, "MOVING")
        )
        self.state.update_telemetry(
            TelemetryPayload.create("AUTO-2", -32.9, -68.9, 130.0, 3000, 70.0, 90.0, "MOVING")
        )
        self.view.refresh_views()

        self.assertEqual(self.view.lbl_total_vehicles.cget("text"), "2")
        self.assertEqual(self.view.lbl_active_vehicles.cget("text"), "2")
        self.assertEqual(self.view.lbl_avg_speed.cget("text"), "95.0 km/h")
        self.assertEqual(self.view.lbl_critical_alerts.cget("text"), "1")


if __name__ == "__main__":
    unittest.main()

