"""
Tests unitarios y de concurrencia para el servidor TCP asíncrono (Issue #2).
Implementados con unittest.IsolatedAsyncioTestCase para compatibilidad nativa.
"""

import asyncio
import json
import unittest

from server import handle_client
from src.protocol import ProtocolFraming


class TestAsyncServer(unittest.IsolatedAsyncioTestCase):
    """Pruebas funcionales y de concurrencia sobre el servidor TCP de telemetría."""

    async def asyncSetUp(self):
        self.server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
        self.addr = self.server.sockets[0].getsockname()
        self.server_task = asyncio.create_task(self._run_server())

    async def _run_server(self):
        async with self.server:
            try:
                await self.server.serve_forever()
            except asyncio.CancelledError:
                pass

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        self.server_task.cancel()
        try:
            await self.server_task
        except asyncio.CancelledError:
            pass

    async def test_valid_telemetry_returns_ack(self):
        reader, writer = await asyncio.open_connection(self.addr[0], self.addr[1])
        try:
            payload = {
                "vehicle_id": "AUTO-001",
                "timestamp": "2026-10-24T18:30:00Z",
                "location": {"lat": -32.8895, "lon": -68.8458},
                "metrics": {
                    "speed_kmh": 65.4,
                    "rpm": 2400,
                    "fuel_level_pct": 85.2,
                    "engine_temp_c": 88.5
                },
                "status": "MOVING"
            }
            writer.write((json.dumps(payload) + "\n").encode("utf-8"))
            await writer.drain()

            response_data = await reader.readline()
            response = json.loads(response_data.decode("utf-8").strip())

            self.assertEqual(response["status"], "ACK")
            self.assertEqual(response["vehicle_id"], "AUTO-001")
            self.assertIn("server_time", response)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def test_invalid_json_returns_nack(self):
        reader, writer = await asyncio.open_connection(self.addr[0], self.addr[1])
        try:
            writer.write(b"NOT A VALID JSON\n")
            await writer.drain()

            response_data = await reader.readline()
            response = json.loads(response_data.decode("utf-8").strip())

            self.assertEqual(response["status"], "NACK")
            self.assertIn("error", response)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def test_schema_violation_returns_nack(self):
        reader, writer = await asyncio.open_connection(self.addr[0], self.addr[1])
        try:
            payload = {"vehicle_id": "INCOMPLETO"}
            writer.write(ProtocolFraming.encode(payload))
            await writer.drain()

            response_data = await reader.readline()
            response = json.loads(response_data.decode("utf-8").strip())

            self.assertEqual(response["status"], "NACK")
            self.assertIn("error", response)
            self.assertIn("obligatorios", response["error"].lower())
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def test_multiple_messages_persistent_connection(self):
        reader, writer = await asyncio.open_connection(self.addr[0], self.addr[1])
        try:
            for i in range(3):
                payload = {
                    "vehicle_id": f"AUTO-00{i+1}",
                    "timestamp": "2026-10-24T18:30:00Z",
                    "location": {"lat": -32.8, "lon": -68.8},
                    "metrics": {
                        "speed_kmh": 50.0 + i,
                        "rpm": 2000,
                        "fuel_level_pct": 90.0,
                        "engine_temp_c": 80.0
                    },
                    "status": "MOVING"
                }
                writer.write((json.dumps(payload) + "\n").encode("utf-8"))
                await writer.drain()

                response_data = await reader.readline()
                response = json.loads(response_data.decode("utf-8").strip())
                self.assertEqual(response["status"], "ACK")
                self.assertEqual(response["vehicle_id"], f"AUTO-00{i+1}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def test_concurrent_clients(self):
        async def client_worker(vehicle_id):
            reader, writer = await asyncio.open_connection(self.addr[0], self.addr[1])
            try:
                payload = {
                    "vehicle_id": vehicle_id,
                    "timestamp": "2026-10-24T18:30:00Z",
                    "location": {"lat": 0.0, "lon": 0.0},
                    "metrics": {
                        "speed_kmh": 60.0,
                        "rpm": 2500,
                        "fuel_level_pct": 80.0,
                        "engine_temp_c": 85.0
                    },
                    "status": "MOVING"
                }
                writer.write((json.dumps(payload) + "\n").encode("utf-8"))
                await writer.drain()

                resp_data = await reader.readline()
                return json.loads(resp_data.decode("utf-8").strip())
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

        results = await asyncio.gather(
            client_worker("CAR-1"),
            client_worker("CAR-2"),
            client_worker("CAR-3")
        )

        for i, resp in enumerate(results):
            self.assertEqual(resp["status"], "ACK")
            self.assertEqual(resp["vehicle_id"], f"CAR-{i+1}")


if __name__ == "__main__":
    unittest.main()

