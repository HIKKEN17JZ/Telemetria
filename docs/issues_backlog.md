# Backlog de Tareas del Proyecto: Sistema de Telemetría de Flota Distribuido

Este documento establece la planificación ágil y la descomposición del trabajo para el examen final de Computación 2. El proyecto se organiza en 12 issues técnicos equilibrados entre los 3 desarrolladores (4 issues por persona), cubriendo todos los requisitos de la cátedra y las devoluciones del docente:
* **Sockets concurrentes y Asincronismo I/O:** `asyncio` (`StreamReader`/`StreamWriter`).
* **Lógica Paralela (CPU-Bound):** Workers de `Celery` con Redis broker y `multiprocessing` (`prefork`) para analítica de flotas.
* **API Gateway con Gunicorn y Uvicorn:** Demostración de workers (procesos) e hilos (threads) concurrentes.
* **IPC (Comunicación Entre Procesos):** Manejo de señales UNIX (`SIGHUP` para hot-reload y `SIGUSR1` para estadísticas).
* **CLI vehicular:** Parser configurable con `argparse` y simulación física de dinámicas.
* **Semi-Frontend de Escritorio:** Interfaz en **Tkinter** con arquitectura **Multithreading** (`threading.Thread` + `queue.Queue`) para no bloquear el `mainloop()`.
* **Infraestructura y Persistencia:** Docker Compose y PostgreSQL con índices para series de tiempo.
* **Documentación formal:** Diagramas de arquitectura y flujo en **PlantUML** (`.puml`).

---

## 👥 Equipo y Asignación de Roles
* **Ale (Dev 1 - `@HIKKEN17JZ`):** Agente CLI vehicular, Semi-Frontend de Escritorio en **Tkinter** e integración con **Multithreading**.
* **Charango (Dev 2 - `@Charango21`):** Core del Servidor asíncrono (`asyncio`), mecanismos de **IPC** (Señales UNIX) y **API Gateway (Gunicorn + Uvicorn Workers & Threads)**.
* **Agus (Dev 3 - `@AgusValdebenito`):** Infraestructura (**Docker Compose**), Base de Datos (**PostgreSQL**), **Lógica Paralela (Celery/Multiprocessing)** y Diagramación **PlantUML**.

---

## 🎯 Resumen y Estado de Sprints

