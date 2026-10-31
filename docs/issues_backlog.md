# Backlog de Tareas del Proyecto: Sistema de Telemetría de Flota Distribuido

Este documento establece la planificación ágil y la descomposición del trabajo para el examen final de Computación 2. El proyecto se organiza en exactamente 12 issues técnicos equilibrados entre los 3 desarrolladores (4 issues por persona), cubriendo todos los requisitos de la cátedra y las devoluciones del docente:
* **Sockets concurrentes y Asincronismo I/O:** `asyncio` (`StreamReader`/`StreamWriter`).
* **Lógica Paralela (CPU-Bound):** Workers de `Celery` con Redis broker y `multiprocessing` para analítica de flotas.
* **API Gateway con Gunicorn y Uvicorn:** Demostración de workers (procesos) e hilos (threads) concurrentes.
* **IPC (Comunicación Entre Procesos):** Manejo de señales UNIX (`SIGHUP` para hot-reload y `SIGUSR1` para estadísticas).
* **CLI vehicular:** Parser configurable con `argparse` y simulación física de dinámicas.
* **Semi-Frontend de Escritorio:** Interfaz en **Tkinter** con arquitectura **Multithreading** (`threading.Thread` + `queue.Queue`) para no bloquear el `mainloop()`.
* **Infraestructura y Persistencia:** Docker Compose y PostgreSQL con índices para series de tiempo.
* **Documentación formal:** Diagramas de arquitectura y flujo en **PlantUML** (`.puml`).

---

## 👥 Equipo y Asignación de Roles
* **Ale (Dev 1):** Agente CLI vehicular, Semi-Frontend de Escritorio en **Tkinter** e integración con **Multithreading**.
* **Charango (Dev 2):** Core del Servidor asíncrono (`asyncio`), mecanismos de **IPC** (Señales UNIX) y **API Gateway (Gunicorn + Uvicorn Workers & Threads)**.
* **Agus (Dev 3):** Infraestructura (**Docker Compose**), Base de Datos (**PostgreSQL**), **Lógica Paralela (Celery/Multiprocessing)** y Diagramación **PlantUML**.

---

## 📊 Estado de los Sprints

