"""
auth.py — OTP generation, JWT tokens, password hashing
"""
import os, random, string
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
from dotenv import load_dotenv
import database as db

load_dotenv()

JWT_SECRET  = os.getenv("JWT_SECRET", "xedu_secret_key_change_this")
JWT_ALGO    = "HS256"
JWT_EXPIRE  = 60 * 24 * 7   # 7 days in minutes
OTP_EXPIRY  = int(os.getenv("OTP_EXPIRY_MINUTES", "10"))

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def create_token(user_id: int, email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE)
    return jwt.encode(
        {"sub": str(user_id), "email": email, "exp": expire},
        JWT_SECRET, algorithm=JWT_ALGO
    )

def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except JWTError:
        return None

def generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))

def save_otp(email: str, otp: str):
    # Invalidate old OTPs for this email
    db.execute("UPDATE otp_tokens SET used=1 WHERE email=?", (email,))
    expires = (datetime.now() + timedelta(minutes=OTP_EXPIRY)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO otp_tokens (email, otp, expires_at) VALUES (?,?,?)",
        (email, otp, expires)
    )

def verify_otp(email: str, otp: str) -> bool:
    row = db.fetchone("""
        SELECT * FROM otp_tokens
        WHERE email=? AND otp=? AND used=0
          AND expires_at > datetime('now','localtime')
        ORDER BY created_at DESC LIMIT 1
    """, (email, otp))
    if row:
        db.execute("UPDATE otp_tokens SET used=1 WHERE id=?", (row["id"],))
        return True
    return False
