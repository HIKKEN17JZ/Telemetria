"""
Tests unitarios y de protocolo para la validación y enmarcado de telemetría (Issue #5).
TDD: Red - Green - Refactor
"""

import pytest
from src.protocol import (
    ProtocolFraming,
    ProtocolValidator,
    ProtocolResponse,
    ProtocolError,
    TelemetryFrame,
)


class TestProtocolFraming:
    """Pruebas del mecanismo de enmarcado (Framing) y delimitación por streams."""

    def test_encode_frame_appends_delimiter(self):
        payload = {"vehicle_id": "TEST-01", "status": "IDLE"}
        encoded = ProtocolFraming.encode(payload)
        assert encoded.endswith(b"\n")
        assert b'"vehicle_id": "TEST-01"' in encoded

    def test_decode_single_frame(self):
        raw_data = b'{"vehicle_id": "TEST-01"}\n'
        frames, remaining = ProtocolFraming.extract_frames(raw_data)
        assert len(frames) == 1
        assert frames[0] == '{"vehicle_id": "TEST-01"}'
        assert remaining == b""

    def test_decode_fragmented_stream(self):
        # Stream que llega en dos partes (fragmentación TCP típica)
        part1 = b'{"vehicle_id": "TE'
        frames, remaining = ProtocolFraming.extract_frames(part1)
        assert len(frames) == 0
        assert remaining == part1

        part2 = b'ST-01"}\n'
        frames, remaining = ProtocolFraming.extract_frames(remaining + part2)
        assert len(frames) == 1
        assert frames[0] == '{"vehicle_id": "TEST-01"}'
        assert remaining == b""

    def test_decode_multiple_frames_in_single_buffer(self):
        # Dos o más paquetes pegados en el mismo buffer TCP
        raw_data = b'{"msg": 1}\n{"msg": 2}\n{"msg": 3}\n'
        frames, remaining = ProtocolFraming.extract_frames(raw_data)
        assert len(frames) == 3
        assert frames == ['{"msg": 1}', '{"msg": 2}', '{"msg": 3}']
        assert remaining == b""

    def test_decode_frames_with_trailing_partial(self):
        raw_data = b'{"msg": 1}\n{"msg": 2}\n{"msg": 3'
        frames, remaining = ProtocolFraming.extract_frames(raw_data)
        assert len(frames) == 2
        assert remaining == b'{"msg": 3'


class TestProtocolValidation:
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
        assert validated.vehicle_id == "AUTO-001"
        assert validated.location.lat == -32.8895
        assert validated.metrics.speed_kmh == 65.4
        assert validated.status == "MOVING"

    def test_validate_missing_required_keys(self):
        invalid_payload = {
            "vehicle_id": "AUTO-001",
            "location": {"lat": -32.8895, "lon": -68.8458},
        }
        with pytest.raises(ProtocolError) as exc_info:
            ProtocolValidator.validate(invalid_payload)
        assert "Faltan campos obligatorios" in str(exc_info.value)

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
        with pytest.raises(ProtocolError) as exc_info:
            ProtocolValidator.validate(invalid_payload)
        assert "timestamp" in str(exc_info.value).lower()

    def test_validate_invalid_latitude_range(self):
        invalid_payload = {
            "vehicle_id": "AUTO-001",
            "timestamp": "2026-10-24T18:30:00Z",
            "location": {"lat": 120.0, "lon": -68.8458},  # Lat > 90
            "metrics": {
                "speed_kmh": 10.0,
                "rpm": 1200,
                "fuel_level_pct": 80.0,
                "engine_temp_c": 85.0,
            },
            "status": "MOVING",
        }
        with pytest.raises(ProtocolError) as exc_info:
            ProtocolValidator.validate(invalid_payload)
        assert "latitud" in str(exc_info.value).lower()

    def test_validate_invalid_speed_negative(self):
        invalid_payload = {
            "vehicle_id": "AUTO-001",
            "timestamp": "2026-10-24T18:30:00Z",
            "location": {"lat": -32.0, "lon": -68.0},
            "metrics": {
                "speed_kmh": -5.0,  # Negativo
                "rpm": 0,
                "fuel_level_pct": 50.0,
                "engine_temp_c": 70.0,
            },
            "status": "STOPPED",
        }
        with pytest.raises(ProtocolError) as exc_info:
            ProtocolValidator.validate(invalid_payload)
        assert "velocidad" in str(exc_info.value).lower()

    def test_validate_invalid_fuel_percentage(self):
        invalid_payload = {
            "vehicle_id": "AUTO-001",
            "timestamp": "2026-10-24T18:30:00Z",
            "location": {"lat": -32.0, "lon": -68.0},
            "metrics": {
                "speed_kmh": 10.0,
                "rpm": 1000,
                "fuel_level_pct": 110.0,  # > 100%
                "engine_temp_c": 70.0,
            },
            "status": "MOVING",
        }
        with pytest.raises(ProtocolError) as exc_info:
            ProtocolValidator.validate(invalid_payload)
        assert "combustible" in str(exc_info.value).lower()


class TestProtocolResponses:
    """Pruebas para generación uniforme de acuses de recibo (ACK/NACK)."""

    def test_create_ack_response(self):
        ack = ProtocolResponse.ack("AUTO-001")
        assert ack["status"] == "ACK"
        assert ack["vehicle_id"] == "AUTO-001"
        assert "server_time" in ack

        # Verificar serialización enmarcada
        ack_bytes = ProtocolResponse.to_bytes(ack)
        assert ack_bytes.endswith(b"\n")

    def test_create_nack_response(self):
        nack = ProtocolResponse.nack("Invalid JSON format")
        assert nack["status"] == "NACK"
        assert nack["error"] == "Invalid JSON format"

        nack_bytes = ProtocolResponse.to_bytes(nack)
        assert nack_bytes.endswith(b"\n")
