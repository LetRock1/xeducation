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

MAX_OTP_ATTEMPTS = 5


def save_otp(email: str, otp: str, purpose: str = "signup"):
    # Invalidate old OTPs for this email + purpose
    db.execute("UPDATE otp_tokens SET used=1 WHERE email=? AND COALESCE(purpose,'signup')=?",
               (email, purpose))
    expires = (datetime.now() + timedelta(minutes=OTP_EXPIRY)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO otp_tokens (email, otp, expires_at, purpose, attempts) VALUES (?,?,?,?,0)",
        (email, otp, expires, purpose)
    )


def last_otp_age_seconds(email: str, purpose: str = "signup"):
    row = db.fetchone("""SELECT (julianday('now','localtime') - julianday(created_at)) * 86400 AS age
                         FROM otp_tokens WHERE email=? AND COALESCE(purpose,'signup')=?
                         ORDER BY id DESC LIMIT 1""", (email, purpose))
    return row["age"] if row else None


def verify_otp(email: str, otp: str, purpose: str = "signup") -> bool:
    """Checks the latest live code. Each wrong guess counts; after 5 the code is burned
    (a 6-digit code could otherwise be brute-forced)."""
    row = db.fetchone("""
        SELECT * FROM otp_tokens
        WHERE email=? AND COALESCE(purpose,'signup')=? AND used=0
          AND expires_at > datetime('now','localtime')
        ORDER BY id DESC LIMIT 1
    """, (email, purpose))
    if not row:
        return False
    if row["otp"] == (otp or "").strip():
        db.execute("UPDATE otp_tokens SET used=1 WHERE id=?", (row["id"],))
        return True
    attempts = (row.get("attempts") or 0) + 1
    db.execute("UPDATE otp_tokens SET attempts=?, used=? WHERE id=?",
               (attempts, 1 if attempts >= MAX_OTP_ATTEMPTS else 0, row["id"]))
    return False
