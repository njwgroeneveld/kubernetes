import threading
import time
import socket
import json
import requests
import os
import random
import gc
import sys # Toegevoegd voor directere logging
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

# Chaos Metrics
LATENCY_METRIC = Histogram('trader_receive_latency_seconds', 'Netwerk latency koers ontvangst', buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5])
ERROR_CHANCE_GAUGE = Gauge('trader_simulated_error_chance', 'Huidige ingestelde foutkans', ['trader_id'])

# --- GLOBALE STATE ---
last_price_time = 0
current_market_price = 0
memory_stresser = []
error_config = {"probability": 0.0, "end_time": 0}

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
        # Check Chaos
        if time.time() < error_config["end_time"]:
            if random.random() < error_config["probability"]:
                TCP_ORDER_FAILURES.labels(trader_id=TRADER_ID).inc()
                # Gebruik \r om de logs niet te vervuilen, of gewoon print
                print(f"[{time.strftime('%H:%M:%S')}] {TRADER_ID} | CHAOS TRIGGERED: Order geblokkeerd!", flush=True)
                time.sleep(1)
                continue

        # Check Stale Data
        if time.time() - last_price_time > 1.5:
            MARKET_DATA_STALE.labels(trader_id=TRADER_ID).set(1)
            print(f"[{time.strftime('%H:%M:%S')}] {TRADER_ID} | WAITING: Geen verse koersdata...", flush=True)
            time.sleep(1)
            continue

        # Normale Order (TCP POST)
        try:
            TCP_ORDERS_SENT.labels(trader_id=TRADER_ID).inc()
            resp = requests.post(EXCHANGE_TCP_URL, json={"trader_id": TRADER_ID, "price": current_market_price}, timeout=0.5)
            if resp.status_code == 201:
                print(f"[{time.strftime('%H:%M:%S')}] {TRADER_ID} | SUCCESS: Order verzonden @ {current_market_price}", flush=True)
            else:
                print(f"[{time.strftime('%H:%M:%S')}] {TRADER_ID} | FAILED: Exchange gaf status {resp.status_code}", flush=True)
        except Exception as e:
            TCP_ORDER_FAILURES.labels(trader_id=TRADER_ID).inc()
            print(f"[{time.strftime('%H:%M:%S')}] {TRADER_ID} | ERROR: Kon exchange niet bereiken", flush=True)
        
        time.sleep(1)

if __name__ == '__main__':
    start_http_server(9090)
    
    threading.Thread(target=udp_listener, daemon=True).start()
    threading.Thread(target=trading_loop, daemon=True).start()
    
    # Gebruik threaded=True om Flask de rest niet te laten blokkeren
    app.run(host='0.0.0.0', port=8080, threaded=True)
