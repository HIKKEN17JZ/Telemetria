"""
Interfaz gráfica de escritorio en Tkinter (Semi-Frontend) - Issue #10.
Monitoreo interactivo de flota en tiempo real con tablas de estado, paneles KPI,
visor de alertas con etiquetas de color y desacoplamiento limpio de la capa de datos.
"""

from __future__ import annotations

import random
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Any
from datetime import datetime, timezone

from src.dashboard_model import (
    FleetDashboardState,
    AlertSeverity,
    AlertItem,
    VehicleSummary,
    FleetMetrics
)
from src.models import TelemetryPayload


class FleetDashboardView:
    """
    Vista principal de la aplicación de escritorio construida en Tkinter / ttk.
    Sigue el patrón MVP/Clean Architecture desacoplada del origen de datos.
    """

    def __init__(self, root: Optional[tk.Tk] = None, state: Optional[FleetDashboardState] = None):
        self.root = root if root is not None else tk.Tk()
        self.state = state if state is not None else FleetDashboardState()

        self._setup_window()
        self._setup_styles()
        self._build_ui()

        # Suscribir la vista a los eventos del modelo
        self.state.subscribe(self._on_state_change)
        self.refresh_views()

    def _setup_window(self) -> None:
        """Configuración general de la ventana principal."""
        self.root.title("🚗 Sistema de Telemetría de Flota - Dashboard de Monitoreo")
        self.root.geometry("1100x720")
        self.root.minsize(950, 600)
        self.root.configure(bg="#f4f6f9")

    def _setup_styles(self) -> None:
        """Configuración de temas y estilos visuales ttk."""
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Estilo para Treeviews
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

        # Estilos para Tarjetas KPI
        self.style.configure("Card.TFrame", background="#ffffff", relief="groove")
        self.style.configure("CardTitle.TLabel", background="#ffffff", foreground="#6c757d", font=("Segoe UI", 9))
        self.style.configure("CardValue.TLabel", background="#ffffff", foreground="#212529", font=("Segoe UI", 16, "bold"))
        self.style.configure("CardValueCritical.TLabel", background="#ffffff", foreground="#dc3545", font=("Segoe UI", 16, "bold"))

    def _build_ui(self) -> None:
        """Construye todos los contenedores y paneles de la interfaz gráfica."""
        # Contenedor raíz con padding
        self.main_container = ttk.Frame(self.root, padding=12)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        self._build_header_kpis()
        self._build_tables_notebook()
        self._build_control_panel()

    def _build_header_kpis(self) -> None:
        """Construye el panel superior de tarjetas KPI con resumen de la flota."""
        self.header_frame = ttk.Frame(self.main_container)
        self.header_frame.pack(fill=tk.X, pady=(0, 10))

        # Configurar 5 columnas homogéneas
        for i in range(5):
            self.header_frame.columnconfigure(i, weight=1)

        # 1. Total Vehículos
        c1, _, self.lbl_total_vehicles = self._create_kpi_card(self.header_frame, "🚗 Total Flota", "0", 0)
        # 2. Vehículos Activos
        c2, _, self.lbl_active_vehicles = self._create_kpi_card(self.header_frame, "⚡ En Movimiento", "0", 1)
        # 3. Velocidad Promedio
        c3, _, self.lbl_avg_speed = self._create_kpi_card(self.header_frame, "📊 Velocidad Promedio", "0.0 km/h", 2)
        # 4. Alertas Críticas
        c4, _, self.lbl_critical_alerts = self._create_kpi_card(
            self.header_frame, "🚨 Alertas Críticas", "0", 3, is_critical=True
        )
        # 5. Total Alertas
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
        self.paned_window.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Panel 1: Tabla de Vehículos
        self.vehicle_frame = ttk.LabelFrame(self.paned_window, text="  🚙 Estado de la Flota en Tiempo Real  ", padding=8)
        self.paned_window.add(self.vehicle_frame, weight=3)
        self._build_vehicle_table(self.vehicle_frame)

        # Panel 2: Registro de Alertas y Eventos
        self.alerts_frame = ttk.LabelFrame(self.paned_window, text="  🚨 Registro de Alertas y Eventos Críticos  ", padding=8)
        self.paned_window.add(self.alerts_frame, weight=2)
        self._build_alerts_table(self.alerts_frame)

    def _build_vehicle_table(self, parent: ttk.LabelFrame) -> None:
        """Crea la tabla ttk.Treeview para monitoreo de vehículos."""
        columns = ("id", "status", "speed", "rpm", "fuel", "temp", "coords", "updated")
        self.vehicle_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")

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

        # Configuración de tags de color para alertas inmediatas
        self.vehicle_tree.tag_configure("critical", background="#ffebee", foreground="#c62828")
        self.vehicle_tree.tag_configure("warning", background="#fff8e1", foreground="#ef6c00")
        self.vehicle_tree.tag_configure("normal", background="#ffffff", foreground="#212529")

        # Scrollbar vertical
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.vehicle_tree.yview)
        self.vehicle_tree.configure(yscrollcommand=scrollbar.set)

        self.vehicle_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_alerts_table(self, parent: ttk.LabelFrame) -> None:
        """Crea la tabla ttk.Treeview para el registro de eventos y alertas."""
        columns = ("timestamp", "vehicle_id", "severity", "alert_type", "description")
        self.alerts_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")

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

        # Tags de severidad
        self.alerts_tree.tag_configure("CRITICAL", background="#ffebee", foreground="#b71c1c")
        self.alerts_tree.tag_configure("WARNING", background="#fff8e1", foreground="#e65100")
        self.alerts_tree.tag_configure("INFO", background="#e1f5fe", foreground="#01579b")

        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.alerts_tree.yview)
        self.alerts_tree.configure(yscrollcommand=scrollbar.set)

        self.alerts_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_control_panel(self) -> None:
        """Construye la botonera inferior para pruebas interactivas y simulación."""
        self.controls_frame = ttk.LabelFrame(self.main_container, text="  🛠️ Panel de Pruebas y Simulación  ", padding=8)
        self.controls_frame.pack(fill=tk.X)

        btn_normal = ttk.Button(
            self.controls_frame, text="🚗 Inyectar Telemetría Normal", command=self._mock_normal_telemetry
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

    def _on_state_change(self, event_type: str, data: Any = None) -> None:
        """Callback del patrón Observer. Programa una actualización en el bucle principal de Tkinter."""
        try:
            self.root.after_idle(self.refresh_views)
        except Exception:
            pass

    def refresh_views(self) -> None:
        """Refresca todos los componentes visuales con los datos actuales del modelo."""
        # 1. Actualizar Tarjetas KPI
        metrics = self.state.get_fleet_metrics()
        self.lbl_total_vehicles.config(text=str(metrics.total_vehicles))
        self.lbl_active_vehicles.config(text=str(metrics.active_vehicles))
        self.lbl_avg_speed.config(text=f"{metrics.average_speed_kmh:.1f} km/h")
        self.lbl_critical_alerts.config(text=str(metrics.critical_alerts))
        self.lbl_total_alerts.config(text=str(metrics.total_alerts))

        # 2. Actualizar Tabla de Vehículos
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

        # 3. Actualizar Registro de Alertas
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

    # Métodos de Simulación / Mocks interactivos
    def _mock_normal_telemetry(self) -> None:
        """Inyecta una medición normal para AUTO-001 o CAMION-002."""
        vid = random.choice(["AUTO-001", "CAMION-002", "VAN-003"])
        payload = TelemetryPayload.create(
            vehicle_id=vid,
            lat=-32.8895 + random.uniform(-0.01, 0.01),
            lon=-68.8458 + random.uniform(-0.01, 0.01),
            speed_kmh=round(random.uniform(30.0, 85.0), 1),
            rpm=random.randint(1800, 2600),
            fuel_level_pct=round(random.uniform(50.0, 95.0), 1),
            engine_temp_c=round(random.uniform(82.0, 91.0), 1),
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
