import threading
import time
import socket
import json
import random
import os
from flask import Flask, request, jsonify
from prometheus_client import start_http_server, Counter, Gauge

# --- METRICS (Hergebruik namen waar mogelijk) ---
# Gauge voor de live koers (Random Walk)
PRICE_GAUGE = Gauge('exchange_market_price', 'Huidige marktprijs')
# We tellen nu wat er BINNENKOMT via TCP
ORDERS_RECEIVED = Counter('exchange_orders_received_total', 'Totaal ontvangen orders via TCP')
# We tellen wat er UITGAAT via UDP
UDP_SENT = Counter('exchange_udp_packets_sent_total', 'Totaal verzonden koers-updates')

app = Flask(__name__)
current_price = 150.00

# --- 1. UDP MARKET DATA (De 'Broadcaster') ---
def market_data_engine():
    global current_price
    # UDP socket setup
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Gebruik de servicenaam van de trader uit je K8s netwerk
    # In K8s kun je vaak naar de service DNS sturen
    TRADER_UDP_HOST = os.getenv("TRADER_SERVICE_HOST", "trader-service")
    TRADER_UDP_PORT = int(os.getenv("TRADER_UDP_PORT", 9999))

    print(f"UDP Stream gestart naar {TRADER_UDP_HOST}:{TRADER_UDP_PORT}")

    while True:
        # Random Walk logica (realistischer dan alleen maar omhoog)
        change = current_price * random.uniform(-0.001, 0.001)
        current_price = round(current_price + change, 2)
        
        PRICE_GAUGE.set(current_price)
        
        payload = {
            "symbol": "AAPL", 
            "price": current_price, 
            "timestamp": time.time()
        }
        
        try:
            udp_sock.sendto(json.dumps(payload).encode(), (TRADER_UDP_HOST, TRADER_UDP_PORT))
            UDP_SENT.inc()
        except:
            pass # Als de trader er nog niet is, geen probleem (dat is UDP)
            
        time.sleep(0.1) # 10Hz frequentie uit je oude code

# --- 2. TCP ORDER GATEWAY (De Flask Server) ---
@app.route('/order', methods=['POST'])
def handle_order():
    ORDERS_RECEIVED.inc()
    # De trader stuurt een JSON met zijn gewenste trade
    data = request.get_json()
    
    # In een echte exchange zou je hier de prijs checken
    print(f"Order ontvangen: {data.get('type')} {data.get('quantity')} stuks @ {current_price}")
    
    return jsonify({
        "status": "filled", 
        "price": current_price,
        "exchange_time": time.time()
    }), 201

if __name__ == '__main__':
    # Start metrics op 8001 (zoals in je oude code)
    start_http_server(8001)
    
    # Start UDP thread op de achtergrond
    threading.Thread(target=market_data_engine, daemon=True).start()
    
    # Start de API op 8080 (waar de trader naar gaat POST-en)
    print("Exchange API luistert op poort 8080...")
    app.run(host='0.0.0.0', port=8080, threaded=True)
