import requests
import time
import random
import os

TRADER_URL = os.getenv("TRADER_URL", "http://127.0.0.1:8080/trade")

print("Exchange gestart. Verbinding maken met Trader...")

try:
    while True:
        payload = {
            "price": random.uniform(100, 200),
            "sent_at": time.time()  # De timestamp van verzenden
        }
        
        try:
            response = requests.post(TRADER_URL, json=payload, timeout=1)
            if response.status_code == 200:
                res_data = response.json()
                print(f"Order verzonden. Trader bevestigde latency: {res_data['latency_ms']:.4f} ms")
            else:
                print(f"Foutmelding van Trader: {response.status_code}")
        except requests.exceptions.ConnectionError:
            print("FOUT: Kan Trader niet bereiken. Staat trader.py wel aan?")
        
        # Wacht 1 seconde voor de volgende koers
        time.sleep(1)

except KeyboardInterrupt:
    print("\nExchange gestopt.")
