"""
Tests unitarios y de resiliencia para TelemetryClient con buffer offline y reconexión automática (TDD - Issue #6).
"""

import json
import socket
import threading
import time
import unittest

from src.models import TelemetryPayload
from src.network import TelemetryClient, NetworkResponse
from src.buffer import TelemetryBuffer
from src.backoff import ExponentialBackoff


class TestResilientTelemetryClient(unittest.TestCase):

    def setUp(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.bind(("127.0.0.1", 0))
        self.server_host, self.server_port = self.server_sock.getsockname()
        self.server_sock.listen(5)
        self.running = True
        self.received_messages = []

    def tearDown(self):
        self.running = False
        try:
            self.server_sock.close()
        except Exception:
            pass

    def _run_mock_server(self):
        """Servidor mock que procesa mensajes delimitados por \\n y responde con ACK."""
        try:
            self.server_sock.settimeout(2.0)
            while self.running:
                try:
                    conn, _ = self.server_sock.accept()
                except (socket.timeout, OSError):
                    continue

                with conn:
                    buffer = ""
                    while self.running:
                        try:
                            data = conn.recv(1024).decode("utf-8")
                        except OSError:
                            break
                        if not data:
                            break
                        buffer += data
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if line:
                                self.received_messages.append(line)
                                ack = json.dumps({"status": "ACK", "ts": time.time()}) + "\n"
                                conn.sendall(ack.encode("utf-8"))
        except Exception:
            pass

    def test_buffer_accumulates_when_server_is_down(self):
        """Verifica que si el servidor está caído, los mensajes se guarden en el buffer sin perder datos."""
        # Cerrar el servidor inmediatamente para simular caída
        self.server_sock.close()

        buffer = TelemetryBuffer()
        backoff = ExponentialBackoff(initial_delay=0.1, max_delay=1.0, jitter=False)
        client = TelemetryClient(
            host=self.server_host,
            port=self.server_port,
            timeout=0.2,
            buffer=buffer,
            backoff=backoff
        )

        payload1 = TelemetryPayload.create(
            vehicle_id="AUTO-01", lat=-32.88, lon=-68.84,
            speed_kmh=40.0, rpm=1800, fuel_level_pct=90.0,
            engine_temp_c=80.0, status="MOVING", timestamp="2026-10-31T20:00:01Z"
        )
        payload2 = TelemetryPayload.create(
            vehicle_id="AUTO-01", lat=-32.89, lon=-68.85,
            speed_kmh=50.0, rpm=2000, fuel_level_pct=89.0,
            engine_temp_c=82.0, status="MOVING", timestamp="2026-10-31T20:00:02Z"
        )

        res1 = client.send_or_buffer(payload1)
        res2 = client.send_or_buffer(payload2)

        # Ambas llamadas fallan a nivel red pero se encolan con éxito
        self.assertFalse(res1.success)
        self.assertTrue(res1.buffered)
        self.assertFalse(res2.success)
        self.assertTrue(res2.buffered)
        self.assertEqual(len(client.buffer), 2)

    def test_flushes_buffer_in_order_upon_reconnection(self):
        """Verifica que al reconectar, el cliente transmita los datos encolados en estricto orden FIFO."""
        # 1. Acumular mensajes con el server caído
        self.server_sock.close()

        buffer = TelemetryBuffer()
        client = TelemetryClient(
            host=self.server_host,
            port=self.server_port,
            timeout=0.5,
            buffer=buffer
        )

        for i in range(3):
            p = TelemetryPayload.create(
                vehicle_id=f"AUTO-0{i}", lat=0.0, lon=0.0,
                speed_kmh=30.0 + i, rpm=1500, fuel_level_pct=90.0,
                engine_temp_c=80.0, status="MOVING",
                timestamp=f"2026-10-31T20:00:0{i}Z"
            )
            client.send_or_buffer(p)

        self.assertEqual(len(client.buffer), 3)

        # 2. Levantar nuevo servidor en el mismo puerto
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.bind((self.server_host, self.server_port))
        self.server_sock.listen(5)
        server_thread = threading.Thread(target=self._run_mock_server, daemon=True)
        server_thread.start()

        # 3. Al enviar un nuevo paquete, debe reconectar, vaciar el buffer (3 paquetes previos) y enviar el nuevo
        new_payload = TelemetryPayload.create(
            vehicle_id="AUTO-NEW", lat=1.0, lon=1.0,
            speed_kmh=60.0, rpm=2500, fuel_level_pct=85.0,
            engine_temp_c=88.0, status="MOVING",
            timestamp="2026-10-31T20:00:10Z"
        )
        response = client.send_or_buffer(new_payload)

        self.assertTrue(response.success)
        self.assertEqual(len(client.buffer), 0)

        # Dar breve momento a la recepción
        time.sleep(0.3)

        # El servidor debe haber recibido los 4 mensajes en orden
        self.assertEqual(len(self.received_messages), 4)
        msg0 = json.loads(self.received_messages[0])
        msg1 = json.loads(self.received_messages[1])
        msg2 = json.loads(self.received_messages[2])
        msg3 = json.loads(self.received_messages[3])

        self.assertEqual(msg0["vehicle_id"], "AUTO-00")
        self.assertEqual(msg1["vehicle_id"], "AUTO-01")
        self.assertEqual(msg2["vehicle_id"], "AUTO-02")
        self.assertEqual(msg3["vehicle_id"], "AUTO-NEW")

        client.disconnect()


if __name__ == "__main__":
    unittest.main()

