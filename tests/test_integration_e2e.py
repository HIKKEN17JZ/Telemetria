"""
Test de integración End-to-End: Server (Charango) + Agente (Ale).
Verifica que el servidor TCP de server.py y el cliente de agent.py se comuniquen
perfectamente sin errores de formato, encoding o framing.
"""

import asyncio
import threading
import time
import unittest

from server import run_server, server_config
from src.cli import AgentConfig
from src.simulator import VehicleSimulator
from src.network import TelemetryClient


class TestIntegrationServerAgent(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Desactivar despacho a Celery durante el test de sockets puro para evitar threads huérfanos
        cls._orig_celery_dispatch = server_config.enable_celery_dispatch
        server_config.enable_celery_dispatch = False

        cls.host = "127.0.0.1"
        cls.port = 5001  # Puerto de test
        cls.loop = asyncio.new_event_loop()

        def start_loop():
            asyncio.set_event_loop(cls.loop)
            try:
                cls.loop.run_until_complete(run_server(cls.host, cls.port))
            except (RuntimeError, asyncio.CancelledError):
                pass

        cls.server_thread = threading.Thread(target=start_loop, daemon=True)
        cls.server_thread.start()
        time.sleep(0.5)  # Dar tiempo a que el socket de escucha esté activo

    @classmethod
    def tearDownClass(cls):
        server_config.enable_celery_dispatch = cls._orig_celery_dispatch
        if hasattr(cls, "loop") and cls.loop.is_running():
            cls.loop.call_soon_threadsafe(cls.loop.stop)

    def test_agent_to_server_communication_and_ack(self):
        """Verifica que un agente envíe telemetría real y reciba el ACK de server.py."""
        client = TelemetryClient(host=self.host, port=self.port, timeout=2.0)
        self.assertTrue(client.connect())

        simulator = VehicleSimulator(vehicle_id="E2E-TEST-01")

        for _ in range(3):
            payload = simulator.next_telemetry()
            response = client.send(payload)

            # Validaciones del contrato
            self.assertTrue(response.success)
            self.assertIsNotNone(response.data)
            self.assertEqual(response.data.get("status"), "ACK")
            self.assertEqual(response.data.get("vehicle_id"), "E2E-TEST-01")
            self.assertIn("server_time", response.data)

        client.disconnect()


if __name__ == "__main__":
    unittest.main()
