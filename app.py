import os
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Header, status, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from clerk_backend_api import Clerk
import jwt
import requests
from functools import lru_cache

# --- Database Connection ---
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Database Model ---
class WalkDB(Base):
    __tablename__ = "walks"
    id = Column(Integer, primary_key=True, index=True)
    person = Column(String)
    dog = Column(String)
    walk_date = Column(Date)

# Create tables on startup
Base.metadata.create_all(bind=engine)

# --- Pydantic Schemas (Validation) ---
class WalkBase(BaseModel):
    person: str
    dog: str
    walk_date: date

class WalkResponse(WalkBase):
    id: int
    class Config:
        from_attributes = True

# --- Dependencies ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@lru_cache()
def get_clerk_jwks():
    """Fetch and cache Clerk's JWKS (public keys) for JWT verification."""
    clerk_frontend_api = os.getenv("CLERK_FRONTEND_API", "growing-python-17.clerk.accounts.dev")
    jwks_url = f"https://{clerk_frontend_api}/.well-known/jwks.json"
    try:
        response = requests.get(jwks_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching JWKS: {e}")
        return None

def get_signing_key(token: str):
    """Get the signing key from Clerk's JWKS."""
    try:
        jwks = get_clerk_jwks()
        if not jwks:
            return None
        
        # Decode token header to get the key ID (kid)
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get('kid')
        
        # Find the matching key in JWKS
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)
        
        return None
    except Exception as e:
        print(f"Error getting signing key: {e}")
        return None

async def verify_clerk_jwt(
    authorization: str = Header(None)
) -> Dict[str, Any]:
    """
    Verify Clerk JWT token from Authorization: Bearer header.
    Returns decoded JWT payload containing user information.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = authorization.replace("Bearer ", "", 1)
    
    try:
        # Get the signing key from JWKS
        signing_key = get_signing_key(token)
        if not signing_key:
            raise HTTPException(status_code=401, detail="Unable to verify token")
        
        # Verify and decode the JWT token
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            options={"verify_signature": True, "verify_exp": True}
        )
        
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as e:
        print(f"JWT verification error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# --- App Initialization ---
app = FastAPI(title="Dog Walker Professional API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8200", "http://192.168.86.249:8200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Endpoints ---

# Health Check (Unprotected)
@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Get Walks (Protected)
@app.get("/api/walks", response_model=List[WalkResponse])
async def get_walks(
    db: Session = Depends(get_db), 
    user: Dict[str, Any] = Depends(verify_clerk_jwt)
):
    return db.query(WalkDB).order_by(WalkDB.walk_date.desc()).all()

# Add a Walk (Protected)
@app.post("/api/walks", response_model=WalkResponse)
async def create_walk(
    walk: WalkBase, 
    db: Session = Depends(get_db), 
    user: Dict[str, Any] = Depends(verify_clerk_jwt)
):
    """Protected: Create a new walk log."""
    db_walk = WalkDB(**walk.model_dump())
    db.add(db_walk)
    db.commit()
    db.refresh(db_walk)
    return db_walk

# Delete a Walk (Protected)
@app.delete("/api/walks/{walk_id}")
async def delete_walk(
    walk_id: int, 
    db: Session = Depends(get_db), 
    user: Dict[str, Any] = Depends(verify_clerk_jwt)
):
    """Protected: Remove a walk log."""
    db_walk = db.query(WalkDB).filter(WalkDB.id == walk_id).first()
    if not db_walk:
        raise HTTPException(status_code=404, detail="Walk not found")
    db.delete(db_walk)
    db.commit()
    return {"message": "Success"}

# Edit Walk Endpoint (Protected)
@app.put("/api/walks/{walk_id}", response_model=WalkResponse)
async def update_walk(
    walk_id: int, 
    updated_data: WalkBase, 
    db: Session = Depends(get_db), 
    user: Dict[str, Any] = Depends(verify_clerk_jwt)
):
    db_walk = db.query(WalkDB).filter(WalkDB.id == walk_id).first()
    if not db_walk:
        raise HTTPException(status_code=404, detail="Walk not found")
    
    # Update the fields
    for key, value in updated_data.model_dump().items():
        setattr(db_walk, key, value)
    
    db.commit()
    db.refresh(db_walk)
    return db_walk