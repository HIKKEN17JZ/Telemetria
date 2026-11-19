"""
Tests unitarios para el punto de entrada agent.py (TDD).
"""

import unittest
from agent import calculate_initial_coordinates, main


class TestAgentEntryPoint(unittest.TestCase):

    def test_coordinates_dispersion(self):
        """Verifica que diferentes IDs de vehículos generen coordenadas distintas."""
        coord1 = calculate_initial_coordinates("AUTO-001")
        coord2 = calculate_initial_coordinates("CAMION-999")
        self.assertNotEqual(coord1, coord2)

    def test_main_with_invalid_args_returns_code_1(self):
        """Verifica que main() retorne código 1 ante error de validación."""
        exit_code = main(["--server-port", "-10"])
        self.assertEqual(exit_code, 1)

    def test_main_with_help_returns_code_0(self):
        """Verifica que main() con --help retorne 0."""
        exit_code = main(["--help"])
        self.assertEqual(exit_code, 0)

    def test_agent_app_waits_backoff_delay_when_buffered(self):
        """Verifica que AgentApp respete el backoff calculado cuando el servidor está caído."""
        import logging
        from unittest.mock import MagicMock
        from agent import AgentApp
        from src.cli import AgentConfig
        from src.network import NetworkResponse

        config = AgentConfig(
            vehicle_id="AUTO-001",
            server_host="127.0.0.1",
            server_port=59999,
            interval=0.1,
            mode="simulation",
            buffer_size=10,
            max_backoff=5.0
        )
        app = AgentApp(config=config, logger=logging.getLogger("TestAgent"))
        app.client = MagicMock()
        app.client.connect.return_value = False
        app.client.backoff.last_delay = 2.5
        app.client.buffer = []
        app.client.send_or_buffer.return_value = NetworkResponse(
            success=False, buffered=True, queue_size=1, error_message="offline"
        )

        waited_durations = []

        def fake_wait(seconds):
            waited_durations.append(seconds)
            app.stop()
            return True

        app._wait_interval = fake_wait
        app.run()

        self.assertEqual(len(waited_durations), 1)
        self.assertGreaterEqual(waited_durations[0], 2.5)


if __name__ == "__main__":
    unittest.main()
