import threading
import time
import socket
import json
import random
import os
from flask import Flask, request, jsonify
from prometheus_client import start_http_server, Counter, Gauge

# --- METRICS ---
PRICE_GAUGE = Gauge('exchange_market_price', 'Huidige marktprijs')
ORDERS_RECEIVED = Counter('exchange_orders_received_total', 'Totaal ontvangen orders via TCP')
# Gefixed: Naam moet overeenkomen met de variabele in de functie (UDP_SENT)
UDP_SENT = Counter('exchange_udp_packets_sent_total', 'Totaal verzonden koers-updates')

app = Flask(__name__)
current_price = 150.00

# --- 1. UDP MARKET DATA (De 'Broadcaster') ---
def market_data_engine():
    global current_price
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Gebruik 'trader-service' als default (matchend met je k8s service naam)
    TRADER_HOSTNAME = os.getenv("TRADER_SERVICE_HOST", "trader-service")
    UDP_PORT = 9999

    print(f" Market Data Engine gestart. Target: {TRADER_HOSTNAME}")

    while True:
        # Random walk prijs
        change = current_price * random.uniform(-0.001, 0.001)
        current_price = round(current_price + change, 2)
        PRICE_GAUGE.set(current_price)
        
        msg = json.dumps({
            "symbol": "AAPL", 
            "price": current_price, 
            "timestamp": time.time()
        })
        
        try:
            # SRE TRICK: Resolven van de Headless Service naar alle Pod IP's
            targets = socket.getaddrinfo(TRADER_HOSTNAME, UDP_PORT, socket.AF_INET, socket.SOCK_DGRAM)
            ips = list(set([t[4][0] for t in targets])) # Unieke IP's filteren
            
            for ip in ips:
                udp_sock.sendto(msg.encode(), (ip, UDP_PORT))
            
            # Update de metric met het aantal verzonden pakketjes
            UDP_SENT.inc(len(ips))
        except Exception as e:
            # Als DNS even niet bereikbaar is, printen we het voor debug, maar gaan we door
            if random.random() < 0.01: # Niet de hele log volspammen
                print(f"DNS lookup failed voor {TRADER_HOSTNAME}: {e}")
            
        time.sleep(0.1)

# --- 2. TCP ORDER GATEWAY (De Flask Server) ---
@app.route('/order', methods=['POST'])
def handle_order():
    ORDERS_RECEIVED.inc()
    data = request.get_json()
    
    # Log de order voor zichtbaarheid in 'kubectl logs'
    print(f" Order van {data.get('trader_id', 'unknown')}: {data.get('type')} @ {current_price}")
    
    return jsonify({
        "status": "filled", 
        "price": current_price,
        "exchange_time": time.time()
    }), 201

if __name__ == '__main__':
    # Start metrics op 8001
    start_http_server(8001)
    
    # Start UDP thread
    threading.Thread(target=market_data_engine, daemon=True).start()
    
    # Start Flask API
    print("Exchange API luistert op poort 8080...")
    app.run(host='0.0.0.0', port=8080, threaded=True)
