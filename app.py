from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv
import hmac
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
from werkzeug.exceptions import HTTPException
import threading

# --------------------
# Load environment variables
# --------------------
load_dotenv()

app = Flask(__name__)

# --------------------
# Logging configuration
# --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not app.debug:
    file_handler = RotatingFileHandler(
        'webhook.log',
        maxBytes=10240,
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Webhook receiver startup')

# --------------------
# MongoDB connection
# --------------------
mongo_uri = os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv('DATABASE_NAME')]
collection = db[os.getenv('COLLECTION_NAME')]

# --------------------
# Webhook secret
# --------------------
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET')

# --------------------
# Helper functions
# --------------------
def verify_signature(payload_body, signature_header):
    if not WEBHOOK_SECRET:
        return True

    expected_signature = 'sha256=' + hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature_header)


def extract_commit_hash(payload):
    try:
        if payload.get('head_commit'):
            return payload['head_commit']['id']
        if payload.get('pull_request'):
            return payload['pull_request']['head']['sha']
        if payload.get('commits'):
            return payload['commits'][0]['id']
    except:
        pass
    return None


def extract_github_data(payload, event_type):
    try:
        author = payload.get('sender', {}).get('login', 'Unknown')
        timestamp = datetime.utcnow().isoformat() + 'Z'

        data = {
            'author': author,
            'timestamp': timestamp,
            'action': event_type.upper(),
            'request_id': extract_commit_hash(payload),
            'from_branch': None,
            'to_branch': None
        }

        if event_type == 'push':
            ref = payload.get('ref', '')
            if ref.startswith('refs/heads/'):
                data['to_branch'] = ref.replace('refs/heads/', '')
                data['action'] = 'PUSH'

        elif event_type == 'pull_request':
            pr = payload.get('pull_request', {})
            action = payload.get('action')

            data['from_branch'] = pr.get('head', {}).get('ref')
            data['to_branch'] = pr.get('base', {}).get('ref')

            if action == 'opened':
                data['action'] = 'PULL_REQUEST'
            elif action == 'closed' and pr.get('merged'):
                data['action'] = 'MERGE'
            else:
                return None

        return data
    except Exception as e:
        app.logger.error(f'Error extracting data: {str(e)}')
        return None


def validate_event_data(event_data):
    """Validate event data before storing"""
    required_fields = ['author', 'timestamp', 'action', 'request_id']

    for field in required_fields:
        if field not in event_data or not event_data[field]:
            raise ValueError(f"Missing required field: {field}")

    valid_actions = ['PUSH', 'PULL_REQUEST', 'MERGE']
    if event_data['action'] not in valid_actions:
        raise ValueError(f"Invalid action: {event_data['action']}")

    try:
        datetime.fromisoformat(event_data['timestamp'].replace('Z', '+00:00'))
    except ValueError:
        raise ValueError(f"Invalid timestamp format: {event_data['timestamp']}")

    return True


def backup_events_to_file():
    """Backup events to JSON file (daily)"""
    try:
        events = list(collection.find({}, {'_id': 0}))
        if not events:
            return

        backup_dir = 'backups'
        os.makedirs(backup_dir, exist_ok=True)

        backup_file = os.path.join(
            backup_dir,
            f"events_backup_{datetime.utcnow().strftime('%Y%m%d')}.json"
        )

        with open(backup_file, 'w') as f:
            json.dump(events, f, indent=2, default=str)

        app.logger.info(f"Backup created: {backup_file} ({len(events)} events)")

        # Keep only last 7 backups
        backups = sorted(os.listdir(backup_dir))
        for old in backups[:-7]:
            os.remove(os.path.join(backup_dir, old))

    except Exception as e:
        app.logger.error(f"Backup failed: {str(e)}")


def format_event_message(event):
    try:
        dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        time = dt.strftime("%d %B %Y - %I:%M %p UTC")

        if event['action'] == 'PUSH':
            return f"{event['author']} pushed to {event['to_branch']} on {time}"
        if event['action'] == 'PULL_REQUEST':
            return f"{event['author']} submitted a pull request from {event['from_branch']} to {event['to_branch']} on {time}"
        if event['action'] == 'MERGE':
            return f"{event['author']} merged branch {event['from_branch']} to {event['to_branch']} on {time}"
        return f"{event['author']} performed {event['action']} on {time}"
    except:
        return str(event)

# --------------------
# Routes
# --------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/webhook', methods=['POST'])
def github_webhook():
    try:
        app.logger.info("Incoming webhook request")

        signature = request.headers.get('X-Hub-Signature-256')
        if not signature:
            return jsonify({'error': 'Missing signature'}), 400

        payload_body = request.get_data()
        if not verify_signature(payload_body, signature):
            return jsonify({'error': 'Invalid signature'}), 401

        event_type = request.headers.get('X-GitHub-Event')
        if event_type not in ['push', 'pull_request']:
            return jsonify({'message': 'Event not supported'}), 200

        payload = request.json
        github_data = extract_github_data(payload, event_type)

        if not github_data:
            return jsonify({'message': 'No valid action'}), 200

        # ✅ Validate
        validate_event_data(github_data)

        # ✅ Store
        result = collection.insert_one(github_data)
        app.logger.info(format_event_message(github_data))

        # ✅ Backup async
        threading.Thread(
            target=backup_events_to_file,
            daemon=True
        ).start()

        return jsonify({
            'message': 'Event processed successfully',
            'event_id': str(result.inserted_id),
            'action': github_data['action']
        }), 200

    except ValueError as e:
        app.logger.error(f"Validation error: {str(e)}")
        return jsonify({'error': str(e)}), 400

    except Exception as e:
        app.logger.error(f'Webhook error: {str(e)}', exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/events', methods=['GET'])
def get_events():
    events = list(collection.find({}, {'_id': 0}).sort('timestamp', -1).limit(50))
    return jsonify(events)


@app.route('/api/events/latest', methods=['GET'])
def get_latest_events():
    events = list(collection.find({}, {'_id': 0}).sort('timestamp', -1).limit(10))
    return jsonify([
        {
            'message': format_event_message(e),
            'action': e['action'],
            'timestamp': e['timestamp']
        } for e in events
    ])


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    }), 200

# --------------------
# Error handlers
# --------------------
@app.errorhandler(HTTPException)
def handle_http_exception(e):
    return jsonify({
        'error': e.name,
        'message': e.description,
        'status_code': e.code
    }), e.code


@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(str(e), exc_info=True)
    return jsonify({
        'error': 'Internal Server Error',
        'message': 'Unexpected error occurred'
    }), 500

# --------------------
# Run app
# --------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
