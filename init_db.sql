-- Script de inicialización de la base de datos para Telemetría de Flota
-- Base de datos: telemetria

-- 1. Tabla de Vehículos
CREATE TABLE IF NOT EXISTS vehicles (
    id VARCHAR(50) PRIMARY KEY,
    model VARCHAR(100),
    type VARCHAR(50),
    status VARCHAR(50) DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabla de Mediciones de Telemetría (Series de tiempo de la flota)
CREATE TABLE IF NOT EXISTS telemetry (
    id BIGSERIAL PRIMARY KEY,
    vehicle_id VARCHAR(50) NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    latitude NUMERIC(10, 6) CHECK (latitude BETWEEN -90.0 AND 90.0),
    longitude NUMERIC(10, 6) CHECK (longitude BETWEEN -180.0 AND 180.0),
    speed_kmh NUMERIC(6, 2) CHECK (speed_kmh >= 0.0),
    rpm INTEGER CHECK (rpm >= 0),
    fuel_level_pct NUMERIC(5, 2) CHECK (fuel_level_pct BETWEEN 0.0 AND 100.0),
    engine_temp_c NUMERIC(5, 2),
    status VARCHAR(50) DEFAULT 'MOVING',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índices para optimizar consultas temporales por vehículo
CREATE INDEX IF NOT EXISTS idx_telemetry_vehicle_timestamp ON telemetry(vehicle_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry(timestamp DESC);

-- 3. Tabla de Alertas Críticas de Flota (Excesos de velocidad, temperatura, etc.)
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    vehicle_id VARCHAR(50) NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'WARNING' CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    description TEXT NOT NULL,
    metric_value NUMERIC(10, 2),
    threshold_value NUMERIC(10, 2),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índices para alertas
CREATE INDEX IF NOT EXISTS idx_alerts_vehicle_timestamp ON alerts(vehicle_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);

-- 4. Vehículos iniciales de prueba (para pruebas con agent.py de Ale)
INSERT INTO vehicles (id, model, type, status) VALUES
    ('AUTO-001', 'Sedan Corp', 'CAR', 'ACTIVE'),
    ('CAMION-002', 'Heavy Duty 500', 'TRUCK', 'ACTIVE'),
    ('PRUEBA-01', 'Van Delivery', 'VAN', 'ACTIVE')
ON CONFLICT (id) DO NOTHING;
