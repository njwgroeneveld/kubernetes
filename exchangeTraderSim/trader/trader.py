from flask import Flask, request, jsonify
from prometheus_client import start_http_server, Histogram # Nieuw
import time

app = Flask(__name__)

# Definieer de metric: we meten latency in seconden
# Buckets zijn de 'bakjes' waarin we de metingen verdelen (bijv. 1ms, 5ms, 10ms, etc.)
LATENCY_METRIC = Histogram(
    'trader_receive_latency_seconds',
    'Tijd tussen verzenden Exchange en ontvangen Trader',
    buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.500]
)

@app.route('/stress', methods=['GET'])
def stress_test():
    # Haal de 'seconds' parameter op uit de URL, standaard is 5 seconden
    # Voorbeeld: /stress?seconds=10
    try:
        duration = int(request.args.get('seconds', 5))
    except ValueError:
        return jsonify({"error": "Ongeldige waarde voor seconds"}), 400

    # Limiet instellen om te voorkomen dat je de pod per ongeluk uren vastzet
    if duration > 60:
        return jsonify({"error": "Duur is te lang, max 60 seconden"}), 400

    end_time = time.time() + duration
    count = 0
    while time.time() < end_time:
        _ = 100 * 100
        count += 1 
        
    return jsonify({
        "status": "CPU stress completed", 
        "duration_seconds": duration,
        "iterations": count
    })

@app.route('/trade', methods=['POST'])
def trade():
    received_at = time.time()
    data = request.json
    sent_at = data.get('sent_at')
    
    if sent_at:
        latency_seconds = received_at - sent_at
        
        # REGISTREER DE METRIC VOOR PROMETHEUS
        LATENCY_METRIC.observe(latency_seconds)
        
        latency_ms = latency_seconds * 1000
        print(f"DEBUG: Ontvangen prijs {data['price']:.2f} | Latency: {latency_ms:.4f} ms")
        return jsonify({"status": "accepted", "latency_ms": latency_ms}), 200
    
    return jsonify({"error": "Geen timestamp gevonden"}), 400

if __name__ == '__main__':
    # Start een aparte server op poort 9090 voor Prometheus om de data op te halen (scrapen)
    start_http_server(9090)
    app.run(host='0.0.0.0', port=8080)
