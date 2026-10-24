"""
Módulo de parseo y validación de argumentos de línea de comandos.
Sigue principios de Clean Code y Single Responsibility Principle (SRP).
"""

import argparse
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class AgentConfig:
    """Configuración inmutable validada para el Agente Vehicular."""
    vehicle_id: str
    server_host: str
    server_port: int
    interval: float
    mode: str


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos con opciones y defaults del contrato."""
    parser = argparse.ArgumentParser(
        description="Agente Vehicular CLI - Transmisor de Telemetría (Computación 2)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "--vehicle-id",
        type=str,
        default="AUTO-001",
        help="Identificador único del vehículo en la flota"
    )
    parser.add_argument(
        "--server-host",
        type=str,
        default="127.0.0.1",
        help="Dirección IP o hostname del servidor TCP de telemetría"
    )
    parser.add_argument(
        "--server-port",
        type=int,
        default=5000,
        help="Puerto TCP de escucha del servidor"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Intervalo de transmisión en segundos"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["simulation", "manual"],
        default="simulation",
        help="Modo de generación de telemetría"
    )

    return parser


def parse_arguments(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parsea los argumentos pasados o los provenientes de sys.argv."""
    parser = build_parser()
    return parser.parse_args(args)


def validate_config(args: argparse.Namespace) -> AgentConfig:
    """
    Valida la coherencia de los argumentos parseados y retorna un AgentConfig inmutable.
    Lanza ValueError si algún parámetro no cumple los criterios de aceptación.
    """
    vehicle_id = args.vehicle_id.strip()
    if not vehicle_id:
        raise ValueError("El identificador del vehículo (vehicle-id) no puede estar vacío.")

    if not (1 <= args.server_port <= 65535):
        raise ValueError(
            f"El puerto del servidor debe estar entre 1 y 65535. Valor recibido: {args.server_port}"
        )

    if args.interval <= 0:
        raise ValueError(
            f"El intervalo de muestreo debe ser mayor a 0 segundos. Valor recibido: {args.interval}"
        )

    return AgentConfig(
        vehicle_id=vehicle_id,
        server_host=args.server_host.strip(),
        server_port=args.server_port,
        interval=args.interval,
        mode=args.mode
    )
