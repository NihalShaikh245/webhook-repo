from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from datetime import datetime
import os
import hmac
import hashlib
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# MongoDB
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]
collection = db[os.getenv("COLLECTION_NAME")]

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")


def verify_signature(payload, signature):
    if not WEBHOOK_SECRET:
        return True

    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def format_message(event):
    dt = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    time = dt.strftime("%d %B %Y - %I:%M %p UTC")

    if event["action"] == "PUSH":
        return f'{event["author"]} pushed to {event["to_branch"]} on {time}'
    if event["action"] == "PULL_REQUEST":
        return f'{event["author"]} submitted a pull request from {event["from_branch"]} to {event["to_branch"]} on {time}'
    if event["action"] == "MERGE":
        return f'{event["author"]} merged branch {event["from_branch"]} to {event["to_branch"]} on {time}'


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Hub-Signature-256")
    if WEBHOOK_SECRET and not signature:
        return jsonify({"error": "Missing signature"}), 400

    if not verify_signature(request.get_data(), signature):
        return jsonify({"error": "Invalid signature"}), 401

    event_type = request.headers.get("X-GitHub-Event")
    payload = request.json

    author = payload.get("sender", {}).get("login", "Unknown")
    timestamp = datetime.utcnow().isoformat() + "Z"

    if event_type == "push":
        branch = payload["ref"].replace("refs/heads/", "")
        event = {
            "request_id": payload["head_commit"]["id"],
            "author": author,
            "action": "PUSH",
            "from_branch": branch,
            "to_branch": branch,
            "timestamp": timestamp
        }

    elif event_type == "pull_request":
        pr = payload["pull_request"]
        action = payload["action"]

        if action == "opened":
            action_type = "PULL_REQUEST"
        elif action == "closed" and pr["merged"]:
            action_type = "MERGE"
        else:
            return jsonify({"message": "Ignored"}), 200

        event = {
            "request_id": pr["id"],
            "author": author,
            "action": action_type,
            "from_branch": pr["head"]["ref"],
            "to_branch": pr["base"]["ref"],
            "timestamp": timestamp
        }

    else:
        return jsonify({"message": "Event not supported"}), 200

    collection.insert_one(event)
    return jsonify({"message": "Stored successfully"}), 200


@app.route("/api/events/latest")
def latest_events():
    events = list(collection.find({}, {"_id": 0}).sort("timestamp", -1).limit(10))
    return jsonify([
        {"message": format_message(e)} for e in events
    ])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
