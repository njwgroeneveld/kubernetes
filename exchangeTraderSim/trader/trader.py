import threading
import time
import socket
import json
import requests
import os
import random
import gc
import sys
from flask import Flask, request, jsonify
from prometheus_client import start_http_server, Counter, Gauge, Histogram

# --- CONFIGURATIE ---
TRADER_ID = os.getenv("HOSTNAME", "local-trader")
EXCHANGE_TCP_URL = os.getenv("EXCHANGE_URL", "http://exchange-service:8080/order")
UDP_PORT = int(os.getenv("UDP_PORT", 9999))

# --- PROMETHEUS METRICS ---
UDP_PRICES_RECEIVED = Counter('trader_udp_prices_total', 'Totaal ontvangen UDP koersen', ['trader_id'])
TCP_ORDERS_SENT = Counter('trader_tcp_orders_total', 'Totaal verzonden orders', ['trader_id'])
TCP_ORDER_FAILURES = Counter('trader_tcp_order_failures_total', 'Aantal gefaalde TCP verzoeken', ['trader_id'])
MARKET_DATA_STALE = Gauge('trader_market_data_stale', 'Status van koersinformatie (0=OK, 1=STALE)', ['trader_id'])
UDP_DROPPED = Counter('trader_udp_dropped_total', 'Totaal gesimuleerde UDP drops', ['trader_id'])
TCP_DROPPED = Counter('trader_tcp_dropped_total', 'Totaal gesimuleerde TCP drops', ['trader_id'])

# Chaos Metrics
LATENCY_METRIC = Histogram('trader_receive_latency_seconds', 'Netwerk latency koers ontvangst', buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5])
ERROR_CHANCE_GAUGE = Gauge('trader_simulated_error_chance', 'Huidige ingestelde foutkans', ['trader_id'])
UDP_LOSS_GAUGE = Gauge('trader_simulated_udp_loss', 'Huidige ingestelde UDP packet loss kans', ['trader_id'])
TCP_LOSS_GAUGE = Gauge('trader_simulated_tcp_loss', 'Huidige ingestelde TCP packet loss kans', ['trader_id'])
PRICE_AGE = Gauge('trader_price_age_ms', 'Leeftijd van laatste prijs in ms', ['trader_id'])


# --- GLOBALE STATE ---
last_price_time = 0
current_market_price = 0
memory_stresser = []

# Chaos configuratie
error_config = {"probability": 0.0, "end_time": 0}
udp_loss_config = {"probability": 0.0}
tcp_loss_config = {"probability": 0.0}

app = Flask(__name__)

# --- 1. CHAOS API ENDPOINTS ---

@app.route('/simulate/error', methods=['GET'])
def set_error_simulation():
    try:
        chance = float(request.args.get('chance', 0.1))
        duration_min = int(request.args.get('minutes', 10))
        error_config["probability"] = chance
        error_config["end_time"] = time.time() + (duration_min * 60)
        ERROR_CHANCE_GAUGE.labels(trader_id=TRADER_ID).set(chance)
        print(f"\n!!! CHAOS MODE GEACTIVEERD: Kans op error = {chance} voor {duration_min} min !!!\n", flush=True)
        return jsonify({"status": "Chaos initiated", "trader": TRADER_ID, "chance": chance})
    except:
        return jsonify({"error": "Invalid input"}), 400

# --- UDP PACKET LOSS CHAOS ---

