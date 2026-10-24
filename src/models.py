"""
Modelos de dominio y DTOs para telemetría vehicular.
Inmutabilidad, tipado estricto y serialización estandarizada según el contrato.
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Any


@dataclass(frozen=True)
class Location:
    """Coordenadas geográficas del vehículo."""
    lat: float
    lon: float


@dataclass(frozen=True)
class VehicleMetrics:
    """Métricas mecánicas y operativas del vehículo."""
    speed_kmh: float
    rpm: int
    fuel_level_pct: float
    engine_temp_c: float


@dataclass(frozen=True)
class TelemetryPayload:
    """Estructura completa de telemetría transmitida por el agente."""
    vehicle_id: str
    timestamp: str
    location: Location
    metrics: VehicleMetrics
    status: str

    def to_dict(self) -> Dict[str, Any]:
        """Convierte la entidad a un diccionario serializable."""
        return asdict(self)

    def to_json(self) -> str:
        """
        Serializa a formato JSON finalizando obligatoriamente en salto de línea (\\n).
        Esto cumple con el protocolo delimitado por newline acordado en el contrato.
        """
        return json.dumps(self.to_dict(), ensure_ascii=False) + "\n"

    @classmethod
    def create(
        cls,
        vehicle_id: str,
        lat: float,
        lon: float,
        speed_kmh: float,
        rpm: int,
        fuel_level_pct: float,
        engine_temp_c: float,
        status: str,
        timestamp: str = None
    ) -> "TelemetryPayload":
        """Factory method para construir un payload con timestamp UTC actual si no se provee."""
        if timestamp is None:
            now_utc = datetime.now(timezone.utc)
            timestamp = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        return cls(
            vehicle_id=vehicle_id,
            timestamp=timestamp,
            location=Location(lat=round(lat, 6), lon=round(lon, 6)),
            metrics=VehicleMetrics(
                speed_kmh=round(speed_kmh, 1),
                rpm=int(rpm),
                fuel_level_pct=round(fuel_level_pct, 2),
                engine_temp_c=round(engine_temp_c, 1)
            ),
            status=status
        )
