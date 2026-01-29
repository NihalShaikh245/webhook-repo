from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

@app.route("/webhook", methods=["POST"])
def webhook():
    return jsonify({"message": "Webhook received"}), 200

if __name__ == "__main__":
    app.run()
