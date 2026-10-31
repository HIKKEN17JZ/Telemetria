"""
Modelo de datos y gestión de estado para el Dashboard de Telemetría (Issue #10).
Desacopla la lógica de negocio y umbrales de alerta de la interfaz gráfica Tkinter.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timezone

from src.models import TelemetryPayload


class AlertSeverity(str, Enum):
    """Niveles de severidad de alertas operativas."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class AlertItem:
    """Representación inmutable de un evento o alerta telemétrica."""
    timestamp: str
    vehicle_id: str
    alert_type: str
    severity: AlertSeverity
    description: str
    metric_value: float
    threshold_value: float


@dataclass
class VehicleSummary:
    """Estado y resumen operacional actual de un vehículo en la flota."""
    vehicle_id: str
    status: str
    speed_kmh: float
    rpm: int
    fuel_level_pct: float
    engine_temp_c: float
    lat: float
    lon: float
    timestamp: str
    has_critical_alert: bool = False
    has_warning_alert: bool = False


@dataclass(frozen=True)
class FleetMetrics:
    """Métricas consolidadas de la flota en tiempo real."""
    total_vehicles: int
    active_vehicles: int
    average_speed_kmh: float
    total_alerts: int
    critical_alerts: int


class FleetDashboardState:
    """
    Gestor de estado en memoria del Dashboard de Flota.
    Implementa el patrón Observer para notificar cambios de estado a la interfaz de usuario.
    """

    DEFAULT_SPEED_LIMIT_KMH = 120.0
    DEFAULT_TEMP_CRITICAL_C = 100.0
    DEFAULT_TEMP_WARNING_C = 95.0
    DEFAULT_FUEL_WARNING_PCT = 15.0
    MAX_ALERTS_HISTORY = 100

    def __init__(
        self,
        speed_limit_kmh: float = DEFAULT_SPEED_LIMIT_KMH,
        temp_critical_c: float = DEFAULT_TEMP_CRITICAL_C,
        temp_warning_c: float = DEFAULT_TEMP_WARNING_C,
        fuel_warning_pct: float = DEFAULT_FUEL_WARNING_PCT
    ):
        self.speed_limit_kmh = speed_limit_kmh
        self.temp_critical_c = temp_critical_c
        self.temp_warning_c = temp_warning_c
        self.fuel_warning_pct = fuel_warning_pct

        self._vehicles: Dict[str, VehicleSummary] = {}
        self._alerts: List[AlertItem] = []
        self._listeners: List[Callable[[str, Any], None]] = []

    def subscribe(self, callback: Callable[[str, Any], None]) -> None:
        """Registra un observador que será invocado ante actualizaciones de estado."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[str, Any], None]) -> None:
        """Remueve un observador previamente registrado."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self, event_type: str, data: Any = None) -> None:
        """Notifica a todos los suscriptores registrados."""
        for listener in self._listeners:
            try:
                listener(event_type, data)
            except Exception:
                pass

    def update_telemetry(self, payload: TelemetryPayload | Dict[str, Any]) -> List[AlertItem]:
        """
        Ingesta una medición de telemetría, actualiza el estado del vehículo y evalúa umbrales.
        Retorna la lista de nuevas alertas generadas por este evento.
        """
        if isinstance(payload, dict):
            vehicle_id = str(payload.get("vehicle_id", "UNKNOWN"))
            timestamp = str(payload.get("timestamp", datetime.now(timezone.utc).isoformat()))
            location = payload.get("location", {})
            lat = float(location.get("lat", 0.0))
            lon = float(location.get("lon", 0.0))
            metrics = payload.get("metrics", {})
            speed = float(metrics.get("speed_kmh", 0.0))
            rpm = int(metrics.get("rpm", 0))
            fuel = float(metrics.get("fuel_level_pct", 100.0))
            temp = float(metrics.get("engine_temp_c", 80.0))
            status = str(payload.get("status", "MOVING"))
        else:
            vehicle_id = payload.vehicle_id
            timestamp = payload.timestamp
            lat = payload.location.lat
            lon = payload.location.lon
            speed = payload.metrics.speed_kmh
            rpm = payload.metrics.rpm
            fuel = payload.metrics.fuel_level_pct
            temp = payload.metrics.engine_temp_c
            status = payload.status

        # 1. Evaluar umbrales de alerta
        new_alerts = self._evaluate_thresholds(
            vehicle_id=vehicle_id,
            timestamp=timestamp,
            speed=speed,
            temp=temp,
            fuel=fuel
        )

        has_critical = any(a.severity == AlertSeverity.CRITICAL for a in new_alerts)
        has_warning = any(a.severity == AlertSeverity.WARNING for a in new_alerts)

        # 2. Actualizar o crear resumen del vehículo
        vehicle_summary = VehicleSummary(
            vehicle_id=vehicle_id,
            status=status,
            speed_kmh=speed,
            rpm=rpm,
            fuel_level_pct=fuel,
            engine_temp_c=temp,
            lat=lat,
            lon=lon,
            timestamp=timestamp,
            has_critical_alert=has_critical,
            has_warning_alert=has_warning
        )
        self._vehicles[vehicle_id] = vehicle_summary

        # 3. Registrar alertas en el historial acumulado
        for alert in new_alerts:
            self._alerts.insert(0, alert)
        if len(self._alerts) > self.MAX_ALERTS_HISTORY:
            self._alerts = self._alerts[:self.MAX_ALERTS_HISTORY]

        # 4. Notificar a observadores de la interfaz
        self._notify("telemetry_updated", vehicle_summary)
        if new_alerts:
            self._notify("alerts_triggered", new_alerts)

        return new_alerts

    def _evaluate_thresholds(
        self,
        vehicle_id: str,
        timestamp: str,
        speed: float,
        temp: float,
        fuel: float
    ) -> List[AlertItem]:
        """Evalúa las reglas de negocio y umbrales operacionales."""
        alerts: List[AlertItem] = []

        # Regla 1: Exceso de velocidad (> 120 km/h)
        if speed > self.speed_limit_kmh:
            alerts.append(
                AlertItem(
                    timestamp=timestamp,
                    vehicle_id=vehicle_id,
                    alert_type="EXCESO_VELOCIDAD",
                    severity=AlertSeverity.CRITICAL,
                    description=f"Exceso de velocidad: {speed:.1f} km/h (límite: {self.speed_limit_kmh:.0f} km/h)",
                    metric_value=speed,
                    threshold_value=self.speed_limit_kmh
                )
            )

        # Regla 2: Recalentamiento de motor (> 100 °C)
        if temp > self.temp_critical_c:
            alerts.append(
                AlertItem(
                    timestamp=timestamp,
                    vehicle_id=vehicle_id,
                    alert_type="TEMPERATURA_MOTOR",
                    severity=AlertSeverity.CRITICAL,
                    description=f"Recalentamiento crítico del motor: {temp:.1f} °C (máx: {self.temp_critical_c:.0f} °C)",
                    metric_value=temp,
                    threshold_value=self.temp_critical_c
                )
            )
        elif temp > self.temp_warning_c:
            alerts.append(
                AlertItem(
                    timestamp=timestamp,
                    vehicle_id=vehicle_id,
                    alert_type="TEMPERATURA_ELEVADA",
                    severity=AlertSeverity.WARNING,
                    description=f"Temperatura de motor elevada: {temp:.1f} °C",
                    metric_value=temp,
                    threshold_value=self.temp_warning_c
                )
            )

        # Regla 3: Nivel bajo de combustible (< 15%)
        if fuel < self.fuel_warning_pct:
            alerts.append(
                AlertItem(
                    timestamp=timestamp,
                    vehicle_id=vehicle_id,
                    alert_type="NIVEL_COMBUSTIBLE",
                    severity=AlertSeverity.WARNING,
                    description=f"Nivel de combustible bajo: {fuel:.1f}% (mín: {self.fuel_warning_pct:.0f}%)",
                    metric_value=fuel,
                    threshold_value=self.fuel_warning_pct
                )
            )

        return alerts

    def get_fleet_metrics(self) -> FleetMetrics:
        """Calcula y retorna las métricas consolidadas de la flota."""
        total = len(self._vehicles)
        if total == 0:
            return FleetMetrics(
                total_vehicles=0,
                active_vehicles=0,
                average_speed_kmh=0.0,
                total_alerts=len(self._alerts),
                critical_alerts=sum(1 for a in self._alerts if a.severity == AlertSeverity.CRITICAL)
            )

        active = sum(1 for v in self._vehicles.values() if v.status == "MOVING" or v.speed_kmh > 0)
        avg_speed = sum(v.speed_kmh for v in self._vehicles.values()) / total
        critical = sum(1 for a in self._alerts if a.severity == AlertSeverity.CRITICAL)

        return FleetMetrics(
            total_vehicles=total,
            active_vehicles=active,
            average_speed_kmh=round(avg_speed, 1),
            total_alerts=len(self._alerts),
            critical_alerts=critical
        )

    def get_vehicles(self) -> List[VehicleSummary]:
        """Retorna la lista de resúmenes de vehículos ordenados por ID."""
        return sorted(self._vehicles.values(), key=lambda v: v.vehicle_id)

    def get_vehicle(self, vehicle_id: str) -> Optional[VehicleSummary]:
        """Obtiene el resumen operacional de un vehículo específico."""
        return self._vehicles.get(vehicle_id)

    def get_alerts(self, limit: int = 50) -> List[AlertItem]:
        """Retorna las alertas más recientes acotadas por el límite."""
        return self._alerts[:limit]

    def clear_alerts(self) -> None:
        """Limpia el historial de alertas y resetea flags en vehículos."""
        self._alerts.clear()
        for v in self._vehicles.values():
            v.has_critical_alert = False
            v.has_warning_alert = False
        self._notify("alerts_cleared")
