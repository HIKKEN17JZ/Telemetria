#!/usr/bin/env python3
"""
Punto de Entrada del API Gateway de Telemetría (Issue #11).
Asignado a: Charango (Dev 2 - @Charango21)

Servidor HTTP REST y WebSockets servido con arquitectura Gunicorn + Uvicorn Workers.

Comando estándar para la cátedra:
    gunicorn -w 2 -k uvicorn.workers.UvicornWorker --threads 2 gateway:app -b 0.0.0.0:8000

O mediante este script CLI:
    python gateway.py --host 0.0.0.0 --port 8000 --workers 2
"""

import argparse
import os
import sys
import uvicorn

# Exponer la instancia FastAPI para Gunicorn (gunicorn gateway:app)
from src.gateway import app, GatewayConfig

__all__ = ["app"]


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="API Gateway de Telemetría (FastAPI + Uvicorn/Gunicorn)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("GATEWAY_HOST", "0.0.0.0"),
        help="Dirección IP o interfaz donde escuchar peticiones"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("GATEWAY_PORT", "8000")),
        help="Puerto TCP para el API Gateway"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.getenv("GATEWAY_WORKERS", "2")),
        help="Cantidad de procesos workers independientes"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=os.getenv("GATEWAY_RELOAD", "false").lower() in ("true", "1", "yes"),
        help="Activar recarga automática en caliente para desarrollo"
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()

    print("=" * 65)
    print("   📡 SISTEMA DE TELEMETRÍA - API GATEWAY (GUNICORN / UVICORN)")
    print("=" * 65)
    print(f" [*] Host:        {args.host}")
    print(f" [*] Puerto:      {args.port}")
    print(f" [*] Workers:     {args.workers} (Procesos paralelos)")
    print(f" [*] Threads/Wk:  2 (Hilos concurrentes para I/O bloqueante)")
    print(f" [*] Docs:        http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}/docs")
    print(f" [*] Healthcheck: http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}/health")
    print("=" * 65)

    # Iniciar con Uvicorn (compatible tanto con Windows como Linux/macOS)
    uvicorn.run(
        "gateway:app",
        host=args.host,
        port=args.port,
        workers=args.workers if not args.reload else 1,
        reload=args.reload,
        log_level="info"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
