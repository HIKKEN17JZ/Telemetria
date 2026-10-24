# 📋 Guía e Instrucciones de Desarrollo: Sprint 1 (Sin Discrepancias)

Este documento es el **contrato técnico único y vinculante** para **Ale**, **Charango** y **Agus**. Su objetivo es definir las interfaces, protocolos y responsabilidades para que los tres puedan programar en paralelo sin pisarse el código y lograr una integración inmediata para la próxima clase.

---

## 🤝 1. El "Contrato de Interfaz" (Protocolo de Red)

Para que el cliente de **Ale** y el servidor de **Charango** se comuniquen de inmediato sin incompatibilidades, se establecen las siguientes reglas de comunicación:

### A. Parámetros de Red por Defecto
* **Protocolo de Transporte:** TCP
* **Host por defecto:** `127.0.0.1` (o `0.0.0.0` para el servidor)
* **Puerto TCP acordado:** `5000` (configurable por CLI en ambos extremos)

### B. Delimitación de Mensajes (Crucial para `asyncio`)
* Todo mensaje enviado por el socket debe ser un string JSON serializado terminado obligatoriamente en un **salto de línea (`\n`)**.
* **Motivo:** En `asyncio`, el servidor debe leer con `await reader.readline()`. Si falta el `\n`, el servidor quedará bloqueado esperando el fin de línea indefinidamente.

### C. Esquema del Payload de Telemetría (Envía Ale -> Recibe Charango)
Cada paquete transmitido por el socket debe respetar la siguiente estructura JSON:

```json
{
  "vehicle_id": "AUTO-001",
  "timestamp": "2026-10-24T18:30:00Z",
  "location": {
    "lat": -32.8895,
    "lon": -68.8458
  },
  "metrics": {
    "speed_kmh": 65.4,
    "rpm": 2400,
    "fuel_level_pct": 85.2,
    "engine_temp_c": 88.5
  },
  "status": "MOVING"
}
```

### D. Esquema de Respuesta del Servidor (Responde Charango -> Recibe Ale)
Al recibir y deserializar correctamente un paquete, el servidor responde:
```json
{
  "status": "ACK",
  "vehicle_id": "AUTO-001",
  "server_time": "2026-10-24T18:30:00Z"
}
```
Si el payload está corrupto o no es JSON válido:
```json
{
  "status": "NACK",
  "error": "Invalid JSON format"
}
```

---

## 🛠️ 2. Especificación por Desarrollador

### 🐳 Agus (Dev 3) — Issue #1: Infraestructura Docker
* **Archivos asignados:** `docker-compose.yml`, `.env.example`, `.env`, `init_db.sql`.
* **Servicios a levantar:**
  * **PostgreSQL:** Versión `15-alpine` en puerto `5435`.
    * Base de datos: `telemetria`
    * Usuario/Password: `postgres` / `postgres`
    * Volumen persistente: `postgres_data`
    * Healthcheck: `pg_isready -U postgres -d telemetria`
  * **Redis:** Versión `7-alpine` en puerto `6380`.
    * Volumen persistente: `redis_data`
    * Healthcheck: `redis-cli ping`
  * **Red compartida:** `telemetria_net` (tipo bridge).
* **Cómo prueba Agus en solitario:**
  ```powershell
  docker compose up -d
  docker compose ps    # Ambos contenedores deben figurar "healthy"
  ```

---

### ⚡ Charango (Dev 2) — Issue #2: Servidor TCP Concurrente
* **Archivo asignado:** `server.py`
* **Tecnología obligatoria:** `asyncio` y sockets (`asyncio.start_server`).
* **Reglas técnicas de oro:**
  1. **Cero llamadas bloqueantes:** Prohibido usar `time.sleep()`. Si se necesita pausar, usar exclusivamente `await asyncio.sleep()`.
  2. **Lectura por Streams:** Usar `await reader.readline()` para procesar línea por línea.
  3. **Envío con Drain:** Siempre que se envíe una respuesta con `writer.write(data)`, ejecutar inmediatamente `await writer.drain()`.
  4. **Tolerancia a desconexiones:** Capturar `ConnectionResetError` y verificar cuando `reader.readline()` retorne vacío (`b""`) para cerrar el socket sin que se caiga el servidor.
* **Argumentos CLI mínimos requeridos:**
  * `--host` (default: `"0.0.0.0"`)
  * `--port` (default: `5000`)
* **Cómo prueba Charango en solitario:**
  ```powershell
  python server.py --port 5000
  # En otra terminal probar con PowerShell:
  Test-NetConnection -Port 5000 -ComputerName localhost
  ```

---

### 🚗 Ale (Dev 1) — Issue #3: Agente Vehicular CLI
* **Archivo asignado:** `agent.py`
* **Tecnología obligatoria:** Módulo estándar `argparse`, `socket`, `time` y `json`.
* **Reglas técnicas de oro:**
  1. **Parseo con `argparse`:** Debe soportar `--vehicle-id`, `--server-host`, `--server-port`, `--interval` y proveer mensaje de `--help` limpio.
  2. **Delimitador `\n` al enviar:** Al enviar el socket hacer:
     `sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))`
  3. **Reintento ante fallos:** Si el servidor no está levantado (`ConnectionRefusedError`), no romper el programa; atrapar la excepción y reintentar cada X segundos.
  4. **Apagado limpio:** Atrapar `KeyboardInterrupt` (Ctrl+C) para cerrar el socket y salir sin arrojar Tracebacks feos.
* **Cómo prueba Ale en solitario:**
  ```powershell
  python agent.py --help
  python agent.py --vehicle-id PRUEBA-01 --interval 1
  ```

---

## 🌿 3. Flujo de Trabajo en Git (Para evitar conflictos)

Para cumplir con la recomendación de la cátedra de realizar **commits periódicos**:

1. **Antes de empezar:** Todos hacen `git pull origin main`.
2. **Cada uno crea su rama de trabajo:**
   * Agus: `git checkout -b feature/docker-infra`
   * Charango: `git checkout -b feature/async-server`
   * Ale: `git checkout -b feature/cli-agent`
3. **Commits frecuentes:** Cada cambio significativo (ej: creación de argumentos CLI, bucle de simulación, conexión de socket) debe commitearse individualmente.
4. **Integración:** Cada uno hace `git push origin <su-rama>` y abren su Pull Request a `main`.

---

## 🎬 4. Orden de Ejecución para la Demo en Vivo

El día de la presentación frente al profesor, el orden exacto de encendido es:

1. **Paso 1 (Agus):** Levanta la infraestructura:
   ```powershell
   docker compose up -d
   ```
2. **Paso 2 (Charango):** Inicia el servidor de telemetría:
   ```powershell
   python server.py --host 0.0.0.0 --port 5000
   ```
3. **Paso 3 (Ale):** Abre 2 o 3 terminales y lanza vehículos concurrentes:
   ```powershell
   # Terminal 1:
   python agent.py --vehicle-id AUTO-001 --interval 1

   # Terminal 2:
   python agent.py --vehicle-id CAMION-002 --interval 2
   ```

**Resultado esperado:** El servidor de Charango mostrará en consola cómo ingresan los datos de ambos vehículos simultáneamente en tiempo real sin bloquearse.
