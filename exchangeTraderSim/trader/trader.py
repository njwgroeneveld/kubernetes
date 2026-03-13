from flask import Flask, request, jsonify
from prometheus_client import start_http_server, Histogram, Counter, Gauge
import time
import random

app = Flask(__name__)

# --- METRICS ---
LATENCY_METRIC = Histogram(
    'trader_receive_latency_seconds',
    'Tijd tussen verzenden Exchange en ontvangen Trader',
    buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.500]
)

# Nieuwe metrics voor SRE simulatie
ERROR_COUNTER = Counter('trader_errors_total', 'Totaal aantal gefaalde trades')
ERROR_CHANCE_GAUGE = Gauge('trader_simulated_error_chance', 'Huidige ingestelde foutkans')

# --- GLOBALE STATE ---
memory_stresser = []
error_config = {
    "probability": 0.0,
    "end_time": 0
}

# --- ROUTES ---

@app.route('/trade', methods=['POST'])
def trade():
    # 1. Check op gesimuleerde fouten
    current_time = time.time()
    if current_time < error_config["end_time"]:
        if random.random() < error_config["probability"]:
            ERROR_COUNTER.inc()
            return jsonify({"error": "Internal Server Error (Simulated Chaos)"}), 500

    # 2. Normale trade logica
    received_at = time.time()
    data = request.json
    sent_at = data.get('sent_at')
    
    if sent_at:
        latency_seconds = received_at - sent_at
        LATENCY_METRIC.observe(latency_seconds)
        latency_ms = latency_seconds * 1000
        return jsonify({"status": "accepted", "latency_ms": latency_ms}), 200
    
    return jsonify({"error": "Geen timestamp gevonden"}), 400

@app.route('/simulate/error', methods=['POST'])
def set_error_simulation():
    """
    Input JSON: {"chance": 0.1, "minutes": 10}
    """
    data = request.json
    chance = data.get('chance', 0.1)
    duration_min = data.get('minutes', 10)
    
    error_config["probability"] = chance
    error_config["end_time"] = time.time() + (duration_min * 60)
    
    ERROR_CHANCE_GAUGE.set(chance)
    
    return jsonify({
        "status": "Chaos initiated",
        "chance": f"{chance*100}%",
        "duration_minutes": duration_min,
        "active_until": time.strftime('%H:%M:%S', time.localtime(error_config["end_time"]))
    })

@app.route('/stress/memory', methods=['GET'])
def stress_memory():
    try:
        megabytes = int(request.args.get('mb', 10))
    except ValueError:
        return jsonify({"error": "Ongeldige waarde voor mb"}), 400

    dummy_data = 'x' * (megabytes * 1024 * 1024)
    memory_stresser.append(dummy_data)
    total_mb = sum(len(i) for i in memory_stresser) / (1024 * 1024)
    
    return jsonify({
        "status": "Memory increased",
        "total_estimated_mb": round(total_mb, 2)
    })

@app.route('/stress/memory/clear', methods=['GET'])
def clear_memory():
    global memory_stresser
    memory_stresser = []
    import gc
    gc.collect()
    return jsonify({"status": "Memory cleared"})

@app.route('/stress', methods=['GET'])
def stress_test():
    try:
        duration = int(request.args.get('seconds', 5))
    except ValueError:
        return jsonify({"error": "Ongeldige waarde voor seconds"}), 400

    if duration > 60:
        return jsonify({"error": "Duur is te lang, max 60 seconden"}), 400

    end_time = time.time() + duration
    while time.time() < end_time:
        _ = 100 * 100
        
    return jsonify({"status": "CPU stress completed"})

if __name__ == '__main__':
    start_http_server(9090)
    # Belangrijk: threaded=True om te zorgen dat de ene route de andere niet blokkeert!
    app.run(host='0.0.0.0', port=8080, threaded=True)
