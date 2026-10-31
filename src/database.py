"""
Capa de acceso a datos y persistencia en PostgreSQL (Issue #4 & Issue #9).
Asignado a: Agus (Dev 3)

Gestiona la conexión con PostgreSQL mediante connection pooling (psycopg_pool),
manejo de transacciones seguras con rollback automático y operaciones CRUD
optimizadas para telemetría vehicular, alertas, persistencia por lotes y reportes agregados.
"""

import os
import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional, Any, Generator, Sequence, Union
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from src.models import TelemetryPayload

logger = logging.getLogger("DatabaseManager")


@dataclass(frozen=True)
class DatabaseConfig:
    """Configuración de parámetros de conexión a PostgreSQL."""
    dbname: str = "telemetria"
    user: str = "postgres"
    password: str = "postgres"
    host: str = "127.0.0.1"
    port: int = 5435
    min_size: int = 2
    max_size: int = 10
    timeout: float = 10.0

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Carga la configuración desde variables de entorno o archivo .env."""
        try:
            from dotenv import load_dotenv
            env_path = Path(__file__).resolve().parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
        except ImportError:
            pass

        return cls(
            dbname=os.getenv("POSTGRES_DB", "telemetria"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
            port=int(os.getenv("POSTGRES_PORT", "5435")),
            min_size=int(os.getenv("DB_POOL_MIN", "2")),
            max_size=int(os.getenv("DB_POOL_MAX", "10")),
            timeout=float(os.getenv("DB_CONNECT_TIMEOUT", "10.0"))
        )

    @property
    def conninfo(self) -> str:
        """Genera el string de conexión URI estándar para PostgreSQL."""
        return (
            f"postgresql://{self.user}:{self.password}@"
            f"{self.host}:{self.port}/{self.dbname}"
        )


class DatabaseManager:
    """
    Gestor de persistencia relacional con connection pooling para PostgreSQL.
    Garantiza el reúso eficiente de conexiones y previene la saturación del servidor.
    """

    def __init__(self, config: Optional[DatabaseConfig] = None):
        self.config = config or DatabaseConfig.from_env()
        self._pool: Optional[ConnectionPool] = None

    @property
    def pool(self) -> ConnectionPool:
        """Inicializa de forma perezosa (lazy) el pool de conexiones si aún no existe."""
        if self._pool is None or self._pool.closed:
            logger.info(
                f"Inicializando pool de conexiones PostgreSQL en {self.config.host}:{self.config.port}/{self.config.dbname} "
                f"(min: {self.config.min_size}, max: {self.config.max_size})"
            )
            self._pool = ConnectionPool(
                conninfo=self.config.conninfo,
                min_size=self.config.min_size,
                max_size=self.config.max_size,
                timeout=self.config.timeout,
                open=True
            )
        return self._pool

    def close(self) -> None:
        """Cierra el pool de conexiones liberando todos los recursos."""
        if self._pool and not self._pool.closed:
            self._pool.close()
            logger.info("Pool de conexiones PostgreSQL cerrado correctamente.")

    @contextmanager
    def get_connection(self) -> Generator[psycopg.Connection, None, None]:
        """Context manager que entrega una conexión del pool con transacción segura."""
        with self.pool.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @contextmanager
    def get_cursor(self) -> Generator[psycopg.Cursor, None, None]:
        """Context manager que entrega un cursor con mapeo a diccionarios (dict_row)."""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                yield cur

    # ==========================================
    # Operaciones de Vehículos
    # ==========================================

    def upsert_vehicle(
        self,
        vehicle_id: str,
        model: Optional[str] = "Vehículo Genérico",
        type_: Optional[str] = "CAR",
        status: str = "ACTIVE"
    ) -> None:
        """Crea o actualiza el registro de un vehículo en la base de datos."""
        query = """
        INSERT INTO vehicles (id, model, type, status)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            status = EXCLUDED.status;
        """
        with self.get_cursor() as cur:
            cur.execute(query, (vehicle_id, model, type_, status))

    def get_vehicle(self, vehicle_id: str) -> Optional[dict[str, Any]]:
        """Obtiene un vehículo por su identificador único."""
        query = "SELECT id, model, type, status, created_at FROM vehicles WHERE id = %s;"
        with self.get_cursor() as cur:
            cur.execute(query, (vehicle_id,))
            return cur.fetchone()

    def get_all_vehicles(self) -> list[dict[str, Any]]:
        """Retorna todos los vehículos registrados en la flota."""
        query = "SELECT id, model, type, status, created_at FROM vehicles ORDER BY id ASC;"
        with self.get_cursor() as cur:
            cur.execute(query)
            return cur.fetchall()

    # ==========================================
    # Operaciones de Telemetría
    # ==========================================

    def insert_telemetry(self, payload: Union[TelemetryPayload, dict[str, Any]]) -> int:
        """
        Inserta un registro individual de telemetría asegurando existencia previa del vehículo.
        Retorna el ID autogenerado del registro.
        """
        data = self._extract_telemetry_dict(payload)
        self.upsert_vehicle(data["vehicle_id"])

        query = """
        INSERT INTO telemetry (
            vehicle_id, timestamp, latitude, longitude,
            speed_kmh, rpm, fuel_level_pct, engine_temp_c, status
        ) VALUES (
            %(vehicle_id)s, %(timestamp)s, %(latitude)s, %(longitude)s,
            %(speed_kmh)s, %(rpm)s, %(fuel_level_pct)s, %(engine_temp_c)s, %(status)s
        ) RETURNING id;
        """
        with self.get_cursor() as cur:
            cur.execute(query, data)
            result = cur.fetchone()
            return result["id"] if result else 0

    def insert_telemetry_batch(
        self,
        payloads: Sequence[Union[TelemetryPayload, dict[str, Any]]]
    ) -> int:
        """
        Inserta masivamente un lote de telemetrías dentro de una sola transacción optimizada.
        Retorna la cantidad de filas insertadas.
        """
        if not payloads:
            return 0

        extracted = [self._extract_telemetry_dict(p) for p in payloads]

        # Asegurar todos los vehículos únicos
        unique_vehicle_ids = {item["vehicle_id"] for item in extracted}
        for vid in unique_vehicle_ids:
            self.upsert_vehicle(vid)

        query = """
        INSERT INTO telemetry (
            vehicle_id, timestamp, latitude, longitude,
            speed_kmh, rpm, fuel_level_pct, engine_temp_c, status
        ) VALUES (
            %(vehicle_id)s, %(timestamp)s, %(latitude)s, %(longitude)s,
            %(speed_kmh)s, %(rpm)s, %(fuel_level_pct)s, %(engine_temp_c)s, %(status)s
        );
        """
        with self.get_cursor() as cur:
            cur.executemany(query, extracted)
            return cur.rowcount

    def get_latest_telemetry(self, vehicle_id: str) -> Optional[dict[str, Any]]:
        """Obtiene la medición más reciente de un vehículo."""
        query = """
        SELECT id, vehicle_id, timestamp, latitude, longitude,
               speed_kmh, rpm, fuel_level_pct, engine_temp_c, status, created_at
        FROM telemetry
        WHERE vehicle_id = %s
        ORDER BY timestamp DESC
        LIMIT 1;
        """
        with self.get_cursor() as cur:
            cur.execute(query, (vehicle_id,))
            return cur.fetchone()

    # ==========================================
    # Operaciones de Alertas
    # ==========================================

    def insert_alert(
        self,
        vehicle_id: str,
        alert_type: str,
        description: str,
        timestamp: str,
        severity: str = "WARNING",
        metric_value: Optional[float] = None,
        threshold_value: Optional[float] = None
    ) -> int:
        """
        Registra una alerta crítica o advertencia para un vehículo.
        Retorna el ID autogenerado de la alerta.
        """
        self.upsert_vehicle(vehicle_id)

        query = """
        INSERT INTO alerts (
            vehicle_id, alert_type, severity, description,
            metric_value, threshold_value, timestamp
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id;
        """
        with self.get_cursor() as cur:
            cur.execute(query, (
                vehicle_id, alert_type, severity, description,
                metric_value, threshold_value, timestamp
            ))
            result = cur.fetchone()
            return result["id"] if result else 0

    def get_recent_alerts(
        self,
        limit: int = 10,
        vehicle_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Retorna las alertas más recientes generadas, opcionalmente filtradas por vehículo."""
        if vehicle_id:
            query = """
            SELECT id, vehicle_id, alert_type, severity, description,
                   metric_value, threshold_value, timestamp, created_at
            FROM alerts
            WHERE vehicle_id = %s
            ORDER BY timestamp DESC
            LIMIT %s;
            """
            params: tuple[Any, ...] = (vehicle_id, limit)
        else:
            query = """
            SELECT id, vehicle_id, alert_type, severity, description,
                   metric_value, threshold_value, timestamp, created_at
            FROM alerts
            ORDER BY timestamp DESC
            LIMIT %s;
            """
            params = (limit,)

        with self.get_cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    # ==========================================
    # Operaciones de Reportes Agregados (Issue #9)
    # ==========================================

    def get_fleet_summary(self) -> dict[str, Any]:
        """
        Calcula métricas agregadas en tiempo real de toda la flota:
        - Total de vehículos activos
        - Total de mediciones registradas
        - Promedios y máximos de velocidad y temperatura por vehículo
        - Conteo de alertas agrupadas por severidad
        """
        summary: dict[str, Any] = {
            "total_vehicles": 0,
            "total_telemetry_records": 0,
            "total_alerts": 0,
            "critical_alerts": 0,
            "warning_alerts": 0,
            "vehicles": [],
            "alerts_breakdown": []
        }

        with self.get_cursor() as cur:
            # 1. Totales generales
            cur.execute("SELECT COUNT(*) AS count FROM vehicles;")
            summary["total_vehicles"] = cur.fetchone()["count"]

            cur.execute("SELECT COUNT(*) AS count FROM telemetry;")
            summary["total_telemetry_records"] = cur.fetchone()["count"]

            cur.execute("SELECT COUNT(*) AS count FROM alerts;")
            summary["total_alerts"] = cur.fetchone()["count"]

            cur.execute("SELECT COUNT(*) AS count FROM alerts WHERE severity = 'CRITICAL';")
            summary["critical_alerts"] = cur.fetchone()["count"]

            cur.execute("SELECT COUNT(*) AS count FROM alerts WHERE severity = 'WARNING';")
            summary["warning_alerts"] = cur.fetchone()["count"]

            # 2. Resumen agregado por vehículo
            veh_query = """
            SELECT 
                v.id AS vehicle_id,
                v.model,
                v.type,
                v.status,
                COUNT(t.id) AS total_points,
                COALESCE(ROUND(AVG(t.speed_kmh), 2), 0.0) AS avg_speed_kmh,
                COALESCE(MAX(t.speed_kmh), 0.0) AS max_speed_kmh,
                COALESCE(ROUND(AVG(t.engine_temp_c), 2), 0.0) AS avg_engine_temp_c,
                COALESCE(MAX(t.engine_temp_c), 0.0) AS max_engine_temp_c,
                COALESCE(
                    (SELECT fuel_level_pct FROM telemetry WHERE vehicle_id = v.id ORDER BY timestamp DESC LIMIT 1),
                    100.0
                ) AS last_fuel_pct
            FROM vehicles v
            LEFT JOIN telemetry t ON v.id = t.vehicle_id
            GROUP BY v.id, v.model, v.type, v.status
            ORDER BY v.id ASC;
            """
            cur.execute(veh_query)
            summary["vehicles"] = cur.fetchall()

            # 3. Desglose de alertas por tipo y severidad
            alert_query = """
            SELECT alert_type, severity, COUNT(*) AS count
            FROM alerts
            GROUP BY alert_type, severity
            ORDER BY severity DESC, count DESC;
            """
            cur.execute(alert_query)
            summary["alerts_breakdown"] = cur.fetchall()

        return summary

    def save_fleet_report(self, summary: dict[str, Any]) -> int:
        """Persiste un snapshot de reporte analítico en la tabla fleet_reports."""
        query = """
        INSERT INTO fleet_reports (
            total_vehicles, total_telemetry_records,
            total_alerts, critical_alerts, summary_json
        ) VALUES (
            %s, %s, %s, %s, %s
        ) RETURNING id;
        """
        summary_clean = {k: v for k, v in summary.items() if k != "summary_json"}
        with self.get_cursor() as cur:
            cur.execute(query, (
                summary.get("total_vehicles", 0),
                summary.get("total_telemetry_records", 0),
                summary.get("total_alerts", 0),
                summary.get("critical_alerts", 0),
                json.dumps(summary_clean, default=str)
            ))
            res = cur.fetchone()
            return res["id"] if res else 0

    def get_latest_fleet_report(self) -> Optional[dict[str, Any]]:
        """Recupera el último snapshot de reporte generado."""
        query = """
        SELECT id, generated_at, total_vehicles, total_telemetry_records,
               total_alerts, critical_alerts, summary_json
        FROM fleet_reports
        ORDER BY generated_at DESC
        LIMIT 1;
        """
        with self.get_cursor() as cur:
            cur.execute(query)
            return cur.fetchone()

    # ==========================================
    # Helper Interno de Normalización
    # ==========================================

    @staticmethod
    def _extract_telemetry_dict(payload: Union[TelemetryPayload, dict[str, Any]]) -> dict[str, Any]:
        """Normaliza un TelemetryPayload o diccionario al formato requerido por la tabla telemetry."""
        if isinstance(payload, TelemetryPayload):
            return {
                "vehicle_id": payload.vehicle_id,
                "timestamp": payload.timestamp,
                "latitude": payload.location.lat,
                "longitude": payload.location.lon,
                "speed_kmh": payload.metrics.speed_kmh,
                "rpm": payload.metrics.rpm,
                "fuel_level_pct": payload.metrics.fuel_level_pct,
                "engine_temp_c": payload.metrics.engine_temp_c,
                "status": payload.status
            }
        elif isinstance(payload, dict):
            loc = payload.get("location", {})
            metrics = payload.get("metrics", {})
            return {
                "vehicle_id": payload["vehicle_id"],
                "timestamp": payload["timestamp"],
                "latitude": loc.get("lat") if isinstance(loc, dict) else payload.get("latitude"),
                "longitude": loc.get("lon") if isinstance(loc, dict) else payload.get("longitude"),
                "speed_kmh": metrics.get("speed_kmh") if isinstance(metrics, dict) else payload.get("speed_kmh"),
                "rpm": metrics.get("rpm") if isinstance(metrics, dict) else payload.get("rpm"),
                "fuel_level_pct": metrics.get("fuel_level_pct") if isinstance(metrics, dict) else payload.get("fuel_level_pct"),
                "engine_temp_c": metrics.get("engine_temp_c") if isinstance(metrics, dict) else payload.get("engine_temp_c"),
                "status": payload.get("status", "MOVING")
            }
        else:
            raise TypeError(f"Tipo de payload de telemetría no soportado: {type(payload)}")
