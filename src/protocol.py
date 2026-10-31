"""
Protocolo de Comunicación de Telemetría (Issue #5).
Capa de aplicación sobre TCP: enmarcado, deserialización, validación estricta y generación de respuestas ACK/NACK.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from src.models import Location, VehicleMetrics, TelemetryPayload


class ProtocolError(ValueError):
    """Excepción específica lanzada ante violación del protocolo o datos corruptos."""
    pass


class ProtocolFraming:
    """
    Estrategia de enmarcado (Framing) delimitada por salto de línea ('\\n').
    Permite procesar streams continuos de TCP evitando fragmentación o concatenación.
    """

    DELIMITER = b"\n"
    DELIMITER_STR = "\n"

    @classmethod
    def encode(cls, payload: Dict[str, Any] | str) -> bytes:
        """
        Codifica un diccionario o string JSON agregando el delimitador de fin de trama.
        """
        if isinstance(payload, str):
            json_str = payload if payload.endswith(cls.DELIMITER_STR) else payload + cls.DELIMITER_STR
            return json_str.encode("utf-8")
        return (json.dumps(payload, ensure_ascii=False) + cls.DELIMITER_STR).encode("utf-8")

    @classmethod
    def extract_frames(cls, buffer: bytes) -> Tuple[List[str], bytes]:
        """
        Extrae tramas completas de un buffer acumulado de bytes.
        Retorna:
            (frames, remaining_bytes)
        donde 'frames' es una lista de strings JSON limpios y 'remaining_bytes'
        es el residuo incompleto para seguir acumulando.
        """
        lines = buffer.split(cls.DELIMITER)
        remaining = lines[-1]  # El último elemento siempre es incompleto (o vacío si terminaba en \n)
        complete_lines = lines[:-1]

        frames: List[str] = []
        for line in complete_lines:
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded:
                frames.append(decoded)

        return frames, remaining


@dataclass(frozen=True)
class TelemetryFrame:
    """Representación fuertemente tipada de una trama validada en el servidor."""
    vehicle_id: str
    timestamp: str
    location: Location
    metrics: VehicleMetrics
    status: str

    def to_payload(self) -> TelemetryPayload:
        """Convierte la trama a un modelo TelemetryPayload estándar de dominio."""
        return TelemetryPayload(
            vehicle_id=self.vehicle_id,
            timestamp=self.timestamp,
            location=self.location,
            metrics=self.metrics,
            status=self.status,
        )


class ProtocolValidator:
    """
    Validador de esquemas e integridad de paquetes de telemetría.
    Asegura tipos de datos válidos, existencia de claves obligatorias y rangos físicos razonables.
    """

    REQUIRED_ROOT_KEYS = {"vehicle_id", "timestamp", "location", "metrics", "status"}
    REQUIRED_LOCATION_KEYS = {"lat", "lon"}
    REQUIRED_METRICS_KEYS = {"speed_kmh", "rpm", "fuel_level_pct", "engine_temp_c"}

    @classmethod
    def validate_raw(cls, raw_json_str: str) -> TelemetryFrame:
        """
        Deserializa y valida un string JSON crudo.
        Lanza ProtocolError si el JSON es inválido o no cumple las restricciones.
        """
        try:
            data = json.loads(raw_json_str)
        except json.JSONDecodeError as e:
            raise ProtocolError(f"Formato JSON inválido: {e}") from e

        if not isinstance(data, dict):
            raise ProtocolError("El payload debe ser un objeto JSON (dict).")

        return cls.validate(data)

    @classmethod
    def validate(cls, data: Dict[str, Any]) -> TelemetryFrame:
        """Valida exhaustivamente un diccionario de datos telemétricos."""
        missing_root = cls.REQUIRED_ROOT_KEYS - data.keys()
        if missing_root:
            raise ProtocolError(f"Faltan campos obligatorios en raíz: {', '.join(sorted(missing_root))}")

        vehicle_id = str(data["vehicle_id"]).strip()
        if not vehicle_id:
            raise ProtocolError("El identificador vehicle_id no puede estar vacío.")

        timestamp = cls._validate_timestamp(data["timestamp"])
        location = cls._validate_location(data["location"])
        metrics = cls._validate_metrics(data["metrics"])
        status = cls._validate_status(data["status"])

        return TelemetryFrame(
            vehicle_id=vehicle_id,
            timestamp=timestamp,
            location=location,
            metrics=metrics,
            status=status,
        )

    @classmethod
    def _validate_timestamp(cls, ts: Any) -> str:
        if not isinstance(ts, str):
            raise ProtocolError(f"El timestamp debe ser string, recibido {type(ts).__name__}")
        try:
            # Soportar ISO 8601 con 'Z' o con offset
            iso_str = ts.replace("Z", "+00:00")
            datetime.fromisoformat(iso_str)
            return ts
        except ValueError as e:
            raise ProtocolError(f"Formato de timestamp inválido (esperado ISO-8601): {ts}") from e

    @classmethod
    def _validate_location(cls, loc: Any) -> Location:
        if not isinstance(loc, dict):
            raise ProtocolError(f"location debe ser un objeto dict, recibido {type(loc).__name__}")

        missing = cls.REQUIRED_LOCATION_KEYS - loc.keys()
        if missing:
            raise ProtocolError(f"Faltan campos en location: {', '.join(sorted(missing))}")

        try:
            lat = float(loc["lat"])
            lon = float(loc["lon"])
        except (ValueError, TypeError) as e:
            raise ProtocolError(f"Coordenadas lat/lon deben ser numéricas: {e}") from e

        if not (-90.0 <= lat <= 90.0):
            raise ProtocolError(f"Latitud fuera de rango (-90 a 90): {lat}")
        if not (-180.0 <= lon <= 180.0):
            raise ProtocolError(f"Longitud fuera de rango (-180 a 180): {lon}")

        return Location(lat=round(lat, 6), lon=round(lon, 6))

    @classmethod
    def _validate_metrics(cls, metrics: Any) -> VehicleMetrics:
        if not isinstance(metrics, dict):
            raise ProtocolError(f"metrics debe ser un objeto dict, recibido {type(metrics).__name__}")

        missing = cls.REQUIRED_METRICS_KEYS - metrics.keys()
        if missing:
            raise ProtocolError(f"Faltan campos en metrics: {', '.join(sorted(missing))}")

        try:
            speed = float(metrics["speed_kmh"])
            rpm = int(metrics["rpm"])
            fuel = float(metrics["fuel_level_pct"])
            temp = float(metrics["engine_temp_c"])
        except (ValueError, TypeError) as e:
            raise ProtocolError(f"Tipos de métricas inválidos: {e}") from e

        if speed < 0.0 or speed > 350.0:
            raise ProtocolError(f"Velocidad (speed_kmh) fuera de rango lógico (0-350): {speed}")
        if rpm < 0 or rpm > 15000:
            raise ProtocolError(f"RPM fuera de rango lógico (0-15000): {rpm}")
        if fuel < 0.0 or fuel > 100.0:
            raise ProtocolError(f"Porcentaje de combustible (fuel_level_pct) fuera de rango (0-100): {fuel}")
        if temp < -50.0 or temp > 200.0:
            raise ProtocolError(f"Temperatura (engine_temp_c) fuera de rango lógico (-50 a 200): {temp}")

        return VehicleMetrics(
            speed_kmh=round(speed, 1),
            rpm=rpm,
            fuel_level_pct=round(fuel, 2),
            engine_temp_c=round(temp, 1),
        )

    @classmethod
    def _validate_status(cls, status: Any) -> str:
        if not isinstance(status, str) or not status.strip():
            raise ProtocolError(f"status debe ser un string no vacío: {status}")
        return status.strip().upper()


class ProtocolResponse:
    """
    Generador estandarizado de respuestas ACK y NACK según el contrato de comunicación.
    """

    @staticmethod
    def ack(vehicle_id: str, server_time: str | None = None) -> Dict[str, Any]:
        """Crea un acuse de recibo exitoso (ACK)."""
        if server_time is None:
            server_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "status": "ACK",
            "vehicle_id": vehicle_id,
            "server_time": server_time,
        }

    @staticmethod
    def nack(error_message: str) -> Dict[str, Any]:
        """Crea una respuesta de error de validación o formato (NACK)."""
        return {
            "status": "NACK",
            "error": error_message,
        }

    @classmethod
    def to_bytes(cls, response_dict: Dict[str, Any]) -> bytes:
        """Serializa la respuesta a bytes enmarcada con salto de línea."""
        return ProtocolFraming.encode(response_dict)
