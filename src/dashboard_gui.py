"""
Interfaz gráfica de escritorio en Tkinter (Semi-Frontend).
Monitoreo interactivo de flota en tiempo real con tablas de estado, paneles KPI,
visor de alertas con etiquetas de color y desacoplamiento limpio de la capa de datos.

Integración Multithreading:
- Consumo seguro de eventos de red mediante cola thread-safe (queue.Queue).
- Polling no bloqueante en el bucle de eventos mediante root.after().
- Indicador visual reactivo de conectividad (🟢 En Línea / 🔴 Desconectado / 🟡 Reconectando).
- Detención ordenada del hilo secundario al cerrar la ventana (WM_DELETE_WINDOW).
"""

from __future__ import annotations

import queue
import random
import tkinter as tk
from datetime import datetime, timezone
from tkinter import messagebox, ttk
from typing import Any, Dict, Optional

from src.dashboard_model import (
    AlertItem,
    AlertSeverity,
    FleetDashboardState,
    FleetMetrics,
    VehicleSummary,
)
from src.models import TelemetryPayload


class FleetDashboardView:
    """
    Vista principal de la aplicación de escritorio construida en Tkinter / ttk.
    Sigue el patrón MVP/Clean Architecture desacoplada del origen de datos.
    Soporta multithreading thread-safe vía queue.Queue y root.after().
    """

    def __init__(
        self,
        root: Optional[tk.Tk] = None,
        state: Optional[FleetDashboardState] = None,
        network_receiver: Optional[Any] = None,
        event_queue: Optional[queue.Queue] = None,
        auto_poll_queue: bool = True,
        queue_poll_interval_ms: int = 100
    ):
        self.root = root if root is not None else tk.Tk()
        self.state = state if state is not None else FleetDashboardState()
        self.network_receiver = network_receiver
        self.event_queue = event_queue if event_queue is not None else (
            network_receiver.event_queue if network_receiver else queue.Queue()
        )
        self.auto_poll_queue = auto_poll_queue
        self.queue_poll_interval_ms = queue_poll_interval_ms
        self._is_destroyed = False
        self._poll_timer_id: Optional[str] = None

        self._setup_window()
        self._setup_styles()
        self._build_ui()

        self.state.subscribe(self._on_state_change)
        self.refresh_views()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.auto_poll_queue:
            self._schedule_queue_poll()

    def _setup_window(self) -> None:
        """Configuración general de la ventana principal."""
        self.root.title("🚗 Sistema de Telemetría de Flota - Dashboard de Monitoreo")
        self.root.geometry("1060x650")
        self.root.minsize(860, 500)
        self.root.configure(bg="#f4f6f9")

    def _setup_styles(self) -> None:
        """Configuración de temas y estilos visuales ttk."""
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self.style.configure(
            "Treeview",
            background="#ffffff",
            foreground="#212529",
            rowheight=26,
            fieldbackground="#ffffff",
            font=("Segoe UI", 9)
        )
        self.style.configure(
            "Treeview.Heading",
            background="#e9ecef",
            foreground="#495057",
            font=("Segoe UI", 9, "bold")
        )

        self.style.configure("Card.TFrame", background="#ffffff", relief="groove")
        self.style.configure("CardTitle.TLabel", background="#ffffff", foreground="#6c757d", font=("Segoe UI", 9))
        self.style.configure("CardValue.TLabel", background="#ffffff", foreground="#212529", font=("Segoe UI", 16, "bold"))
        self.style.configure("CardValueCritical.TLabel", background="#ffffff", foreground="#dc3545", font=("Segoe UI", 16, "bold"))
        self.style.configure("TopBar.TFrame", background="#ffffff", relief="solid", borderwidth=1)

    def _build_ui(self) -> None:
        """Construye todos los contenedores y paneles de la interfaz gráfica."""
        self.main_container = ttk.Frame(self.root, padding=10)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        self._build_top_app_bar()
        self._build_control_panel()
        self._build_header_kpis()
        self._build_tables_notebook()

    def _build_top_app_bar(self) -> None:
        """Construye la barra superior con el título y el indicador de estado de conexión en vivo."""
        top_bar = tk.Frame(self.main_container, bg="#ffffff", bd=1, relief="solid", padx=12, pady=8)
        top_bar.pack(fill=tk.X, pady=(0, 10))

        left_frame = tk.Frame(top_bar, bg="#ffffff")
        left_frame.pack(side=tk.LEFT, fill=tk.Y)

        lbl_app_title = tk.Label(
            left_frame,
            text="🚗 SISTEMA DE TELEMETRÍA DE FLOTA DISTRIBUIDO",
            font=("Segoe UI", 11, "bold"),
            bg="#ffffff",
            fg="#1a202c"
        )
        lbl_app_title.pack(anchor="w")

        lbl_app_sub = tk.Label(
            left_frame,
            text="Dashboard de Monitoreo de Escritorio (Tkinter Multithreading & Async Stream)",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#718096"
        )
        lbl_app_sub.pack(anchor="w")

        right_frame = tk.Frame(top_bar, bg="#ffffff")
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.btn_reconnect = tk.Button(
            right_frame,
            text="🔄 Reconectar",
            font=("Segoe UI", 8, "bold"),
            bg="#e2e8f0",
            fg="#2d3748",
            relief="flat",
            padx=8,
            pady=3,
            command=self.reconnect_network
        )
        self.btn_reconnect.pack(side=tk.RIGHT, padx=(8, 0))

        status_box = tk.Frame(right_frame, bg="#ffffff")
        status_box.pack(side=tk.RIGHT)

        self.lbl_connection_badge = tk.Label(
            status_box,
            text="● DESCONECTADO",
            font=("Segoe UI", 9, "bold"),
            bg="#f8d7da",
            fg="#721c24",
            padx=8,
            pady=2,
            relief="flat"
        )
        self.lbl_connection_badge.pack(anchor="e")

        receiver_cfg = getattr(self.network_receiver, "config", None)
        default_url = getattr(receiver_cfg, "gateway_url", "http://127.0.0.1:8000") if receiver_cfg else "Modo Local / Mocks"
        self.lbl_connection_detail = tk.Label(
            status_box,
            text=f"API Gateway: {default_url}",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#a0aec0"
        )
        self.lbl_connection_detail.pack(anchor="e", pady=(2, 0))

    def _build_header_kpis(self) -> None:
        """Construye el panel superior de tarjetas KPI con resumen de la flota."""
        self.header_frame = ttk.Frame(self.main_container)
        self.header_frame.pack(fill=tk.X, pady=(0, 10))

        for i in range(5):
            self.header_frame.columnconfigure(i, weight=1)

        c1, _, self.lbl_total_vehicles = self._create_kpi_card(self.header_frame, "🚗 Total Flota", "0", 0)
        c2, _, self.lbl_active_vehicles = self._create_kpi_card(self.header_frame, "⚡ En Movimiento", "0", 1)
        c3, _, self.lbl_avg_speed = self._create_kpi_card(self.header_frame, "📊 Velocidad Promedio", "0.0 km/h", 2)
        c4, _, self.lbl_critical_alerts = self._create_kpi_card(
            self.header_frame, "🚨 Alertas Críticas", "0", 3, is_critical=True
        )
        c5, _, self.lbl_total_alerts = self._create_kpi_card(self.header_frame, "🔔 Total Alertas", "0", 4)

    def _create_kpi_card(
        self, parent: ttk.Frame, title: str, initial_value: str, col: int, is_critical: bool = False
    ) -> tuple[ttk.Frame, ttk.Label, ttk.Label]:
        """Crea una tarjeta KPI estilizada en la grilla superior."""
        frame = ttk.Frame(parent, style="Card.TFrame", padding=10)
        frame.grid(row=0, column=col, padx=4, sticky="nsew")

        lbl_title = ttk.Label(frame, text=title, style="CardTitle.TLabel")
        lbl_title.pack(anchor="w")

        val_style = "CardValueCritical.TLabel" if is_critical else "CardValue.TLabel"
        lbl_value = ttk.Label(frame, text=initial_value, style=val_style)
        lbl_value.pack(anchor="w", pady=(4, 0))

        return frame, lbl_title, lbl_value

    def _build_tables_notebook(self) -> None:
        """Construye el panel central con pestañas para Vehículos y Alertas."""
        self.paned_window = ttk.PanedWindow(self.main_container, orient=tk.VERTICAL)
        self.paned_window.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 6))

        self.vehicle_frame = ttk.LabelFrame(self.paned_window, text="  🚙 Estado de la Flota en Tiempo Real  ", padding=6)
        self.paned_window.add(self.vehicle_frame, weight=3)
        self._build_vehicle_table(self.vehicle_frame)

        self.alerts_frame = ttk.LabelFrame(self.paned_window, text="  🚨 Registro de Alertas y Eventos Críticos  ", padding=6)
        self.paned_window.add(self.alerts_frame, weight=2)
        self._build_alerts_table(self.alerts_frame)

    def _build_vehicle_table(self, parent: ttk.LabelFrame) -> None:
        """Crea la tabla ttk.Treeview para monitoreo de vehículos."""
        columns = ("id", "status", "speed", "rpm", "fuel", "temp", "coords", "updated")
        self.vehicle_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse", height=6)

        self.vehicle_tree.heading("id", text="ID Vehículo", anchor="center")
        self.vehicle_tree.heading("status", text="Estado", anchor="center")
        self.vehicle_tree.heading("speed", text="Velocidad (km/h)", anchor="center")
        self.vehicle_tree.heading("rpm", text="RPM", anchor="center")
        self.vehicle_tree.heading("fuel", text="Combustible (%)", anchor="center")
        self.vehicle_tree.heading("temp", text="Temp Motor (°C)", anchor="center")
        self.vehicle_tree.heading("coords", text="GPS (Lat, Lon)", anchor="center")
        self.vehicle_tree.heading("updated", text="Hora UTC", anchor="center")

        self.vehicle_tree.column("id", width=110, anchor="center")
        self.vehicle_tree.column("status", width=90, anchor="center")
        self.vehicle_tree.column("speed", width=120, anchor="center")
        self.vehicle_tree.column("rpm", width=80, anchor="center")
        self.vehicle_tree.column("fuel", width=110, anchor="center")
        self.vehicle_tree.column("temp", width=110, anchor="center")
        self.vehicle_tree.column("coords", width=160, anchor="center")
        self.vehicle_tree.column("updated", width=110, anchor="center")

        self.vehicle_tree.tag_configure("critical", background="#ffebee", foreground="#c62828")
        self.vehicle_tree.tag_configure("warning", background="#fff8e1", foreground="#ef6c00")
        self.vehicle_tree.tag_configure("normal", background="#ffffff", foreground="#212529")

        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.vehicle_tree.yview)
        self.vehicle_tree.configure(yscrollcommand=scrollbar.set)

        self.vehicle_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_alerts_table(self, parent: ttk.LabelFrame) -> None:
        """Crea la tabla ttk.Treeview para el registro de eventos y alertas."""
        columns = ("timestamp", "vehicle_id", "severity", "alert_type", "description")
        self.alerts_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse", height=4)

        self.alerts_tree.heading("timestamp", text="Hora UTC", anchor="center")
        self.alerts_tree.heading("vehicle_id", text="Vehículo", anchor="center")
        self.alerts_tree.heading("severity", text="Severidad", anchor="center")
        self.alerts_tree.heading("alert_type", text="Tipo de Evento", anchor="w")
        self.alerts_tree.heading("description", text="Descripción Detallada", anchor="w")

        self.alerts_tree.column("timestamp", width=110, anchor="center")
        self.alerts_tree.column("vehicle_id", width=100, anchor="center")
        self.alerts_tree.column("severity", width=90, anchor="center")
        self.alerts_tree.column("alert_type", width=160, anchor="w")
        self.alerts_tree.column("description", width=450, anchor="w")

        self.alerts_tree.tag_configure("CRITICAL", background="#ffebee", foreground="#b71c1c")
        self.alerts_tree.tag_configure("WARNING", background="#fff8e1", foreground="#e65100")
        self.alerts_tree.tag_configure("INFO", background="#e1f5fe", foreground="#01579b")

        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.alerts_tree.yview)
        self.alerts_tree.configure(yscrollcommand=scrollbar.set)

        self.alerts_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_control_panel(self) -> None:
        """Construye la botonera inferior para pruebas interactivas y simulación."""
        self.controls_frame = ttk.LabelFrame(self.main_container, text="  🛠️ Panel de Pruebas y Simulación  ", padding=6)
        self.controls_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

        btn_normal = ttk.Button(
            self.controls_frame, text="🚐 Inyectar Furgoneta (VAN-003)", command=self._mock_normal_telemetry
        )
        btn_normal.pack(side=tk.LEFT, padx=4)

        btn_speed = ttk.Button(
            self.controls_frame, text="⚡ Simular Exceso de Vel (>120 km/h)", command=self._mock_speed_alert
        )
        btn_speed.pack(side=tk.LEFT, padx=4)

        btn_temp = ttk.Button(
            self.controls_frame, text="🔥 Simular Recalentamiento (>100°C)", command=self._mock_temp_alert
        )
        btn_temp.pack(side=tk.LEFT, padx=4)

        btn_fuel = ttk.Button(
            self.controls_frame, text="⛽ Simular Bajo Combustible (<15%)", command=self._mock_fuel_alert
        )
        btn_fuel.pack(side=tk.LEFT, padx=4)

        btn_clear = ttk.Button(
            self.controls_frame, text="🗑️ Limpiar Alertas", command=self.state.clear_alerts
        )
        btn_clear.pack(side=tk.RIGHT, padx=4)

    def process_queue_events(self, max_events_per_cycle: int = 50) -> int:
        """
        Consume de forma segura los eventos entregados por el hilo de red secundario en queue.Queue.
        Garantiza que toda modificación de widgets y estado ocurra en el hilo principal de Tkinter.
        """
        processed_count = 0
        state_updated = False

        while not self.event_queue.empty() and processed_count < max_events_per_cycle:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break

            processed_count += 1
            ev_type = getattr(event, "event_type", None)
            data = getattr(event, "data", None)

            type_str = ev_type.value if hasattr(ev_type, "value") else str(ev_type)

            if type_str == "STATUS":
                self._handle_status_event(data)
            elif type_str == "TELEMETRY":
                if isinstance(data, (TelemetryPayload, dict)):
                    try:
                        self.state.update_telemetry(data)
                        state_updated = True
                    except Exception:
                        pass
            elif type_str == "ALERT":
                self._handle_alert_event(data)
                state_updated = True

        if state_updated:
            self.refresh_views()

        return processed_count

    def _schedule_queue_poll(self) -> None:
        """Programa la consulta periódica no bloqueante de la cola en el bucle principal de Tkinter."""
        if self._is_destroyed:
            return
        try:
            self.process_queue_events()
            self._poll_timer_id = self.root.after(self.queue_poll_interval_ms, self._schedule_queue_poll)
        except Exception:
            pass

    def _handle_status_event(self, data: Dict[str, Any]) -> None:
        """Actualiza el indicador visual de conectividad en función del estado de red recibido."""
        state_str = str(data.get("state", "DISCONNECTED")).upper()
        msg = data.get("message", "")
        url = data.get("url", "")
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

        if state_str == "CONNECTED":
            self.lbl_connection_badge.config(
                text="● EN LÍNEA",
                bg="#d4edda",
                fg="#155724"
            )
            detail = f"{url} | Última sincronización: {now_str}"
            if msg:
                detail += f" ({msg})"
            self.lbl_connection_detail.config(text=detail)
        elif state_str in ("CONNECTING", "RECONNECTING"):
            badge_text = "● CONECTANDO..." if state_str == "CONNECTING" else "● RECONECTANDO..."
            self.lbl_connection_badge.config(
                text=badge_text,
                bg="#fff3cd",
                fg="#856404"
            )
            detail = f"{url} | {msg}" if msg else f"{url} | Intentando conectar..."
            self.lbl_connection_detail.config(text=detail)
        else:
            self.lbl_connection_badge.config(
                text="● DESCONECTADO",
                bg="#f8d7da",
                fg="#721c24"
            )
            detail = f"{url} | {msg}" if msg else f"{url} | Sin conexión activa"
            self.lbl_connection_detail.config(text=detail)

    def _handle_alert_event(self, data: Dict[str, Any]) -> None:
        """Maneja e inserta un evento de alerta en el estado del dashboard."""
        if isinstance(data, AlertItem):
            self.state.add_alert(data)
        elif isinstance(data, dict):
            severity_str = str(data.get("severity", "WARNING")).upper()
            try:
                sev = AlertSeverity(severity_str)
            except Exception:
                sev = AlertSeverity.WARNING

            alert_item = AlertItem(
                vehicle_id=data.get("vehicle_id", "UNKNOWN"),
                alert_type=data.get("alert_type", "GENERAL_ALERT"),
                severity=sev,
                description=data.get("description", "Alerta telemétrica"),
                timestamp=data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                metric_value=float(data.get("metric_value", 0.0)) if data.get("metric_value") is not None else None,
                threshold_value=float(data.get("threshold_value", 0.0)) if data.get("threshold_value") is not None else None
            )
            self.state.add_alert(alert_item)

    def reconnect_network(self) -> None:
        """Reinicia la conexión del hilo de red si fue detenido o está desconectado."""
        if self.network_receiver is not None:
            if not self.network_receiver.is_alive():
                from src.dashboard_network import DashboardNetworkReceiver
                self.network_receiver = DashboardNetworkReceiver(
                    config=self.network_receiver.config,
                    event_queue=self.event_queue
                )
                self.network_receiver.start()
            else:
                from src.dashboard_network import ConnectionState
                self.network_receiver.set_state(
                    ConnectionState.CONNECTING, message="Reconexión manual iniciada..."
                )

    def on_close(self) -> None:
        """Manejador del evento de cierre de ventana WM_DELETE_WINDOW."""
        self._is_destroyed = True
        if self._poll_timer_id is not None:
            try:
                self.root.after_cancel(self._poll_timer_id)
            except Exception:
                pass
            self._poll_timer_id = None

        if self.network_receiver is not None:
            try:
                self.network_receiver.stop()
            except Exception:
                pass

        self.destroy()

    def destroy(self) -> None:
        """Cierra y destruye la ventana principal de forma segura."""
        self._is_destroyed = True
        try:
            self.root.destroy()
        except Exception:
            pass

    def _on_state_change(self, event_type: str, data: Any = None) -> None:
        """Callback del patrón Observer. Programa una actualización en el bucle principal de Tkinter."""
        if self._is_destroyed:
            return
        try:
            self.root.after_idle(self.refresh_views)
        except Exception:
            pass

    def refresh_views(self) -> None:
        """Refresca todos los componentes visuales con los datos actuales del modelo."""
        if self._is_destroyed:
            return

        metrics = self.state.get_fleet_metrics()
        self.lbl_total_vehicles.config(text=str(metrics.total_vehicles))
        self.lbl_active_vehicles.config(text=str(metrics.active_vehicles))
        self.lbl_avg_speed.config(text=f"{metrics.average_speed_kmh:.1f} km/h")
        self.lbl_critical_alerts.config(text=str(metrics.critical_alerts))
        self.lbl_total_alerts.config(text=str(metrics.total_alerts))

        existing_vehicle_items = {self.vehicle_tree.item(item)["values"][0]: item for item in self.vehicle_tree.get_children()}
        for v in self.state.get_vehicles():
            tag = "critical" if v.has_critical_alert else ("warning" if v.has_warning_alert else "normal")
            coords_str = f"({v.lat:.4f}, {v.lon:.4f})"
            time_str = v.timestamp.split("T")[-1].replace("Z", "") if "T" in v.timestamp else v.timestamp

            values = (
                v.vehicle_id,
                v.status,
                f"{v.speed_kmh:.1f}",
                v.rpm,
                f"{v.fuel_level_pct:.1f}%",
                f"{v.engine_temp_c:.1f}°C",
                coords_str,
                time_str
            )

            if v.vehicle_id in existing_vehicle_items:
                item_id = existing_vehicle_items[v.vehicle_id]
                self.vehicle_tree.item(item_id, values=values, tags=(tag,))
            else:
                self.vehicle_tree.insert("", tk.END, values=values, tags=(tag,))

        self.alerts_tree.delete(*self.alerts_tree.get_children())
        for a in self.state.get_alerts(limit=50):
            time_str = a.timestamp.split("T")[-1].replace("Z", "") if "T" in a.timestamp else a.timestamp
            tag = a.severity.value
            values = (
                time_str,
                a.vehicle_id,
                a.severity.value,
                a.alert_type,
                a.description
            )
            self.alerts_tree.insert("", tk.END, values=values, tags=(tag,))

    def _mock_normal_telemetry(self) -> None:
        """Inyecta una medición manual para la furgoneta de reparto (VAN-003)."""
        vid = "VAN-003"
        payload = TelemetryPayload.create(
            vehicle_id=vid,
            lat=-32.8895 + random.uniform(-0.01, 0.01),
            lon=-68.8458 + random.uniform(-0.01, 0.01),
            speed_kmh=round(random.uniform(45.0, 75.0), 1),
            rpm=random.randint(1900, 2400),
            fuel_level_pct=round(random.uniform(55.0, 90.0), 1),
            engine_temp_c=round(random.uniform(82.0, 88.0), 1),
            status="MOVING"
        )
        self.state.update_telemetry(payload)

    def _mock_speed_alert(self) -> None:
        """Inyecta una telemetría con velocidad excesiva para probar alerta visual roja."""
        payload = TelemetryPayload.create(
            vehicle_id="AUTO-001",
            lat=-32.8895,
            lon=-68.8458,
            speed_kmh=round(random.uniform(128.0, 145.0), 1),
            rpm=4100,
            fuel_level_pct=72.0,
            engine_temp_c=88.0,
            status="MOVING"
        )
        self.state.update_telemetry(payload)

    def _mock_temp_alert(self) -> None:
        """Inyecta una telemetría con recalentamiento crítico."""
        payload = TelemetryPayload.create(
            vehicle_id="CAMION-002",
            lat=-32.8988,
            lon=-68.8519,
            speed_kmh=75.0,
            rpm=2900,
            fuel_level_pct=60.0,
            engine_temp_c=round(random.uniform(103.0, 114.0), 1),
            status="MOVING"
        )
        self.state.update_telemetry(payload)

    def _mock_fuel_alert(self) -> None:
        """Inyecta una telemetría con nivel bajo de combustible."""
        payload = TelemetryPayload.create(
            vehicle_id="VAN-003",
            lat=-32.8750,
            lon=-68.8350,
            speed_kmh=45.0,
            rpm=1900,
            fuel_level_pct=round(random.uniform(5.0, 12.0), 1),
            engine_temp_c=84.0,
            status="MOVING"
        )
        self.state.update_telemetry(payload)

    def run(self) -> None:
        """Inicia el bucle principal de la interfaz gráfica."""
        self.root.mainloop()
