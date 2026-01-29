import unittest
import json
from datetime import datetime
from app import app, verify_signature, extract_github_data

class TestWebhookReceiver(unittest.TestCase):
    
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        
    def test_health_endpoint(self):
        """Test health check endpoint"""
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')
    
    def test_webhook_signature_verification(self):
        """Test signature verification"""
        secret = 'test_secret'
        payload = b'{"test": "data"}'
        
        # Test with correct signature
        import hmac
        import hashlib
        signature = 'sha256=' + hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        self.assertTrue(verify_signature(payload, signature))
        
        # Test with incorrect signature
        self.assertFalse(verify_signature(payload, 'sha256=wrong'))
    
    def test_extract_push_data(self):
        """Test data extraction from push event"""
        payload = {
            'ref': 'refs/heads/main',
            'head_commit': {'id': 'abc123'},
            'sender': {'login': 'testuser'},
            'commits': [{'id': 'abc123'}]
        }
        
        data = extract_github_data(payload, 'push')
        
        self.assertEqual(data['action'], 'PUSH')
        self.assertEqual(data['author'], 'testuser')
        self.assertEqual(data['to_branch'], 'main')
        self.assertEqual(data['request_id'], 'abc123')
    
    def test_extract_pull_request_data(self):
        """Test data extraction from pull request event"""
        payload = {
            'action': 'opened',
            'pull_request': {
                'head': {'ref': 'feature-branch'},
                'base': {'ref': 'main'},
                'head': {'sha': 'def456'}
            },
            'sender': {'login': 'pruser'}
        }
        
        data = extract_github_data(payload, 'pull_request')
        
        self.assertEqual(data['action'], 'PULL_REQUEST')
        self.assertEqual(data['author'], 'pruser')
        self.assertEqual(data['from_branch'], 'feature-branch')
        self.assertEqual(data['to_branch'], 'main')
    
    def test_webhook_without_signature(self):
        """Test webhook without signature"""
        response = self.app.post('/webhook', 
                                json={'test': 'data'},
                                headers={'X-GitHub-Event': 'push'})
        self.assertEqual(response.status_code, 400)
    
    def test_unsupported_event(self):
        """Test unsupported GitHub event"""
        response = self.app.post('/webhook',
                                json={'test': 'data'},
                                headers={'X-GitHub-Event': 'issues'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('not supported', data['message'])

if __name__ == '__main__':
    unittest.main()