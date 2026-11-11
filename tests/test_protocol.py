"""
Tests unitarios y de protocolo para la validación y enmarcado de telemetría (Issue #5).
TDD: Red - Green - Refactor
Compatible con unittest estándar y pytest.
"""

import unittest
from src.protocol import (
    ProtocolFraming,
    ProtocolValidator,
    ProtocolResponse,
    ProtocolError,
    TelemetryFrame,
)


class TestProtocolFraming(unittest.TestCase):
    """Pruebas del mecanismo de enmarcado (Framing) y delimitación por streams."""

    def test_encode_frame_appends_delimiter(self):
        payload = {"vehicle_id": "TEST-01", "status": "IDLE"}
        encoded = ProtocolFraming.encode(payload)
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertIn(b'"vehicle_id": "TEST-01"', encoded)

    def test_decode_single_frame(self):
        raw_data = b'{"vehicle_id": "TEST-01"}\n'
        frames, remaining = ProtocolFraming.extract_frames(raw_data)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0], '{"vehicle_id": "TEST-01"}')
        self.assertEqual(remaining, b"")

    def test_decode_fragmented_stream(self):
        part1 = b'{"vehicle_id": "TE'
        frames, remaining = ProtocolFraming.extract_frames(part1)
        self.assertEqual(len(frames), 0)
        self.assertEqual(remaining, part1)

        part2 = b'ST-01"}\n'
        frames, remaining = ProtocolFraming.extract_frames(remaining + part2)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0], '{"vehicle_id": "TEST-01"}')
        self.assertEqual(remaining, b"")

    def test_decode_multiple_frames_in_single_buffer(self):
        raw_data = b'{"msg": 1}\n{"msg": 2}\n{"msg": 3}\n'
        frames, remaining = ProtocolFraming.extract_frames(raw_data)
        self.assertEqual(len(frames), 3)
        self.assertEqual(frames, ['{"msg": 1}', '{"msg": 2}', '{"msg": 3}'])
        self.assertEqual(remaining, b"")

    def test_decode_frames_with_trailing_partial(self):
        raw_data = b'{"msg": 1}\n{"msg": 2}\n{"msg": 3'
        frames, remaining = ProtocolFraming.extract_frames(raw_data)
        self.assertEqual(len(frames), 2)
        self.assertEqual(remaining, b'{"msg": 3')


class TestProtocolValidation(unittest.TestCase):
    """Pruebas de validación estricta de esquemas, tipos y rangos de telemetría."""

    def test_validate_valid_payload_success(self):
        valid_payload = {
            "vehicle_id": "AUTO-001",
            "timestamp": "2026-10-24T18:30:00Z",
            "location": {"lat": -32.8895, "lon": -68.8458},
            "metrics": {
                "speed_kmh": 65.4,
                "rpm": 2400,
                "fuel_level_pct": 85.2,
                "engine_temp_c": 88.5,
            },
            "status": "MOVING",
        }
        validated = ProtocolValidator.validate(valid_payload)
        self.assertEqual(validated.vehicle_id, "AUTO-001")
        self.assertEqual(validated.location.lat, -32.8895)
        self.assertEqual(validated.metrics.speed_kmh, 65.4)
        self.assertEqual(validated.status, "MOVING")

    def test_validate_missing_required_keys(self):
        invalid_payload = {
            "vehicle_id": "AUTO-001",
            "location": {"lat": -32.8895, "lon": -68.8458},
        }
        with self.assertRaises(ProtocolError) as ctx:
            ProtocolValidator.validate(invalid_payload)
        self.assertIn("Faltan campos obligatorios", str(ctx.exception))

    def test_validate_invalid_timestamp_format(self):
        invalid_payload = {
            "vehicle_id": "AUTO-001",
            "timestamp": "24/10/2026 18:30",
            "location": {"lat": 0.0, "lon": 0.0},
            "metrics": {
                "speed_kmh": 0.0,
                "rpm": 800,
                "fuel_level_pct": 50.0,
                "engine_temp_c": 70.0,
            },
            "status": "IDLE",
        }
        with self.assertRaises(ProtocolError) as ctx:
            ProtocolValidator.validate(invalid_payload)
        self.assertIn("timestamp", str(ctx.exception).lower())

    def test_validate_invalid_latitude_range(self):
        invalid_payload = {
            "vehicle_id": "AUTO-001",
            "timestamp": "2026-10-24T18:30:00Z",
            "location": {"lat": 120.0, "lon": -68.8458},
            "metrics": {
                "speed_kmh": 10.0,
                "rpm": 1200,
                "fuel_level_pct": 80.0,
                "engine_temp_c": 85.0,
            },
            "status": "MOVING",
        }
        with self.assertRaises(ProtocolError) as ctx:
            ProtocolValidator.validate(invalid_payload)
        self.assertIn("latitud", str(ctx.exception).lower())

    def test_validate_invalid_speed_negative(self):
        invalid_payload = {
            "vehicle_id": "AUTO-001",
            "timestamp": "2026-10-24T18:30:00Z",
            "location": {"lat": -32.0, "lon": -68.0},
            "metrics": {
                "speed_kmh": -5.0,
                "rpm": 0,
                "fuel_level_pct": 50.0,
                "engine_temp_c": 70.0,
            },
            "status": "STOPPED",
        }
        with self.assertRaises(ProtocolError) as ctx:
            ProtocolValidator.validate(invalid_payload)
        self.assertIn("velocidad", str(ctx.exception).lower())

    def test_validate_invalid_fuel_percentage(self):
        invalid_payload = {
            "vehicle_id": "AUTO-001",
            "timestamp": "2026-10-24T18:30:00Z",
            "location": {"lat": -32.0, "lon": -68.0},
            "metrics": {
                "speed_kmh": 10.0,
                "rpm": 1000,
                "fuel_level_pct": 110.0,
                "engine_temp_c": 70.0,
            },
            "status": "MOVING",
        }
        with self.assertRaises(ProtocolError) as ctx:
            ProtocolValidator.validate(invalid_payload)
        self.assertIn("combustible", str(ctx.exception).lower())


class TestProtocolResponses(unittest.TestCase):
    """Pruebas para generación uniforme de acuses de recibo (ACK/NACK)."""

    def test_create_ack_response(self):
        ack = ProtocolResponse.ack("AUTO-001")
        self.assertEqual(ack["status"], "ACK")
        self.assertEqual(ack["vehicle_id"], "AUTO-001")
        self.assertIn("server_time", ack)

        ack_bytes = ProtocolResponse.to_bytes(ack)
        self.assertTrue(ack_bytes.endswith(b"\n"))

    def test_create_nack_response(self):
        nack = ProtocolResponse.nack("Invalid JSON format")
        self.assertEqual(nack["status"], "NACK")
        self.assertEqual(nack["error"], "Invalid JSON format")

        nack_bytes = ProtocolResponse.to_bytes(nack)
        self.assertTrue(nack_bytes.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
