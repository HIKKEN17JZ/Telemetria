"""
Configuración de Gunicorn para el API Gateway (Issue #11).
Asignado a: Charango (Dev 2 - @Charango21)

Orquesta workers de Uvicorn con combinación de paralelismo multi-proceso
y concurrencia multihilo:
- workers = 2 (Procesos aislados en memoria, aprovechan núcleos de CPU)
- threads = 2 (Hilos concurrentes por worker para operaciones I/O-bound)
- worker_class = "uvicorn.workers.UvicornWorker" (Event loop no bloqueante con asyncio)

Comando equivalente por CLI:
    gunicorn -w 2 -k uvicorn.workers.UvicornWorker --threads 2 gateway:app -b 0.0.0.0:8000
"""

import os
import multiprocessing

# Interfaz de red y puerto de escucha
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# Cantidad de procesos workers independientes (Multiprocessing)
# Cada worker tiene su propio PID, su propio GIL y su propio Event Loop de asyncio
workers = int(os.getenv("GUNICORN_WORKERS", "2"))

# Clase de worker asíncrono basada en Uvicorn
worker_class = "uvicorn.workers.UvicornWorker"

# Cantidad de hilos por worker (Multithreading)
# Asisten al worker en la ejecución de tareas de I/O bloqueante (ej. psycopg hacia PostgreSQL)
threads = int(os.getenv("GUNICORN_THREADS", "2"))

# Parámetros de conexión y timeouts
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
backlog = 2048

# Configuración de logging estructurado a stdout/stderr
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" (pid:%(p)s)'


def on_starting(server):
    """Hook ejecutado al inicializar el proceso maestro de Gunicorn."""
    server.log.info(
        f"Iniciando Master Gunicorn (PID {os.getpid()}) con {workers} Uvicorn workers "
        f"y {threads} hilos por worker..."
    )


def post_fork(server, worker):
    """Hook ejecutado luego de que el proceso master crea un worker hijo con fork()."""
    server.log.info(
        f"Worker inicializado con fork() -> PID: {worker.pid} (threads: {threads})"
    )
