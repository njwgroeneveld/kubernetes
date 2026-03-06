from flask import Flask, request, jsonify
import time

app = Flask(__name__)

@app.route('/trade', methods=['POST'])
def trade():
    # Pak de huidige tijd zodra het pakketje binnenkomt
    received_at = time.time()
    
    data = request.json
    sent_at = data.get('sent_at')
    
    if sent_at:
        # Bereken latency in milliseconden
        latency = (received_at - sent_at) * 1000
        print(f"DEBUG: Ontvangen prijs {data['price']:.2f} | Latency: {latency:.4f} ms")
        return jsonify({"status": "accepted", "latency_ms": latency}), 200
    
    return jsonify({"error": "Geen timestamp gevonden"}), 400

if __name__ == '__main__':
    # We draaien lokaal op poort 8080
    app.run(host='0.0.0.0', port=8080)

