"""
Tests unitarios para la capa de red del agente (TCP Socket Client) (TDD).
Usa un servidor TCP mock local en un hilo para probar la comunicación real.
"""

import json
import socket
import threading
import time
import unittest

from src.models import TelemetryPayload, Location, VehicleMetrics
from src.network import TelemetryClient, NetworkResponse


class TestTelemetryNetworkClient(unittest.TestCase):

    def setUp(self):
        # Crear servidor mock en puerto efímero (0)
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.bind(("127.0.0.1", 0))
        self.server_host, self.server_port = self.server_sock.getsockname()
        self.server_sock.listen(1)
        self.running = True
        self.received_messages = []

    def tearDown(self):
        self.running = False
        try:
            self.server_sock.close()
        except Exception:
            pass

    def _run_mock_server(self, ack_response: str = '{"status": "ACK"}\n'):
        """Servidor de prueba que recibe un mensaje terminado en \\n y responde un ACK."""
        try:
            self.server_sock.settimeout(2.0)
            client_conn, _ = self.server_sock.accept()
            with client_conn:
                buffer = ""
                while self.running:
                    data = client_conn.recv(1024).decode("utf-8")
                    if not data:
                        break
                    buffer += data
                    if "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        self.received_messages.append(line)
                        client_conn.sendall(ack_response.encode("utf-8"))
        except (socket.timeout, OSError):
            pass

    def test_send_telemetry_and_receive_ack(self):
        """Verifica que el cliente envíe con delimitador \\n y reciba el ACK parseado."""
        server_thread = threading.Thread(target=self._run_mock_server)
        server_thread.start()

        client = TelemetryClient(host=self.server_host, port=self.server_port, timeout=1.0)
        connected = client.connect()
        self.assertTrue(connected)
        self.assertTrue(client.is_connected)

        payload = TelemetryPayload.create(
            vehicle_id="VEH-TEST",
            lat=-32.88,
            lon=-68.84,
            speed_kmh=55.0,
            rpm=2100,
            fuel_level_pct=90.0,
            engine_temp_c=85.0,
            status="MOVING"
        )

        response = client.send(payload)
        self.assertIsInstance(response, NetworkResponse)
        self.assertTrue(response.success)
        self.assertEqual(response.data.get("status"), "ACK")

        client.disconnect()
        server_thread.join()

        # Verificar que el servidor recibió el mensaje con vehicle_id correcto
        self.assertEqual(len(self.received_messages), 1)
        received_json = json.loads(self.received_messages[0])
        self.assertEqual(received_json["vehicle_id"], "VEH-TEST")

    def test_connect_failure_to_closed_port(self):
        """Verifica que intentar conectar a un puerto cerrado devuelva False sin crashear."""
        # Cerrar el servidor para asegurar que el puerto esté cerrado
        self.server_sock.close()

        client = TelemetryClient(host=self.server_host, port=self.server_port, timeout=0.5)
        connected = client.connect()
        self.assertFalse(connected)
        self.assertFalse(client.is_connected)


if __name__ == "__main__":
    unittest.main()
