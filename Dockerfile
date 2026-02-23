FROM python:3.13-slim

WORKDIR /app

# Závislosti
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kód aplikace
COPY src/ src/
COPY config/keywords.yaml config/keywords.yaml
COPY config/config.cloud.yaml config/config.yaml

# Spuštění scanu s emailem
CMD ["python", "-m", "src.cli", "scan", "--email"]
