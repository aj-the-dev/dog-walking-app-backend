import pytest
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app import app, get_db, Base, verify_clerk_jwt

TEST_TOKEN = "test-bearer-token"

# 1. Use StaticPool to keep the same connection alive in memory
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool, 
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 2. Create tables once at the module level for the in-memory engine
Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

async def mock_verify_clerk_jwt():
    """Mock Clerk JWT verification for tests."""
    return {
        "sub": "user_test123",
        "email": "test@example.com",
        "iss": "https://clerk.test"
    }

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_clerk_jwt] = mock_verify_clerk_jwt
client = TestClient(app)

# --- Authentication Tests ---

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_get_walks_no_auth():
    response = client.get("/api/walks")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"

def test_get_walks_wrong_auth():
    headers = {"Authorization": "Bearer invalid-token"}
    # Remove the mock temporarily to test invalid token
    app.dependency_overrides.pop(verify_clerk_jwt, None)
    response = client.get("/api/walks", headers=headers)
    # Restore the mock
    app.dependency_overrides[verify_clerk_jwt] = mock_verify_clerk_jwt
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"

# --- Database Mock Tests ---

def test_create_and_get_walk():
    """Verify adding a walk and retrieving it in the same test run."""
    # Ensure tables exist for this specific test
    Base.metadata.create_all(bind=engine) 
    
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    payload = {
        "person": "Oskar",
        "dog": "Buddy",
        "walk_date": "2026-02-15"
    }
    
    # 1. Create the walk
    post_res = client.post("/api/walks", json=payload, headers=headers)
    assert post_res.status_code == 200
    
    # 2. Retrieve the walks
    get_res = client.get("/api/walks", headers=headers)
    assert get_res.status_code == 200
    
    data = get_res.json()
    assert len(data) >= 1
    assert any(walk["dog"] == "Buddy" for walk in data)

def test_create_and_delete_walk():
    """Verify that we can create a walk and then successfully delete it."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    payload = {
        "person": "Oskar",
        "dog": "Buddy",
        "walk_date": "2026-02-15"
    }
    
    # 1. Create a walk to get a valid ID
    post_res = client.post("/api/walks", json=payload, headers=headers)
    assert post_res.status_code == 200
    walk_id = post_res.json()["id"] # Capture the ID from the response

    # 2. Delete the walk using the ID
    delete_res = client.get(f"/api/walks/{walk_id}", headers=headers)
    # Note: Your app.py delete logic returns {"message": "Success"}
    response = client.delete(f"/api/walks/{walk_id}", headers=headers)
    
    assert response.status_code == 200
    assert response.json()["message"] == "Success"

    # 3. Verify it is actually gone
    get_res = client.get("/api/walks", headers=headers)
    walks = get_res.json()
    assert not any(walk["id"] == walk_id for walk in walks)