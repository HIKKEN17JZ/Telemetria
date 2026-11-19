# Guía de Instalación y Despliegue (`INSTALL.md`)

Esta guía detalla los pasos necesarios para clonar, configurar, desplegar y probar el **Sistema de Telemetría de Flota Distribuido** en entornos **Linux** (recomendado para producción, IPC UNIX y Gunicorn) y **Windows**.

---

## 1. Requisitos Previos

* **Git**
* **Python 3.10 o superior** (el proyecto está probado hasta Python 3.14)
* **Docker y Docker Compose** (para PostgreSQL 15, Redis 7 y el worker de Celery)
* **Tkinter (solo Linux):** en varias distribuciones Linux no viene preinstalado con Python.
  * **Fedora / RHEL:** `sudo dnf install python3-tkinter`
  * **Ubuntu / Debian:** `sudo apt-get update && sudo apt-get install -y python3-tk`
  * **Arch Linux:** `sudo pacman -S tk`

---

## 2. Clonar el Repositorio

```bash
git clone https://github.com/HIKKEN17JZ/Telemetria.git
cd Telemetria
```

---

## 3. Configuración de Variables de Entorno

Copia la plantilla `.env.example` hacia `.env` en la raíz del proyecto:

```bash
cp .env.example .env
```

Contenido base de `.env` (puedes ajustarlo según tu entorno):

```env
# PostgreSQL
POSTGRES_DB=telemetria
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_PORT=5435

# Redis
REDIS_PORT=6380
```

> **Nota:** En `docker-compose.yml`, PostgreSQL se expone en el puerto local `5435` (para evitar colisiones con un Postgres local en `5432`) y Redis en `6380` (para evitar colisiones con `6379`).

---

## 4. Entorno Virtual e Instalación de Dependencias Python

### En Linux / macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### En Windows (PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Despliegue de Infraestructura con Docker Compose

Levanta PostgreSQL 15, Redis 7 y el worker paralelo de Celery:

```bash
docker compose up -d --build
```

Verifica que los contenedores estén corriendo y saludables (`healthy`):

```bash
docker compose ps
docker compose logs -f celery_worker
```

Al iniciar por primera vez, PostgreSQL ejecuta automáticamente [`init_db.sql`](init_db.sql), creando las tablas `vehicles`, `telemetry`, `alerts`, `fleet_reports`, sus índices y los vehículos iniciales (`AUTO-001`, `CAMION-002`, `PRUEBA-01`).

Para detener la infraestructura sin borrar datos:

```bash
docker compose down
```

Para borrar también los volúmenes persistentes y reiniciar la base de datos desde cero:

```bash
docker compose down -v
```

---

## 6. Ejecución de los Componentes del Sistema

Con el entorno virtual activado (`.venv`) y los contenedores Docker en marcha, abre terminales separadas para cada servicio:

### 6.1. Servidor de Ingestión TCP (`server.py`)
```bash
python server.py --host 0.0.0.0 --port 5000
```

En **Linux**, puedes probar el mecanismo IPC por señales UNIX desde otra terminal:
```bash
# Obtener PID del servidor
pgrep -af "server.py"

# Recargar configuración en caliente (SIGHUP)
kill -s SIGHUP <PID>

# Volcar métricas operativas en consola/logs (SIGUSR1)
kill -s SIGUSR1 <PID>
```

### 6.2. API Gateway (`gateway.py` / Gunicorn)

* **En Linux (recomendado, usando Gunicorn + Uvicorn Workers & Threads):**
  ```bash
  gunicorn -c gunicorn.conf.py gateway:app
  # Equivalente explícito:
  gunicorn -w 2 -k uvicorn.workers.UvicornWorker --threads 2 gateway:app -b 0.0.0.0:8000
  ```
  > **Importante para streaming SSE en vivo:** Como `StreamBroadcaster` mantiene suscripciones en memoria por worker, si ejecutas `gateway` con múltiples workers (`-w 2`) un cliente SSE conectado al worker A podría no recibir publicaciones enviadas al worker B. Para pruebas de streaming en tiempo real en vivo puedes iniciar con `-w 1` (`GUNICORN_WORKERS=1 gunicorn -c gunicorn.conf.py gateway:app`).

* **Multiplataforma (Uvicorn directo desde `gateway.py`):**
  ```bash
  python gateway.py --host 0.0.0.0 --port 8000 --workers 1
  ```

Endpoints útiles para verificar:
* Documentación interactiva Swagger: `http://127.0.0.1:8000/docs`
* Healthcheck: `http://127.0.0.1:8000/health`
* Diagnóstico de concurrencia: `http://127.0.0.1:8000/api/system/concurrency`

### 6.3. Agentes Vehiculares CLI (`agent.py`)
```bash
# Vehículo 1
python agent.py --vehicle-id AUTO-001 --server-host 127.0.0.1 --server-port 5000 --interval 2.0

# Vehículo 2 (en otra terminal)
python agent.py --vehicle-id CAMION-002 --server-host 127.0.0.1 --server-port 5000 --interval 1.0
```

### 6.4. Dashboard de Escritorio Tkinter (`dashboard.py`)
Requiere sesión gráfica (`$DISPLAY` en Linux o escritorio Windows):

```bash
# Conectado al API Gateway (SSE con fallback automático)
python dashboard.py --gateway-url http://127.0.0.1:8000 --stream-mode auto

# Modo offline (solo simulación local mediante botonera)
python dashboard.py --offline
```

---

## 7. Ejecución de la Suite de Pruebas Automatizadas

Con el entorno virtual activado (`.venv`):

```bash
# Ejecutar toda la suite con pytest (recomendado)
pytest -v

# Ejecutar pruebas específicas sin entorno gráfico (por ej. servidor SSH/headless)
pytest -v --ignore=tests/test_dashboard_gui.py
```

Si PostgreSQL está levantado en `127.0.0.1:5435`, [`tests/test_database.py`](tests/test_database.py) ejecutará también las pruebas de integración reales contra la base de datos; de lo contrario, las omitirá limpiamente (`skipped`).
