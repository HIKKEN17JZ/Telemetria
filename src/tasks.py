"""
Tareas distribuidas de Celery para procesamiento analítico de telemetría (Issue #7 & Issue #9).
Asignado a: Agus (Dev 3)

Implementa:
- Evaluación en segundo plano de umbrales críticos de seguridad (velocidad, temperatura, combustible).
- Registro asíncrono en PostgreSQL mediante DatabaseManager con reintentos automáticos.
- Pipeline de persistencia masiva por lotes (batch persistence).
- Tarea analítica periódica/bajo demanda para reportes y agregaciones de flota.
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
    Tarea Celery principal para un registro individual:
    1. Evalúa umbrales críticos de seguridad.
    2. Persiste la telemetría en PostgreSQL.
    3. Si hubo alertas, las registra en la tabla de alertas.
    """
    vehicle_id = payload.get("vehicle_id", "UNKNOWN")
    logger.info(f"[Celery] Procesando telemetria para vehiculo: {vehicle_id}")

    alerts = evaluate_telemetry_thresholds(payload)
    
    db = DatabaseManager()
    try:
        telemetry_id = db.insert_telemetry(payload)
        
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


@app.task(
    bind=True,
    name="src.tasks.process_telemetry_batch",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3}
)
def process_telemetry_batch(self, batch: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Tarea Celery para procesamiento masivo por lotes (Issue #9):
    Inserta masivamente registros en PostgreSQL en una sola transacción optimizada
    y registra las alertas detectadas de forma agrupada.
    """
    if not batch:
        return {"status": "SUCCESS", "processed_count": 0, "alerts_count": 0, "alerts": []}

    logger.info(f"[Celery] Procesando lote masivo de {len(batch)} mediciones de telemetria")

    # 1. Evaluar umbrales de todos los elementos del lote
    all_alerts = []
    for item in batch:
        alerts = evaluate_telemetry_thresholds(item)
        all_alerts.extend(alerts)

    db = DatabaseManager()
    try:
        # 2. Inserción optimizada por lote
        inserted_count = db.insert_telemetry_batch(batch)

        # 3. Inserción de alertas detectadas
        for alert in all_alerts:
            db.insert_alert(
                vehicle_id=alert["vehicle_id"],
                alert_type=alert["alert_type"],
                description=alert["description"],
                timestamp=alert["timestamp"],
                severity=alert["severity"],
                metric_value=alert["metric_value"],
                threshold_value=alert["threshold_value"]
            )

        return {
            "status": "SUCCESS",
            "processed_count": inserted_count,
            "alerts_count": len(all_alerts),
            "alerts": all_alerts
        }

    except Exception as exc:
        logger.error(f"[Celery ERROR] Error en procesamiento por lote masivo: {exc}")
        raise exc
    finally:
        db.close()


@app.task(name="src.tasks.generate_fleet_summary")
def generate_fleet_summary() -> dict[str, Any]:
    """
    Tarea analítica de Celery (Issue #9):
    Calcula métricas agregadas de la flota y guarda un snapshot persistido en PostgreSQL.
    """
    logger.info("[Celery] Generando reporte analitico agregado de la flota...")
    db = DatabaseManager()
    try:
        summary = db.get_fleet_summary()
        summary["generated_at"] = datetime.now(timezone.utc).isoformat()
        report_id = db.save_fleet_report(summary)
        summary["report_id"] = report_id
        logger.info(f"[Celery] Reporte analitico #{report_id} generado y guardado en PostgreSQL.")
        return summary
    finally:
        db.close()


@app.task(name="src.tasks.health_check")
def health_check() -> dict[str, str]:
    """Tarea de ping para comprobación del estado del worker."""
    return {
        "status": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
