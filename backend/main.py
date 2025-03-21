import os
import base64
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, TIMESTAMP, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel
import google.generativeai as genai
from datetime import datetime, timedelta, timezone
import jwt
from typing import List, Optional
import asyncio
import uvicorn

# Load environment variables
load_dotenv()

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Database setup
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

if not TURSO_DATABASE_URL or not TURSO_AUTH_TOKEN:
    raise ValueError("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be set in .env file")

dbUrl = f"sqlite+libsql:///doodledict-patilshrinivas078.turso.io/?authToken={TURSO_AUTH_TOKEN}&secure=true"
engine = create_engine(dbUrl, connect_args={'check_same_thread': False}, echo=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

# Database models
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String, unique=True)
    email = Column(String, unique=True)
    password = Column(String)
    name = Column(String)
    
    scores = relationship("Score", back_populates="user")

class Score(Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, ForeignKey("users.username"), nullable=False)
    score = Column(Integer, nullable=False)
    total_attempts = Column(Integer, nullable=False)
    timestamp = Column(TIMESTAMP, server_default=func.current_timestamp())

    user = relationship("User", back_populates="scores")

# Pydantic models
class ImageRecognitionRequest(BaseModel):
    image: str

class ScoreRequest(BaseModel):
    username: str
    score: int
    total_attempts: int

class UserSignup(BaseModel):
    username: str
    password: str
    email: str
    name: str

class PasswordReset(BaseModel):
    email: str

class UserLogin(BaseModel):
    username: str
    password: str

# Authentication
SECRET_KEY = "doodleisawesome"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# FastAPI app
app = FastAPI()

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database dependency
def get_db():
    """
    Get database connection
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Setup database on startup
@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(engine)

# Helper functions
def preprocess_image(image_base64):
    """
    Preprocess the base64 encoded image for AI recognition
    """
    # Remove data URL prefix if present
    if "base64," in image_base64:
        image_base64 = image_base64.split("base64,")[1]

    # Decode base64 to image bytes
    image_bytes = base64.b64decode(image_base64)

    return image_bytes

def create_access_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# API Routes
@app.get("/")
async def root():
    return {"message": "Welcome to Doodle AI!"}

@app.post("/recognize")
async def recognize_doodle(request: ImageRecognitionRequest):
    try:
        base64_image = preprocess_image(request.image)
        
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content([
            "Identify the object in this doodle in a single word.",
            {
                "mime_type": "image/png",
                "data": base64_image
            }
        ])

        result = response.text.split()[0].strip(".,!?").lower()
        return {"result": result}

    except Exception as e:
        print(f"Error in recognition: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to recognize doodle"
        )

@app.post("/save-score", tags=['doodle'])
async def save_score(request: ScoreRequest, db: Session = Depends(get_db)):
    try:
        # Check if user exists
        user = db.query(User).filter(User.username == request.username).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Get highest score for user
        highest_score = db.query(Score).filter(
            Score.username == request.username
        ).order_by(Score.score.desc()).first()
        
        # Save score if it's the first one or better than previous
        if not highest_score or request.score > highest_score.score:
            new_score = Score(
                username=request.username, 
                score=request.score, 
                total_attempts=request.total_attempts
            )
            db.add(new_score)
            db.commit()

        return {"message": "Score saved successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/leaderboard")
async def get_leaderboard(db: Session = Depends(get_db)):
    try:
        # Query top 10 scores
        scores = db.query(Score).order_by(Score.score.desc()).limit(10).all()
        
        # Convert to list of dictionaries
        leaderboard = [
            {
                "username": score.username,
                "score": score.score,
                "total_attempts": score.total_attempts
            } 
            for score in scores
        ]
        return {"leaderboard": leaderboard}
    except Exception as e:
        print(f"Error in leaderboard: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/login")
async def login(request: UserLogin, db: Session = Depends(get_db)):
    try:
        # Find user by username
        user = db.query(User).filter(User.username == request.username).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User does not exist")
        
        # Verify password
        if not pwd_context.verify(request.password, user.password):
            raise HTTPException(status_code=401, detail="Incorrect password")

        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username}, 
            expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "username": user.username,
                "email": user.email,
                "name": user.name
            }
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in login: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/signup")
async def signup(request: UserSignup, db: Session = Depends(get_db)):
    try:
        # Check if username or email already exists
        existing_user = db.query(User).filter(
            (User.username == request.username) | 
            (User.email == request.email)
        ).first()
        
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="Username or email already exists"
            )
            
        # Create new user
        hashed_password = pwd_context.hash(request.password)
        new_user = User(
            username=request.username,
            password=hashed_password,
            email=request.email,
            name=request.name
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": new_user.username}, 
            expires_delta=access_token_expires
        )

        response= {"access_token": access_token, "token_type": "bearer"}
        print(f"Signup Successful: {response}")
        return response
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in signup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/forgot-password")
async def forgot_password(request: PasswordReset, db: Session = Depends(get_db)):
    try:
        # Check if email exists
        user = db.query(User).filter(User.email == request.email).first()

        if not user:
            raise HTTPException(status_code=404, detail="Email not found")

        # In a real application, send a password reset email here
        # For now, return a success message
        return {"message": "Password reset instructions sent to email"}

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in forgot password: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/verify-token")
async def verify_token(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
            
        # Get user data
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        return {
            "username": user.username,
            "email": user.email,
            "name": user.name
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Could not validate token")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)