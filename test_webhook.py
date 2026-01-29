import requests
import json
import hmac
import hashlib
from datetime import datetime


class WebhookTester:
    def __init__(self, webhook_url, secret):
        self.webhook_url = webhook_url
        self.secret = secret

    def generate_signature(self, payload):
        """Generate GitHub webhook signature"""
        signature = hmac.new(
            self.secret.encode("utf-8"),
            json.dumps(payload).encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    def test_push_event(self):
        """Test PUSH event webhook"""
        payload = {
            "ref": "refs/heads/main",
            "before": "abc123",
            "after": "def456",
            "created": False,
            "deleted": False,
            "forced": False,
            "base_ref": None,
            "compare": "https://github.com/user/repo/compare/abc123...def456",
            "commits": [
                {
                    "id": "def456",
                    "message": "Test commit message",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "author": {
                        "name": "Test User",
                        "email": "test@example.com"
                    }
                }
            ],
            "head_commit": {
                "id": "def456",
                "message": "Test commit message",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "author": {
                    "name": "Test User",
                    "email": "test@example.com"
                }
            },
            "repository": {
                "name": "action-repo",
                "full_name": "user/action-repo"
            },
            "pusher": {
                "name": "Test User",
                "email": "test@example.com"
            },
            "sender": {
                "login": "testuser"
            }
        }

        headers = {
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": self.generate_signature(payload)
        }

        return requests.post(self.webhook_url, json=payload, headers=headers)

    def test_pull_request_opened(self):
        """Test PULL_REQUEST opened event"""
        payload = {
            "action": "opened",
            "number": 1,
            "pull_request": {
                "url": "https://api.github.com/repos/user/repo/pulls/1",
                "number": 1,
                "state": "open",
                "title": "Test Pull Request",
                "body": "This is a test PR",
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "merged": False,
                "mergeable": True,
                "head": {
                    "ref": "test-branch",
                    "sha": "abc123",
                    "repo": {
                        "full_name": "user/action-repo"
                    }
                },
                "base": {
                    "ref": "main",
                    "sha": "def456",
                    "repo": {
                        "full_name": "user/action-repo"
                    }
                }
            },
            "repository": {
                "full_name": "user/action-repo"
            },
            "sender": {
                "login": "testuser"
            }
        }

        headers = {
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": self.generate_signature(payload)
        }

        return requests.post(self.webhook_url, json=payload, headers=headers)

    def test_pull_request_merged(self):
        """Test PULL_REQUEST merged event"""
        payload = {
            "action": "closed",
            "number": 1,
            "pull_request": {
                "url": "https://api.github.com/repos/user/repo/pulls/1",
                "number": 1,
                "state": "closed",
                "title": "Test Pull Request",
                "body": "This is a test PR",
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "closed_at": datetime.utcnow().isoformat() + "Z",
                "merged": True,
                "mergeable": None,
                "merged_by": {
                    "login": "testuser"
                },
                "head": {
                    "ref": "test-branch",
                    "sha": "abc123",
                    "repo": {
                        "full_name": "user/action-repo"
                    }
                },
                "base": {
                    "ref": "main",
                    "sha": "def456",
                    "repo": {
                        "full_name": "user/action-repo"
                    }
                }
            },
            "repository": {
                "full_name": "user/action-repo"
            },
            "sender": {
                "login": "testuser"
            }
        }

        headers = {
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": self.generate_signature(payload)
        }

        return requests.post(self.webhook_url, json=payload, headers=headers)


# --------------------
# Usage
# --------------------
if __name__ == "__main__":
    tester = WebhookTester(
        "https://your-webhook-url.com/webhook",
        "your_secret"
    )

    push_result = tester.test_push_event()
    print(f"PUSH Status: {push_result.status_code}, Response: {push_result.text}")

    pr_open_result = tester.test_pull_request_opened()
    print(f"PR OPEN Status: {pr_open_result.status_code}, Response: {pr_open_result.text}")

    pr_merge_result = tester.test_pull_request_merged()
    print(f"PR MERGED Status: {pr_merge_result.status_code}, Response: {pr_merge_result.text}")
