import uuid
import sqlite3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta
import httpx

app = FastAPI()

# --- НАСТРОЙКИ ЮKASSA ---
YOOKASSA_SHOP_ID = "1444358"
YOOKASSA_SECRET_KEY = "live_7YgYIW8xKJsRDfqlSt2P-fqubRhw4Fs8eUr-R5wJYq4"

class YooKassaRequest(BaseModel):
    tg_id: str
    amount: float
    description: str

@app.post("/create-yookassa-invoice")
async def create_yookassa_invoice(req: YooKassaRequest):
    url = "https://api.yookassa.ru/v3/payments"
    payload = {
        "amount": {
            "value": f"{req.amount:.2f}",
            "currency": "RUB"
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/afroslavyanVPN_bot"
        },
        "description": req.description,
        "metadata": {
            "tg_id": str(req.tg_id)
        }
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url, 
                json=payload, 
                auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
                headers={
                    "Idempotence-Key": str(uuid.uuid4()),
                    "Content-Type": "application/json"
                }
            )
            result = response.json()
            
            if response.status_code in [200, 201]:
                confirmation_url = result["confirmation"]["confirmation_url"]
                payment_id = result["id"]
                
                with sqlite3.connect("vpn_users.db") as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO transactions (tg_id, amount, description, date) VALUES (?, ?, ?, ?)", 
                                   (req.tg_id, req.amount, req.description, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    
                    new_exp = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("""
                        INSERT INTO subscriptions (tg_id, expires_at, status) VALUES (?, ?, 'active')
                        ON CONFLICT(tg_id) DO UPDATE SET expires_at=excluded.expires_at, status='active'
                    """, (req.tg_id, new_exp))
                    conn.commit()
                
                return {
                    "success": True,
                    "pay_url": confirmation_url,
                    "payment_id": payment_id
                }
            else:
                error_msg = result.get("description", "Ошибка создания платежа в ЮKassa")
                raise HTTPException(status_code=400, detail=error_msg)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/stats")
def get_admin_stats():
    """Дашборд проекта: пользователи, активные подписки и общая выручка[cite: 6, 10]"""
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT tg_id) FROM subscriptions")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'")
        active_subs = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(amount) FROM transactions")
        revenue_row = cursor.fetchone()[0]
        total_revenue = revenue_row if revenue_row else 0.0
        
    return {
        "success": True,
        "total_users": total_users,
        "active_subs": active_subs,
        "total_revenue": total_revenue
    }

@app.get("/admin/withdrawals")
def get_admin_withdrawals():
    """Получение списка заявок на вывод со статусом pending[cite: 6, 10]"""
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, tg_id, amount, date FROM withdrawals WHERE status = 'pending'")
        rows = cursor.fetchall()
    
    withdrawals = [{"id": r[0], "tg_id": r[1], "amount": r[2], "date": r[3]} for r in rows]
    return {"success": True, "withdrawals": withdrawals}

class WithdrawalAction(BaseModel):
    withdrawal_id: int
    action: str  # 'approve' или 'reject'

@app.post("/admin/withdrawal-action")
def admin_withdrawal_action(req: WithdrawalAction):
    """Модерация заявки на вывод (подтверждение или отклонение)[cite: 6, 10]"""
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        new_status = 'approved' if req.action == 'approve' else 'rejected'
        cursor.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (new_status, req.withdrawal_id))
        conn.commit()
    return {"success": True, "message": f"Заявка переведена в статус {new_status}"}

class AdminPromoCreate(BaseModel):
    code: str
    discount_percent: int

@app.post("/admin/create-promo")
def admin_create_promo(req: AdminPromoCreate):
    """Генератор промокодов: добавление или обновление промокода[cite: 6, 10]"""
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO promocodes (code, discount_percent) VALUES (?, ?)", 
            (req.code.strip().upper(), req.discount_percent)
        )
        conn.commit()
    return {"success": True, "message": f"Промокод {req.code.upper()} на {req.discount_percent}% успешно создан"}