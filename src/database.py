"""
Capa de acceso a datos y persistencia en PostgreSQL (Issue #4).
Asignado a: Agus (Dev 3)

Gestiona la conexión con PostgreSQL mediante connection pooling (psycopg_pool),
manejo de transacciones seguras con rollback automático y operaciones CRUD
optimizadas para telemetría vehicular, alertas y estado de la flota.
"""

import os
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
        # Intenta cargar variables desde .env si python-dotenv está disponible
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
        
        # Garantizar que el vehículo existe en la tabla vehicles para evitar FK violation
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
