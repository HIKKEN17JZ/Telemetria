"""
Tareas distribuidas de Celery para procesamiento analítico de telemetría (Issue #7).
Asignado a: Agus (Dev 3)

Implementa:
- Evaluación en segundo plano de umbrales críticos de seguridad (velocidad, temperatura, combustible).
- Registro asíncrono en PostgreSQL mediante DatabaseManager con reintentos automáticos.
- Disparo de alertas preventivas y críticas sin bloquear el servidor de sockets.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.celery_app import app
from src.database import DatabaseManager

logger = logging.getLogger("CeleryTasks")

# Constantes de umbrales operativos de seguridad
SPEED_WARNING_LIMIT_KMH = 120.0
SPEED_CRITICAL_LIMIT_KMH = 130.0
ENGINE_TEMP_CRITICAL_C = 105.0
LOW_FUEL_WARNING_PCT = 10.0


def evaluate_telemetry_thresholds(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Evalúa las métricas de un paquete de telemetría y detecta violaciones de umbrales.
    Función pura, determinística y fácilmente testeable.
    """
    alerts = []
    vehicle_id = payload.get("vehicle_id", "UNKNOWN")
    metrics = payload.get("metrics", {})
    timestamp = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()

    speed = float(metrics.get("speed_kmh", 0.0))
    temp = float(metrics.get("engine_temp_c", 0.0))
    fuel = float(metrics.get("fuel_level_pct", 100.0))

    # 1. Chequeo de exceso de velocidad
    if speed > SPEED_WARNING_LIMIT_KMH:
        severity = "CRITICAL" if speed > SPEED_CRITICAL_LIMIT_KMH else "WARNING"
        alerts.append({
            "vehicle_id": vehicle_id,
            "alert_type": "EXCESS_SPEED",
            "severity": severity,
            "description": f"Exceso de velocidad: {speed:.1f} km/h detectado (Limite: {SPEED_WARNING_LIMIT_KMH} km/h)",
            "metric_value": speed,
            "threshold_value": SPEED_WARNING_LIMIT_KMH,
            "timestamp": timestamp
        })

    # 2. Chequeo de temperatura del motor
    if temp > ENGINE_TEMP_CRITICAL_C:
        alerts.append({
            "vehicle_id": vehicle_id,
            "alert_type": "HIGH_ENGINE_TEMP",
            "severity": "CRITICAL",
            "description": f"Temperatura critica de motor: {temp:.1f}°C (Limite: {ENGINE_TEMP_CRITICAL_C}°C)",
            "metric_value": temp,
            "threshold_value": ENGINE_TEMP_CRITICAL_C,
            "timestamp": timestamp
        })

    # 3. Chequeo de nivel bajo de combustible
    if fuel < LOW_FUEL_WARNING_PCT:
        alerts.append({
            "vehicle_id": vehicle_id,
            "alert_type": "LOW_FUEL",
            "severity": "WARNING",
            "description": f"Nivel critico de combustible: {fuel:.1f}% restante",
            "metric_value": fuel,
            "threshold_value": LOW_FUEL_WARNING_PCT,
            "timestamp": timestamp
        })

    return alerts


@app.task(
    bind=True,
    name="src.tasks.process_telemetry",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3}
)
def process_telemetry(self, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Tarea Celery principal:
    1. Evalúa umbrales críticos de seguridad.
    2. Persiste la telemetría en PostgreSQL.
    3. Si hubo alertas, las registra en la tabla de alertas.
    """
    vehicle_id = payload.get("vehicle_id", "UNKNOWN")
    logger.info(f"[Celery] Procesando telemetria para vehiculo: {vehicle_id}")

    # Evaluación de umbrales
    alerts = evaluate_telemetry_thresholds(payload)
    
    db = DatabaseManager()
    try:
        # Inserción de la medición
        telemetry_id = db.insert_telemetry(payload)
        
        # Inserción de alertas generadas
        alert_ids = []
        for alert in alerts:
            aid = db.insert_alert(
                vehicle_id=alert["vehicle_id"],
                alert_type=alert["alert_type"],
                description=alert["description"],
                timestamp=alert["timestamp"],
                severity=alert["severity"],
                metric_value=alert["metric_value"],
                threshold_value=alert["threshold_value"]
            )
            alert_ids.append(aid)
            logger.warning(
                f"[Celery ALERT] {alert['severity']} - {alert['alert_type']} en {vehicle_id}: {alert['description']}"
            )

        return {
            "status": "SUCCESS",
            "vehicle_id": vehicle_id,
            "telemetry_id": telemetry_id,
            "alerts_count": len(alerts),
            "alerts": alerts
        }

    except Exception as exc:
        logger.error(f"[Celery ERROR] Error al persistir telemetria de {vehicle_id}: {exc}")
        raise exc
    finally:
        db.close()


@app.task(name="src.tasks.health_check")
def health_check() -> dict[str, str]:
    """Tarea de ping para comprobación del estado del worker."""
    return {
        "status": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
