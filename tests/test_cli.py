"""
Tests unitarios para el parser de argumentos CLI del Agente (TDD).
"""

import unittest
from src.cli import parse_arguments, validate_config, AgentConfig


class TestAgentCLI(unittest.TestCase):

    def test_default_arguments(self):
        """Verifica que sin argumentos se carguen los valores por defecto del contrato."""
        args = parse_arguments([])
        config = validate_config(args)

        self.assertEqual(config.vehicle_id, "AUTO-001")
        self.assertEqual(config.server_host, "127.0.0.1")
        self.assertEqual(config.server_port, 5000)
        self.assertEqual(config.interval, 2.0)
        self.assertEqual(config.mode, "simulation")

    def test_custom_arguments(self):
        """Verifica que se parseen correctamente argumentos personalizados."""
        custom_args = [
            "--vehicle-id", "CAMION-99",
            "--server-host", "192.168.1.100",
            "--server-port", "6000",
            "--interval", "0.5",
            "--mode", "simulation"
        ]
        args = parse_arguments(custom_args)
        config = validate_config(args)

        self.assertEqual(config.vehicle_id, "CAMION-99")
        self.assertEqual(config.server_host, "192.168.1.100")
        self.assertEqual(config.server_port, 6000)
        self.assertEqual(config.interval, 0.5)
        self.assertEqual(config.mode, "simulation")

    def test_invalid_port_range(self):
        """Verifica que un puerto fuera de rango (1-65535) arroje error de validación."""
        args = parse_arguments(["--server-port", "70000"])
        with self.assertRaises(ValueError) as ctx:
            validate_config(args)
        self.assertIn("puerto", str(ctx.exception).lower())

        args_low = parse_arguments(["--server-port", "0"])
        with self.assertRaises(ValueError) as ctx:
            validate_config(args_low)
        self.assertIn("puerto", str(ctx.exception).lower())

    def test_invalid_interval(self):
        """Verifica que un intervalo negativo o cero arroje error de validación."""
        args = parse_arguments(["--interval", "-1"])
        with self.assertRaises(ValueError) as ctx:
            validate_config(args)
        self.assertIn("intervalo", str(ctx.exception).lower())

    def test_empty_vehicle_id(self):
        """Verifica que no se permita un vehicle-id vacío."""
        args = parse_arguments(["--vehicle-id", "   "])
        with self.assertRaises(ValueError) as ctx:
            validate_config(args)
        self.assertIn("vehicle", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
