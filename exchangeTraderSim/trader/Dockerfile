# Gebruik een lichte Python versie
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# Installeer systeem-tools voor chaos engineering (SRE toolkit)
RUN apt-get update && apt-get install -y \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Zet de werkmap in de container
WORKDIR /app

# Kopieer de benodigde bestanden
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Start het script  
CMD ["python", "trader.py"]



