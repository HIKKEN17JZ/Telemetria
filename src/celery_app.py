"""
Configuración e inicialización de Celery Application (Issue #7).
Asignado a: Agus (Dev 3)

Define la aplicación distribuida Celery utilizando Redis como Message Broker
y Result Backend, con serialización estricta en JSON y control de concurrencia.
"""

import os
from pathlib import Path
from celery import Celery

# Cargar variables de entorno desde .env si existe
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# Configuración de URLs de conexión a Redis (Message Broker & Result Backend)
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = os.getenv("REDIS_PORT", "6380")
REDIS_DB = os.getenv("REDIS_DB", "0")

DEFAULT_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
BROKER_URL = os.getenv("CELERY_BROKER_URL", DEFAULT_BROKER_URL)
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", DEFAULT_BROKER_URL)

# Instancia central de Celery
app = Celery(
    "telemetria_tasks",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["src.tasks"]
)

# Configuración técnica optimizada y segura
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True
)

if __name__ == "__main__":
    app.start()
