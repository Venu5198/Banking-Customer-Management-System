import secrets
from cryptography.fernet import Fernet

secret_key = secrets.token_hex(32)
fernet_key = Fernet.generate_key().decode()

lines = [
    "# Application",
    "APP_NAME=BankingApp",
    "APP_ENV=development",
    "DEBUG=true",
    "",
    "# Security",
    f"SECRET_KEY={secret_key}",
    "ALGORITHM=HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES=30",
    "",
    "# Fernet key for encrypting National ID",
    f"FERNET_KEY={fernet_key}",
    "",
    "# Database",
    "DATABASE_URL=sqlite:///./banking.db",
    "",
    "# Banking Rules (all amounts in paise, 1 INR = 100 paise)",
    "SAVINGS_MIN_BALANCE=100000",
    "CURRENT_MIN_BALANCE=500000",
    "FD_MIN_BALANCE=1000000",
    "SAVINGS_DAILY_WITHDRAWAL=5000000",
    "CURRENT_DAILY_WITHDRAWAL=20000000",
    "AML_THRESHOLD=100000000",
    "CTR_THRESHOLD=5000000",
    "",
    "# Account Lockout",
    "MAX_LOGIN_ATTEMPTS=3",
    "LOCKOUT_MINUTES=15",
]

with open(".env", "w") as f:
    f.write("\n".join(lines))

print("SUCCESS: .env created")
print(f"SECRET_KEY (first 16): {secret_key[:16]}...")
print(f"FERNET_KEY (first 16): {fernet_key[:16]}...")
