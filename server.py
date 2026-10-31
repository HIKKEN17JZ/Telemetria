"""
Servidor Asíncrono Concurrente de Telemetría (Issue #2 & Issue #5).
Asignado a: Charango (Dev 2 - @Charango21)

Implementa:
- Servidor TCP concurrente de alto rendimiento basado en asyncio (I/O no bloqueante).
- Manejo estricto de conexiones simultáneas mediante StreamReader y StreamWriter.
- Protocolo delimitado por fin de línea ('\\n') con validación robusta y acuses de recibo ACK/NACK.
- Registro en memoria de clientes conectados activamente.
"""

import asyncio
import argparse
import logging
from typing import Dict, Tuple

from src.protocol import ProtocolValidator, ProtocolResponse, ProtocolError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Registro en memoria de sesiones activas: client_id -> (peername, vehicle_id)
active_clients: Dict[int, Tuple[str, str]] = {}


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Maneja la conexión TCP individual de un cliente de telemetría de forma no bloqueante."""
    peername = writer.get_extra_info('peername')
    client_id = id(writer)
    active_clients[client_id] = (str(peername), "UNKNOWN")
    logger.info(f"New connection from {peername} (Active: {len(active_clients)})")
    
    try:
        while True:
            line = await reader.readline()
            if not line:
                logger.info(f"Client {peername} disconnected (EOF)")
                break
                
            message_str = line.decode("utf-8").strip()
            if not message_str:
                continue
                
            try:
                # Validar paquete mediante la capa de aplicación de protocolo (Issue #5)
                frame = ProtocolValidator.validate_raw(message_str)
                active_clients[client_id] = (str(peername), frame.vehicle_id)
                logger.info(
                    f"Received valid telemetry from {frame.vehicle_id}: "
                    f"speed={frame.metrics.speed_kmh}km/h, rpm={frame.metrics.rpm}, "
                    f"fuel={frame.metrics.fuel_level_pct}%, temp={frame.metrics.engine_temp_c}°C"
                )
                response = ProtocolResponse.ack(frame.vehicle_id)

            except ProtocolError as e:
                logger.warning(f"Protocol validation error from {peername}: {e}")
                response = ProtocolResponse.nack(str(e))
            except Exception as e:
                logger.error(f"Unexpected error processing message from {peername}: {e}")
                response = ProtocolResponse.nack(f"Server error: {e}")
                
            response_bytes = ProtocolResponse.to_bytes(response)
            writer.write(response_bytes)
            await writer.drain()
            
    except ConnectionResetError:
        logger.warning(f"Connection reset by peer {peername}")
    except Exception as e:
        logger.error(f"Unexpected error with {peername}: {e}")
    finally:
        active_clients.pop(client_id, None)
        logger.info(f"Closing connection for {peername} (Active: {len(active_clients)})")
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def run_server(host: str, port: int) -> None:
    """Arranca el bucle de eventos del servidor TCP concurrente."""
    server = await asyncio.start_server(handle_client, host, port)
    addr = server.sockets[0].getsockname()
    logger.info(f"Telemetry server serving on {addr}")
    
    async with server:
        await server.serve_forever()


def main() -> None:
    """Punto de entrada CLI para el servidor de telemetría."""
    parser = argparse.ArgumentParser(description="Concurrent Asyncio Telemetry Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind server to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind server to")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(run_server(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Server stopped by user (KeyboardInterrupt)")


if __name__ == "__main__":
    main()
