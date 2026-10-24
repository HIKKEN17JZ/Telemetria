"""
Tests unitarios para el generador/simulador de telemetría vehicular (TDD).
"""

import json
import unittest
from datetime import datetime
from src.models import TelemetryPayload, Location, VehicleMetrics
from src.simulator import VehicleSimulator


class TestTelemetryModelsAndSimulator(unittest.TestCase):

    def test_payload_structure_matches_contract(self):
        """Verifica que el payload cumpla estrictamente la estructura de INSTRUCCIONES.md."""
        simulator = VehicleSimulator(vehicle_id="AUTO-001", start_lat=-32.8895, start_lon=-68.8458)
        payload = simulator.next_telemetry()

        # Validación de tipo
        self.assertIsInstance(payload, TelemetryPayload)
        self.assertEqual(payload.vehicle_id, "AUTO-001")

        # Conversión a diccionario para validar esquema
        data = payload.to_dict()
        required_keys = {"vehicle_id", "timestamp", "location", "metrics", "status"}
        self.assertTrue(required_keys.issubset(data.keys()))

        # Location
        self.assertIn("lat", data["location"])
        self.assertIn("lon", data["location"])
        self.assertIsInstance(data["location"]["lat"], float)
        self.assertIsInstance(data["location"]["lon"], float)

        # Metrics
        metrics = data["metrics"]
        required_metrics = {"speed_kmh", "rpm", "fuel_level_pct", "engine_temp_c"}
        self.assertTrue(required_metrics.issubset(metrics.keys()))

        # Status
        self.assertIn(data["status"], ["MOVING", "IDLE"])

    def test_json_serialization_includes_newline(self):
        """Verifica que to_json() termine obligatoriamente en newline '\\n' para el contrato."""
        simulator = VehicleSimulator(vehicle_id="TEST-100")
        payload = simulator.next_telemetry()

        json_str = payload.to_json()
        self.assertTrue(json_str.endswith("\n"))

        # El contenido antes del \n debe ser JSON válido
        parsed = json.loads(json_str.strip())
        self.assertEqual(parsed["vehicle_id"], "TEST-100")

    def test_status_based_on_speed(self):
        """Verifica que status sea 'IDLE' si speed <= 5 y 'MOVING' si speed > 5."""
        simulator = VehicleSimulator(vehicle_id="TEST-100")

        # Forzar IDLE
        simulator.speed = 0.0
        payload_idle = simulator.next_telemetry()
        self.assertEqual(payload_idle.status, "IDLE")

        # Forzar MOVING
        simulator.speed = 50.0
        payload_moving = simulator.next_telemetry()
        self.assertEqual(payload_moving.status, "MOVING")

    def test_fuel_consumption_and_metrics_ranges(self):
        """Verifica que las métricas simulen valores físicos coherentes a lo largo de pasos."""
        simulator = VehicleSimulator(vehicle_id="TEST-100")
        initial_fuel = simulator.fuel

        # Simular 10 pasos de avance
        for _ in range(10):
            payload = simulator.next_telemetry()
            self.assertGreaterEqual(payload.metrics.speed_kmh, 0.0)
            self.assertLessEqual(payload.metrics.speed_kmh, 150.0)
            self.assertGreaterEqual(payload.metrics.fuel_level_pct, 0.0)
            self.assertLessEqual(payload.metrics.fuel_level_pct, 100.0)
            self.assertGreaterEqual(payload.metrics.engine_temp_c, 50.0)
            self.assertLessEqual(payload.metrics.engine_temp_c, 130.0)

        # El combustible debe haber disminuido o ser menor/igual al inicial
        self.assertLessEqual(simulator.fuel, initial_fuel)


if __name__ == "__main__":
    unittest.main()
