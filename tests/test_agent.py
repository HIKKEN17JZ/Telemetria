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


if __name__ == "__main__":
    unittest.main()
