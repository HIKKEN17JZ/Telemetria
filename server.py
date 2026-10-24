import asyncio
import argparse
import json
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peername = writer.get_extra_info('peername')
    logger.info(f"New connection from {peername}")
    
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
                data = json.loads(message_str)
                vehicle_id = data.get("vehicle_id", "UNKNOWN")
                logger.info(f"Received telemetry from {vehicle_id}: {data}")
                
                response = {
                    "status": "ACK",
                    "vehicle_id": vehicle_id,
                    "server_time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                }
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received from {peername}: {message_str}")
                response = {
                    "status": "NACK",
                    "error": "Invalid JSON format"
                }
            except Exception as e:
                logger.error(f"Error processing message from {peername}: {e}")
                response = {
                    "status": "NACK",
                    "error": str(e)
                }
                
            response_bytes = (json.dumps(response) + "\n").encode("utf-8")
            writer.write(response_bytes)
            await writer.drain()
            
    except ConnectionResetError:
        logger.warning(f"Connection reset by peer {peername}")
    except Exception as e:
        logger.error(f"Unexpected error with {peername}: {e}")
    finally:
        logger.info(f"Closing connection for {peername}")
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

async def run_server(host: str, port: int) -> None:
    server = await asyncio.start_server(handle_client, host, port)
    addr = server.sockets[0].getsockname()
    logger.info(f"Telemetry server serving on {addr}")
    
    async with server:
        await server.serve_forever()

def main() -> None:
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
