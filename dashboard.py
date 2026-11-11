#!/usr/bin/env python3
"""
Dashboard de Monitoreo de Flota en Escritorio (Tkinter).

Punto de entrada ejecutable para la interfaz gráfica de escritorio.
Integra una arquitectura Multithreading (threading.Thread + queue.Queue)
para consumir telemetría y alertas en tiempo real desde el API Gateway / Servidor
sin bloquear el bucle principal de la GUI (mainloop).
"""

import argparse
import os
import queue
import sys
import tkinter as tk

from src.dashboard_model import FleetDashboardState
from src.dashboard_gui import FleetDashboardView
from src.dashboard_network import (
    DashboardNetworkReceiver,
    NetworkReceiverConfig
)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dashboard de Monitoreo de Flota en Escritorio (Tkinter con Multithreading)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--gateway-url",
        type=str,
        default=os.getenv("GATEWAY_URL", "http://127.0.0.1:8000"),
        help="URL base del API Gateway de telemetría"
    )
    parser.add_argument(
        "--speed-limit",
        type=float,
        default=float(os.getenv("SPEED_LIMIT_KMH", "120.0")),
        help="Umbral de velocidad máxima (km/h) para alerta crítica"
    )
    parser.add_argument(
        "--temp-limit",
        type=float,
        default=float(os.getenv("TEMP_LIMIT_C", "100.0")),
        help="Umbral de temperatura máxima (°C) para alerta crítica"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Intervalo de sondeo REST en segundos (modo fallback)"
    )
    parser.add_argument(
        "--stream-mode",
        choices=["auto", "stream", "poll"],
        default="auto",
        help="Modo de conexión de red: 'auto' (SSE con fallback REST), 'stream' (solo SSE) o 'poll' (solo REST)"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        default=False,
        help="Modo fuera de línea: Desactiva el hilo de red y permite usar la botonera de simulación local"
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()

    print("=" * 65)
    print("   🖥️ DASHBOARD DE MONITOREO DE FLOTA (TKINTER MULTITHREADING)")
    print("=" * 65)
    print(f" [*] Modo de red:     {'OFFLINE (Simulación local)' if args.offline else args.stream_mode.upper()}")
    if not args.offline:
        print(f" [*] API Gateway:     {args.gateway_url}")
        print(f" [*] Sondeo Fallback: cada {args.poll_interval}s")
    print(f" [*] Umbral Vel:      {args.speed_limit} km/h")
    print(f" [*] Umbral Temp:     {args.temp_limit} °C")
    print("=" * 65)

    state = FleetDashboardState(
        speed_limit_kmh=args.speed_limit,
        temp_critical_c=args.temp_limit
    )

    event_queue = queue.Queue()
    receiver = None

    if not args.offline:
        config = NetworkReceiverConfig(
            gateway_url=args.gateway_url,
            poll_interval=args.poll_interval,
            stream_mode=args.stream_mode
        )
        receiver = DashboardNetworkReceiver(config=config, event_queue=event_queue)
        receiver.start()

    root = tk.Tk()
    app = FleetDashboardView(
        root=root,
        state=state,
        network_receiver=receiver,
        event_queue=event_queue,
        auto_poll_queue=True,
        queue_poll_interval_ms=100
    )

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        if receiver and receiver.is_alive():
            receiver.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
