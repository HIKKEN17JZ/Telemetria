# Backlog de Tareas del Proyecto: Sistema de Telemetría de Flota Distribuido

Este documento establece la planificación ágil y la descomposición del trabajo para el examen final de Computación 2. El proyecto se organiza en 12 issues técnicos equilibrados entre 3 desarrolladores, cubriendo todos los requisitos de la cátedra: sockets concurrentes, asincronismo I/O, IPC (señales UNIX), colas de tareas distribuidas (Celery), CLI con `argparse`, contenedores Docker, base de datos PostgreSQL y entorno visual (Vite).

## 👥 Equipo y Asignación de Roles
* **Ale (Dev 1):** Agente CLI, recolección de datos vehiculares y Frontend (Vite).
* **Charango (Dev 2):** Core del Servidor asíncrono (Sockets + `asyncio`) y mecanismos de IPC (Señales UNIX).
* **Agus (Dev 3):** Infraestructura (Docker Compose), Broker/Workers (Celery) y Base de Datos (PostgreSQL).

---

## 🎯 Sprint 1 — Foco de Hoy (Demo Próxima Clase)
Para llevar un avance sólido, funcional y sin bloqueos a la próxima clase, cada desarrollador completará un issue clave:
1. **Agu (Dev 3):** **[Issue #1]** — Infraestructura base con Docker Compose (PostgreSQL + Redis).
2. **Charango (Dev 2):** **[Issue #3]** — Core del Servidor TCP concurrente con `asyncio`.
3. **Ale (Dev 1):** **[Issue #4]** — Agente vehicular CLI con `argparse` y envío de telemetría por Sockets.

---

### [Issue #1] Infraestructura base y orquestación con Docker Compose
- **Asignado a:** Agu (Dev 3)
- **Descripción:** Diseñar y configurar la infraestructura contenerizada del proyecto para permitir el despliegue orquestado y reproducible de todos los servicios (PostgreSQL, Redis como message broker de Celery, y servicios base en Python), garantizando un entorno aislado y homogéneo para todo el equipo de desarrollo.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Implementar un archivo `docker-compose.yml` que defina los contenedores para PostgreSQL 15+, Redis Alpine y variables de entorno parametrizadas vía `.env`.
  - Configurar volúmenes persistentes (`named volumes`) para evitar la pérdida de datos de la base de datos y de la cola de mensajes en caso de reinicio de contenedores.
  - Definir una red puente interna (`network`) para la comunicación segura entre microservicios y mapear los puertos necesarios para el acceso de desarrollo local.
  - Incluir `healthchecks` en PostgreSQL y Redis para garantizar que los servicios dependientes arranquen únicamente cuando los servidores base estén listos para recibir tráfico.
- **Dependencias:** Ninguna (Tarea inicial de infraestructura).

---

### [Issue #2] Modelado relacional y persistencia en PostgreSQL
- **Asignado a:** Agu (Dev 3)
- **Descripción:** Diseñar la estructura de base de datos relacional para el sistema de telemetría de flota y generar los scripts de inicialización DDL/migraciones para almacenar vehículos, mediciones periódicas (sensores, velocidad, ubicación GPS, combustible) y alertas críticas generadas por eventos del sistema.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Crear tablas normalizadas con claves primarias, foráneas e índices (especialmente en `vehicle_id` y `timestamp` para acelerar consultas temporales de series de tiempo).
  - Utilizar una librería de acceso a datos eficiente (como `psycopg2` / `asyncpg` o SQLAlchemy) asegurando el uso de connection pooling para prevenir saturación de conexiones.
  - Escribir un script SQL de inicialización montado en `/docker-entrypoint-initdb.d/` para que la base de datos se configure automáticamente al iniciar el contenedor.
  - Implementar restricciones de integridad (ej. rangos válidos para coordenadas, velocidad >= 0, estados válidos de vehículo).
- **Dependencias:** Requiere que el entorno base de base de datos esté configurado (Depende del Issue #1).

---

### [Issue #3] Core del Servidor de Sockets concurrente con Asyncio I/O
- **Asignado a:** Charango (Dev 2)
- **Descripción:** Implementar el servidor TCP de recepción de telemetría utilizando el bucle de eventos (`event loop`) de Python y el módulo `asyncio` (`asyncio.start_server`), permitiendo que decenas o cientos de vehículos envíen telemetría simultáneamente sin incurrir en overhead de hilos bloqueantes o multi-proceso innecesario.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Utilizar las abstracciones de alto nivel `StreamReader` y `StreamWriter` de `asyncio` para gestionar las conexiones entrantes de forma no bloqueante.
  - Evitar cualquier llamada bloqueante sincrónica (ej. `time.sleep`, lecturas de disco estándar) dentro de las corrutinas que manejan los sockets.
  - Manejar excepciones de conexión (`ConnectionResetError`, `IncompleteReadError`, timeouts) para desconectar clientes limpiamente sin tumbar el servidor.
  - Implementar control de concurrencia y un registro en memoria de clientes conectados activamente con sus identificadores de sesión.
- **Dependencias:** Ninguna (Puede iniciarse de forma independiente con mocks de red).

---

### [Issue #4] Agente vehicular CLI con recolección de métricas y Argparse
- **Asignado a:** Ale (Dev 1)
- **Descripción:** Desarrollar el agente cliente que correrá en cada vehículo de la flota, el cual recolectará y simulará métricas telemétricas (coordenadas GPS, velocidad, nivel de combustible, RPM, temperatura del motor) y admitirá configuración flexible y parametrizada mediante argumentos de línea de comandos.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Utilizar la biblioteca estándar `argparse` para recibir parámetros como `--server-host`, `--server-port`, `--vehicle-id`, `--interval` (frecuencia de muestreo) y `--mode` (simulación o real).
  - Diseñar el generador de datos telemétricos simulando trayectorias coherentes (rutas realistas, aceleraciones suaves y variaciones lógicas de temperatura/combustible).
  - Validar los tipos de datos y rangos de los argumentos provistos por CLI, arrojando mensajes de ayuda (`--help`) claros y código de salida semántico ante errores.
  - Estructurar el payload de telemetría en un formato estándar serializable (JSON estructurado con campos: `vehicle_id`, `timestamp`, `location`, `metrics`, `status`).
- **Dependencias:** Ninguna (Desarrollo autónomo del cliente vehicular).

---

### [Issue #5] Protocolo de comunicación, enmarcado y validación de paquetes
- **Asignado a:** Charango (Dev 2)
- **Descripción:** Definir y programar el protocolo de capa de aplicación sobre TCP para delimitar los mensajes entre el agente del vehículo y el servidor (evitando problemas de paquetes fragmentados o pegados en el buffer TCP), realizando el parseo y validación de integridad de los datos recibidos.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Implementar una estrategia de enmarcado de mensajes robusta (por ejemplo, delimitación por fin de línea `\n` o prefijo de longitud fija de bytes) para manejar lectura por streams en `asyncio`.
  - Deserializar y validar esquemas de datos JSON entrantes de forma segura, rechazando payloads corruptos o incompletos sin corromper el stream de datos.
  - Responder al cliente con acuses de recibo (ACK/NACK) para garantizar que el agente conozca el estado de entrega de su paquete.
  - Asegurar que la deserialización y validación no bloqueen el bucle de eventos mediante corrutinas optimizadas o ejecución protegida.
- **Dependencias:** Depende del Issue #3 y debe consensuar el formato definido en el Issue #4.

---

### [Issue #6] Conector TCP resiliente en el Agente con reconexión automática
- **Asignado a:** Ale (Dev 1)
- **Descripción:** Integrar en el agente CLI la capa de comunicación de red por sockets, asegurando el envío periódico de los paquetes de telemetría hacia el servidor y dotándolo de tolerancia a fallos y resiliencia ante pérdidas de conectividad celular/red típicas en vehículos en movimiento.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Utilizar sockets asíncronos o no bloqueantes para la transmisión continua de datos respetando la frecuencia indicada en los argumentos CLI.
  - Implementar un algoritmo de reintento con retroceso exponencial (`exponential backoff`) y jitter ante caídas de conexión o servidores no disponibles.
  - Incorporar una cola o búfer local en memoria para almacenar las mediciones pendientes de envío cuando se pierde la conexión, retransmitiéndolas al reconectar.
  - Gestionar el apagado ordenado (`graceful shutdown`) capturando señales `SIGINT` (Ctrl+C) y `SIGTERM` para cerrar el socket sin dejar conexiones colgadas.
- **Dependencias:** Depende del Issue #4 y del protocolo delimitado en el Issue #5.

---

### [Issue #7] Configuración de Celery, Broker y Workers para procesamiento pesado
- **Asignado a:** Agu (Dev 3)
- **Descripción:** Configurar e instanciar Celery como sistema de colas de tareas distribuidas utilizando Redis como broker y result backend, preparando el entorno para delegar el cálculo intensivo de analítica de flotas (detección de anomalías, excesos de velocidad y alertas de mantenimiento) fuera del ciclo del servidor de sockets.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Crear la instancia de Celery (`Celery application`) con configuración de serialización segura (JSON), control de concurrencia de workers (`prefork` o `gevent`) y reintentos automáticos.
  - Configurar en `docker-compose.yml` el servicio del worker de Celery, montando el código fuente y sincronizando variables de entorno con Redis y PostgreSQL.
  - Implementar tareas Celery base para la evaluación de umbrales críticos (ej. alerta si velocidad > 120 km/h o temperatura del motor > 105°C).
  - Asegurar el manejo de logs estructurados y gestión de fallos (`dead letter` o reintentos con `autoretry_for`) para que ninguna tarea fallida cause un bloqueo del worker.
- **Dependencias:** Depende del Issue #1 y del modelo de datos del Issue #2.

---

### [Issue #8] Despacho asíncrono a Celery e IPC mediante Señales UNIX en el Servidor
- **Asignado a:** Charango (Dev 2)
- **Descripción:** Conectar el servidor de sockets asíncrono con el sistema de tareas Celery (enviando la telemetría recibida a la cola sin bloquear `asyncio`) e implementar mecanismos de Comunicación Entre Procesos (IPC) mediante señales UNIX estándar (`SIGHUP` y `SIGUSR1`) para control operativo del servidor en caliente.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Despachar tareas hacia Celery desde el flujo asíncrono mediante `send_task` o `delay()` ejecutado sin bloquear el event loop (usando `loop.run_in_executor` si el cliente de Celery fuera sincrónico).
  - Implementar el manejador de la señal `signal.SIGHUP` registrado en el bucle de eventos (`loop.add_signal_handler`) para recargar dinámicamente configuraciones (umbrales de alerta, nivel de logging) sin reiniciar el servidor.
  - Implementar el manejador de la señal `signal.SIGUSR1` para volcar métricas y estadísticas operativas del servidor (clientes activos, paquetes/segundo) a un archivo de log o consola.
  - Garantizar la compatibilidad en entornos POSIX/Linux (adecuado para ejecución en Docker o sistemas compatibles) cumpliendo estrictamente los requisitos de IPC de la cátedra.
- **Dependencias:** Depende del Issue #5 y del Issue #7.

---

### [Issue #9] Pipeline de persistencia masiva en PostgreSQL y reportes agregados vía Celery
- **Asignado a:** Agu (Dev 3)
- **Descripción:** Desarrollar las tareas de Celery dedicadas a la inserción en base de datos de los datos telemétricos procesados y la generación periódica/bajo demanda de métricas agregadas de la flota (kilometraje total, consumo estimado, promedio de velocidades y eventos de riesgo).
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Implementar inserciones optimizadas por lotes (`batch inserts` o transacciones controladas) para evitar saturar el pool de conexiones de PostgreSQL ante alto volumen de telemetría.
  - Desarrollar una tarea Celery para registrar alertas en la tabla correspondiente cuando una medición exceda los rangos de seguridad.
  - Programar una tarea periódica (utilizando Celery Beat o scheduled task) para calcular resúmenes horarios/diarios por vehículo y estado general de la flota.
  - Gestionar transacciones de base de datos con manejo estricto de rollback ante excepciones para preservar la consistencia relacional.
- **Dependencias:** Depende del Issue #2 y del Issue #7.

---

### [Issue #10] Setup del Frontend SPA con Vite y Dashboard de Flota
- **Asignado a:** Ale (Dev 1)
- **Descripción:** Inicializar el entorno visual del proyecto mediante una Single Page Application (SPA) desarrollada con Vite, diseñando la interfaz de usuario moderna y responsiva para visualizar en tiempo real el mapa de la flota, el listado de vehículos activos y sus métricas principales.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Configurar el proyecto con Vite asegurando scripts de desarrollo rápido (`npm run dev`) y build de producción optimizado.
  - Diseñar componentes modulares (Panel de métricas globales, Tarjeta de estado de cada vehículo, Panel de alertas recientes e historial).
  - Incluir una librería ligera para visualización de mapas (ej. Leaflet / MapLibre) o gráficos de telemetría (ej. Chart.js / Recharts) para representar las rutas y velocidades.
  - Crear un diseño profesional con paleta oscura/moderna, tipografía legible y estados de carga/error visuales.
- **Dependencias:** Ninguna (Se puede maquetar inicialmente con mocks de datos locales).

---

### [Issue #11] Capa de distribución asíncrona hacia el Frontend (WebSocket / API Gateway)
- **Asignado a:** Charango (Dev 2)
- **Descripción:** Implementar una capa de exposición de datos en el servidor (mediante WebSockets o endpoints asíncronos rápidos con `aiohttp` / `FastAPI` / `websockets`) que permita al dashboard web conectarse y recibir en tiempo real la telemetría y las alertas procesadas por el backend sin sondeo continuo (polling) innecesario.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Utilizar corrutinas asíncronas para gestionar conexiones WebSocket simultáneas provenientes de navegadores web sin degradar el rendimiento del servidor de sockets.
  - Implementar el patrón Publicador/Suscriptor (Pub/Sub) utilizando Redis o colas en memoria de `asyncio` para retransmitir instantáneamente las alertas y mediciones hacia los clientes web suscritos.
  - Manejar el ciclo de vida de los WebSockets (mensajes `ping`/`pong`, desconexiones y reconexiones) liberando recursos de memoria.
  - Exponer endpoints HTTP de consulta histórica básica (ej. `/api/vehicles`, `/api/alerts`) consumiendo directamente de PostgreSQL de forma asíncrona.
- **Dependencias:** Depende del Issue #3, Issue #8 e Issue #9.

---

### [Issue #12] Integración en tiempo real del Frontend con la Telemetría y Alertas
- **Asignado a:** Ale (Dev 1)
- **Descripción:** Conectar el dashboard web desarrollado con Vite al gateway de WebSockets y API HTTP del servidor, logrando una experiencia interactiva en vivo donde los vehículos se actualicen en el mapa en tiempo real y las alertas críticas se notifiquen visualmente de inmediato.
- **Cosas a tener en cuenta (Criterios de Aceptación):**
  - Implementar un cliente WebSocket robusto en el frontend con reconexión automática y manejo de estado de conexión (Online / Offline / Reconectando).
  - Actualizar de forma reactiva la posición de los marcadores en el mapa y los indicadores de velocidad, RPM y combustible sin renderizados innecesarios.
  - Mostrar notificaciones flotantes (toasts / banners) animadas cuando se reciba una alerta de exceso de velocidad, temperatura o geocerca desde Celery/Backend.
  - Integrar vistas de consulta histórica consumiendo los endpoints REST para inspeccionar trayectorias previas de los vehículos.
- **Dependencias:** Depende del Issue #10 y del Issue #11.
