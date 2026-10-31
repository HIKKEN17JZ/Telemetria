"""
Tests unitarios y de integración para Celery y procesamiento analítico (Issue #7 & Issue #9).
Asignado a: Agus (Dev 3)
"""

import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.celery_app import app
from src.tasks import (
    evaluate_telemetry_thresholds,
    process_telemetry,
    process_telemetry_batch,
    generate_fleet_summary,
    health_check,
    SPEED_WARNING_LIMIT_KMH,
    SPEED_CRITICAL_LIMIT_KMH,
    ENGINE_TEMP_CRITICAL_C,
    LOW_FUEL_WARNING_PCT
)


class TestTelemetryThresholds(unittest.TestCase):
    """Pruebas unitarias para la lógica de detección de anomalías y umbrales."""

    def test_normal_metrics_produce_no_alerts(self):
        payload = {
            "vehicle_id": "AUTO-001",
            "timestamp": "2026-10-31T20:00:00Z",
            "location": {"lat": -32.8895, "lon": -68.8458},
            "metrics": {
                "speed_kmh": 65.0,
                "rpm": 2400,
                "fuel_level_pct": 75.0,
                "engine_temp_c": 88.0
            },
            "status": "MOVING"
        }
        alerts = evaluate_telemetry_thresholds(payload)
        self.assertEqual(len(alerts), 0)

    def test_warning_speed_alert(self):
        payload = {
            "vehicle_id": "AUTO-001",
            "metrics": {"speed_kmh": 125.0, "engine_temp_c": 90.0, "fuel_level_pct": 50.0}
        }
        alerts = evaluate_telemetry_thresholds(payload)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_type"], "EXCESS_SPEED")
        self.assertEqual(alerts[0]["severity"], "WARNING")
        self.assertEqual(alerts[0]["metric_value"], 125.0)

    def test_critical_speed_alert(self):
        payload = {
            "vehicle_id": "AUTO-001",
            "metrics": {"speed_kmh": 140.0, "engine_temp_c": 90.0, "fuel_level_pct": 50.0}
        }
        alerts = evaluate_telemetry_thresholds(payload)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_type"], "EXCESS_SPEED")
        self.assertEqual(alerts[0]["severity"], "CRITICAL")

    def test_critical_engine_temp_alert(self):
        payload = {
            "vehicle_id": "CAMION-002",
            "metrics": {"speed_kmh": 50.0, "engine_temp_c": 112.5, "fuel_level_pct": 60.0}
        }
        alerts = evaluate_telemetry_thresholds(payload)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_type"], "HIGH_ENGINE_TEMP")
        self.assertEqual(alerts[0]["severity"], "CRITICAL")

    def test_low_fuel_alert(self):
        payload = {
            "vehicle_id": "PRUEBA-01",
            "metrics": {"speed_kmh": 40.0, "engine_temp_c": 85.0, "fuel_level_pct": 8.5}
        }
        alerts = evaluate_telemetry_thresholds(payload)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_type"], "LOW_FUEL")
        self.assertEqual(alerts[0]["severity"], "WARNING")

    def test_multiple_simultaneous_alerts(self):
        payload = {
            "vehicle_id": "AUTO-999",
            "metrics": {
                "speed_kmh": 138.0,
                "engine_temp_c": 109.0,
                "fuel_level_pct": 4.0
            }
        }
        alerts = evaluate_telemetry_thresholds(payload)
        self.assertEqual(len(alerts), 3)
        types = [a["alert_type"] for a in alerts]
        self.assertIn("EXCESS_SPEED", types)
        self.assertIn("HIGH_ENGINE_TEMP", types)
        self.assertIn("LOW_FUEL", types)


class TestCeleryAppConfiguration(unittest.TestCase):
    """Pruebas de la configuración de Celery."""

    def test_celery_configuration_settings(self):
        self.assertEqual(app.conf.task_serializer, "json")
        self.assertEqual(app.conf.result_serializer, "json")
        self.assertEqual(app.conf.timezone, "UTC")
        self.assertTrue(app.conf.enable_utc)
        self.assertTrue(app.conf.task_acks_late)
        self.assertEqual(app.conf.worker_prefetch_multiplier, 1)

    def test_health_check_task(self):
        result = health_check()
        self.assertEqual(result["status"], "OK")
        self.assertIn("timestamp", result)


