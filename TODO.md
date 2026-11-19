# Lista de Mejoras, Correcciones Pendientes y Futuras Versiones (`TODO.md`)

Este documento detalla los problemas detectados durante la auditoría técnica del proyecto y las mejoras planificadas para próximas iteraciones.

---

## 🔴 Prioridad Alta (Bugs y Brechas Detectadas Pre-Final)

- [ ] **Corregir registro de señales UNIX fuera del hilo principal (`server.py`):**
  - En `setup_signal_handlers()`, `loop.add_signal_handler(...)` lanza `RuntimeError` en Linux cuando se invoca desde un hilo secundario (como ocurre en `tests/test_integration_e2e.py`). Capturar `RuntimeError` junto a `(ValueError, NotImplementedError)` para degradar limpiamente y destrabar el test E2E en Linux.
- [ ] **Corregir lógica de `stream_mode` en el receptor del Dashboard (`src/dashboard_network.py`):**
  - En `DashboardNetworkReceiver.run()`, cuando `stream_mode="poll"` entra incorrectamente a `_stream_tcp_server("127.0.0.1", 5000)` en lugar de `_poll_fallback()`, y cuando `stream_mode="stream"` falla el SSE cae al polling REST. Además, desparametrizar el host/puerto TCP hardcoded (`127.0.0.1:5000`).
- [ ] **Aplicar efectivamente el *Exponential Backoff* en el bucle del Agente (`agent.py` / `src/network.py`):**
  - Actualmente `ExponentialBackoff.next_delay()` calcula y loguea el retardo, pero `AgentApp.run()` siempre duerme `time.sleep(self.config.interval)` sin respetar el tiempo calculado de backoff cuando la conexión está caída.
- [ ] **Corregir dependencia `httpx2` en `requirements.txt`:**
  - Reemplazar `httpx2>=2.0.0` por `httpx>=0.27.0` (requerido por `fastapi.testclient.TestClient`).
- [ ] **Manejar entorno sin display (`TkError`) en `tests/test_dashboard_gui.py`:**
  - Agregar `try/except tk.TclError: self.skipTest(...)` en `setUp()` al igual que en `tests/test_dashboard_gui_multithreading.py` y `tests/test_dashboard_e2e_multithreading.py`, para que la suite completa pueda ejecutarse en servidores Linux sin X11/Wayland (CI/CD).

---

## 🟠 Prioridad Media (Arquitectura, Clean Code y Consistencia)

- [ ] **Soporte multi-worker real para streaming en `src/gateway.py` (Redis Pub/Sub):**
  - Reemplazar `StreamBroadcaster` en memoria local por suscripción a Redis Pub/Sub para que con `gunicorn -w 2` (o más workers) todos los procesos reciban y retransmitan los eventos SSE y WebSockets sin importar qué worker atendió `POST /api/telemetry/publish`.
- [ ] **Unificar umbrales y nombres de alertas entre Backend y Frontend:**
  - Extraer una única fuente de verdad (módulo compartido o configuración central) para los umbrales de velocidad, temperatura y combustible que hoy difieren entre `src/tasks.py` (`120/130 km/h`, `105°C`, `10%`) y `src/dashboard_model.py` (`120 km/h`, `100°C`, `15%`).
- [ ] **Reutilizar `ConnectionPool` a nivel de worker en `src/tasks.py`:**
  - Evitar instanciar y cerrar un `DatabaseManager()` completo dentro de cada ejecución de `process_telemetry` / `process_telemetry_batch` / `generate_fleet_summary`. Mantener un pool reutilizable por proceso worker de Celery.
- [ ] **Eliminar problema de consultas N+1 en `GET /api/vehicles` (`src/gateway.py`):**
  - Agregar en `DatabaseManager` una consulta SQL única con `DISTINCT ON (vehicle_id)` o `LATERAL JOIN` para traer todos los vehículos junto a su última medición en una sola ida a PostgreSQL.
- [ ] **Hacer efectivo el hot-reload de `SIGHUP` (`server.py`):**
  - Releer el archivo `.env` (`dotenv.load_dotenv(..., override=True)`) o un archivo de configuración JSON/YAML al recibir `SIGHUP`, e incluir parámetros dinámicos adicionales (como umbrales de alerta o límite de clientes).
- [ ] **Reutilizar `ExponentialBackoff` en `src/dashboard_network.py`:**
  - Reemplazar el cálculo manual de backoff en `DashboardNetworkReceiver.run()` por la clase `src/backoff.py` (principio DRY).
- [ ] **Desacoplar el estado global de `server.py` y mejorar el handshake de monitores:**
  - Encapsular `server_config`, `server_metrics`, `active_clients`, `dashboard_subscribers` y `background_tasks` en una clase `TelemetryServer`.
  - Cambiar la detección de monitores (`"dashboard" in message_str.lower()`) por un mensaje de protocolo JSON explícito (por ejemplo `{"type": "subscribe", "role": "dashboard"}`).
- [ ] **Implementar `--mode manual` en `agent.py`:**
  - Permitir ingreso interactivo de métricas o lectura desde archivo/stdin cuando se pase `--mode manual` (actualmente definido en `src/cli.py` pero sin lógica diferenciada en `agent.py`).
- [ ] **Seed determinista de coordenadas iniciales (`agent.py`):**
  - Reemplazar `hash(vehicle_id)` por `hashlib.sha256` o `zlib.crc32` en `calculate_initial_coordinates()` para que el mismo vehículo inicie en la misma posición entre distintas ejecuciones.

---

## 🟢 Futuras Funcionalidades (Roadmap v2.0)

- [ ] **Programación periódica con Celery Beat + Batching real:**
  - Agregar servicio `celery_beat` en `docker-compose.yml` para ejecutar `generate_fleet_summary` periódicamente (cada 5 minutos), y habilitar un acumulador/buffer de micro-lotes que invoque `process_telemetry_batch`.
- [ ] **Propagación de alertas persistidas al Dashboard en tiempo real:**
  - Publicar también las alertas generadas por Celery hacia el API Gateway (`/api/alerts/publish` o canal Redis Pub/Sub) para que el Dashboard muestre alertas originadas en el backend y no solo las evaluadas localmente.
- [ ] **Seguridad y Autenticación:**
  - Cifrado TLS en sockets TCP del servidor de ingesta y HTTPS/WSS en el API Gateway.
  - Autenticación por API Key o JWT para agentes vehiculares y endpoints del Gateway.
- [ ] **Persistencia local del Agente ante reinicios:**
  - Respaldar el búfer offline en SQLite local en lugar de memoria volátil para no perder telemetría acumulada si se apaga el proceso del vehículo.
- [ ] **Frontend Web con Mapa en Vivo:**
  - Consumir `/api/stream` o `/ws` desde una interfaz web con mapa interactivo (Leaflet / OpenStreetMap) para visualizar rutas y geocercas en tiempo real.
- [ ] **Pipeline de CI/CD:**
  - Agregar GitHub Actions para correr `pytest`, `flake8`/`ruff` y validación de `docker compose` en cada push/PR.
