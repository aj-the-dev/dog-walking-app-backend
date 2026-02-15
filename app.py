import os
from datetime import date, datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
import bcrypt

# --- Configuration & Security ---
# Pull the key
API_KEY = os.getenv("API_KEY", "").strip()

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

async def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Authentication required.")

    # Prepare bytes for bcrypt
    try:
        user_bytes = x_api_key.encode('utf-8')
        hash_bytes = API_KEY.encode('utf-8')
    except Exception:
        raise HTTPException(status_code=500, detail="Server security configuration error.")

    is_valid = bcrypt.checkpw(user_bytes, hash_bytes)

    if not is_valid:
        raise HTTPException(status_code=403, detail="Authentication failed.")

    return x_api_key

# --- App Initialization ---
app = FastAPI(title="Dog Walker Professional API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
def get_walks(
    db: Session = Depends(get_db), 
    auth: str = Depends(verify_api_key)
):
    return db.query(WalkDB).order_by(WalkDB.walk_date.desc()).all()

# Add a Walk (Protected)
@app.post("/api/walks", response_model=WalkResponse)
def create_walk(
    walk: WalkBase, 
    db: Session = Depends(get_db), 
    auth: str = Depends(verify_api_key)
):
    """Protected: Create a new walk log."""
    db_walk = WalkDB(**walk.model_dump())
    db.add(db_walk)
    db.commit()
    db.refresh(db_walk)
    return db_walk

# Delete a Walk (Protected)
@app.delete("/api/walks/{walk_id}")
def delete_walk(
    walk_id: int, 
    db: Session = Depends(get_db), 
    auth: str = Depends(verify_api_key)
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
def update_walk(
    walk_id: int, 
    updated_data: WalkBase, 
    db: Session = Depends(get_db), 
    auth: str = Depends(verify_api_key)
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