class TestCeleryProcessingTask(unittest.TestCase):
    """Pruebas de la ejecución de las tareas process_telemetry y batch."""

    @patch("src.tasks.DatabaseManager")
    def test_process_telemetry_normal_flow(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db.insert_telemetry.return_value = 101
        mock_db_cls.return_value = mock_db

        payload = {
            "vehicle_id": "AUTO-001",
            "timestamp": "2026-10-31T20:00:00Z",
            "location": {"lat": -32.8895, "lon": -68.8458},
            "metrics": {"speed_kmh": 55.0, "rpm": 2100, "fuel_level_pct": 80.0, "engine_temp_c": 85.0},
            "status": "MOVING"
        }

        result = process_telemetry(payload)

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["vehicle_id"], "AUTO-001")
        self.assertEqual(result["telemetry_id"], 101)
        self.assertEqual(result["alerts_count"], 0)
        mock_db.insert_telemetry.assert_called_once_with(payload)
        mock_db.insert_alert.assert_not_called()
        mock_db.close.assert_called_once()

    @patch("src.tasks.DatabaseManager")
    def test_process_telemetry_with_alerts_persisted(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db.insert_telemetry.return_value = 202
        mock_db.insert_alert.return_value = 999
        mock_db_cls.return_value = mock_db

        payload = {
            "vehicle_id": "CAMION-002",
            "timestamp": "2026-10-31T20:00:00Z",
            "location": {"lat": -32.8895, "lon": -68.8458},
            "metrics": {"speed_kmh": 135.0, "rpm": 3500, "fuel_level_pct": 5.0, "engine_temp_c": 108.0},
            "status": "MOVING"
        }

        result = process_telemetry(payload)

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["alerts_count"], 3)
        mock_db.insert_telemetry.assert_called_once_with(payload)
        self.assertEqual(mock_db.insert_alert.call_count, 3)
        mock_db.close.assert_called_once()

    @patch("src.tasks.DatabaseManager")
    def test_process_telemetry_batch_flow(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db.insert_telemetry_batch.return_value = 3
        mock_db.insert_alert.return_value = 555
        mock_db_cls.return_value = mock_db

        batch = [
            {
                "vehicle_id": "AUTO-001",
                "metrics": {"speed_kmh": 50.0, "engine_temp_c": 80.0, "fuel_level_pct": 80.0}
            },
            {
                "vehicle_id": "CAMION-002",
                "metrics": {"speed_kmh": 135.0, "engine_temp_c": 85.0, "fuel_level_pct": 70.0}  # 1 alerta
            },
            {
                "vehicle_id": "PRUEBA-01",
                "metrics": {"speed_kmh": 60.0, "engine_temp_c": 110.0, "fuel_level_pct": 5.0}   # 2 alertas
            }
        ]

        result = process_telemetry_batch(batch)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["processed_count"], 3)
        self.assertEqual(result["alerts_count"], 3)
        mock_db.insert_telemetry_batch.assert_called_once_with(batch)
        self.assertEqual(mock_db.insert_alert.call_count, 3)
        mock_db.close.assert_called_once()

    @patch("src.tasks.DatabaseManager")
    def test_generate_fleet_summary_task(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db.get_fleet_summary.return_value = {
            "total_vehicles": 3,
            "total_telemetry_records": 100,
            "total_alerts": 2
        }
        mock_db.save_fleet_report.return_value = 77
        mock_db_cls.return_value = mock_db

        result = generate_fleet_summary()
        self.assertEqual(result["report_id"], 77)
        self.assertEqual(result["total_vehicles"], 3)
        mock_db.get_fleet_summary.assert_called_once()
        mock_db.save_fleet_report.assert_called_once()
        mock_db.close.assert_called_once()


class TestPlantUMLDiagrams(unittest.TestCase):
    """Verifica que los diagramas PlantUML de arquitectura y flujo de datos estén correctamente creados (Issue #9)."""

    def setUp(self):
        self.docs_dir = Path(__file__).resolve().parent.parent / "docs"

    def test_architecture_diagram_exists_and_valid(self):
        arch_file = self.docs_dir / "architecture.puml"
        self.assertTrue(arch_file.exists(), "Falta el archivo docs/architecture.puml")
        content = arch_file.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("@startuml"))
        self.assertTrue("@enduml" in content)
        self.assertIn("server.py", content)
        self.assertIn("Celery", content)
        self.assertIn("PostgreSQL", content)

    def test_data_flow_diagram_exists_and_valid(self):
        flow_file = self.docs_dir / "data_flow.puml"
        self.assertTrue(flow_file.exists(), "Falta el archivo docs/data_flow.puml")
        content = flow_file.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("@startuml"))
        self.assertTrue("@enduml" in content)
        self.assertIn("SIGHUP", content)
        self.assertIn("SIGUSR1", content)
        self.assertIn("Redis", content)
        self.assertIn("Tkinter", content)


if __name__ == "__main__":
    unittest.main()
