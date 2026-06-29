# face_recognition-ng — InsightFace + FastAPI
# NON usa dlib. NON usa setup.py install.

FROM python:3.10-slim-bullseye

# Dipendenze di sistema per OpenCV e InsightFace
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libglib2.0-0 \
    libgl1-mesa-glx \
    libgomp1 \
    wget \
    curl \
    git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia requirements e installa PRIMA (layer cache)
COPY requirements_ng.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements_ng.txt

# Copia tutto il progetto
COPY . .

# Installa il package face_recognition locale (con backends/)
RUN pip install --no-cache-dir -e .

# Porta default FastAPI
EXPOSE 8000

# Variabili ENV di default (override con -e al run)
ENV FR_API_TOKEN=changeme \
    FR_DB_PATH=/app/data/faces.db \
    FR_OSINT_DB_PATH=/app/data/osint_results.db \
    OSINT_ENABLE_EXTERNAL=true \
    RATE_LIMIT_ENABLED=true

# Crea cartella dati
RUN mkdir -p /app/data

CMD ["python", "api_server.py"]
