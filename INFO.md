# Informe Técnico y Decisiones de Diseño (`INFO.md`)

Este documento resume la arquitectura del **Sistema de Telemetría de Flota Distribuido**, las responsabilidades de cada entidad y la justificación técnica de las decisiones de diseño adoptadas para el examen final de **Computación 2**.

---

## 1. Descripción Conceptual del Sistema

El sistema resuelve el problema de **recolección, validación, procesamiento analítico distribuido, almacenamiento histórico y visualización en tiempo real** de métricas generadas por múltiples vehículos en movimiento (coordenadas GPS, velocidad, RPM, combustible y temperatura de motor).

### Entidades y Responsabilidades
1. **Agente Vehicular CLI (`agent.py`, `src/cli.py`, `src/simulator.py`, `src/network.py`, `src/buffer.py`, `src/backoff.py`):**
   * Recolecta/simula telemetría física de un vehículo con configuración por línea de comandos (`argparse`).
   * Serializa paquetes JSON delimitados por `\n` sobre TCP y procesa respuestas `ACK`/`NACK`.
   * Tolera caídas de conectividad mediante un búfer circular FIFO en memoria acotada (`collections.deque(maxlen=N)`) y cálculo de reconexión con *exponential backoff* y *jitter*.
2. **Servidor de Ingestión TCP (`server.py`, `src/protocol.py`):**
   * Atiende múltiples vehículos en paralelo mediante I/O asíncrono no bloqueante (`asyncio.start_server`).
   * Valida sintaxis JSON, estructura y rangos físicos de cada trama antes de aceptarla (`ProtocolValidator`).
   * Despacha tareas de análisis/persistencia a Celery sin bloquear el *event loop*, reenvía telemetría en vivo al API Gateway y admite control operativo en caliente vía señales UNIX (`SIGHUP`, `SIGUSR1`).
3. **Broker y Workers Paralelos (`src/celery_app.py`, `src/tasks.py`, Redis):**
   * Desacoplan la ingestión de red del trabajo pesado o lento (reglas de umbral y escritura en base de datos).
   * Los workers Celery usan el pool `prefork` (`multiprocessing`) para aprovechar múltiples núcleos de CPU de forma paralela e independiente del GIL.
4. **Capa de Persistencia Relacional (`init_db.sql`, `src/database.py`, PostgreSQL 15):**
   * Almacena vehículos, series temporales de telemetría, alertas y reportes agregados con restricciones `CHECK` e integridad referencial.
5. **API Gateway (`gateway.py`, `src/gateway.py`, `gunicorn.conf.py`):**
   * Expone endpoints REST (`/api/vehicles`, `/api/alerts`, `/api/stats`, `/api/system/concurrency`) y canales de streaming en vivo (SSE `/api/stream` y WebSockets `/ws`) ejecutados bajo Gunicorn + Uvicorn.
6. **Dashboard de Escritorio (`dashboard.py`, `src/dashboard_gui.py`, `src/dashboard_model.py`, `src/dashboard_network.py`):**
   * Interfaz gráfica en `Tkinter`/`ttk` desacoplada mediante patrón MVP/Observer y arquitectura multihilo (`threading.Thread` + `queue.Queue` + `root.after()`).

---

## 2. Decisiones Principales de Diseño y Justificación

### 2.1. ¿Por qué `asyncio` en el Servidor TCP (`server.py`) en lugar de `threading` o `multiprocessing` por cliente?
* **Justificación:** La recepción de telemetría por sockets TCP es un problema netamente **I/O-bound** con muchas conexiones persistentes de bajo tráfico por segundo. Crear un proceso o un hilo del sistema operativo por cada vehículo consumiría memoria y tiempo de *context switching* innecesarios al escalar a cientos de vehículos.
* Con `asyncio.start_server` (`StreamReader` / `StreamWriter`), un único hilo con un *event loop* multiplexa todas las conexiones de forma no bloqueante.
* **Resguardo del Event Loop:** Las operaciones síncronas potencialmente bloqueantes (como `process_telemetry.delay(...)` hacia Redis o el POST HTTP hacia el API Gateway) se delegan mediante `loop.run_in_executor(...)` para no congelar la atención de otros clientes TCP.

### 2.2. ¿Por qué enmarcado delimitado por `\n` sobre TCP?
* **Justificación:** TCP es un flujo continuo de bytes (*stream*), no orientado a mensajes. Un paquete grande puede llegar fragmentado en múltiples `recv()`, o varios paquetes pueden llegar concatenados en un único `recv()`.
* Usar JSON compacto terminado en `\n` (`ProtocolFraming`) permite usar `await reader.readline()` en `asyncio` y `extract_frames()` sobre buffers parciales de forma simple, legible y depurable con herramientas estándar.
* El envío de respuestas `ACK`/`NACK` le confirma al agente vehicular si la trama fue aceptada antes de descartarla del búfer local.

