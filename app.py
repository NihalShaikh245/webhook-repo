from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv
import hmac
import hashlib
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)

# MongoDB connection
mongo_uri = os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv('DATABASE_NAME')]
collection = db[os.getenv('COLLECTION_NAME')]

# Webhook secret
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET')

def verify_signature(payload_body, signature_header):
    """Verify GitHub webhook signature"""
    if not WEBHOOK_SECRET:
        return True  # Skip verification if no secret set
    
    # Create HMAC hex digest
    expected_signature = 'sha256=' + hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature_header)

def extract_commit_hash(payload):
    """Extract commit hash from payload"""
    try:
        if 'head_commit' in payload and payload['head_commit']:
            return payload['head_commit']['id']
        elif 'pull_request' in payload and payload['pull_request']:
            return payload['pull_request']['head']['sha']
        elif 'commits' in payload and payload['commits']:
            return payload['commits'][0]['id']
    except:
        pass
    return None

def extract_github_data(payload, event_type):
    """Extract and format data from GitHub webhook payload"""
    try:
        # Extract basic information
        author = payload.get('sender', {}).get('login', 'Unknown')
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        # Initialize with default values
        data = {
            'author': author,
            'timestamp': timestamp,
            'action': event_type.upper(),
            'request_id': extract_commit_hash(payload),
            'from_branch': None,
            'to_branch': None
        }
        
        # Handle different event types
        if event_type == 'push':
            # Extract branch name from ref (refs/heads/branch_name)
            ref = payload.get('ref', '')
            if ref.startswith('refs/heads/'):
                data['to_branch'] = ref.replace('refs/heads/', '')
                
        elif event_type == 'pull_request':
            pr_data = payload.get('pull_request', {})
            action = payload.get('action', '')
            
            # Only process when PR is opened or closed
            if action in ['opened', 'closed']:
                data['from_branch'] = pr_data.get('head', {}).get('ref')
                data['to_branch'] = pr_data.get('base', {}).get('ref')
                
                # Determine if it's a merge
                if action == 'closed' and pr_data.get('merged'):
                    data['action'] = 'MERGE'
                else:
                    data['action'] = 'PULL_REQUEST'
                    
        return data
    except Exception as e:
        print(f"Error extracting data: {e}")
        return None

@app.route('/')
def index():
    """Render the UI dashboard"""
    return render_template('index.html')

@app.route('/webhook', methods=['POST'])
def github_webhook():
    """Handle GitHub webhook events"""
    try:
        # Get GitHub signature
        signature = request.headers.get('X-Hub-Signature-256')
        
        # Get raw payload for verification
        payload_body = request.get_data()
        
        # Verify signature
        if not verify_signature(payload_body, signature):
            return jsonify({'error': 'Invalid signature'}), 401
        
        # Get event type
        event_type = request.headers.get('X-GitHub-Event')
        
        if event_type not in ['push', 'pull_request']:
            return jsonify({'message': 'Event not supported'}), 200
        
        # Parse JSON payload
        payload = request.json
        
        # Extract and format data
        github_data = extract_github_data(payload, event_type)
        
        if github_data and github_data['action'] in ['PUSH', 'PULL_REQUEST', 'MERGE']:
            # Insert into MongoDB
            result = collection.insert_one(github_data)
            print(f"Inserted document with id: {result.inserted_id}")
            
            return jsonify({'message': 'Event processed successfully'}), 200
        else:
            return jsonify({'message': 'No valid action to process'}), 200
            
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/events', methods=['GET'])
def get_events():
    """API endpoint to fetch events for UI"""
    try:
        # Get latest events (most recent first)
        events = list(collection.find(
            {},
            {'_id': 0}  # Exclude MongoDB _id field
        ).sort('timestamp', -1).limit(50))
        
        # Format timestamp for display
        for event in events:
            if 'timestamp' in event:
                try:
                    dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                    event['formatted_timestamp'] = dt.strftime("%d %B %Y - %I:%M %p UTC")
                except:
                    event['formatted_timestamp'] = event['timestamp']
        
        return jsonify(events)
    except Exception as e:
        print(f"Error fetching events: {e}")
        return jsonify({'error': 'Failed to fetch events'}), 500

@app.route('/api/events/latest', methods=['GET'])
def get_latest_events():
    """Get only the latest events (for polling)"""
    try:
        events = list(collection.find(
            {},
            {'_id': 0}
        ).sort('timestamp', -1).limit(10))
        
        # Format for UI display
        formatted_events = []
        for event in events:
            try:
                dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                formatted_time = dt.strftime("%d %B %Y - %I:%M %p UTC")
                
                # Create display message based on action type
                if event['action'] == 'PUSH':
                    message = f"{event['author']} pushed to {event['to_branch']} on {formatted_time}"
                elif event['action'] == 'PULL_REQUEST':
                    message = f"{event['author']} submitted a pull request from {event['from_branch']} to {event['to_branch']} on {formatted_time}"
                elif event['action'] == 'MERGE':
                    message = f"{event['author']} merged branch {event['from_branch']} to {event['to_branch']} on {formatted_time}"
                else:
                    message = f"{event['author']} performed {event['action']} on {formatted_time}"
                
                formatted_events.append({
                    'message': message,
                    'action': event['action'],
                    'timestamp': event['timestamp']
                })
            except:
                continue
        
        return jsonify(formatted_events)
    except Exception as e:
        print(f"Error fetching latest events: {e}")
        return jsonify({'error': 'Failed to fetch events'}), 500

# Add this at the very end of app.py (before if __name__ == '__main__')
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)