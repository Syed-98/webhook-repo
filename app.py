from flask import Flask, request, jsonify
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
app = Flask(__name__)

# MongoDB Setup with error handling
try:
    client = MongoClient(os.getenv("MONGO_URI", ""), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')  # Test connection
    db = client[os.getenv("DB_NAME", "github_events")]
    collection = db["webhooks"]
    logger.info("✅ MongoDB connected successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    raise

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400

        payload = request.json
        event_type = request.headers.get('X-GitHub-Event')
        logger.info(f"Received {event_type} event")

        # Validate payload structure
        if not payload.get('sender') or not payload['sender'].get('login'):
            return jsonify({"error": "Invalid payload: missing sender info"}), 400

        # Common fields
        author = payload['sender']['login']
        timestamp = datetime.utcnow().isoformat() + 'Z'

        # Event processing
        data = None
        if event_type == 'push':
            if not payload.get('ref') or not payload.get('head_commit'):
                return jsonify({"error": "Invalid push payload"}), 400
            
            data = {
                'author': author,
                'action': 'PUSH',
                'to_branch': payload['ref'].split('/')[-1],
                'from_branch': None,
                'timestamp': timestamp,
                'request_id': payload['head_commit']['id']
            }

        elif event_type == 'pull_request':
            pr_payload = payload.get('pull_request', {})
            if not pr_payload.get('head') or not pr_payload.get('base'):
                return jsonify({"error": "Invalid PR payload"}), 400
            
            data = {
                'author': author,
                'action': 'PULL_REQUEST',
                'from_branch': pr_payload['head']['ref'],
                'to_branch': pr_payload['base']['ref'],
                'timestamp': timestamp,
                'request_id': str(pr_payload['number'])
            }

        elif event_type == 'pull_request' and payload.get('action') == 'closed':
            if payload.get('pull_request', {}).get('merged'):
                pr_payload = payload['pull_request']
                data = {
                    'author': author,
                    'action': 'MERGE',
                    'from_branch': pr_payload['head']['ref'],
                    'to_branch': pr_payload['base']['ref'],
                    'timestamp': timestamp,
                    'request_id': str(pr_payload['number'])
                }

        if not data:
            return jsonify({"status": "ignored"}), 200

        # Insert into MongoDB
        collection.insert_one(data)
        logger.info(f"Inserted data: {data}")
        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"Webhook processing failed: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)