#!/usr/bin/env python3
"""
Agente Vehicular CLI - Transmisor de Telemetría Resiliente.

Punto de entrada principal para la ejecución del agente vehicular en terminal.
Combina parseo de argumentos CLI, simulación de dinámicas vehiculares,
transmisión TCP resiliente con buffer offline FIFO y reconexión exponencial con jitter.
"""

import logging
import signal
import sys
import time
from typing import Optional

from src.cli import parse_arguments, validate_config, AgentConfig
from src.simulator import VehicleSimulator
from src.network import TelemetryClient
from src.buffer import TelemetryBuffer
from src.backoff import ExponentialBackoff


def setup_logger() -> logging.Logger:
    """Configura el sistema de logging con formato limpio para consola."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] (%(name)s): %(message)s",
        datefmt="%H:%M:%S"
    )
    return logging.getLogger("AgenteCLI")


def calculate_initial_coordinates(vehicle_id: str) -> tuple[float, float]:
    """Genera coordenadas iniciales dispersas basadas en el hash del ID para evitar colisiones."""
    base_lat = -32.8895
    base_lon = -68.8458
    offset_hash = hash(vehicle_id) % 1000
    lat_offset = (offset_hash / 10000.0) - 0.05
    lon_offset = ((hash(vehicle_id[::-1]) % 1000) / 10000.0) - 0.05
    return (base_lat + lat_offset, base_lon + lon_offset)


class AgentApp:
    """Orquestador principal del ciclo de vida del agente vehicular."""

    def __init__(self, config: AgentConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.running = False

        init_lat, init_lon = calculate_initial_coordinates(config.vehicle_id)
        self.simulator = VehicleSimulator(
            vehicle_id=config.vehicle_id,
            start_lat=init_lat,
            start_lon=init_lon
        )

        buffer = TelemetryBuffer(max_size=config.buffer_size)
        backoff = ExponentialBackoff(
            initial_delay=1.0,
            max_delay=config.max_backoff,
            multiplier=2.0,
            jitter=True
        )

        self.client = TelemetryClient(
            host=config.server_host,
            port=config.server_port,
            timeout=3.0,
            buffer=buffer,
            backoff=backoff
        )

    def stop(self) -> None:
        """Detiene de forma limpia el bucle de ejecución."""
        self.running = False

    def run(self) -> None:
        """Ejecuta el bucle continuo de muestreo y transmisión periódica resiliente."""
        self.running = True
        self.logger.info("=" * 65)
        self.logger.info(f"🚗 Iniciando Agente Vehicular Resiliente: {self.config.vehicle_id}")
        self.logger.info(f"🎯 Servidor Destino: {self.config.server_host}:{self.config.server_port}")
        self.logger.info(
            f"⏱️ Frecuencia: cada {self.config.interval}s | "
            f"Búfer: {self.config.buffer_size} max | Modo: {self.config.mode}"
        )
        self.logger.info("=" * 65)

        if not self.client.connect():
            self.logger.warning("⚠️ Servidor no disponible al iniciar. Se acumulará telemetría en buffer local.")

        while self.running:
            try:
                payload = self.simulator.next_telemetry()
                metrics = payload.metrics
                coords = payload.location

                self.logger.info(
                    f"📤 [{payload.vehicle_id}] Vel: {metrics.speed_kmh:5.1f} km/h | "
                    f"RPM: {metrics.rpm:4d} | Temp: {metrics.engine_temp_c:4.1f}°C | "
                    f"Comb: {metrics.fuel_level_pct:5.1f}% | "
                    f"GPS: ({coords.lat:.4f}, {coords.lon:.4f})"
                )

                response = self.client.send_or_buffer(payload)
                if response.success:
                    ack_status = response.data.get("status") if response.data else "OK"
                    self.logger.info(f"   📥 ACK recibido del servidor: {ack_status}")
                elif response.buffered:
                    self.logger.warning(
                        f"   ⚠️ Modo Offline: medición encolada en buffer local (Total en cola: {response.queue_size}). "
                        f"Próximo reintento calculado: {self.client.backoff.last_delay:.1f}s"
                    )
                else:
                    self.logger.warning(f"   ⚠️ Falló transmisión: {response.error_message}")

                time.sleep(self.config.interval)

            except Exception as e:
                self.logger.error(f"Error inesperado en el ciclo del agente: {e}")
                time.sleep(self.config.interval)

        pending = len(self.client.buffer)
        if pending > 0:
            self.logger.info(f"📦 El agente se detuvo con {pending} mediciones pendientes en búfer local.")
        self.client.disconnect()
        self.logger.info("✅ Agente desconectado limpiamente.")


def main(argv: Optional[list[str]] = None) -> int:
    """Punto de entrada de la aplicación."""
    logger = setup_logger()

    try:
        raw_args = parse_arguments(argv)
        config = validate_config(raw_args)
    except ValueError as e:
        logger.error(f"Error de configuración: {e}")
        return 1
    except SystemExit as e:
        return e.code

    app = AgentApp(config=config, logger=logger)

    def handle_signal(sig, frame):
        logger.info("\n🛑 Señal recibida (Ctrl+C / SIGINT). Apagando agente ordenadamente...")
        app.stop()
        app.client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
