@app.get("/admin/stats")
def get_admin_stats():
    """Дашборд проекта: пользователи, активные подписки и общая выручка[cite: 6]"""
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
    """Получение списка заявок на вывод со статусом pending[cite: 6]"""
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
    """Модерация заявки на вывод (подтверждение или отклонение)[cite: 6]"""
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
    """Генератор промокодов: добавление или обновление промокода[cite: 6]"""
    with sqlite3.connect("vpn_users.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO promocodes (code, discount_percent) VALUES (?, ?)", 
            (req.code.strip().upper(), req.discount_percent)
        )
        conn.commit()
    return {"success": True, "message": f"Промокод {req.code.upper()} на {req.discount_percent}% успешно создан"}