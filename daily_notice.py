import os
import requests
from datetime import datetime, timezone, timedelta
from supabase import create_client

# 1. 從環境變數讀取 Supabase 與 LINE API 設定
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
LINE_TOKEN = os.getenv("LINE_TOKEN")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def send_broadcast_notice(msg):
    """發送廣播訊息給所有加入好友的使用者"""
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}",
    }
    payload = {
        "messages": [
            {
                "type": "text",
                "text": msg
            }
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.status_code

def check_and_send():
    # 2. 取得台灣時間 (UTC+8) 當天日期 (2026-08-24)
    tw_tz = timezone(timedelta(hours=8))
    today_str = datetime.now(tw_tz).strftime("%Y-%m-%d")
    
    # 修正：更正資料表名稱為 test_data
    response = supabase.table("test_data").select("*").execute()
    all_rows = response.data or []

    today_items = []
    
    # 全欄位比對，只要包含今日日期 2026-08-24 即視為今日待取測項目
    for row in all_rows:
        row_str = str(row)
        if today_str in row_str:
            today_items.append(row)

    # 【無抽驗項目判斷】：若今天沒有任何需抽驗項目，直接結束，不發送 LINE 訊息
    if not today_items:
        print(f"[{today_str}] 今日無需抽驗項目，跳過通知發送。")
        print(f"資料庫 (test_data) 現有總筆數：{len(all_rows)} 筆。")
        return

    # 3. 組合通知訊息內容
    msg_lines = [f"📋 【SPCAP 信賴性取測提醒】({today_str})", f"今日共有 {len(today_items)} 項需取測/巡檢：\n"]
    for idx, item in enumerate(today_items, 1):
        p_id = item.get('project_id') or item.get('item_id') or 'N/A'
        spec = item.get('product_spec') or item.get('spec') or 'N/A'
        owner = item.get('owner') or item.get('engineer') or 'N/A'
        hour = item.get('hour_key') or item.get('hours') or 'N/A'
        
        msg_lines.append(f"{idx}. 項目編號：{p_id}")
        if spec != 'N/A':
            msg_lines.append(f"   產品規格：{spec}")
        if owner != 'N/A':
            msg_lines.append(f"   負責人：{owner}")
        msg_lines.append(f"   取測時數：{hour}")
        msg_lines.append("")
    
    full_message = "\n".join(msg_lines)

    # 4. 執行廣播發送
    status_code = send_broadcast_notice(full_message)
    if status_code == 200:
        print("LINE 通知廣播成功！")
    else:
        print(f"發送失敗，API 回應碼：{status_code}")

if __name__ == "__main__":
    check_and_send()