@app.route('/chaos/udp_loss', methods=['GET'])
def set_udp_loss():
    try:
        chance = float(request.args.get('chance', 0.0))
        if not 0.0 <= chance <= 1.0:
            return jsonify({"error": "chance moet tussen 0.0 en 1.0 zijn"}), 400
        udp_loss_config["probability"] = chance
        UDP_LOSS_GAUGE.labels(trader_id=TRADER_ID).set(chance)
        print(f"\n!!! UDP LOSS CHAOS: {chance*100:.1f}% packet loss geactiveerd !!!\n", flush=True)
        return jsonify({
            "status": "UDP loss set",
            "trader": TRADER_ID,
            "probability": chance,
            "description": f"{chance*100:.1f}% van UDP prijsupdates wordt genegeerd"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/chaos/udp_loss/clear', methods=['GET'])
def clear_udp_loss():
    udp_loss_config["probability"] = 0.0
    UDP_LOSS_GAUGE.labels(trader_id=TRADER_ID).set(0.0)
    print(f"--- UDP LOSS CHAOS GESTOPT ---", flush=True)
    return jsonify({"status": "UDP loss cleared", "trader": TRADER_ID})

# --- TCP PACKET LOSS CHAOS ---

@app.route('/chaos/tcp_loss', methods=['GET'])
def set_tcp_loss():
    try:
        chance = float(request.args.get('chance', 0.0))
        if not 0.0 <= chance <= 1.0:
            return jsonify({"error": "chance moet tussen 0.0 en 1.0 zijn"}), 400
        tcp_loss_config["probability"] = chance
        TCP_LOSS_GAUGE.labels(trader_id=TRADER_ID).set(chance)
        print(f"\n!!! TCP LOSS CHAOS: {chance*100:.1f}% order loss geactiveerd !!!\n", flush=True)
        return jsonify({
            "status": "TCP loss set",
            "trader": TRADER_ID,
            "probability": chance,
            "description": f"{chance*100:.1f}% van TCP orders wordt geblokkeerd"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/chaos/tcp_loss/clear', methods=['GET'])
def clear_tcp_loss():
    tcp_loss_config["probability"] = 0.0
    TCP_LOSS_GAUGE.labels(trader_id=TRADER_ID).set(0.0)
    print(f"--- TCP LOSS CHAOS GESTOPT ---", flush=True)
    return jsonify({"status": "TCP loss cleared", "trader": TRADER_ID})

# --- STATUS ENDPOINT ---

@app.route('/chaos/status', methods=['GET'])
def chaos_status():
    return jsonify({
        "trader": TRADER_ID,
        "chaos": {
            "udp_loss": {
                "active": udp_loss_config["probability"] > 0,
                "probability": udp_loss_config["probability"],
                "percent": f"{udp_loss_config['probability']*100:.1f}%"
            },
            "tcp_loss": {
                "active": tcp_loss_config["probability"] > 0,
                "probability": tcp_loss_config["probability"],
                "percent": f"{tcp_loss_config['probability']*100:.1f}%"
            },
            "error_simulation": {
                "active": time.time() < error_config["end_time"],
                "probability": error_config["probability"],
                "remaining_seconds": max(0, error_config["end_time"] - time.time())
            }
        },
        "market": {
            "current_price": current_market_price,
            "last_price_age_ms": round((time.time() - last_price_time) * 1000, 1),
            "stale": (time.time() - last_price_time) > 2.0
        }
    })

# --- MEMORY EN CPU STRESS ---

@app.route('/stress/memory', methods=['GET'])
def stress_memory():
    mb = int(request.args.get('mb', 10))
    print(f"--- STRESS TEST: Geheugen verhogen met {mb}MB ---", flush=True)
    dummy_data = 'x' * (mb * 1024 * 1024)
    memory_stresser.append(dummy_data)
    return jsonify({"status": "Memory increased", "trader": TRADER_ID})

@app.route('/stress/memory/clear', methods=['GET'])
def clear_memory():
    global memory_stresser
    memory_stresser = []
    gc.collect()
    print("--- STRESS TEST: Geheugen vrijgegeven ---", flush=True)
    return jsonify({"status": "Memory cleared"})

@app.route('/stress/cpu', methods=['GET'])
def stress_cpu():
    duration = int(request.args.get('seconds', 5))
    print(f"--- STRESS TEST: CPU belasten voor {duration}s ---", flush=True)
    end_time = time.time() + min(duration, 60)
    while time.time() < end_time:
        _ = 100 * 100
    return jsonify({"status": "CPU stress completed"})

# --- 2. UDP LISTENER THREAD ---

def udp_listener():
    global last_price_time, current_market_price
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', UDP_PORT))
    print(f"[*] Luisteren naar UDP koersen op poort {UDP_PORT}...", flush=True)
    while True:
        try:
            data, addr = sock.recvfrom(1024)

            # --- CHAOS: UDP packet loss simulatie ---
            if udp_loss_config["probability"] > 0:
                if random.random() < udp_loss_config["probability"]:
                    UDP_DROPPED.labels(trader_id=TRADER_ID).inc()
                    continue  # packet weggooien zonder te verwerken

            msg = json.loads(data.decode())
            latency = time.time() - msg.get('timestamp', time.time())
            LATENCY_METRIC.observe(latency)
            current_market_price = msg['price']
            last_price_time = time.time()
            UDP_PRICES_RECEIVED.labels(trader_id=TRADER_ID).inc()
            MARKET_DATA_STALE.labels(trader_id=TRADER_ID).set(0)
        except Exception as e:
            print(f"[UDP ERROR] {e}", flush=True)

# --- 3. TRADING LOGIC THREAD ---

def trading_loop():
    print(f"[*] Trading loop gestart voor {TRADER_ID}", flush=True)
    while True:

        age_ms = (time.time() - last_price_time) * 1000
        PRICE_AGE.labels(trader_id=TRADER_ID).set(age_ms)
        # 1. Hebben we wel verse data?
        if time.time() - last_price_time > 2.0:
            MARKET_DATA_STALE.labels(trader_id=TRADER_ID).set(1)
            time.sleep(0.5)
            continue

        MARKET_DATA_STALE.labels(trader_id=TRADER_ID).set(0)

        # 2. CHAOS CHECK: applicatie error simulatie
        if time.time() < error_config["end_time"]:
            if random.random() < error_config["probability"]:
                TCP_ORDER_FAILURES.labels(trader_id=TRADER_ID).inc()
                print(f"[{time.strftime('%H:%M:%S')}] {TRADER_ID} | CHAOS: Order geblokkeerd (Kans: {error_config['probability']})", flush=True)
                time.sleep(1)
                continue

        # 3. CHAOS CHECK: TCP loss simulatie
        if tcp_loss_config["probability"] > 0:
            if random.random() < tcp_loss_config["probability"]:
                TCP_DROPPED.labels(trader_id=TRADER_ID).inc()
                TCP_ORDER_FAILURES.labels(trader_id=TRADER_ID).inc()
                print(f"[{time.strftime('%H:%M:%S')}] {TRADER_ID} | CHAOS: TCP order gedropped ({tcp_loss_config['probability']*100:.1f}% loss)", flush=True)
                time.sleep(1)
                continue

        # 4. VERSTUREN
        try:
            TCP_ORDERS_SENT.labels(trader_id=TRADER_ID).inc()
            resp = requests.post(EXCHANGE_TCP_URL, json={"trader_id": TRADER_ID, "price": current_market_price}, timeout=0.5)
            if resp.status_code == 201:
                print(f"[{time.strftime('%H:%M:%S')}] {TRADER_ID} | SUCCESS: Order @ {current_market_price}", flush=True)
        except Exception as e:
            TCP_ORDER_FAILURES.labels(trader_id=TRADER_ID).inc()
            print(f"[{time.strftime('%H:%M:%S')}] {TRADER_ID} | NETWERK ERROR: Exchange onbereikbaar", flush=True)

        time.sleep(1)

if __name__ == '__main__':
    start_http_server(9090)

    threading.Thread(target=udp_listener, daemon=True).start()
    threading.Thread(target=trading_loop, daemon=True).start()

    app.run(host='0.0.0.0', port=8080, threaded=True)