### ✅ Sprint 1 — Walking Skeleton (Completado)
* **[Issue #1]** Infraestructura base con Docker Compose (PostgreSQL + Redis) — **Agus** *(Cerrado)*
* **[Issue #2]** Core del Servidor de Sockets concurrente con Asyncio I/O — **Charango** *(Cerrado)*
* **[Issue #3]** Agente vehicular CLI con recolección de métricas y Argparse — **Ale** *(Cerrado)*

### 🚀 Sprint 2 — Foco de Hoy (Robustez, Persistencia y Protocolo)
* **Agus (Dev 3):** **[Issue #4]** — Modelado relacional y persistencia en PostgreSQL desde Python.
* **Charango (Dev 2):** **[Issue #5]** — Protocolo de comunicación, enmarcado y validación estricta de paquetes.
* **Ale (Dev 1):** **[Issue #6]** — Conector TCP resiliente en el Agente con buffer offline y reconexión automática.

---

## 📝 Detalle de los 12 Issues del Proyecto

### [Issue #1] Infraestructura base y orquestación con Docker Compose
- **Estado:** ✅ Cerrado / Completado
- **Asignado a:** Agus (Dev 3)
- **Descripción:** Diseñar y configurar la infraestructura contenerizada del proyecto para permitir el despliegue orquestado y reproducible de todos los servicios (PostgreSQL 15, Redis 7 como message broker de Celery, y servicios base en Python), garantizando un entorno aislado y homogéneo.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Implementar un archivo `docker-compose.yml` que defina los contenedores para PostgreSQL 15-alpine y Redis 7-alpine con puertos mapeados (5435 y 6380) y variables vía `.env`.
  - Configurar volúmenes persistentes (`named volumes`) para evitar pérdida de datos relacionales y de la cola de mensajes en reinicios.
  - Definir una red puente interna (`telemetria_net`) para la comunicación segura entre microservicios.
  - Incluir `healthchecks` en PostgreSQL y Redis para garantizar que los servicios dependientes arranquen únicamente cuando los servidores base estén listos.
- **Dependencias:** Ninguna (Tarea inicial de infraestructura).

---

### [Issue #2] Core del Servidor de Sockets concurrente con Asyncio I/O
- **Estado:** ✅ Cerrado / Completado
- **Asignado a:** Charango (Dev 2)
- **Descripción:** Implementar el servidor TCP de recepción de telemetría utilizando el bucle de eventos (`event loop`) de Python y el módulo `asyncio` (`asyncio.start_server`), permitiendo que decenas o cientos de vehículos envíen telemetría simultáneamente sin incurrir en overhead de hilos bloqueantes.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Utilizar las abstracciones de alto nivel `StreamReader` y `StreamWriter` de `asyncio` para gestionar las conexiones entrantes de forma no bloqueante.
  - Evitar cualquier llamada bloqueante sincrónica (ej. `time.sleep`, I/O bloqueante) dentro de las corrutinas que manejan los sockets.
  - Manejar excepciones de conexión (`ConnectionResetError`, `IncompleteReadError`, timeouts) para desconectar clientes limpiamente sin tumbar el servidor.
  - Implementar control de concurrencia y responder con acuses de recibo (`ACK`) terminados en `\n` mediante `writer.drain()`.
- **Dependencias:** Ninguna (Desarrollo independiente del servidor core).

---

### [Issue #3] Agente vehicular CLI con recolección de métricas y Argparse
- **Estado:** ✅ Cerrado / Completado
- **Asignado a:** Ale (Dev 1)
- **Descripción:** Desarrollar el agente cliente que correrá en cada vehículo de la flota, el cual recolectará y simulará métricas telemétricas (coordenadas GPS, velocidad, nivel de combustible, RPM, temperatura del motor) y admitirá configuración flexible y parametrizada mediante argumentos de línea de comandos.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Utilizar la biblioteca estándar `argparse` para recibir parámetros como `--server-host`, `--server-port`, `--vehicle-id`, `--interval` y `--mode`.
  - Diseñar el generador de datos telemétricos simulando trayectorias coherentes (rutas realistas, aceleraciones suaves y variaciones físicas lógicas).
  - Validar los tipos de datos y rangos de los argumentos provistos por CLI con mensajes de ayuda (`--help`) claros y código de salida semántico.
  - Estructurar el payload de telemetría en formato JSON terminado en salto de línea (`\n`), cubierto al 100% con tests unitarios bajo metodología TDD.
- **Dependencias:** Ninguna (Desarrollo autónomo del cliente vehicular).

---

### [Issue #4] Modelado relacional y persistencia en PostgreSQL
- **Estado:** 🟡 Abierto (Sprint 2)
- **Asignado a:** Agus (Dev 3)
- **Descripción:** Diseñar e integrar la capa de persistencia relacional en PostgreSQL para almacenar vehículos, mediciones periódicas de telemetría (series de tiempo) y alertas críticas generadas por eventos del sistema, implementando conexión eficiente desde Python.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Crear y consolidar tablas normalizadas (`vehicles`, `telemetry`, `alerts`) con claves foráneas, restricciones de integridad y partición/índices temporales (`vehicle_id`, `timestamp DESC`).
  - Desarrollar un módulo de conexión en Python utilizando connection pooling (`psycopg2.pool` o `asyncpg`/SQLAlchemy) para prevenir saturación de conexiones.
  - Asegurar la inicialización automática mediante el script montado en `/docker-entrypoint-initdb.d/init.sql`.
  - Implementar funciones CRUD seguras contra SQL injection con transacciones ACID y rollback automático ante errores.
- **Dependencias:** Requiere que el entorno base de Docker esté configurado (Depende del Issue #1).

---

### [Issue #5] Protocolo de comunicación, enmarcado y validación de paquetes
- **Estado:** 🟡 Abierto (Sprint 2)
- **Asignado a:** Charango (Dev 2)
- **Descripción:** Definir y programar formalmente el protocolo de capa de aplicación sobre TCP para delimitar los mensajes entre el agente del vehículo y el servidor (evitando problemas de paquetes fragmentados o pegados en el buffer TCP), realizando el parseo y validación de integridad de los datos recibidos.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Implementar una estrategia de enmarcado de mensajes robusta delimitada por fin de línea `\n` o prefijo de longitud para streams en `asyncio`.
  - Validar los esquemas de datos entrantes rechazando payloads corruptos, incompletos o con tipos erróneos sin corromper el stream de datos.
  - Responder al cliente con acuses de recibo estructurados (`ACK`/`NACK`) indicando código de error si el mensaje es inválido.
  - Asegurar que la deserialización y validación no bloqueen el event loop de `asyncio` mediante corrutinas optimizadas.
- **Dependencias:** Depende del Issue #2 y del formato establecido en el Issue #3.

---

### [Issue #6] Conector TCP resiliente en el Agente con reconexión automática
- **Estado:** 🟡 Abierto (Sprint 2)
- **Asignado a:** Ale (Dev 1)
- **Descripción:** Mejorar la capa de comunicación de red por sockets en el agente CLI, asegurando tolerancia a fallos, resiliencia ante pérdidas de conectividad celular/red y almacenamiento en buffer local para no perder telemetría durante desconexiones.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Implementar un algoritmo de reintento con retroceso exponencial (`exponential backoff`) y jitter ante caídas de conexión o servidores no disponibles.
  - Incorporar una cola o búfer local en memoria (`collections.deque` o cola FIFO) para almacenar las mediciones pendientes cuando se pierde la conexión, retransmitiéndolas en orden al reconectar.
  - Gestionar el apagado ordenado (`graceful shutdown`) capturando señales `SIGINT` (Ctrl+C) y `SIGTERM` para vaciar el socket y cerrar recursos limpiamente.
  - Probar la resiliencia matando y levantando el servidor mientras el agente sigue corriendo sin crashear.
- **Dependencias:** Depende del Issue #3 y del protocolo delimitado en el Issue #5.

---

### [Issue #7] Configuración de Celery, Broker y Workers para procesamiento paralelo (CPU-Bound)
- **Estado:** ⚪ Planificado
- **Asignado a:** Agus (Dev 3)
- **Descripción:** Configurar e instanciar Celery como sistema de colas de tareas distribuidas utilizando Redis como broker y result backend, demostrando el uso de **lógica paralela real con multiprocessing (`prefork`)** para cálculos matemáticos pesados de analítica de flotas, distinguiéndolo claramente de la concurrencia I/O del servidor de sockets.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Crear la instancia de aplicación Celery con configuración de serialización segura (JSON), control de concurrencia de workers (`--concurrency` / `prefork`) y reintentos automáticos.
  - Configurar en `docker-compose.yml` el servicio del worker de Celery sincronizado con Redis y PostgreSQL.
  - Implementar tareas paralelas CPU-Bound: cálculo de excesos de velocidad continuos, detección de anomalías térmicas y verificación de geocercas poligonales.
  - Garantizar logs estructurados y gestión de fallos (`autoretry_for`) para que ninguna tarea fallida bloquee el worker.
- **Dependencias:** Depende del Issue #1 y del modelo de datos del Issue #4.

---

### [Issue #8] Despacho asíncrono a Celery e IPC mediante Señales UNIX en el Servidor
- **Estado:** ⚪ Planificado
- **Asignado a:** Charango (Dev 2)
- **Descripción:** Conectar el servidor de sockets asíncrono con Celery (despachando la telemetría a la cola sin bloquear `asyncio`) e implementar mecanismos de Comunicación Entre Procesos (IPC) mediante señales UNIX estándar (`SIGHUP` y `SIGUSR1`) para control operativo del servidor en caliente.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Despachar tareas hacia Celery desde el flujo asíncrono mediante `send_task` o `delay()` ejecutado sin bloquear el event loop (usando `loop.run_in_executor` si el cliente fuera síncrono).
  - Implementar el manejador de la señal `signal.SIGHUP` registrado en el bucle de eventos (`loop.add_signal_handler`) para recargar dinámicamente configuraciones (umbrales de alerta, nivel de logging) sin reiniciar el proceso.
  - Implementar el manejador de la señal `signal.SIGUSR1` para volcar métricas y estadísticas operativas del servidor (clientes activos, paquetes/segundo) a un archivo de log o consola.
  - Garantizar la compatibilidad en entornos POSIX/Linux (adecuado para ejecución en Docker o sistemas compatibles) cumpliendo los requisitos de IPC de la cátedra.
- **Dependencias:** Depende del Issue #5 y del Issue #7.

---

### [Issue #9] Pipeline de persistencia masiva en PostgreSQL, reportes agregados y Diagramación PlantUML
- **Estado:** ⚪ Planificado
- **Asignado a:** Agus (Dev 3)
- **Descripción:** Desarrollar las tareas de Celery dedicadas a la inserción en base de datos de los datos telemétricos procesados, generación de resúmenes agregados y crear la documentación formal de arquitectura y flujo del sistema completo utilizando **PlantUML**.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Implementar inserciones optimizadas por lotes (`batch inserts` o transacciones controladas) para persistir la telemetría sin degradar el rendimiento relacional.
  - Desarrollar tareas periódicas (Celery Beat) para calcular estadísticas históricas (kilometraje estimado, velocidad promedio por vehículo, conteo de alertas).
  - Diseñar y versionar en `docs/` el diagrama de arquitectura general y componentes en PlantUML (`architecture.puml`).
  - Diseñar y versionar en `docs/` el diagrama de secuencia del flujo de datos en PlantUML (`data_flow.puml`), mostrando la interacción: Agente ➡️ Servidor asyncio ➡️ IPC SIGHUP ➡️ Redis ➡️ Celery Paralelo ➡️ PostgreSQL ➡️ API Gateway (Gunicorn/Uvicorn) ➡️ Dashboard Tkinter.
- **Dependencias:** Depende del Issue #4 y del Issue #7.

---

### [Issue #10] Semi-Frontend de Escritorio con Tkinter y Dashboard de Monitoreo de Flota
- **Estado:** ⚪ Planificado
- **Asignado a:** Ale (Dev 1)
- **Descripción:** Desarrollar una interfaz gráfica de escritorio interactiva en Python nativo utilizando **Tkinter** para el monitoreo y gestión en tiempo real de la flota de vehículos, presentando tablas de estado, velocímetros/indicadores y visor de eventos críticos en reemplazo de una aplicación web compleja.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Diseñar la interfaz modular en Tkinter (`ttk`) con panel principal de vehículos (ID, Velocidad, Combustible, Temperatura, Estado y Coordenadas).
  - Implementar componentes visuales o paneles coloreados de alerta inmediata ante excesos de velocidad (> 120 km/h) o recalentamiento (> 100°C).
  - Diseñar una vista de resumen general de la flota (cantidad de vehículos conectados, promedio de velocidad, total de alertas).
  - Diseñar la UI completamente desacoplada de la capa de datos para facilitar la inyección de actualizaciones desde un hilo secundario sin dependencias circulares.
- **Dependencias:** Ninguna (Puede maquetarse inicialmente con datos simulados o mocks).

---

### [Issue #11] API Gateway con Gunicorn y Uvicorn (Workers y Threads)
- **Estado:** ⚪ Planificado
- **Asignado a:** Charango (Dev 2)
- **Descripción:** Implementar una capa de exposición de datos (API Gateway con FastAPI o Starlette) servida mediante **Gunicorn** orquestando workers de **Uvicorn** con configuración explícita de **workers (procesos)** e **hilos (threads)**, demostrando ante la cátedra la combinación de paralelismo por procesos y concurrencia por hilos y asincronismo para alimentar el dashboard de Tkinter.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Configurar el arranque del servicio con Gunicorn utilizando workers de Uvicorn (`gunicorn -w 2 -k uvicorn.workers.UvicornWorker --threads 2 app:app`).
  - Justificar conceptualmente la distinción entre workers (procesos independientes aislados en memoria) y threads (hilos concurrentes por worker) para la defensa oral del examen.
  - Exponer endpoints REST (`/api/vehicles`, `/api/alerts`, `/api/stats`) consultando de forma eficiente a PostgreSQL.
  - Implementar un endpoint de streaming (Server-Sent Events o WebSocket) para transmitir en vivo las mediciones hacia el dashboard.
- **Dependencias:** Depende del Issue #2, Issue #8 e Issue #9.

---

### [Issue #12] Integración en tiempo real del Dashboard Tkinter con Multithreading
- **Estado:** ⚪ Planificado
- **Asignado a:** Ale (Dev 1)
- **Descripción:** Conectar el dashboard de escritorio en **Tkinter** con el API Gateway / Servidor, implementando una arquitectura de **Multithreading** (`threading.Thread` + `queue.Queue`) para consumir la telemetría en tiempo real sin congelar ni degradar el bucle principal de la interfaz gráfica (`mainloop()`).
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Crear un hilo de red secundario (`daemon thread`) dedicado a recibir las actualizaciones continuas de telemetría y alertas desde el backend.
  - Utilizar una cola thread-safe (`queue.Queue`) y el método `root.after()` de Tkinter para pasar datos de forma segura entre el hilo de red y el hilo de interfaz, evitando condiciones de carrera (*race conditions*).
  - Actualizar de forma reactiva y fluida la tabla de vehículos, los indicadores de combustible/temperatura y el panel de alertas.
  - Manejar reconexión automática en el cliente y mostrar un indicador visual de estado de conectividad (🟢 Conectado / 🔴 Desconectado).
- **Dependencias:** Depende del Issue #10 y del Issue #11.
