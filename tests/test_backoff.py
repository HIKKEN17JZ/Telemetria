"""
Tests unitarios para la estrategia de reintentos con retroceso exponencial y jitter (TDD - Issue #6).
"""

import unittest
from src.backoff import ExponentialBackoff


class TestExponentialBackoff(unittest.TestCase):

    def test_backoff_growth_without_jitter(self):
        """Verifica el crecimiento exponencial estricto: 1s, 2s, 4s, 8s..."""
        backoff = ExponentialBackoff(initial_delay=1.0, max_delay=10.0, multiplier=2.0, jitter=False)

        self.assertEqual(backoff.current_attempt, 0)
        self.assertAlmostEqual(backoff.next_delay(), 1.0)
        self.assertEqual(backoff.current_attempt, 1)

        self.assertAlmostEqual(backoff.next_delay(), 2.0)
        self.assertEqual(backoff.current_attempt, 2)

        self.assertAlmostEqual(backoff.next_delay(), 4.0)
        self.assertEqual(backoff.current_attempt, 3)

        self.assertAlmostEqual(backoff.next_delay(), 8.0)
        self.assertEqual(backoff.current_attempt, 4)

        # Capping en max_delay (10.0)
        self.assertAlmostEqual(backoff.next_delay(), 10.0)
        self.assertEqual(backoff.current_attempt, 5)

    def test_backoff_with_jitter_stays_within_bounds(self):
        """Verifica que con jitter el delay esté entre base_delay y base_delay * (1 + jitter_ratio)."""
        backoff = ExponentialBackoff(initial_delay=2.0, max_delay=20.0, multiplier=2.0, jitter=True, jitter_ratio=0.5)

        for _ in range(10):
            delay = backoff.next_delay()
            # Delay no puede ser menor a 0 ni exceder max_delay * 1.5
            self.assertGreaterEqual(delay, 2.0)
            self.assertLessEqual(delay, 20.0 * 1.5)

    def test_backoff_reset(self):
        """Verifica que reset() reestablezca los intentos al valor inicial."""
        backoff = ExponentialBackoff(initial_delay=1.0, max_delay=10.0, multiplier=2.0, jitter=False)
        backoff.next_delay()
        backoff.next_delay()
        self.assertEqual(backoff.current_attempt, 2)

        backoff.reset()
        self.assertEqual(backoff.current_attempt, 0)
        self.assertAlmostEqual(backoff.next_delay(), 1.0)


if __name__ == "__main__":
    unittest.main()
