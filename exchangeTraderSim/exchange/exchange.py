import requests
import time
import random
import os
from prometheus_client import start_http_server, Counter

# --- METRICS ---
# We tellen wat de Exchange VERZENDT. Als dit meer is dan wat de Trader ONTVANGT, heb je een lek.
ORDERS_ATTEMPTED = Counter('exchange_orders_attempted_total', 'Totaal aantal verzendpogingen')
ORDERS_TIMEOUT = Counter('exchange_orders_timeout_total', 'Aantal verzoeken dat bleef hangen')

TRADER_URL = os.getenv("TRADER_URL", "http://trader:8080/trade")

if __name__ == '__main__':
    # Start metrics server op poort 8001 (zodat hij niet botst met de Trader)
    start_http_server(8001)
    print("Exchange gestart op 10Hz. Verbinding maken met Trader...")

    try:
        while True:
            payload = {"price": random.uniform(100, 200), "sent_at": time.time()}
            ORDERS_ATTEMPTED.inc()
            
            try:
                # We zetten de timeout op 0.5s. Sneller falen = sneller in je dashboard.
                response = requests.post(TRADER_URL, json=payload, timeout=0.5)
                
                if response.status_code == 200:
                    pass # Alles ok
                else:
                    print(f"Trader Error: {response.status_code}")

            except requests.exceptions.Timeout:
                # DIT is wat er gebeurt bij kill -STOP!
                ORDERS_TIMEOUT.inc()
                print("TIMEOUT: Trader reageert niet!")
            except requests.exceptions.ConnectionError:
                print("FOUT: Verbinding geweigerd.")
            
            # We verlagen de sleep naar 0.1 (10 trades per seconde)
            # Hierdoor vullen we de TCP buffers sneller en zie je retransmits eerder.
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nExchange gestopt.")