### 2.3. ¿Por qué `Celery` con Redis y `prefork` para el procesamiento?
* **Justificación:** Aunque el servidor TCP necesita baja latencia para responder `ACK`, evaluar reglas, hacer cálculos analíticos o escribir en PostgreSQL puede volverse lento o fallar temporalmente si la base de datos está saturada.
* **Desacoplamiento:** Redis actúa como *Message Broker* duradero y rápido en memoria. Si la base de datos o los workers se reinician, los mensajes no se pierden en el socket del vehículo.
* **Paralelismo real:** Los workers de Celery corren por defecto con `prefork` (*multiprocessing*), evitando el límite del GIL de Python para tareas CPU-bound y permitiendo escalar horizontalmente agregando más contenedores worker. Además, se configuró `task_acks_late=True` y `autoretry_for` para tolerancia a fallos.

### 2.4. ¿Por qué IPC mediante Señales UNIX (`SIGHUP` y `SIGUSR1`)?
* **Justificación:** Cumple el requisito de Comunicación Entre Procesos (IPC) permitiendo inspeccionar o reconfigurar el servidor en ejecución sin abrir otro socket administrativo ni reiniciar el proceso (lo que cortaría las conexiones TCP activas de los vehículos):
  * `SIGHUP`: Recarga configuración operativa en caliente.
  * `SIGUSR1`: Vuelca estadísticas en tiempo real (clientes activos, mensajes recibidos/procesados/errores y tasa por segundo).
* Se registran mediante `loop.add_signal_handler(...)` para que la ejecución del callback esté sincronizada con el *event loop* de `asyncio`, con degradación controlada en plataformas sin soporte POSIX completo (como Windows).

### 2.5. ¿Por qué PostgreSQL con `psycopg_pool` e índices compuestos?
* **Justificación del motor relacional:** Los datos tienen relaciones claras (`vehicles` 1:N `telemetry`, `vehicles` 1:N `alerts`) e invariantes físicos estrictos garantizados a nivel de motor con restricciones `CHECK` (`latitude BETWEEN -90 AND 90`, `speed_kmh >= 0`, `fuel_level_pct BETWEEN 0 AND 100`, `severity IN ('INFO', 'WARNING', 'CRITICAL')`).
* **Optimización para series de tiempo:** Las consultas más frecuentes del Gateway buscan la última medición o las últimas alertas de un vehículo (`WHERE vehicle_id = %s ORDER BY timestamp DESC LIMIT 1`). El índice compuesto `idx_telemetry_vehicle_timestamp ON telemetry(vehicle_id, timestamp DESC)` evita escaneos completos de tabla.
* **Connection Pooling:** `psycopg_pool.ConnectionPool` reutiliza conexiones abiertas y evita el costo de handshake TCP/SSL/autenticación en cada inserción o consulta HTTP.

### 2.6. ¿Por qué Gunicorn + Uvicorn (`workers` + `threads`) en el API Gateway?
* **Justificación de los 3 niveles de concurrencia:**
  1. **Procesos (`workers = 2` en Gunicorn):** Cada worker es un proceso independiente con su propio PID, su propio GIL y su propio *event loop*. Permite aprovechar múltiples núcleos de CPU y aislar fallos.
  2. **Asincronismo (`UvicornWorker`):** Cada worker ejecuta un bucle `asyncio` capaz de sostener múltiples conexiones HTTP, SSE (`/api/stream`) y WebSockets (`/ws`) concurrentes sin bloquearse esperando I/O de red.
  3. **Hilos (`threads = 2` + `asyncio.to_thread`):** Como `DatabaseManager` usa `psycopg` en modo síncrono, las consultas a PostgreSQL dentro de los endpoints `async def` de FastAPI se ejecutan en hilos secundarios vía `asyncio.to_thread(...)`, evitando bloquear el *event loop* de Uvicorn.
* **Limitación conocida:** `StreamBroadcaster` almacena las colas `asyncio.Queue` de suscriptores SSE/WebSocket en memoria local de cada worker. En despliegues con `workers > 1`, requiere un bus compartido (p. ej. Redis Pub/Sub) para garantizar que todos los workers difundan los mismos eventos (registrado en [`TODO.md`](TODO.md)).

### 2.7. ¿Por qué Tkinter con `threading.Thread` + `queue.Queue` + `root.after()`?
* **Justificación:** El `mainloop()` de Tkinter **no es thread-safe**: si un hilo secundario modifica widgets directamente provoca bloqueos o errores de Tcl/Tk, y si se hacen peticiones HTTP o lecturas de streaming dentro del hilo principal la ventana se congela.
* **Solución adoptada:**
  * Un hilo demonio (`DashboardNetworkReceiver`) consume SSE / REST / TCP en segundo plano y solo deposita objetos `NetworkEvent` en una cola thread-safe (`queue.Queue`).
  * El hilo principal de la GUI consulta la cola de forma periódica y no bloqueante mediante `root.after(100, ...)` y actualiza el modelo (`FleetDashboardState`) y los `ttk.Treeview`.
  * El modelo está completamente desacoplado de Tkinter (patrón MVP + Observer), lo que permite testear las reglas de negocio sin interfaz gráfica.

---

## 3. Diagramas de Arquitectura y Flujo

Los diagramas formales en PlantUML y su versión renderizada se encuentran en `docs/`:
* Arquitectura de componentes: [`docs/architecture.puml`](docs/architecture.puml) ([`docs/architecture.png`](docs/architecture.png))
* Flujo de datos extremo a extremo: [`docs/data_flow.puml`](docs/data_flow.puml) ([`docs/data_flow.png`](docs/data_flow.png))
