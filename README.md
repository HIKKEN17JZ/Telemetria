# 📡 Sistema de Telemetría de Flota Distribuido

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Architecture](https://img.shields.io/badge/architecture-Distributed%20%7C%20Event--Driven-orange.svg)]()
[![Code Style](https://img.shields.io/badge/code%20style-Clean%20Code%20%7C%20TDD-brightgreen.svg)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)]()

Proyecto integrador para el examen final de **Computación 2**. Consiste en un sistema distribuido de recolección, procesamiento en tiempo real, persistencia y visualización de telemetría vehicular, diseñado bajo principios de **alta concurrencia I/O**, **resiliencia de red**, **procesamiento paralelo CPU-bound** y **arquitectura limpia**.

---

## 🏛️ Arquitectura del Sistema

```text
 ┌────────────────────────────────────────────────────────┐
 │                   VEHÍCULOS (CLI)                      │
 │                     (agent.py)                         │
 │  - Simulación física de dinámicas (GPS, Vel, Temp, Comb)│
 │  - Búfer Offline FIFO (Memoria acotada: 1000 items)    │
 │  - Retroceso Exponencial con Jitter (Backoff)          │
 └──────────────────────────┬─────────────────────────────┘
                            │ TCP Sockets (Enmarcado '\n')
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │           SERVIDOR DE INGESTIÓN ASÍNCRONO              │
 │                     (server.py)                        │
 │  - I/O No Bloqueante con asyncio.start_server          │
 │  - Validación estricta de esquemas (src/protocol.py)   │
 │  - IPC: Manejador de señales UNIX (SIGHUP / SIGUSR1)   │
 └─────────────┬──────────────────────────┬───────────────┘
               │                          │
    (Despacho) │                          │ (Persistencia directa)
               ▼                          ▼
 ┌───────────────────────────┐  ┌──────────────────────────┐
 │   REDIS (Message Broker)  │  │   POSTGRESQL 15 (BD)     │
 │       (Puerto: 6380)      │  │      (Puerto: 5435)      │
 └─────────────┬─────────────┘  │  - Series de tiempo      │
               │                │  - Pool de conexiones    │
               ▼                │  - Índices temporales    │
 ┌───────────────────────────┐  └──────────────▲───────────┘
 │  CELERY WORKERS (Paralelo)│                 │
 │  - Multiprocessing prefork│─────────────────┘
 │  - Cálculo de geocercas   │ (Persistencia en lotes y alertas)
 │  - Detección de anomalías │
 └───────────────────────────┘
               │
               ▼
 ┌────────────────────────────────────────────────────────┐
 │       API GATEWAY & MONITOREO EN TIEMPO REAL           │
 │  - Gunicorn + Uvicorn (Workers procesos e hilos threads)│
 │  - Semi-Frontend de Escritorio en Tkinter              │
 │    (Multithreading: Thread UI + Thread Red vía Queue)  │
 └────────────────────────────────────────────────────────┘
```

---

## 👥 Equipo y Distribución de Roles

| Desarrollador | Rol | Áreas de Enfoque Principal |
| :--- | :--- | :--- |
| **Ale** (`@HIKKEN17JZ`) | **Dev 1** | Agente vehicular CLI, Resiliencia de red con búfer offline, Frontend en **Tkinter** con **Multithreading**. |
| **Charango** (`@Charango21`) | **Dev 2** | Core del Servidor Asíncrono (`asyncio`), Protocolo de enmarcado (`\n`), **IPC (Señales UNIX)** y **API Gateway (Gunicorn + Uvicorn)**. |
| **Agus** (`@AgusValdebenito`) | **Dev 3** | Infraestructura con **Docker Compose**, Persistencia en **PostgreSQL**, **Lógica Paralela (Celery)** y **PlantUML**. |

---

## 🚀 Estado Actual del Desarrollo

### ✅ Sprint 1 — Pipeline Base y Transmisión Concurrente (Completado)
* **[Issue #1] Infraestructura base con Docker Compose:** Servicios de PostgreSQL 15 y Redis 7 con *healthchecks*, redes puente y volúmenes persistentes.
* **[Issue #2] Core del Servidor TCP Asíncrono:** Servidor de alta concurrencia I/O implementado con `asyncio.start_server`, `StreamReader` y `StreamWriter`.
* **[Issue #3] Agente vehicular CLI:** Emisor de métricas configurable por línea de comandos (`argparse`) con simulación física realista.

### ⚙️ Sprint 2 — Persistencia, Protocolo y Resiliencia (Completado)
* **[Issue #4] Persistencia en PostgreSQL (`src/database.py`):** Connection pool seguro (`psycopg_pool`), transacciones ACID y consultas optimizadas para series de tiempo.
* **[Issue #5] Protocolo de comunicación y validación (`src/protocol.py`):** Enmarcado por fin de línea `\n`, deserialización robusta y generación de respuestas `ACK`/`NACK`.
* **[Issue #6] Conector TCP resiliente con Búfer Offline (`src/buffer.py`, `src/backoff.py`):**
  * **Búfer FIFO en memoria acotado:** Acumula mediciones si el servidor se cae y las descarga secuencialmente en ráfaga al reconectar.
  * **Exponential Backoff con Jitter:** Evita sobrecargas en reconexiones calculando esperas progresivas con dispersión aleatoria.
  * **Graceful Shutdown:** Captura señales `SIGINT` (Ctrl+C) y `SIGTERM` para liberar sockets y recursos limpiamente.

---

## 📂 Estructura del Repositorio

```text
.
├── agent.py                     # Punto de entrada del Agente Vehicular CLI
├── server.py                    # Punto de entrada del Servidor TCP Asíncrono
├── boot.ps1                     # Lanzador rápido interactivo para Windows PowerShell
├── boot.sh                      # Lanzador rápido interactivo para Bash / Linux
├── docker-compose.yml           # Orquestación de infraestructura (Postgres + Redis)
├── init_db.sql                  # Esquema DDL inicial e índices para PostgreSQL
├── requirements.txt             # Dependencias del proyecto Python
├── .env.example                 # Plantilla de variables de entorno
├── docs/                        # Documentación técnica
│   └── issues_backlog.md        # Planificación ágil y especificación de los 12 issues
├── src/                         # Código fuente modular (Clean Architecture)
│   ├── backoff.py               # Algoritmo de retroceso exponencial con jitter
│   ├── buffer.py                # Búfer circular FIFO para tolerancia a caídas
│   ├── cli.py                   # Parser y validación estricta con argparse
│   ├── database.py              # Pool de conexiones y capa de datos PostgreSQL
│   ├── models.py                # Modelos de dominio fuertemente tipados
│   ├── network.py               # Cliente TCP socket resiliente
│   ├── protocol.py              # Enmarcado, validación de esquemas y ACK/NACK
│   └── simulator.py             # Generador sintético de cinemática vehicular
└── tests/                       # Suite de pruebas automatizadas (TDD)
    ├── test_agent.py            # Tests de inicialización y ciclo de vida del agente
    ├── test_backoff.py          # Tests del cálculo de retardos y jitter
    ├── test_buffer.py           # Tests del búfer FIFO y descarte acotado
    ├── test_cli.py              # Tests del parser de argumentos y validaciones
    ├── test_database.py         # Tests de persistencia relacional
    ├── test_integration_e2e.py  # Test de integración extremo a extremo Server-Agent
    ├── test_network.py          # Tests de conectividad TCP con socket mock
    ├── test_protocol.py         # Tests de validación de tramas y enmarcado
    ├── test_resilient_network.py# Tests de tolerancia a caídas y vaciado de búfer
    └── test_simulator.py        # Tests de coherencia física y modelos
```

---

## ⚡ Guía de Inicio Rápido

### Requisitos Previos
* **Python 3.10 o superior**
* **Docker y Docker Compose** (opcional para levantar base de datos PostgreSQL y broker Redis)

### Instalación de Dependencias
```bash
pip install -r requirements.txt
```

---

### Opción A: Usando los Scripts de Arranque Rápido (Recomendado)

#### En Windows (PowerShell):
```powershell
# Lanzar la DEMO completa (Abre 3 ventanas: Servidor + 2 Vehículos en paralelo)
.\boot.ps1 demo

# O abrir el menú interactivo:
.\boot.ps1
```

#### En Linux / macOS / Git Bash:
```bash
chmod +x boot.sh
./boot.sh demo
```

---

### Opción B: Ejecución Manual

#### 1. Iniciar la infraestructura (Opcional):
```bash
docker compose up -d
docker compose ps
```

#### 2. Iniciar el Servidor de Ingestión TCP:
```bash
python server.py --host 127.0.0.1 --port 5000
```

#### 3. Iniciar Agentes Vehiculares (en terminales separadas):
```bash
# Vehículo 1 (Automóvil con frecuencia de 2s):
python agent.py --vehicle-id AUTO-001 --interval 2.0

# Vehículo 2 (Camión con frecuencia de 1s):
python agent.py --vehicle-id CAMION-002 --interval 1.0
```

#### Opciones de configuración del Agente CLI (`agent.py --help`):
* `--vehicle-id`: Identificador único del vehículo (default: `AUTO-001`).
* `--server-host`: IP o hostname del servidor TCP (default: `127.0.0.1`).
* `--server-port`: Puerto TCP del servidor (default: `5000`).
* `--interval`: Intervalo de muestreo en segundos (default: `2.0`).
* `--buffer-size`: Capacidad del búfer offline en memoria (default: `1000`).
* `--max-backoff`: Tiempo máximo de reintento en segundos (default: `30.0`).

---

## 🧪 Ejecución de Pruebas Automatizadas (TDD)

El proyecto se desarrolla bajo metodología **Test-Driven Development (TDD)** con una cobertura integral de pruebas unitarias y de integración de red:

```bash
# Ejecutar todas las pruebas unitarias y de integración del agente:
python -m unittest tests/test_agent.py tests/test_cli.py tests/test_simulator.py tests/test_network.py tests/test_buffer.py tests/test_backoff.py tests/test_resilient_network.py tests/test_integration_e2e.py

# O mediante los lanzadores automatizados:
.\boot.ps1 test
./boot.sh test
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
