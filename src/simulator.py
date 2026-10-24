"""
Simulador de dinámicas vehiculares y generación de telemetría sintética.
Cumple con el criterio de trayectorias coherentes y variaciones físicas lógicas.
"""

import random
from typing import Optional
from src.models import TelemetryPayload


class VehicleSimulator:
    """
    Simula el comportamiento físico de un vehículo en ruta (posición, velocidad,
    revoluciones del motor, temperatura y consumo de combustible).
    """

    # Constantes físicas de simulación
    SPEED_MIN_KMH = 0.0
    SPEED_MAX_KMH = 135.0
    IDLE_SPEED_THRESHOLD = 5.0
    BASE_ENGINE_TEMP_C = 80.0
    MAX_ENGINE_TEMP_C = 110.0

    def __init__(
        self,
        vehicle_id: str,
        start_lat: float = -32.8895,
        start_lon: float = -68.8458,
        initial_fuel: float = 95.0,
        initial_speed: float = 40.0
    ):
        self.vehicle_id = vehicle_id
        self.lat = start_lat
        self.lon = start_lon
        self.fuel = initial_fuel
        self.speed = initial_speed
        self.temp = self.BASE_ENGINE_TEMP_C

    def step(self) -> None:
        """Avanza un paso de tiempo en la simulación actualizando las variables de estado."""
        # Avance geográfico gradual (aprox. unas pocas decenas de metros por paso)
        if self.speed > self.IDLE_SPEED_THRESHOLD:
            lat_delta = random.uniform(-0.0004, 0.0004)
            lon_delta = random.uniform(-0.0004, 0.0004)
            self.lat += lat_delta
            self.lon += lon_delta

        # Aceleración o desaceleración suave
        acceleration = random.uniform(-4.5, 4.5)
        self.speed = max(self.SPEED_MIN_KMH, min(self.SPEED_MAX_KMH, self.speed + acceleration))

        # Consumo de combustible proporcional al uso
        fuel_consumption = 0.005 if self.speed < self.IDLE_SPEED_THRESHOLD else 0.02 + (self.speed / 2000.0)
        self.fuel = max(0.0, self.fuel - fuel_consumption)

        # Temperatura del motor: aumenta con la velocidad y se estabiliza alrededor de 88°C-98°C
        target_temp = self.BASE_ENGINE_TEMP_C + (self.speed / self.SPEED_MAX_KMH) * 20.0
        temp_delta = (target_temp - self.temp) * 0.1 + random.uniform(-0.4, 0.4)
        self.temp = max(60.0, min(self.MAX_ENGINE_TEMP_C, self.temp + temp_delta))

    @property
    def rpm(self) -> int:
        """Calcula las revoluciones por minuto coherentemente con la velocidad."""
        if self.speed < self.IDLE_SPEED_THRESHOLD:
            return random.randint(750, 850)  # Ralentí
        # Simulación de marchas en régimen normal de crucero
        rpm_factor = 28.0 + random.uniform(-2.0, 2.0)
        return int(min(5500, self.speed * rpm_factor + 900))

    @property
    def status(self) -> str:
        """Determina el estado operativo del vehículo."""
        return "MOVING" if self.speed > self.IDLE_SPEED_THRESHOLD else "IDLE"

    def next_telemetry(self) -> TelemetryPayload:
        """Ejecuta una iteración y retorna el payload serializable listo para el contrato."""
        self.step()
        return TelemetryPayload.create(
            vehicle_id=self.vehicle_id,
            lat=self.lat,
            lon=self.lon,
            speed_kmh=self.speed,
            rpm=self.rpm,
            fuel_level_pct=self.fuel,
            engine_temp_c=self.temp,
            status=self.status
        )
