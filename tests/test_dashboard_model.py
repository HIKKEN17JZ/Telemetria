"""
Tests unitarios para el modelo y estado del Dashboard de Telemetría (TDD - Issue #10).
Valida métricas agregadas de flota, detección de umbrales y desacoplamiento con la GUI.
"""

import unittest
from src.models import TelemetryPayload
from src.dashboard_model import (
    FleetDashboardState,
    AlertSeverity,
    AlertItem,
    VehicleSummary,
    FleetMetrics
)


class TestFleetDashboardState(unittest.TestCase):

    def setUp(self):
        self.state = FleetDashboardState()

    def _create_payload(
        self,
        vehicle_id: str = "AUTO-001",
        speed: float = 60.0,
        temp: float = 85.0,
        fuel: float = 90.0,
        status: str = "MOVING"
    ) -> TelemetryPayload:
        return TelemetryPayload.create(
            vehicle_id=vehicle_id,
            lat=-32.8895,
            lon=-68.8458,
            speed_kmh=speed,
            rpm=2200,
            fuel_level_pct=fuel,
            engine_temp_c=temp,
            status=status
        )

    def test_initial_state_empty(self):
        """Verifica que el estado inicial de la flota esté vacío."""
        metrics = self.state.get_fleet_metrics()
        self.assertEqual(metrics.total_vehicles, 0)
        self.assertEqual(metrics.active_vehicles, 0)
        self.assertEqual(metrics.average_speed_kmh, 0.0)
        self.assertEqual(metrics.total_alerts, 0)
        self.assertEqual(metrics.critical_alerts, 0)
        self.assertEqual(len(self.state.get_vehicles()), 0)
        self.assertEqual(len(self.state.get_alerts()), 0)

    def test_update_single_vehicle_normal(self):
        """Verifica la inserción y actualización de un vehículo con métricas normales."""
        payload = self._create_payload(vehicle_id="AUTO-001", speed=65.0, temp=85.0, fuel=80.0)
        alerts = self.state.update_telemetry(payload)

        self.assertEqual(len(alerts), 0)
        vehicles = self.state.get_vehicles()
        self.assertEqual(len(vehicles), 1)

        v = vehicles[0]
        self.assertEqual(v.vehicle_id, "AUTO-001")
        self.assertEqual(v.speed_kmh, 65.0)
        self.assertEqual(v.engine_temp_c, 85.0)
        self.assertEqual(v.fuel_level_pct, 80.0)
        self.assertFalse(v.has_critical_alert)

        metrics = self.state.get_fleet_metrics()
        self.assertEqual(metrics.total_vehicles, 1)
        self.assertEqual(metrics.active_vehicles, 1)
        self.assertEqual(metrics.average_speed_kmh, 65.0)

    def test_speed_threshold_triggers_critical_alert(self):
        """Verifica que velocidad > 120 km/h genere alerta CRITICAL."""
        payload = self._create_payload(vehicle_id="AUTO-SPEED", speed=132.5)
        alerts = self.state.update_telemetry(payload)

        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert.vehicle_id, "AUTO-SPEED")
        self.assertEqual(alert.severity, AlertSeverity.CRITICAL)
        self.assertEqual(alert.alert_type, "EXCESO_VELOCIDAD")
        self.assertIn("132.5", alert.description)

        v = self.state.get_vehicle("AUTO-SPEED")
        self.assertIsNotNone(v)
        self.assertTrue(v.has_critical_alert)

        metrics = self.state.get_fleet_metrics()
        self.assertEqual(metrics.total_alerts, 1)
        self.assertEqual(metrics.critical_alerts, 1)

    def test_engine_overheat_triggers_critical_alert(self):
        """Verifica que temperatura de motor > 100°C genere alerta CRITICAL."""
        payload = self._create_payload(vehicle_id="AUTO-HOT", speed=50.0, temp=106.5)
        alerts = self.state.update_telemetry(payload)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type, "TEMPERATURA_MOTOR")
        self.assertEqual(alerts[0].severity, AlertSeverity.CRITICAL)

    def test_low_fuel_triggers_warning_alert(self):
        """Verifica que combustible < 15% genere alerta WARNING."""
        payload = self._create_payload(vehicle_id="AUTO-LOWFUEL", speed=40.0, fuel=12.5)
        alerts = self.state.update_telemetry(payload)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type, "NIVEL_COMBUSTIBLE")
        self.assertEqual(alerts[0].severity, AlertSeverity.WARNING)

    def test_multiple_vehicles_average_speed_calculation(self):
        """Verifica cálculo exacto de promedio de velocidad con múltiples vehículos."""
        self.state.update_telemetry(self._create_payload("AUTO-01", speed=40.0))
        self.state.update_telemetry(self._create_payload("AUTO-02", speed=60.0))
        self.state.update_telemetry(self._create_payload("AUTO-03", speed=80.0))

        metrics = self.state.get_fleet_metrics()
        self.assertEqual(metrics.total_vehicles, 3)
        self.assertAlmostEqual(metrics.average_speed_kmh, 60.0)

    def test_observer_callback_notification(self):
        """Verifica que los suscriptores reciban notificación de cambio de estado (Patrón Observer)."""
        notified = []

        def on_change(event_type: str, data):
            notified.append((event_type, data))

        self.state.subscribe(on_change)
        payload = self._create_payload("AUTO-OBS", speed=55.0)
        self.state.update_telemetry(payload)

        self.assertGreaterEqual(len(notified), 1)
        self.assertEqual(notified[0][0], "telemetry_updated")

    def test_clear_alerts(self):
        """Verifica el vaciado de historial de alertas."""
        self.state.update_telemetry(self._create_payload("AUTO-1", speed=140.0))
        self.assertGreater(len(self.state.get_alerts()), 0)

        self.state.clear_alerts()
        self.assertEqual(len(self.state.get_alerts()), 0)
        self.assertEqual(self.state.get_fleet_metrics().total_alerts, 0)


if __name__ == "__main__":
    unittest.main()

