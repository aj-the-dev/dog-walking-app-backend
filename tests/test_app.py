import pytest
from fastapi.testclient import TestClient
from app import app  # Imports the FastAPI app
import sys
import os

# Adds the parent directory (backend/) to the path so it can find app.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

client = TestClient(app)

def test_health_check():
    """Test the unprotected health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_get_walks_no_auth():
    """Test that accessing walks without a key fails with 401."""
    response = client.get("/api/walks")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required."

def test_get_walks_wrong_auth():
    """Test that a wrong key fails with 403."""
    headers = {"x-api-key": "wrong_key"}
    response = client.get("/api/walks", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Authentication failed."
