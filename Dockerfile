FROM python:3.14-slim

WORKDIR /app

# Instalar dependencias del proyecto
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar codigo fuente
COPY . .

# Comando por defecto para el worker de Celery
CMD ["celery", "-A", "src.celery_app", "worker", "--loglevel=info"]
