"""
Tests unitarios y de integración para la capa de base de datos (Issue #4 & Issue #9).
Asignado a: Agus (Dev 3)
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.database import DatabaseConfig, DatabaseManager
from src.models import TelemetryPayload, Location, VehicleMetrics


class TestDatabaseConfig(unittest.TestCase):
    """Pruebas para la configuración y carga de credenciales de PostgreSQL."""

    def test_default_config_values(self):
        config = DatabaseConfig()
        self.assertEqual(config.dbname, "telemetria")
        self.assertEqual(config.user, "postgres")
        self.assertEqual(config.port, 5435)
        self.assertEqual(config.host, "127.0.0.1")
        self.assertIn("postgresql://postgres:postgres@127.0.0.1:5435/telemetria", config.conninfo)

    def test_config_from_env(self):
        env_vars = {
            "POSTGRES_DB": "test_db",
            "POSTGRES_USER": "test_user",
            "POSTGRES_PASSWORD": "secret_password",
            "POSTGRES_PORT": "5499",
            "POSTGRES_HOST": "localhost"
        }
        with patch.dict("os.environ", env_vars):
            config = DatabaseConfig.from_env()
            self.assertEqual(config.dbname, "test_db")
            self.assertEqual(config.user, "test_user")
            self.assertEqual(config.port, 5499)
            self.assertEqual(config.host, "localhost")
            self.assertIn("postgresql://test_user:secret_password@localhost:5499/test_db", config.conninfo)


class TestDatabaseManagerUnit(unittest.TestCase):
    """Pruebas unitarias con mocks para el gestor de base de datos."""

    def setUp(self):
        self.config = DatabaseConfig(dbname="mock_db")
        self.db = DatabaseManager(self.config)

    def test_extract_telemetry_dict_from_payload(self):
        payload = TelemetryPayload.create(
            vehicle_id="AUTO-001",
            lat=-32.8895,
            lon=-68.8458,
            speed_kmh=60.0,
            rpm=2500,
            fuel_level_pct=85.0,
            engine_temp_c=90.0,
            status="MOVING",
            timestamp="2026-10-31T18:00:00Z"
        )
        data = self.db._extract_telemetry_dict(payload)
        self.assertEqual(data["vehicle_id"], "AUTO-001")
        self.assertEqual(data["latitude"], -32.8895)
        self.assertEqual(data["speed_kmh"], 60.0)
        self.assertEqual(data["status"], "MOVING")

    def test_extract_telemetry_dict_from_plain_dict(self):
        raw_dict = {
            "vehicle_id": "MOCK-99",
            "timestamp": "2026-10-31T18:00:00Z",
            "location": {"lat": -33.0, "lon": -68.0},
            "metrics": {
                "speed_kmh": 45.0,
                "rpm": 1800,
                "fuel_level_pct": 50.0,
                "engine_temp_c": 82.0
            },
            "status": "MOVING"
        }
        data = self.db._extract_telemetry_dict(raw_dict)
        self.assertEqual(data["vehicle_id"], "MOCK-99")
        self.assertEqual(data["latitude"], -33.0)
        self.assertEqual(data["rpm"], 1800)

    def test_extract_telemetry_invalid_type_raises(self):
        with self.assertRaises(TypeError):
            self.db._extract_telemetry_dict("invalid string data")


class TestDatabaseIntegrationLive(unittest.TestCase):
    """
    Pruebas de integración reales contra el contenedor Docker de PostgreSQL (puerto 5435).
    Se ejecutan solo si PostgreSQL está escuchando; de lo contrario se omiten limpiamente.
    """

    @classmethod
    def setUpClass(cls):
        cls.config = DatabaseConfig.from_env()
        cls.db = DatabaseManager(cls.config)
        try:
            with cls.db.get_cursor() as cur:
                cur.execute("SELECT 1;")
            cls.is_db_available = True
        except Exception:
            cls.is_db_available = False

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "db"):
            cls.db.close()

    def setUp(self):
        if not self.is_db_available:
            self.skipTest("Contenedor PostgreSQL no disponible en 127.0.0.1:5435.")

    def test_upsert_and_get_vehicle(self):
        test_id = "TEST-VEH-01"
        self.db.upsert_vehicle(test_id, model="Tesla Cyber", type_="TRUCK", status="ACTIVE")
        vehicle = self.db.get_vehicle(test_id)

        self.assertIsNotNone(vehicle)
        self.assertEqual(vehicle["id"], test_id)
        self.assertEqual(vehicle["model"], "Tesla Cyber")
        self.assertEqual(vehicle["type"], "TRUCK")

    def test_insert_and_get_latest_telemetry(self):
        payload = TelemetryPayload.create(
            vehicle_id="AUTO-001",
            lat=-32.8895,
            lon=-68.8458,
            speed_kmh=75.5,
            rpm=3100,
            fuel_level_pct=92.0,
            engine_temp_c=89.0,
            status="MOVING"
        )
        row_id = self.db.insert_telemetry(payload)
        self.assertGreater(row_id, 0)

        latest = self.db.get_latest_telemetry("AUTO-001")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["vehicle_id"], "AUTO-001")
        self.assertEqual(float(latest["speed_kmh"]), 75.5)

    def test_insert_telemetry_batch(self):
        payloads = [
            TelemetryPayload.create(
                vehicle_id="CAMION-002",
                lat=-32.88 + (i * 0.001),
                lon=-68.84 + (i * 0.001),
                speed_kmh=50.0 + i,
                rpm=2000,
                fuel_level_pct=80.0 - i,
                engine_temp_c=85.0,
                status="MOVING"
            )
            for i in range(5)
        ]
        inserted_count = self.db.insert_telemetry_batch(payloads)
        self.assertEqual(inserted_count, 5)

    def test_insert_and_get_recent_alerts(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        alert_id = self.db.insert_alert(
            vehicle_id="AUTO-001",
            alert_type="EXCESS_SPEED",
            description="Velocidad superior al límite de 120 km/h",
            timestamp=now_iso,
            severity="CRITICAL",
            metric_value=135.2,
            threshold_value=120.0
        )
        self.assertGreater(alert_id, 0)

        alerts = self.db.get_recent_alerts(limit=5, vehicle_id="AUTO-001")
        self.assertTrue(len(alerts) > 0)
        self.assertEqual(alerts[0]["alert_type"], "EXCESS_SPEED")
        self.assertEqual(alerts[0]["severity"], "CRITICAL")

    def test_constraint_validation_negative_speed_fails(self):
        """Verifica que la restricción CHECK (speed_kmh >= 0.0) de init_db.sql falle y haga rollback."""
        invalid_payload = {
            "vehicle_id": "AUTO-001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "location": {"lat": -32.8, "lon": -68.8},
            "metrics": {
                "speed_kmh": -20.0,
                "rpm": 1000,
                "fuel_level_pct": 50.0,
                "engine_temp_c": 80.0
            },
            "status": "MOVING"
        }
        with self.assertRaises(Exception):
            self.db.insert_telemetry(invalid_payload)

    def test_get_fleet_summary(self):
        """Prueba la agregación analítica de la flota completa (Issue #9)."""
        summary = self.db.get_fleet_summary()
        self.assertIsInstance(summary, dict)
        self.assertIn("total_vehicles", summary)
        self.assertIn("total_telemetry_records", summary)
        self.assertIn("total_alerts", summary)
        self.assertIn("vehicles", summary)
        self.assertIn("alerts_breakdown", summary)
        self.assertGreaterEqual(summary["total_vehicles"], 1)

    def test_save_and_get_latest_fleet_report(self):
        """Prueba la persistencia de snapshots analíticos de flota (Issue #9)."""
        mock_summary = {
            "total_vehicles": 3,
            "total_telemetry_records": 150,
            "total_alerts": 4,
            "critical_alerts": 2,
            "vehicles": [{"vehicle_id": "AUTO-001", "avg_speed_kmh": 65.2}]
        }
        report_id = self.db.save_fleet_report(mock_summary)
        self.assertGreater(report_id, 0)

        latest = self.db.get_latest_fleet_report()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["total_vehicles"], 3)
        self.assertEqual(latest["total_alerts"], 4)
        self.assertEqual(latest["critical_alerts"], 2)


if __name__ == "__main__":
    unittest.main()
