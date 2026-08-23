import sqlite3
import random
import smtplib
from email.mime.text import MIMEText
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import httpx

# --- НАСТРОЙКИ ВАШЕЙ ПОЧТЫ ---[cite: 6]
SMTP_SERVER = "smtp.mail.ru" # Или smtp.yandex.ru[cite: 6]
SMTP_PORT = 465 # SSL порт[cite: 6]
SMTP_EMAIL = "afrovpn@mail.ru" # Ваш email отправителя[cite: 6]
SMTP_PASSWORD = "yGCJ2FTxrad97gsQM60T" # Тот самый пароль для приложений[cite: 6]

app = FastAPI()

# Разрешаем запросы с вашего сайта на GitHub Pages (очень важно!)[cite: 6]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Разрешаем все домены (для тестов)[cite: 6]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Токен от @CryptoBot
CRYPTO_BOT_TOKEN = "625448:AAdE7FGbHENh9wL9OmqYFv9buLQoSoCQRGV"

# Подготовка Базы Данных[cite: 6]
def init_db():
    conn = sqlite3.connect("vpn_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_verifications (
            tg_id TEXT PRIMARY KEY,
            email TEXT,
            code TEXT,
            expires_at DATETIME,
            is_verified BOOLEAN DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Функция отправки письма[cite: 6]
def send_email(to_email, code):
    msg = MIMEText(f"Ваш код подтверждения для AFROVPN: {code}")
    msg["Subject"] = "Код подтверждения AFROVPN"
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
    except Exception as e:
        print(f"Ошибка отправки письма: {e}")
        return False
    return True

# Модели данных[cite: 6]
class EmailRequest(BaseModel):
    tg_id: str
    email: str

class CodeVerify(BaseModel):
    tg_id: str
    code: str

class InvoiceRequest(BaseModel):
    tg_id: str
    amount: float
    description: str

# 1. Эндпоинт: ОТПРАВИТЬ КОД[cite: 6]
@app.post("/send-code")
def send_code(req: EmailRequest):
    code = str(random.randint(100000, 999999)) # Генерируем 6 цифр[cite: 6]
    expires = datetime.now() + timedelta(minutes=10) # Код живет 10 минут[cite: 6]
    
    # Сохраняем в БД[cite: 6]
    conn = sqlite3.connect("vpn_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO email_verifications (tg_id, email, code, expires_at, is_verified)
        VALUES (?, ?, ?, ?, 0)
        ON CONFLICT(tg_id) DO UPDATE SET 
        email=excluded.email, code=excluded.code, expires_at=excluded.expires_at, is_verified=0
    """, (req.tg_id, req.email, code, expires))
    conn.commit()
    conn.close()

    # Отправляем письмо[cite: 6]
    if send_email(req.email, code):
        return {"success": True, "message": "Код отправлен"}
    else:
        raise HTTPException(status_code=500, detail="Ошибка отправки письма")

# 2. Эндпоинт: ПРОВЕРИТЬ КОД[cite: 6]
@app.post("/verify-code")
def verify_code(req: CodeVerify):
    conn = sqlite3.connect("vpn_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT code, expires_at FROM email_verifications WHERE tg_id = ?", (req.tg_id,))
    row = cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=400, detail="Код не запрашивался")
    
    db_code, expires_at = row
    expires_at = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S.%f")

    if datetime.now() > expires_at:
        raise HTTPException(status_code=400, detail="Срок действия кода истек")
    
    if req.code != db_code:
        raise HTTPException(status_code=400, detail="Неверный код")
    
    # Если всё ок, помечаем как верифицированного[cite: 6]
    cursor.execute("UPDATE email_verifications SET is_verified = 1 WHERE tg_id = ?", (req.tg_id,))
    conn.commit()
    conn.close()

    return {"success": True, "message": "Почта подтверждена"}

# 3. Эндпоинт: СОЗДАТЬ СЧЕТ В CRYPTOBOT
@app.post("/create-crypto-invoice")
async def create_crypto_invoice(req: InvoiceRequest):
    url = "https://pay.crypt.bot/api/createInvoice"
    
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    
    payload = {
        "asset": "USDT",
        "amount": str(req.amount),
        "description": req.description,
        "payload": str(req.tg_id),
        "paid_btn_name": "callback",
        "paid_btn_url": "https://t.me/afroVPN_bot"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            result = response.json()
            
            if result.get("ok"):
                invoice = result["result"]
                return {
                    "success": True,
                    "pay_url": invoice["pay_url"],
                    "invoice_id": invoice["invoice_id"]
                }
            else:
                error_msg = result.get("error", {}).get("name", "Ошибка создания счета")
                raise HTTPException(status_code=400, detail=error_msg)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))