### 🏁 Sprint 1 — Pipeline Base y Transmisión Concurrente (Completado)
* [x] **[Issue #1](https://github.com/HIKKEN17JZ/Telemetria/issues/1):** Infraestructura base con Docker Compose (PostgreSQL + Redis) — **Agus** ✅
* [x] **[Issue #2](https://github.com/HIKKEN17JZ/Telemetria/issues/2):** Core del Servidor de Sockets concurrente con Asyncio I/O — **Charango** ✅
* [x] **[Issue #3](https://github.com/HIKKEN17JZ/Telemetria/issues/3):** Agente vehicular CLI con `argparse` y simulación de métricas — **Ale** ✅

---

### ⚙️ Sprint 2 — Procesamiento Distribuido (Celery), Persistencia en BD e IPC (En Curso)
* [x] **[Issue #4](https://github.com/HIKKEN17JZ/Telemetria/issues/4):** Modelado relacional y persistencia en PostgreSQL — **Agus** ✅
* [x] **[Issue #5](https://github.com/HIKKEN17JZ/Telemetria/issues/5):** Protocolo de comunicación, enmarcado y validación de paquetes — **Charango** ✅
* [x] **[Issue #6](https://github.com/HIKKEN17JZ/Telemetria/issues/6):** Conector TCP resiliente en el Agente con reconexión automática — **Ale** ✅
* [x] **[Issue #7](https://github.com/HIKKEN17JZ/Telemetria/issues/7):** Configuración de Celery, Broker y Workers para procesamiento paralelo (CPU-Bound) — **Agus** ✅
* [ ] **[Issue #8](https://github.com/HIKKEN17JZ/Telemetria/issues/8):** Despacho asíncrono a Celery e IPC mediante Señales UNIX en el Servidor — **Charango**
* [ ] **[Issue #9](https://github.com/HIKKEN17JZ/Telemetria/issues/9):** Pipeline de persistencia masiva en PostgreSQL, reportes y Diagramación PlantUML — **Agus**

---

### 🖥️ Sprint 3 — Semi-Frontend de Escritorio (Tkinter), API Gateway y Tiempo Real (Próximo)
* [ ] **[Issue #10](https://github.com/HIKKEN17JZ/Telemetria/issues/10):** Semi-Frontend de Escritorio con Tkinter y Dashboard de Monitoreo de Flota — **Ale**
* [ ] **[Issue #11](https://github.com/HIKKEN17JZ/Telemetria/issues/11):** API Gateway con Gunicorn y Uvicorn (Workers y Threads) — **Charango**
* [ ] **[Issue #12](https://github.com/HIKKEN17JZ/Telemetria/issues/12):** Integración en tiempo real del Dashboard Tkinter con Multithreading — **Ale**

---

## 📋 Especificación Detallada de Issues

### [Issue #1] Infraestructura base y orquestación con Docker Compose
- **Estado:** ✅ CERRADA ([#1](https://github.com/HIKKEN17JZ/Telemetria/issues/1))
- **Asignado a:** Agus (Dev 3 - `@AgusValdebenito`)
- **Descripción:** Diseñar y configurar la infraestructura contenerizada del proyecto para permitir el despliegue orquestado y reproducible de todos los servicios (PostgreSQL 15, Redis 7 como message broker de Celery, y servicios base en Python), garantizando un entorno aislado y homogéneo para todo el equipo de desarrollo.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Implementar un archivo `docker-compose.yml` que defina los contenedores para PostgreSQL 15+, Redis Alpine y variables de entorno parametrizadas vía `.env`.
  - Configurar volúmenes persistentes (`named volumes`) para evitar la pérdida de datos de la base de datos y de la cola de mensajes en caso de reinicio de contenedores.
  - Definir una red puente interna (`telemetria_net`) para la comunicación segura entre microservicios y mapear los puertos necesarios para el acceso de desarrollo local.
  - Incluir `healthchecks` en PostgreSQL y Redis para garantizar que los servicios dependientes arranquen únicamente cuando los servidores base estén listos para recibir tráfico.
- **Dependencias:** Ninguna (Tarea inicial de infraestructura).

---

### [Issue #2] Core del Servidor de Sockets concurrente con Asyncio I/O
- **Estado:** ✅ CERRADA ([#2](https://github.com/HIKKEN17JZ/Telemetria/issues/2))
- **Asignado a:** Charango (Dev 2 - `@Charango21`)
- **Descripción:** Implementar el servidor TCP de recepción de telemetría utilizando el bucle de eventos (`event loop`) de Python y el módulo `asyncio` (`asyncio.start_server`), permitiendo que decenas o cientos de vehículos envíen telemetría simultáneamente sin incurrir en overhead de hilos bloqueantes o multi-proceso innecesario.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Utilizar las abstracciones de alto nivel `StreamReader` y `StreamWriter` de `asyncio` para gestionar las conexiones entrantes de forma no bloqueante.
  - Evitar cualquier llamada bloqueante sincrónica (ej. `time.sleep`, lecturas de disco estándar) dentro de las corrutinas que manejan los sockets.
  - Manejar excepciones de conexión (`ConnectionResetError`, `IncompleteReadError`, timeouts) para desconectar clientes limpiamente sin tumbar el servidor.
  - Implementar control de concurrencia y un registro en memoria de clientes conectados activamente con sus identificadores de sesión.
- **Dependencias:** Ninguna (Puede iniciarse de forma independiente con mocks de red).

---

### [Issue #3] Agente vehicular CLI con recolección de métricas y Argparse
- **Estado:** ✅ CERRADA ([#3](https://github.com/HIKKEN17JZ/Telemetria/issues/3))
- **Asignado a:** Ale (Dev 1 - `@HIKKEN17JZ`)
- **Descripción:** Desarrollar el agente cliente que correrá en cada vehículo de la flota, el cual recolectará y simulará métricas telemétricas (coordenadas GPS, velocidad, nivel de combustible, RPM, temperatura del motor) y admitirá configuración flexible y parametrizada mediante argumentos de línea de comandos.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Utilizar la biblioteca estándar `argparse` para recibir parámetros como `--server-host`, `--server-port`, `--vehicle-id`, `--interval` (frecuencia de muestreo) y `--mode` (simulación o real).
  - Diseñar el generador de datos telemétricos simulando trayectorias coherentes (rutas realistas, aceleraciones suaves y variaciones lógicas de temperatura/combustible).
  - Validar los tipos de datos y rangos de los argumentos provistos por CLI, arrojando mensajes de ayuda (`--help`) claros y código de salida semántico ante errores.
  - Estructurar el payload de telemetría en un formato estándar serializable (JSON estructurado con campos: `vehicle_id`, `timestamp`, `location`, `metrics`, `status`).
- **Dependencias:** Ninguna (Desarrollo autónomo del cliente vehicular).

---

### [Issue #4] Modelado relacional y persistencia en PostgreSQL
- **Estado:** ✅ CERRADA ([#4](https://github.com/HIKKEN17JZ/Telemetria/issues/4))
- **Asignado a:** Agus (Dev 3 - `@AgusValdebenito`)
- **Descripción:** Diseñar la estructura de base de datos relacional para el sistema de telemetría de flota y generar los scripts de inicialización DDL/migraciones para almacenar vehículos, mediciones periódicas (sensores, velocidad, ubicación GPS, combustible) y alertas críticas generadas por eventos del sistema.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Crear tablas normalizadas con claves primarias, foráneas e índices (especialmente en `vehicle_id` y `timestamp` para acelerar consultas temporales de series de tiempo).
  - Utilizar una librería de acceso a datos eficiente (como `psycopg2` / `asyncpg` o SQLAlchemy) asegurando el uso de connection pooling para prevenir saturación de conexiones.
  - Escribir un script SQL de inicialización montado en `/docker-entrypoint-initdb.d/init.sql` para que la base de datos se configure automáticamente al iniciar el contenedor.
  - Implementar restricciones de integridad (ej. rangos válidos para coordenadas, velocidad >= 0, estados válidos de vehículo).
- **Dependencias:** Requiere que el entorno base de base de datos esté configurado (Depende del Issue #1).

---

### [Issue #5] Protocolo de comunicación, enmarcado y validación de paquetes
- **Estado:** ✅ CERRADA ([#5](https://github.com/HIKKEN17JZ/Telemetria/issues/5))
- **Asignado a:** Charango (Dev 2 - `@Charango21`)
- **Descripción:** Definir y programar el protocolo de capa de aplicación sobre TCP para delimitar los mensajes entre el agente del vehículo y el servidor (evitando problemas de paquetes fragmentados o pegados en el buffer TCP), realizando el parseo y validación de integridad de los datos recibidos.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Implementar una estrategia de enmarcado de mensajes robusta (por ejemplo, delimitación por fin de línea `\n` o prefijo de longitud fija de bytes) para manejar lectura por streams en `asyncio`.
  - Deserializar y validar esquemas de datos JSON entrantes de forma segura, rechazando payloads corruptos o incompletos sin corromper el stream de datos.
  - Responder al cliente con acuses de recibo (ACK/NACK) para garantizar que el agente conozca el estado de entrega de su paquete.
  - Asegurar que la deserialización y validación no bloqueen el bucle de eventos mediante corrutinas optimizadas o ejecución protegida.
- **Dependencias:** Depende del Issue #2 y debe consensuar el formato definido en el Issue #3.

---

### [Issue #6] Conector TCP resiliente en el Agente con reconexión automática
- **Estado:** ✅ CERRADA ([#6](https://github.com/HIKKEN17JZ/Telemetria/issues/6))
- **Asignado a:** Ale (Dev 1 - `@HIKKEN17JZ`)
- **Descripción:** Integrar en el agente CLI la capa de comunicación de red por sockets, asegurando el envío periódico de los paquetes de telemetría hacia el servidor y dotándolo de tolerancia a fallos y resiliencia ante pérdidas de conectividad celular/red típicas en vehículos en movimiento.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Utilizar sockets asíncronos o no bloqueantes para la transmisión continua de datos respetando la frecuencia indicada en los argumentos CLI.
  - Implementar un algoritmo de reintento con retroceso exponencial (`exponential backoff`) y jitter ante caídas de conexión o servidores no disponibles.
  - Incorporar una cola o búfer local en memoria para almacenar las mediciones pendientes de envío cuando se pierde la conexión, retransmitiéndolas en orden al reconectar.
  - Gestionar el apagado ordenado (`graceful shutdown`) capturando señales `SIGINT` (Ctrl+C) y `SIGTERM` para cerrar el socket sin dejar conexiones colgadas.
- **Dependencias:** Depende del Issue #3 y del protocolo delimitado en el Issue #5.

---

### [Issue #7] Configuración de Celery, Broker y Workers para procesamiento paralelo (CPU-Bound)
- **Estado:** ✅ CERRADA ([#7](https://github.com/HIKKEN17JZ/Telemetria/issues/7))
- **Asignado a:** Agus (Dev 3 - `@AgusValdebenito`)
- **Descripción:** Configurar e instanciar Celery como sistema de colas de tareas distribuidas utilizando Redis como broker y result backend, preparando el entorno para delegar el cálculo intensivo de analítica de flotas (detección de anomalías, excesos de velocidad y alertas de mantenimiento) fuera del ciclo del servidor de sockets, demostrando **lógica paralela real con multiprocessing (`prefork`)**.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Crear la instancia de Celery (`Celery application`) con configuración de serialización segura (JSON), control de concurrencia de workers (`prefork` o `gevent`) y reintentos automáticos.
  - Configurar en `docker-compose.yml` el servicio del worker de Celery, montando el código fuente y sincronizando variables de entorno con Redis y PostgreSQL.
  - Implementar tareas Celery base para la evaluación de umbrales críticos (ej. alerta si velocidad > 120 km/h o temperatura del motor > 105°C).
  - Asegurar el manejo de logs estructurados y gestión de fallos (`dead letter` o reintentos con `autoretry_for`) para que ninguna tarea fallida cause un bloqueo del worker.
- **Dependencias:** Depende del Issue #1 y del modelo de datos del Issue #4.

---

### [Issue #8] Despacho asíncrono a Celery e IPC mediante Señales UNIX en el Servidor
- **Estado:** ⏳ ABIERTA ([#8](https://github.com/HIKKEN17JZ/Telemetria/issues/8))
- **Asignado a:** Charango (Dev 2 - `@Charango21`)
- **Descripción:** Conectar el servidor de sockets asíncrono con el sistema de tareas Celery (enviando la telemetría recibida a la cola sin bloquear `asyncio`) e implementar mecanismos de Comunicación Entre Procesos (IPC) mediante señales UNIX estándar (`SIGHUP` y `SIGUSR1`) para control operativo del servidor en caliente.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Despachar tareas hacia Celery desde el flujo asíncrono mediante `send_task` o `delay()` ejecutado sin bloquear el event loop (usando `loop.run_in_executor` si el cliente de Celery fuera sincrónico).
  - Implementar el manejador de la señal `signal.SIGHUP` registrado en el bucle de eventos (`loop.add_signal_handler`) para recargar dinámicamente configuraciones (umbrales de alerta, nivel de logging) sin reiniciar el servidor.
  - Implementar el manejador de la señal `signal.SIGUSR1` para volcar métricas y estadísticas operativas del servidor (clientes activos, paquetes/segundo) a un archivo de log o consola.
  - Garantizar la compatibilidad en entornos POSIX/Linux (adecuado para ejecución en Docker o sistemas compatibles) cumpliendo estrictamente los requisitos de IPC de la cátedra.
- **Dependencias:** Depende del Issue #5 y del Issue #7.

---

### [Issue #9] Pipeline de persistencia masiva en PostgreSQL, reportes agregados y Diagramación PlantUML
- **Estado:** ⏳ ABIERTA ([#9](https://github.com/HIKKEN17JZ/Telemetria/issues/9))
- **Asignado a:** Agus (Dev 3 - `@AgusValdebenito`)
- **Descripción:** Desarrollar las tareas de Celery dedicadas a la inserción en base de datos de los datos telemétricos procesados y la generación periódica/bajo demanda de métricas agregadas de la flota, y crear la documentación formal de arquitectura y flujo del sistema completo utilizando **PlantUML**.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Implementar inserciones optimizadas por lotes (`batch inserts` o transacciones controladas) para evitar saturar el pool de conexiones de PostgreSQL ante alto volumen de telemetría.
  - Desarrollar una tarea Celery para registrar alertas en la tabla correspondiente cuando una medición exceda los rangos de seguridad.
  - Diseñar y versionar en `docs/` el diagrama de arquitectura general y componentes en PlantUML (`architecture.puml`).
  - Diseñar y versionar en `docs/` el diagrama de secuencia del flujo de datos en PlantUML (`data_flow.puml`), mostrando la interacción: Agente ➡️ Servidor asyncio ➡️ IPC SIGHUP ➡️ Redis ➡️ Celery Paralelo ➡️ PostgreSQL ➡️ API Gateway (Gunicorn/Uvicorn) ➡️ Dashboard Tkinter.
- **Dependencias:** Depende del Issue #4 y del Issue #7.

---

### [Issue #10] Semi-Frontend de Escritorio con Tkinter y Dashboard de Monitoreo de Flota
- **Estado:** ⏳ ABIERTA ([#10](https://github.com/HIKKEN17JZ/Telemetria/issues/10))
- **Asignado a:** Ale (Dev 1 - `@HIKKEN17JZ`)
- **Descripción:** Desarrollar una interfaz gráfica de escritorio interactiva en Python nativo utilizando **Tkinter** para el monitoreo y gestión en tiempo real de la flota de vehículos, presentando tablas de estado, velocímetros/indicadores y visor de eventos críticos en reemplazo de una aplicación web compleja.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Diseñar la interfaz modular en Tkinter (`ttk`) con panel principal de vehículos (ID, Velocidad, Combustible, Temperatura, Estado y Coordenadas).
  - Implementar componentes visuales o paneles coloreados de alerta inmediata ante excesos de velocidad (> 120 km/h) o recalentamiento (> 100°C).
  - Diseñar una vista de resumen general de la flota (cantidad de vehículos conectados, promedio de velocidad, total de alertas).
  - Diseñar la UI desacoplada de la capa de datos para facilitar la inyección de actualizaciones desde un hilo secundario sin dependencias circulares.
- **Dependencias:** Ninguna (Puede maquetarse inicialmente con datos simulados o mocks).

---

### [Issue #11] API Gateway con Gunicorn y Uvicorn (Workers y Threads)
- **Estado:** ⏳ ABIERTA ([#11](https://github.com/HIKKEN17JZ/Telemetria/issues/11))
- **Asignado a:** Charango (Dev 2 - `@Charango21`)
- **Descripción:** Implementar una capa de exposición de datos (API Gateway con FastAPI o Starlette) servida mediante **Gunicorn** orquestando workers de **Uvicorn** con configuración explícita de **workers (procesos)** e **hilos (threads)**, demostrando ante la cátedra la combinación de paralelismo por procesos y concurrencia por hilos y asincronismo para alimentar el dashboard de Tkinter.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Configurar el arranque del servicio con Gunicorn utilizando workers de Uvicorn (`gunicorn -w 2 -k uvicorn.workers.UvicornWorker --threads 2 app:app`).
  - Justificar conceptualmente la distinción entre workers (procesos independientes aislados en memoria) y threads (hilos concurrentes por worker) para la defensa oral del examen.
  - Exponer endpoints REST (`/api/vehicles`, `/api/alerts`, `/api/stats`) consultando de forma eficiente a PostgreSQL.
  - Implementar un endpoint de streaming (Server-Sent Events o WebSocket) para transmitir en vivo las mediciones hacia el dashboard.
- **Dependencias:** Depende del Issue #2, Issue #8 e Issue #9.

---

### [Issue #12] Integración en tiempo real del Dashboard Tkinter con Multithreading
- **Estado:** ⏳ ABIERTA ([#12](https://github.com/HIKKEN17JZ/Telemetria/issues/12))
- **Asignado a:** Ale (Dev 1 - `@HIKKEN17JZ`)
- **Descripción:** Conectar el dashboard de escritorio en **Tkinter** con el API Gateway / Servidor, implementando una arquitectura de **Multithreading** (`threading.Thread` + `queue.Queue`) para consumir la telemetría en tiempo real sin congelar ni degradar el bucle principal de la interfaz gráfica (`mainloop()`).
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Crear un hilo de red secundario (`daemon thread`) dedicado a recibir las actualizaciones continuas de telemetría y alertas desde el backend.
  - Utilizar una cola thread-safe (`queue.Queue`) y el método `root.after()` de Tkinter para pasar datos de forma segura entre el hilo de red y el hilo de interfaz, evitando condiciones de carrera (*race conditions*).
  - Actualizar de forma reactiva y fluida la tabla de vehículos, los indicadores de combustible/temperatura y el panel de alertas.
  - Manejar reconexión automática en el cliente y mostrar un indicador visual de estado de conectividad (🟢 Conectado / 🔴 Desconectado).
- **Dependencias:** Depende del Issue #10 y del Issue #11.
