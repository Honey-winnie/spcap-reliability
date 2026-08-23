import os
import requests
from datetime import datetime, timezone, timedelta
from dateutil import parser as date_parser
from supabase import create_client

# 1. 從環境變數讀取 Supabase 與 LINE API 設定
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
LINE_TOKEN = os.getenv("LINE_TOKEN")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def send_broadcast_notice(msg):
    """發送廣播訊息給所有 LINE 好友"""
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
    # 2. 取得台灣時間 (Asia/Taipei) 當天日期 (2026-08-24)
    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    today_str = now.strftime("%Y-%m-%d")

    # 3. 讀取專案總表
    res_proj = supabase.table("projects").select("*").execute()
    projects = res_proj.data or []

    # 4. 讀取測試數據 (用於確認是否已完成取測)
    res_data = supabase.table("test_data").select("project_id, hour_key").execute()
    test_data = res_data.data or []
    
    # 建立已完成紀錄集合 set: {(project_id, hour_key), ...}
    completed_set = set()
    for d in test_data:
        completed_set.add((str(d.get("project_id")), str(d.get("hour_key"))))

    today_alerts = []

    # 5. 計算每個專案的取測時間點
    for p in projects:
        # 跳過停測專案
        if p.get("status") == "停測":
            continue

        p_id = str(p.get("id", ""))
        owner = str(p.get("owner", ""))
        spec = str(p.get("spec", ""))
        condition = str(p.get("condition", ""))
        
        # 解析投入時間
        start_raw = str(p.get("start_time", "")).strip()
        if not start_raw or start_raw.lower() == "none":
            continue
            
        try:
            start_dt = date_parser.parse(start_raw)
        except Exception:
            continue

        # 解析時數列表
        hours_raw = str(p.get("hours_list", ""))
        hours_list = [int(h.strip()) for h in hours_raw.split(",") if h.strip().isdigit()]

        # 比對每個時數節點的預計日期
        for h in hours_list:
            target_dt = start_dt + timedelta(hours=h)
            target_date_str = target_dt.strftime("%Y-%m-%d")
            hour_key = f"{h}H"

            # 如果預計取測日期是「今天」
            if target_date_str == today_str:
                # 檢查是否已經填過數據，若已填過則不再提醒
                if (p_id, hour_key) not in completed_set:
                    today_alerts.append({
                        "id": p_id,
                        "owner": owner,
                        "spec": spec,
                        "condition": condition,
                        "hour_key": hour_key,
                        "time_str": target_dt.strftime("%H:%M")
                    })

    # 6. 若今天沒有需要取測的項目，結束執行
    if not today_alerts:
        print(f"[{today_str}] 今日無預計取測項目，跳過 LINE 推播發送。")
        return

    # 7. 組合廣播訊息
    msg_lines = [f"📋 【SPCAP 今日信賴性取測提醒】({today_str})", f"今日共有 {len(today_alerts)} 項待處理：\n"]
    for idx, item in enumerate(today_alerts, 1):
        msg_lines.append(f"{idx}. 批號：#{item['id']}")
        msg_lines.append(f"   負責人：{item['owner']}")
        msg_lines.append(f"   規格：{item['spec']}")
        msg_lines.append(f"   取測時數：{item['hour_key']} (預計 {item['time_str']})")
        msg_lines.append("")

    full_message = "\n".join(msg_lines)

    # 8. 發送 LINE 廣播
    status_code = send_broadcast_notice(full_message)
    if status_code == 200:
        print("LINE 通知廣播成功！")
    else:
        print(f"發送失敗，API 回應碼：{status_code}")

if __name__ == "__main__":
    check_and_send()
