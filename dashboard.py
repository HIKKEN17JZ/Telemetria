#!/usr/bin/env python3
"""
Dashboard de Monitoreo de Flota en Escritorio (Tkinter) - Issue #10
Asignado a: Ale (Dev 1 - @HIKKEN17JZ)

Punto de entrada ejecutable para la interfaz gráfica de escritorio.
Permite visualizar la flota en tiempo real, evaluar alertas visuales y simular eventos.
"""

import argparse
import sys
import tkinter as tk

from src.dashboard_model import FleetDashboardState
from src.dashboard_gui import FleetDashboardView


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dashboard de Monitoreo de Flota en Escritorio (Tkinter)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--speed-limit",
        type=float,
        default=120.0,
        help="Umbral de velocidad máxima (km/h) para alerta crítica"
    )
    parser.add_argument(
        "--temp-limit",
        type=float,
        default=100.0,
        help="Umbral de temperatura máxima (°C) para alerta crítica"
    )

    args = parser.parse_args()

    state = FleetDashboardState(
        speed_limit_kmh=args.speed_limit,
        temp_critical_c=args.temp_limit
    )

    root = tk.Tk()
    app = FleetDashboardView(root=root, state=state)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

