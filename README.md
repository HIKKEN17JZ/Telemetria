# 📡 Sistema de Telemetría de Flota Distribuido

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Architecture](https://img.shields.io/badge/architecture-Distributed%20%7C%20Event--Driven-orange.svg)]()
[![Code Style](https://img.shields.io/badge/code%20style-Clean%20Code%20%7C%20TDD-brightgreen.svg)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)]()

Proyecto integrador para el examen final de **Computación 2**. Consiste en un sistema distribuido de recolección, procesamiento paralelo en segundo plano, persistencia relacional y visualización en tiempo real de telemetría vehicular, diseñado bajo principios de **concurrencia I/O**, **procesamiento distribuido CPU-bound**, **IPC mediante señales UNIX**, **resiliencia de red** y **arquitectura desacoplada**.

---

## 📚 Documentación del Proyecto

* **[INSTALL.md](INSTALL.md):** Guía paso a paso de clonado, entorno virtual, Docker Compose, despliegue y ejecución de pruebas en Linux y Windows.
* **[INFO.md](INFO.md):** Informe de arquitectura, responsabilidades por entidad y justificación técnica de las decisiones de diseño.
* **[TODO.md](TODO.md):** Listado de mejoras, bugs detectados y futuras funcionalidades planificadas.
* **[docs/Requisitos.md](docs/Requisitos.md):** Consigna y requisitos del examen final.
* **[docs/issues_backlog.md](docs/issues_backlog.md):** Planificación ágil y criterios de aceptación de los 12 issues del proyecto.
* **Diagramas PlantUML:** [`docs/architecture.puml`](docs/architecture.puml) y [`docs/data_flow.puml`](docs/data_flow.puml).

---

## 🏛️ Arquitectura del Sistema

```text
 ┌────────────────────────────────────────────────────────┐
 │                   VEHÍCULOS (CLI)                      │
 │                     (agent.py)                         │
 │  - Simulación física de dinámicas (GPS, Vel, Temp, Comb)│
 │  - Búfer Offline FIFO (Memoria acotada: 1000 items)    │
 │  - Exponential Backoff con Jitter + Graceful Shutdown  │
 └──────────────────────────┬─────────────────────────────┘
                            │ TCP Sockets (JSON + '\n')
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │           SERVIDOR DE INGESTIÓN ASÍNCRONO              │
 │                     (server.py)                        │
 │  - I/O No Bloqueante con asyncio.start_server          │
 │  - Validación de esquemas y ACK/NACK (src/protocol.py) │
 │  - IPC: Señales UNIX (SIGHUP / SIGUSR1)                │
 └─────────────┬──────────────────────────┬───────────────┘
               │                          │
 (Despacho     │                          │ (Streaming en vivo
  no bloq.)    ▼                          ▼  vía HTTP POST)
 ┌───────────────────────────┐  ┌─────────────────────────┐
 │   REDIS (Message Broker)  │  │      API GATEWAY        │
 │       (Puerto: 6380)      │  │     (gateway.py)        │
 └─────────────┬─────────────┘  │ - FastAPI + Gunicorn    │
               │                │ - Uvicorn Workers/Thrds │
               ▼                │ - REST + SSE + WS       │
 ┌───────────────────────────┐  └───────────▲──┬──────────┘
 │  CELERY WORKERS (Paralelo)│              │  │
 │  - Multiprocessing prefork│              │  │ SSE / REST
 │  - Detección de anomalías │              │  ▼
 │  - Persistencia batch/rep │  ┌───────────┴─────────────┐
 └─────────────┬─────────────┘  │  DASHBOARD ESCRITORIO   │
               │                │    (dashboard.py)       │
               ▼                │  - Tkinter / ttk (MVP)  │
 ┌───────────────────────────┐  │  - Hilo Red + Queue     │
 │   POSTGRESQL 15 (BD)      │◄─┤  - Actualización segura │
 │      (Puerto: 5435)       │  │    con root.after()     │
 └───────────────────────────┘  └─────────────────────────┘
```

---

## 👥 Equipo y Distribución de Roles

| Desarrollador | Rol | Áreas de Enfoque Principal |
| :--- | :--- | :--- |
| **Ale** (`@HIKKEN17JZ`) | **Dev 1** | Agente vehicular CLI, Resiliencia de red con búfer offline, Dashboard en **Tkinter** con **Multithreading**. |
| **Charango** (`@Charango21`) | **Dev 2** | Core del Servidor Asíncrono (`asyncio`), Protocolo de enmarcado (`\n`), **IPC (Señales UNIX)** y **API Gateway (Gunicorn + Uvicorn)**. |
| **Agus** (`@AgusValdebenito`) | **Dev 3** | Infraestructura con **Docker Compose**, Persistencia en **PostgreSQL**, **Lógica Paralela (Celery)** y **PlantUML**. |

---

## 🚀 Estado del Desarrollo (3 Sprints / 12 Issues)

### 🏁 Sprint 1 — Pipeline Base y Transmisión Concurrente
* **[Issue #1] Infraestructura base con Docker Compose:** PostgreSQL 15, Redis 7 y worker Celery con *healthchecks*, red puente (`telemetria_net`) y volúmenes persistentes.
* **[Issue #2] Core del Servidor TCP Asíncrono:** Servidor concurrente con `asyncio.start_server`, `StreamReader` y `StreamWriter`.
* **[Issue #3] Agente vehicular CLI:** Emisor configurable por CLI (`argparse`) con simulación física de trayectorias y métricas.

### ⚙️ Sprint 2 — Persistencia, Protocolo, IPC y Resiliencia
* **[Issue #4] Persistencia en PostgreSQL (`src/database.py`):** Connection pool con `psycopg_pool`, transacciones seguras y esquema relacional con índices temporales (`init_db.sql`).
* **[Issue #5] Protocolo y validación (`src/protocol.py`):** Enmarcado delimitado por `\n`, validación estricta de rangos/esquemas y respuestas `ACK`/`NACK`.
* **[Issue #6] Conector TCP resiliente (`src/buffer.py`, `src/backoff.py`, `src/network.py`):** Búfer FIFO acotado offline, cálculo de *exponential backoff* con jitter y apagado ordenado (`SIGINT`/`SIGTERM`).
* **[Issue #7] Celery y procesamiento paralelo (`src/celery_app.py`, `src/tasks.py`):** Workers `prefork` con Redis como broker/backend, serialización JSON y detección de umbrales con reintentos automáticos.
* **[Issue #8] Despacho asíncrono e IPC (`server.py`):** Despacho no bloqueante hacia Celery (`run_in_executor`) y manejadores de señales UNIX (`SIGHUP` y `SIGUSR1`).
* **[Issue #9] Persistencia masiva, reportes y PlantUML:** Inserción por lotes (`executemany`), snapshots agregados (`fleet_reports`) y diagramas en `docs/`.

### 🖥️ Sprint 3 — Dashboard Tkinter, API Gateway y Tiempo Real
* **[Issue #10] Dashboard de Escritorio Tkinter (`src/dashboard_gui.py`, `src/dashboard_model.py`):** Interfaz gráfica desacoplada (MVP + Observer) con KPIs, tabla de vehículos y visor de alertas coloreadas.
* **[Issue #11] API Gateway (`gateway.py`, `src/gateway.py`, `gunicorn.conf.py`):** FastAPI servida con Gunicorn + Uvicorn workers/threads, endpoints REST (`/api/vehicles`, `/api/alerts`, `/api/stats`, `/api/system/concurrency`), SSE (`/api/stream`) y WebSockets (`/ws`).
* **[Issue #12] Integración en Tiempo Real Multithreading (`src/dashboard_network.py`, `dashboard.py`):** Hilo secundario demonio conectado por `queue.Queue` y `root.after()` al bucle principal de Tkinter, con indicador de conectividad y panel de simulación.

---

## 📂 Estructura del Repositorio

```text
.
├── agent.py                     # Punto de entrada del Agente Vehicular CLI
├── server.py                    # Punto de entrada del Servidor TCP Asíncrono + IPC
├── gateway.py                   # Punto de entrada del API Gateway (FastAPI / Uvicorn)
├── dashboard.py                 # Punto de entrada del Dashboard de Escritorio Tkinter
├── gunicorn.conf.py             # Configuración Gunicorn (UvicornWorker + threads)
├── docker-compose.yml           # Orquestación: PostgreSQL + Redis + Celery Worker
├── Dockerfile                   # Imagen Python 3.14 para el worker de Celery
├── init_db.sql                  # DDL inicial, constraints e índices PostgreSQL
├── pytest.ini                   # Configuración de pytest y pytest-asyncio
├── requirements.txt             # Dependencias Python del proyecto
├── .env.example                 # Plantilla de variables de entorno
├── INSTALL.md                   # Guía de instalación, despliegue y ejecución
├── INFO.md                      # Informe de decisiones de diseño y justificaciones
├── TODO.md                      # Lista de mejoras, bugs conocidos y roadmap
├── docs/                        # Requisitos, backlog y diagramas PlantUML
│   ├── Requisitos.md
│   ├── issues_backlog.md
│   ├── architecture.puml / .png
│   └── data_flow.puml / .png
├── src/                         # Código fuente modular
│   ├── backoff.py
│   ├── buffer.py
│   ├── celery_app.py
│   ├── cli.py
│   ├── dashboard_gui.py
│   ├── dashboard_model.py
│   ├── dashboard_network.py
│   ├── database.py
│   ├── gateway.py
│   ├── models.py
│   ├── network.py
│   ├── protocol.py
│   ├── simulator.py
│   └── tasks.py
└── tests/                       # Suite de pruebas unitarias, integración y E2E
```

---

## ⚡ Uso Básico

Para la instalación detallada de dependencias y entorno virtual, consulta **[INSTALL.md](INSTALL.md)**.

### 1. Infraestructura base (Docker Compose)
```bash
cp .env.example .env
docker compose up -d
```

### 2. Servidor TCP de Ingestión
```bash
python server.py --host 0.0.0.0 --port 5000
```

### 3. API Gateway
```bash
# En Linux con Gunicorn + Uvicorn Workers (recomendado):
gunicorn -c gunicorn.conf.py gateway:app

# O multiplataforma con Uvicorn directo:
python gateway.py --host 0.0.0.0 --port 8000 --workers 1
```

### 4. Agentes Vehiculares CLI
```bash
python agent.py --vehicle-id AUTO-001 --server-host 127.0.0.1 --server-port 5000 --interval 2.0
python agent.py --vehicle-id CAMION-002 --server-host 127.0.0.1 --server-port 5000 --interval 1.0
```

Opciones principales de `agent.py --help`:
* `--vehicle-id`: Identificador único del vehículo (default: `AUTO-001`)
* `--server-host`: Host del servidor TCP (default: `127.0.0.1`)
* `--server-port`: Puerto del servidor TCP (default: `5000`)
* `--interval`: Frecuencia de envío en segundos (default: `2.0`)
* `--mode`: Modo de generación (`simulation` o `manual`, default: `simulation`)
* `--buffer-size`: Capacidad del búfer offline en memoria (default: `1000`)
* `--max-backoff`: Tope de espera para reconexión en segundos (default: `30.0`)

### 5. Dashboard Tkinter
```bash
# Conectado al API Gateway en tiempo real:
python dashboard.py --gateway-url http://127.0.0.1:8000 --stream-mode auto

# Modo offline (pruebas locales con la botonera):
python dashboard.py --offline
```

---

## 🧪 Ejecución de Pruebas Automatizadas

Con las dependencias instaladas en tu entorno virtual (`.venv`):

```bash
# Ejecutar toda la suite con pytest:
pytest -v

# En entornos Linux sin servidor gráfico ($DISPLAY):
pytest -v --ignore=tests/test_dashboard_gui.py

# Alternativa con unittest estándar (módulos sin dependencias externas):
python3 -m unittest discover -s tests -v
```

---

## 🛡️ Protocolo de Comunicación sobre TCP

* **Transporte:** TCP Sockets.
* **Enmarcado:** Delimitación obligatoria por salto de línea (`\n`).
* **Payload telemétrico (Vehículo ➡️ Servidor):**
  ```json
  {
    "vehicle_id": "AUTO-001",
    "timestamp": "2026-10-31T20:00:00Z",
    "location": { "lat": -32.8895, "lon": -68.8458 },
    "metrics": {
      "speed_kmh": 65.4,
      "rpm": 2400,
      "fuel_level_pct": 85.2,
      "engine_temp_c": 88.5
    },
    "status": "MOVING"
  }
  ```
* **Acuse de recibo (Servidor ➡️ Vehículo):**
  ```json
  {
    "status": "ACK",
    "vehicle_id": "AUTO-001",
    "server_time": "2026-10-31T20:00:00Z"
  }
  ```
