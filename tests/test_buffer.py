"""
Tests unitarios para el buffer offline en memoria (TDD - Issue #6).
Garantiza encolado FIFO, recuperación en orden y límites de capacidad.
"""

import unittest
from src.models import TelemetryPayload
from src.buffer import TelemetryBuffer


class TestTelemetryBuffer(unittest.TestCase):

    def setUp(self):
        self.payload1 = TelemetryPayload.create(
            vehicle_id="AUTO-001",
            lat=-32.88,
            lon=-68.84,
            speed_kmh=40.0,
            rpm=1500,
            fuel_level_pct=90.0,
            engine_temp_c=80.0,
            status="MOVING",
            timestamp="2026-10-31T20:00:01Z"
        )
        self.payload2 = TelemetryPayload.create(
            vehicle_id="AUTO-001",
            lat=-32.89,
            lon=-68.85,
            speed_kmh=50.0,
            rpm=2000,
            fuel_level_pct=89.5,
            engine_temp_c=82.0,
            status="MOVING",
            timestamp="2026-10-31T20:00:02Z"
        )
        self.payload3 = TelemetryPayload.create(
            vehicle_id="AUTO-001",
            lat=-32.90,
            lon=-68.86,
            speed_kmh=60.0,
            rpm=2500,
            fuel_level_pct=89.0,
            engine_temp_c=85.0,
            status="MOVING",
            timestamp="2026-10-31T20:00:03Z"
        )

    def test_buffer_push_and_pop_fifo_order(self):
        """Verifica que los paquetes se recuperen estrictamente en orden FIFO."""
        buf = TelemetryBuffer(max_size=10)
        self.assertTrue(buf.is_empty)
        self.assertEqual(len(buf), 0)

        buf.push(self.payload1)
        buf.push(self.payload2)

        self.assertFalse(buf.is_empty)
        self.assertEqual(len(buf), 2)

        first = buf.pop()
        self.assertEqual(first.timestamp, "2026-10-31T20:00:01Z")
        self.assertEqual(len(buf), 1)

        second = buf.pop()
        self.assertEqual(second.timestamp, "2026-10-31T20:00:02Z")
        self.assertTrue(buf.is_empty)

        # Pop en buffer vacío retorna None sin excepción
        self.assertIsNone(buf.pop())

    def test_buffer_capacity_limit(self):
        """Verifica que el buffer respete max_size descartando los más antiguos (o impidiendo desborde)."""
        buf = TelemetryBuffer(max_size=2)
        buf.push(self.payload1)
        buf.push(self.payload2)
        buf.push(self.payload3)  # Supera capacidad de 2

        self.assertEqual(len(buf), 2)
        # El más antiguo (payload1) fue descartado para mantener los 2 más recientes
        self.assertEqual(buf.pop().timestamp, "2026-10-31T20:00:02Z")
        self.assertEqual(buf.pop().timestamp, "2026-10-31T20:00:03Z")

    def test_buffer_peek(self):
        """Verifica inspeccionar el próximo elemento sin extraerlo."""
        buf = TelemetryBuffer()
        self.assertIsNone(buf.peek())

        buf.push(self.payload1)
        self.assertEqual(buf.peek().vehicle_id, "AUTO-001")
        self.assertEqual(len(buf), 1)


if __name__ == "__main__":
    unittest.main()

