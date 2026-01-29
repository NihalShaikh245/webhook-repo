import requests
import json
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import logging

class SystemMonitor:
    def __init__(self, webhook_url, mongodb_uri, alert_email=None):
        self.webhook_url = webhook_url
        self.mongodb_uri = mongodb_uri
        self.alert_email = alert_email
        self.logger = logging.getLogger(__name__)
    
    def check_webhook_endpoint(self):
        """Check if webhook endpoint is responsive"""
        try:
            response = requests.get(self.webhook_url, timeout=10)
            health_response = requests.get(f"{self.webhook_url.rstrip('/')}/health", timeout=10)
            
            return {
                'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                'webhook_status': response.status_code,
                'health_status': health_response.status_code if health_response.status_code == 200 else 'unhealthy',
                'response_time': response.elapsed.total_seconds()
            }
        except Exception as e:
            self.logger.error(f"Webhook endpoint check failed: {str(e)}")
            return {'status': 'down', 'error': str(e)}
    
    def check_database_connection(self):
        """Check MongoDB connection"""
        try:
            from pymongo import MongoClient
            client = MongoClient(self.mongodb_uri, serverSelectionTimeoutMS=5000)
            client.server_info()  # Will raise exception if can't connect
            return {'status': 'connected', 'databases': client.list_database_names()[:5]}
        except Exception as e:
            self.logger.error(f"Database connection check failed: {str(e)}")
            return {'status': 'disconnected', 'error': str(e)}
    
    def check_recent_activity(self):
        """Check for recent activity in the system"""
        try:
            from pymongo import MongoClient
            client = MongoClient(self.mongodb_uri)
            db = client.get_database()
            collection = db.events
            
            # Count events in last hour
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            recent_count = collection.count_documents({
                'timestamp': {'$gte': one_hour_ago.isoformat() + 'Z'}
            })
            
            # Get latest event
            latest = collection.find_one(
                {},
                sort=[('timestamp', -1)]
            )
            
            return {
                'recent_events_count': recent_count,
                'latest_event': latest['timestamp'] if latest else None,
                'total_events': collection.count_documents({})
            }
        except Exception as e:
            self.logger.error(f"Activity check failed: {str(e)}")
            return {'status': 'error', 'error': str(e)}
    
    def send_alert(self, subject, message):
        """Send alert email"""
        if not self.alert_email:
            return
        
        try:
            msg = MIMEText(message)
            msg['Subject'] = subject
            msg['From'] = 'monitor@github-webhook.com'
            msg['To'] = self.alert_email
            
            # Configure your SMTP server here
            # For Gmail: smtp.gmail.com
            # For SendGrid: smtp.sendgrid.net
            with smtplib.SMTP('localhost') as server:
                server.send_message(msg)
            
            self.logger.info(f"Alert sent: {subject}")
        except Exception as e:
            self.logger.error(f"Failed to send alert: {str(e)}")
    
    def run_health_check(self):
        """Run comprehensive health check"""
        checks = {
            'webhook_endpoint': self.check_webhook_endpoint(),
            'database': self.check_database_connection(),
            'recent_activity': self.check_recent_activity(),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Check if any component is unhealthy
        if (checks['webhook_endpoint']['status'] != 'healthy' or 
            checks['database']['status'] != 'connected'):
            
            alert_msg = f"""
            System Health Alert!
            
            Webhook Endpoint: {checks['webhook_endpoint']['status']}
            Database: {checks['database']['status']}
            
            Details:
            {json.dumps(checks, indent=2)}
            """
            
            self.send_alert('GitHub Webhook System Alert', alert_msg)
            self.logger.warning("System health check failed, alert sent")
        
        return checks

# Add to app.py for periodic health checks
def start_monitoring():
    """Start monitoring service"""
    import threading
    import time
    
    def monitor_loop():
        monitor = SystemMonitor(
            webhook_url="https://your-webhook-url.com",
            mongodb_uri=os.getenv('MONGODB_URI'),
            alert_email=os.getenv('ALERT_EMAIL')
        )
        
        while True:
            try:
                health_status = monitor.run_health_check()
                app.logger.info(f"Health check: {health_status}")
            except Exception as e:
                app.logger.error(f"Monitoring error: {str(e)}")
            
            # Run every 5 minutes
            time.sleep(300)
    
    # Start monitoring in background thread
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()