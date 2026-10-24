import asyncio
import json
import pytest
from server import handle_client

@pytest.mark.asyncio
async def test_valid_telemetry_returns_ack():
    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    
    async def run_server_task():
        async with server:
            await server.serve_forever()
            
    server_task = asyncio.create_task(run_server_task())
    
    try:
        reader, writer = await asyncio.open_connection(addr[0], addr[1])
        
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
        
        assert response["status"] == "ACK"
        assert response["vehicle_id"] == "AUTO-001"
        assert "server_time" in response
        
        writer.close()
        await writer.wait_closed()
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

@pytest.mark.asyncio
async def test_invalid_json_returns_nack():
    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    
    async def run_server_task():
        async with server:
            await server.serve_forever()
            
    server_task = asyncio.create_task(run_server_task())
    
    try:
        reader, writer = await asyncio.open_connection(addr[0], addr[1])
        
        writer.write(b"NOT A VALID JSON\n")
        await writer.drain()
        
        response_data = await reader.readline()
        response = json.loads(response_data.decode("utf-8").strip())
        
        assert response["status"] == "NACK"
        assert "error" in response
        
        writer.close()
        await writer.wait_closed()
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

@pytest.mark.asyncio
async def test_multiple_messages_persistent_connection():
    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    
    async def run_server_task():
        async with server:
            await server.serve_forever()
            
    server_task = asyncio.create_task(run_server_task())
    
    try:
        reader, writer = await asyncio.open_connection(addr[0], addr[1])
        
        for i in range(3):
            payload = {
                "vehicle_id": f"AUTO-00{i+1}",
                "timestamp": "2026-10-24T18:30:00Z",
                "location": {"lat": -32.8, "lon": -68.8},
                "metrics": {"speed_kmh": 50.0 + i, "rpm": 2000, "fuel_level_pct": 90.0, "engine_temp_c": 80.0},
                "status": "MOVING"
            }
            writer.write((json.dumps(payload) + "\n").encode("utf-8"))
            await writer.drain()
            
            response_data = await reader.readline()
            response = json.loads(response_data.decode("utf-8").strip())
            assert response["status"] == "ACK"
            assert response["vehicle_id"] == f"AUTO-00{i+1}"
            
        writer.close()
        await writer.wait_closed()
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

@pytest.mark.asyncio
async def test_concurrent_clients():
    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    
    async def run_server_task():
        async with server:
            await server.serve_forever()
            
    server_task = asyncio.create_task(run_server_task())
    
    async def client_worker(vehicle_id):
        reader, writer = await asyncio.open_connection(addr[0], addr[1])
        payload = {
            "vehicle_id": vehicle_id,
            "timestamp": "2026-10-24T18:30:00Z",
            "location": {"lat": 0.0, "lon": 0.0},
            "metrics": {"speed_kmh": 60.0, "rpm": 2500, "fuel_level_pct": 80.0, "engine_temp_c": 85.0},
            "status": "MOVING"
        }
        writer.write((json.dumps(payload) + "\n").encode("utf-8"))
        await writer.drain()
        
        resp_data = await reader.readline()
        resp = json.loads(resp_data.decode("utf-8").strip())
        writer.close()
        await writer.wait_closed()
        return resp
        
    try:
        results = await asyncio.gather(
            client_worker("CAR-1"),
            client_worker("CAR-2"),
            client_worker("CAR-3")
        )
        
        for i, resp in enumerate(results):
            assert resp["status"] == "ACK"
            assert resp["vehicle_id"] == f"CAR-{i+1}"
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
