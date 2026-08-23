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
    # 2. 取得台灣時間 (UTC+8) 當天日期 (格式：YYYY-MM-DD)
    tw_tz = timezone(timedelta(hours=8))
    today_str = datetime.now(tw_tz).strftime("%Y-%m-%d")
    
    # 先嘗試查詢 scheduled_date 欄位
    response = supabase.table("reliability_tests") \
        .select("*") \
        .eq("scheduled_date", today_str) \
        .execute()
    
    data = response.data

    # 若 scheduled_date 查無資料，自動改查 due_date 欄位
    if not data:
        response = supabase.table("reliability_tests") \
            .select("*") \
            .eq("due_date", today_str) \
            .execute()
        data = response.data

    # 【無抽驗項目判斷】：若今天沒有任何需抽驗項目，直接結束，不發送 LINE 訊息
    if not data:
        print(f"[{today_str}] 今日無需抽驗項目，跳過通知發送。")
        return

    # 3. 組合通知訊息內容
    msg_lines = [f"📋 【SPCAP 信賴性取測提醒】({today_str})", f"今日共有 {len(data)} 項需取測/巡檢：\n"]
    for idx, item in enumerate(data, 1):
        spec = item.get('product_spec') or item.get('sample_name') or 'N/A'
        owner = item.get('owner') or item.get('engineer') or 'N/A'
        hours = item.get('test_hours') or item.get('status') or 'N/A'
        time_str = item.get('scheduled_date') or item.get('due_date') or today_str
        
        msg_lines.append(f"{idx}. 產品規格：{spec}")
        msg_lines.append(f"   負責人：{owner}")
        msg_lines.append(f"   取測時數：{hours}")
        msg_lines.append(f"   預計日期：{time_str}\n")
    
    full_message = "\n".join(msg_lines)

    # 4. 執行廣播發送
    status_code = send_broadcast_notice(full_message)
    if status_code == 200:
        print("LINE 通知廣播成功！")
    else:
        print(f"發送失敗，API 回應碼：{status_code}")

if __name__ == "__main__":
    check_and_send()
