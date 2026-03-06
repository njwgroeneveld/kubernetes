# Gebruik een lichte Python versie
FROM python:3.11-slim

# Zet de werkmap in de container
WORKDIR /app

# Kopieer de benodigde bestanden
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Start het script 
CMD ["python", "exchange.py"]

