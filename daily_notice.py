import os
from datetime import datetime
import requests
from supabase import create_client

# 從 GitHub Secrets 讀取設定
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
LINE_TOKEN = os.getenv("LINE_TOKEN")
MY_USER_ID = os.getenv("MY_USER_ID")


def push_line_notice(msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}",
    }
    payload = {"to": MY_USER_ID, "messages": [{"type": "text", "text": msg}]}
    res = requests.post(url, headers=headers, json=payload)
    return res.status_code


def check_and_send():
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 查詢 Supabase 今天的取測任務
    res = (
        supabase.table("reliability_tests")
        .select("*")
        .eq("scheduled_date", today_str)
        .execute()
    )
    records = res.data

    if records:
        msg = f"【SPCAP 今日取測提醒 - {today_str}】\n今日共有 {len(records)} 筆取測任務：\n"
        for i, item in enumerate(records, 1):
            msg += f"\n{i}. 批號：{item.get('lot_id', 'N/A')}\n   項目：{item.get('test_item', 'N/A')}\n   預計時間：{item.get('scheduled_time', '未指定')}"
    else:
        msg = f"【SPCAP 今日取測提醒 - {today_str}】\n今日無預計取測項目。"

    push_line_notice(msg)


if __name__ == "__main__":
    check_and_send()
