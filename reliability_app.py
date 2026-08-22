import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from supabase import create_client, Client

# -----------------------------------------------------------------------------
# 1. 頁面配置與權限登入
# -----------------------------------------------------------------------------
st.set_page_config(page_title="SPCAP 信賴性管理系統 (雲端多人協作版)", layout="wide", initial_sidebar_state="expanded")

def check_password():
    """系統登入驗證"""
    if st.session_state.get("password_correct", False):
        return True
    
    st.title("🔒 SPCAP 信賴性管理系統 - 登入")
    role = st.radio("請選擇您的身份：", ["OP 現場操作員", "主管 / 工程師"])
    pwd = st.text_input("請輸入系統存取密碼：", type="password")
    
    if st.button("🔑 登入系統", type="primary"):
        if pwd == "E0567":  # 預設系統密碼
            st.session_state["password_correct"] = True
            st.session_state["user_role"] = role
            st.rerun()
        else:
            st.error("❌ 密碼錯誤，請重新輸入！")
    return False

if not check_password():
    st.stop()

# -----------------------------------------------------------------------------
# 2. 連線 Supabase 雲端資料庫 (從 Secrets 讀取)
# -----------------------------------------------------------------------------
supabase_url = st.secrets.get("SUPABASE_URL", "").strip()
supabase_key = st.secrets.get("SUPABASE_KEY", "").strip()

if not supabase_url or not supabase_key:
    st.error("❌ 尚未讀取到 Supabase Secrets，請至 Streamlit 設定 SUPABASE_URL 與 SUPABASE_KEY！")
    st.stop()

@st.cache_resource
def init_supabase() -> Client:
    try:
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        st.error(f"⚠️ 雲端資料庫連線失敗，請檢查 URL 與 Key 設定：{e}")
        st.stop()

supabase = init_supabase()

# -----------------------------------------------------------------------------
# 3. 資料庫讀取輔助函式
# -----------------------------------------------------------------------------
def load_projects():
    try:
        res = supabase.table("projects").select("*").execute()
        raw = res.data or []
        projects = []
        for r in raw:
            hours = [int(h.strip()) for h in str(r.get("hours_list", "")).split(",") if h.strip().isdigit()]
            
            # 多重格式相容解析，避免時間格式解析失敗被 reset 為當前時間
            start_str = str(r.get("start_time", "")).strip()
            start_dt = None
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
                try:
                    start_dt = datetime.strptime(start_str, fmt)
                    break
                except ValueError:
                    continue
            
            if start_dt is None:
                start_dt = datetime.now()
                
            projects.append({
                "id": str(r.get("id", "")),
                "owner": str(r.get("owner", "")),
                "spec": str(r.get("spec", "")),
                "sample_size": int(r.get("sample_size", 10)),
                "condition": str(r.get("condition", "")),
                "status": str(r.get("status", "進行中")),
                "start_time": start_dt,
                "hours_list": hours,
                "target_hours": f"{max(hours)}H" if hours else "0H",
                "description": str(r.get("description", ""))
            })
        return projects
    except Exception as e:
        st.sidebar.error(f"⚠️ 專案列表讀取異常：{e}")
        return []

def load_testdata():
    try:
        res = supabase.table("test_data").select("*").execute()
        raw = res.data or []
        test_data = {}
        for r in raw:
            p_id = str(r.get("project_id", ""))
            hour = str(r.get("hour_key", ""))
            
            if p_id not in test_data:
                test_data[p_id] = {}
            if hour not in test_data[p_id]:
                test_data[p_id][hour] = []
                
            test_data[p_id][hour].append({
                "顆數": str(r.get("sample_no", "")),
                "Cap (uF)": float(r.get("cap", 0)),
                "DF (%)": float(r.get("df", 0)),
                "ESR (mΩ)": float(r.get("esr", 0)),
                "LC (uA)": float(r.get("lc", 0))
            })
            
        for p_id in test_data:
            for hour in test_data[p_id]:
                test_data[p_id][hour] = pd.DataFrame(test_data[p_id][hour])
                
        return test_data
    except Exception as e:
        st.sidebar.error(f"⚠️ 測試數據讀取異常：{e}")
        return {}

projects_list = load_projects()
test_data_dict = load_testdata()

# -----------------------------------------------------------------------------
# 4. 主介面導覽與標籤
# -----------------------------------------------------------------------------
st.title("🧪 SPCAP 信賴性投測管理系統 (雲端多人同步版)")
st.caption(f"👤 當前登入身份：**{st.session_state.get('user_role', '使用者')}** ｜ ☁️ 資料庫狀態：Supabase 即時連線中")

menu = st.sidebar.radio("系統功能導覽", [
    "📌 提醒與逾期看板", 
    "📋 投測總表與查詢", 
    "➕ 新增投測項目", 
    "✏️ 修改 / 刪除專案", 
    "📝 OP 數據填寫與變化率繪圖", 
    "📊 跨批號電性數據比較",
    "📅 甘特圖排程檢視"
])

# -----------------------------------------------------------------------------
# 功能 1：提醒與逾期看板
# -----------------------------------------------------------------------------
if menu == "📌 提醒與逾期看板":
    st.header("🔔 每日取測提醒與逾期追蹤")
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    
    st.info(f"當前系統時間：**{now.strftime('%Y-%m-%d %H:%M')}**")
    
    alerts = []
    month_schedule = []
    future_30_days = now + timedelta(days=30)
    
    for p in projects_list:
        p_id = p['id']
        start = p['start_time']
        
        for h in p['hours_list']:
            target_dt = start + timedelta(hours=h)
            date_str = target_dt.strftime("%Y-%m-%d")
            hour_key = f"{h}H"
            
            has_data = (p_id in test_data_dict) and (hour_key in test_data_dict[p_id])
            
            if now.date() <= target_dt.date() <= future_30_days.date():
                month_schedule.append({
                    "取測日期": target_dt.strftime("%Y-%m-%d"),
                    "預計時間": target_dt.strftime("%H:%M"),
                    "項目編號": p['id'],
                    "負責人": p['owner'],
                    "產品規格": p['spec'],
                    "投測條件": p['condition'],
                    "取測時數": hour_key,
                    "狀態": "✅ 已完成" if has_data else "⏳ 待取測"
                })

            if has_data:
                continue

            if target_dt < now:
                status_type = "🔴 逾期未完成"
            elif date_str == today_str:
                status_type = "🟡 今日預計取測"
            elif date_str == tomorrow_str:
                status_type = "🔵 明日預計取測"
            else:
                status_type = "🟢 排程中"
                
            alerts.append({
                "項目編號": p['id'],
                "負責人": p['owner'],
                "產品規格": p['spec'],
                "投測條件": p['condition'],
                "取測時數": hour_key,
                "預計取測時間": target_dt.strftime("%Y-%m-%d %H:%M"),
                "提醒狀態": status_type
            })
            
    df_alerts = pd.DataFrame(alerts) if alerts else pd.DataFrame(columns=["項目編號", "負責人", "產品規格", "投測條件", "取測時數", "預計取測時間", "提醒狀態"])
    
    st.subheader("🔴 逾期或需補填項目")
    df_red = df_alerts[df_alerts['提醒狀態'].str.contains("🔴")] if not df_alerts.empty else pd.DataFrame()
    if not df_red.empty:
        st.dataframe(df_red.drop(columns=['提醒狀態']), use_container_width=True, hide_index=True)
    else:
        st.success("目前無逾期項目！")

    st.markdown("---")
    st.subheader("🟡 今日待取測項目")
    df_yellow = df_alerts[df_alerts['提醒狀態'].str.contains("🟡")] if not df_alerts.empty else pd.DataFrame()
    if not df_yellow.empty:
        st.dataframe(df_yellow.drop(columns=['提醒狀態']), use_container_width=True, hide_index=True)
    else:
        st.info("今日無預計取測項目。")

    st.markdown("---")
    st.subheader("📅 近一個月 (未來 30 天) 取測日程表")
    if month_schedule:
        df_month = pd.DataFrame(month_schedule).sort_values(by=["取測日期", "預計時間"]).reset_index(drop=True)
        st.dataframe(df_month, use_container_width=True, hide_index=True)
    else:
        st.info("未來 30 天內無排定任何取測項目。")

# -----------------------------------------------------------------------------
# 功能 2：投測總表與查詢 (含目前測試時數與完成進度)
# -----------------------------------------------------------------------------
elif menu == "📋 投測總表與查詢":
    st.header("📋 投測項目總表")
    
    if not projects_list:
        st.warning("目前尚無任何投測項目。")
    else:
        table_rows = []
        for p in projects_list:
            p_id = p['id']
            sorted_hours = sorted(p['hours_list']) if p['hours_list'] else [0]
            max_target_h = max(sorted_hours)
            
            current_done_h = 0
            if p_id in test_data_dict:
                for h in sorted_hours:
                    if f"{h}H" in test_data_dict[p_id]:
                        current_done_h = h
                        
            progress_pct = round((current_done_h / max_target_h * 100), 1) if max_target_h > 0 else 0
            
            table_rows.append({
                'id': p['id'],
                'owner': p['owner'],
                'spec': p['spec'],
                'condition': p['condition'],
                'sample_size': p['sample_size'],
                'current_hours': f"{current_done_h}H",
                'target_hours': f"{max_target_h}H",
                'progress': f"{progress_pct}%",
                'status': p['status'],
                'description': p['description']
            })
            
        df_projects = pd.DataFrame(table_rows)
        search_keyword = st.text_input("🔍 輸入關鍵字查詢 (規格/負責人/描述/批號)：", "")
        
        if search_keyword:
            filtered_df = df_projects[
                df_projects['spec'].str.contains(search_keyword, case=False, na=False) |
                df_projects['owner'].str.contains(search_keyword, case=False, na=False) |
                df_projects['id'].str.contains(search_keyword, case=False, na=False) |
                df_projects['description'].str.contains(search_keyword, case=False, na=False)
            ]
        else:
            filtered_df = df_projects

        display_df = filtered_df[['id', 'owner', 'spec', 'condition', 'sample_size', 'current_hours', 'target_hours', 'progress', 'status', 'description']].copy()
        display_df.columns = ['項目編號', '負責人', '產品規格', '投測條件', '投測數量(顆)', '目前測試時數', '目標總時數', '完成進度', '狀態', '詳細描述']
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# 功能 3：新增投測項目
# -----------------------------------------------------------------------------
elif menu == "➕ 新增投測項目":
    st.header("➕ 新建信賴性投測實驗")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        p_id = st.text_input("項目編號 / 批號", value=str(datetime.now().strftime("%Y%m%d%H%M")))
        owner = st.text_input("產品負責人", value="Eric")
    with col2:
        spec = st.text_input("產品規格", value="ACLL2R0S561E03")
        sample_size = st.number_input("投測數量 (顆數)", min_value=1, max_value=100, value=10)
    with col3:
        start_date = st.date_input("投入日期")
        start_time = st.time_input("投入時間")
    with col4:
        st.write(" ")
        st.info(f"💡 建立後將自動生成 **{sample_size}** 顆數據表格")

    st.markdown("---")
    st.subheader("🧪 測試條件與時數")
    
    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    with col_t1:
        test_item = st.selectbox("測試項目", ["DC", "RC", "SURGE", "高溫高濕60/90", "高溫高濕85/85"])
    with col_t2:
        test_voltage = st.text_input("通電電壓 (V)", value="1.6")
    with col_t3:
        test_temp = st.text_input("測試溫度 (°C)", value="135")
    with col_t4:
        msl3 = st.selectbox("MSL3處理", ["無", "有"], index=1)

    preset_hours = [24, 48, 72, 96, 200, 500, 750, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500]
    selected_preset = st.multiselect("選擇標準測試時間 (HR)", options=preset_hours, default=[24, 72, 200, 1000])
    
    custom_hours_str = st.text_input("➕ 自訂額外取測時間 (HR，請以逗號分隔)", "")
    custom_hours = [int(i.strip()) for i in custom_hours_str.split(",") if i.strip().isdigit()]
    selected_hours_list = sorted(list(set(selected_preset + custom_hours)))

    st.markdown("---")
    st.subheader("🧩 材料與製程詳細參數")
    
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        foil_name = st.text_input("鋁箔名稱", value="A4R2125JLK01B014")
        foil_width = st.selectbox("鋁箔寬度", ["3.55mm", "3.65mm", "3.85mm"], index=0)
    with col_m2:
        stack_layers = st.selectbox("堆疊層數 (上+下)", ["1+1", "1+2", "2+1", "2+2", "2+3", "3+2", "3+3", "3+4", "4+3", "4+4"], index=4)
        leadframe_type = st.selectbox("導線架種類", ["C1814導線架", "C1100選鍍導線架", "紫銅導線架", "黃銅導線架", "加寬導線架", "粗化導線架"])
    with col_m3:
        leadframe_thickness = st.selectbox("導線架厚度 (mm)", ["0.1", "0.15"], index=1)
        molding_die = st.text_input("封裝模具", value="MOLD-A01")

    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    with col_c1:
        impregnation_param = st.text_input("含浸參數", value="PEDOT:PSS / 3次")
    with col_c2:
        carbon_paste = st.text_input("碳膠參數", value="Carbon-A / 150°C")
    with col_c3:
        silver_paste = st.text_input("銀膠參數", value="Ag-Paste-01")
    with col_c4:
        stack_silver_paste = st.text_input("堆疊銀膠", value="Stack-Ag-02")

    if st.button("🚀 建立專案並寫入雲端資料庫", type="primary", use_container_width=True):
        if not selected_hours_list:
            st.error("請至少選擇一個取測時數！")
        else:
            start_dt_str = f"{start_date.strftime('%Y-%m-%d')} {start_time.strftime('%H:%M')}"
            condition_str = f"{test_temp}°C - {test_item}({test_voltage}V) | MSL3: {msl3}"
            hours_str = ",".join(map(str, selected_hours_list))
            formatted_desc = f"鋁箔: {foil_name} ({foil_width}) | 堆疊: {stack_layers} | 導線架: {leadframe_type} ({leadframe_thickness}mm)"
            
            data = {
                "id": p_id,
                "owner": owner,
                "spec": spec,
                "sample_size": sample_size,
                "condition": condition_str,
                "status": "進行中",
                "start_time": start_dt_str,
                "hours_list": hours_str,
                "description": formatted_desc
            }
            try:
                supabase.table("projects").upsert(data).execute()
                st.success(f"✅ 已成功建立專案 #{p_id} 並同步至雲端！")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 專案同步雲端失敗：{e}")

# -----------------------------------------------------------------------------
# 功能 4：修改 / 刪除專案
# -----------------------------------------------------------------------------
elif menu == "✏️ 修改 / 刪除專案":
    st.header("✏️ 修改 / 刪除專案資料")
    
    if not projects_list:
        st.warning("目前尚無可編輯的專案。")
    else:
        project_ids = [p["id"] for p in projects_list]
        selected_p_id = st.selectbox("請選擇要編輯的專案編號 / 批號：", project_ids)
        target_project = next(p for p in projects_list if p["id"] == selected_p_id)

        st.subheader(f"🛠️ 編輯專案：{selected_p_id}")
        
        with st.form("edit_project_form"):
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                new_id = st.text_input("專案編號 / 批號 (更正打錯的編號)", value=target_project["id"])
                new_owner = st.text_input("負責工程師", value=target_project["owner"])
                new_spec = st.text_input("產品規格", value=target_project["spec"])
                new_status = st.selectbox("專案狀態", ["進行中", "已完成", "已暫停", "異常終止"], index=["進行中", "已完成", "已暫停", "異常終止"].index(target_project["status"]) if target_project["status"] in ["進行中", "已完成", "已暫停", "異常終止"] else 0)
            
            with col_e2:
                new_sample_size = st.number_input("投測數量 (顆數)", min_value=1, max_value=100, value=target_project["sample_size"])
                new_condition = st.text_input("投測條件", value=target_project["condition"])
                new_start_time = st.text_input("投入時間 (YYYY-MM-DD HH:MM)", value=target_project["start_time"].strftime("%Y-%m-%d %H:%M"))
                hours_str_val = ",".join(map(str, target_project["hours_list"]))
                new_hours_list_str = st.text_input("取測時數列表 (逗號分隔)", value=hours_str_val)

            new_desc = st.text_area("詳細描述", value=target_project["description"])
            
            submit_edit = st.form_submit_button("💾 儲存修改並更新雲端資料庫", type="primary")

        if submit_edit:
            try:
                if new_id != selected_p_id:
                    update_data = {
                        "id": new_id,
                        "owner": new_owner,
                        "spec": new_spec,
                        "sample_size": new_sample_size,
                        "condition": new_condition,
                        "status": new_status,
                        "start_time": new_start_time,
                        "hours_list": new_hours_list_str,
                        "description": new_desc
                    }
                    supabase.table("projects").insert(update_data).execute()
                    supabase.table("test_data").update({"project_id": new_id}).eq("project_id", selected_p_id).execute()
                    supabase.table("projects").delete().eq("id", selected_p_id).execute()
                else:
                    update_data = {
                        "owner": new_owner,
                        "spec": new_spec,
                        "sample_size": new_sample_size,
                        "condition": new_condition,
                        "status": new_status,
                        "start_time": new_start_time,
                        "hours_list": new_hours_list_str,
                        "description": new_desc
                    }
                    supabase.table("projects").update(update_data).eq("id", selected_p_id).execute()

                st.success("✅ 專案資料已成功修改！")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 修改失敗：{e}")

        st.markdown("---")
        st.subheader("⚠️ 危險操作區")
        if st.button(f"🗑️ 徹底刪除專案 #{selected_p_id} (含所有測試數據)", type="secondary"):
            try:
                supabase.table("test_data").delete().eq("project_id", selected_p_id).execute()
                supabase.table("projects").delete().eq("id", selected_p_id).execute()
                st.success(f"✅ 專案 #{selected_p_id} 及其測試數據已全部徹底刪除！")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 刪除專案失敗：{e}")

# -----------------------------------------------------------------------------
# 功能 5：OP 數據填寫與變化率繪圖
# -----------------------------------------------------------------------------
elif menu == "📝 OP 數據填寫與變化率繪圖":
    st.header("📝 OP 實測數據錄入與變化率趨勢圖")
    
    if not projects_list:
        st.warning("請先建立投測專案！")
    else:
        p_ids = [p['id'] for p in projects_list]
        selected_id = st.selectbox("選擇投測專案編號：", p_ids)
        selected_p = next(p for p in projects_list if p['id'] == selected_id)
        
        n_samples = selected_p["sample_size"]
        st.write(f"**規格**：{selected_p['spec']} ({selected_p['condition']}) | **總顆數**：{n_samples} 顆")
        st.markdown("---")
        
        st.subheader("✍️ OP 數據輸入區")
        hours_options = [0] + selected_p['hours_list']
        selected_hour = st.selectbox("選擇目前填寫的取測時間：", [f"{h}H" for h in hours_options])
        
        has_existing_data = (selected_id in test_data_dict) and (selected_hour in test_data_dict[selected_id])
        
        if has_existing_data:
            df_current = test_data_dict[selected_id][selected_hour]
        else:
            if (selected_id in test_data_dict) and ("0H" in test_data_dict[selected_id]):
                df_current = test_data_dict[selected_id]["0H"].copy()
            else:
                df_current = pd.DataFrame({
                    "顆數": [f"#{i+1}" for i in range(n_samples)],
                    "Cap (uF)": [560.0] * n_samples,
                    "DF (%)": [1.2] * n_samples,
                    "ESR (mΩ)": [3.2] * n_samples,
                    "LC (uA)": [12.5] * n_samples
                })

        edited_df = st.data_editor(df_current, num_rows="fixed", use_container_width=True, key=f"editor_{selected_id}_{selected_hour}")
        
        if st.button(f"☁️ 儲存 {selected_hour} 數據並同步雲端", type="primary"):
            if (edited_df["Cap (uF)"] <= 0).any() or (edited_df["ESR (mΩ)"] <= 0).any():
                st.error("⚠️ 發現電容值或 ESR 包含 <= 0 的異常數據，請確認後重新儲存！")
            else:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                rows = []
                for _, r in edited_df.iterrows():
                    rows.append({
                        "project_id": str(selected_id),
                        "hour_key": selected_hour,
                        "sample_no": str(r["顆數"]),
                        "cap": float(r["Cap (uF)"]),
                        "df": float(r["DF (%)"]),
                        "esr": float(r["ESR (mΩ)"]),
                        "lc": float(r["LC (uA)"]),
                        "update_time": now_str
                    })
                try:
                    supabase.table("test_data").upsert(rows).execute()
                    st.success(f"✅ 成功！已同步 #{selected_id} 在 {selected_hour} 的數據至雲端！")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 測試數據同步失敗：{e}")

        st.markdown("---")
        st.subheader("📈 信賴性變化率趨勢圖與統計 (主管 / 工程師檢視區)")
        
        tab_cap, tab_df, tab_esr, tab_lc = st.tabs(["⚡ Cap 變化率 (%)", "📉 DF 損耗角", "🔌 ESR 變化率 (%)", "💧 LC 漏電流"])
        has_0h = (selected_id in test_data_dict) and ("0H" in test_data_dict[selected_id])
        
        if has_0h:
            df_0h = test_data_dict[selected_id]["0H"]
            avail_hours = [h for h in hours_options if f"{h}H" in test_data_dict[selected_id]]
            
            def append_avg_row(df_table):
                avg_row = {"顆數": "🔥 AVG (平均值)"}
                for col in df_table.columns:
                    if col != "顆數":
                        avg_row[col] = round(df_table[col].mean(), 2)
                return pd.concat([df_table, pd.DataFrame([avg_row])], ignore_index=True)

            with tab_cap:
                fig_cap = go.Figure()
                cap_data = []
                for i in range(len(df_0h)):
                    cap_0 = df_0h.loc[i, "Cap (uF)"]
                    rates = []
                    row = {"顆數": f"#{i+1}", "0H (uF)": cap_0}
                    for h in avail_hours:
                        curr = test_data_dict[selected_id][f"{h}H"].loc[i, "Cap (uF)"]
                        rate = ((curr - cap_0) / cap_0) * 100
                        rates.append(rate)
                        if h != 0:
                            row[f"{h}H 變化率(%)"] = round(rate, 2)
                    fig_cap.add_trace(go.Scatter(x=avail_hours, y=rates, mode='lines+markers', name=f'#{i+1}'))
                    cap_data.append(row)
                
                fig_cap.add_hline(y=-20, line_dash="dash", line_color="red", annotation_text="Cap 下限 (-20%)")
                fig_cap.update_layout(title="Cap 變化率趨勢圖 (%)", xaxis_title="時數 (H)", yaxis_title="變化率 (%)")
                st.plotly_chart(fig_cap, use_container_width=True)
                st.dataframe(append_avg_row(pd.DataFrame(cap_data)), use_container_width=True, hide_index=True)

            with tab_df:
                fig_df = go.Figure()
                df_data = []
                for i in range(len(df_0h)):
                    vals = [test_data_dict[selected_id][f"{h}H"].loc[i, "DF (%)"] for h in avail_hours]
                    fig_df.add_trace(go.Scatter(x=avail_hours, y=vals, mode='lines+markers', name=f'#{i+1}'))
                    row = {"顆數": f"#{i+1}"}
                    for idx, h in enumerate(avail_hours):
                        row[f"{h}H (%)"] = vals[idx]
                    df_data.append(row)
                fig_df.update_layout(title="DF 損耗角趨勢圖 (%)", xaxis_title="時數 (H)", yaxis_title="DF (%)")
                st.plotly_chart(fig_df, use_container_width=True)
                st.dataframe(append_avg_row(pd.DataFrame(df_data)), use_container_width=True, hide_index=True)

            with tab_esr:
                fig_esr = go.Figure()
                esr_data = []
                for i in range(len(df_0h)):
                    esr_0 = df_0h.loc[i, "ESR (mΩ)"]
                    rates = []
                    row = {"顆數": f"#{i+1}", "0H (mΩ)": esr_0}
                    for h in avail_hours:
                        curr = test_data_dict[selected_id][f"{h}H"].loc[i, "ESR (mΩ)"]
                        rate = ((curr - esr_0) / esr_0) * 100
                        rates.append(rate)
                        if h != 0:
                            row[f"{h}H 變化率(%)"] = round(rate, 2)
                    fig_esr.add_trace(go.Scatter(x=avail_hours, y=rates, mode='lines+markers', name=f'#{i+1}'))
                    esr_data.append(row)
                
                fig_esr.add_hline(y=200, line_dash="dash", line_color="red", annotation_text="ESR 上限 (+200%)")
                fig_esr.update_layout(title="ESR 變化率趨勢圖 (%)", xaxis_title="時數 (H)", yaxis_title="變化率 (%)")
                st.plotly_chart(fig_esr, use_container_width=True)
                st.dataframe(append_avg_row(pd.DataFrame(esr_data)), use_container_width=True, hide_index=True)

            with tab_lc:
                fig_lc = go.Figure()
                lc_data = []
                for i in range(len(df_0h)):
                    vals = [test_data_dict[selected_id][f"{h}H"].loc[i, "LC (uA)"] for h in avail_hours]
                    fig_lc.add_trace(go.Scatter(x=avail_hours, y=vals, mode='lines+markers', name=f'#{i+1}'))
                    row = {"顆數": f"#{i+1}"}
                    for idx, h in enumerate(avail_hours):
                        row[f"{h}H (uA)"] = vals[idx]
                    lc_data.append(row)
                fig_lc.update_layout(title="LC 漏電流趨勢圖 (uA)", xaxis_title="時數 (H)", yaxis_title="LC (uA)")
                st.plotly_chart(fig_lc, use_container_width=True)
                st.dataframe(append_avg_row(pd.DataFrame(lc_data)), use_container_width=True, hide_index=True)
        else:
            st.info("💡 請先完成並上傳 **0H 數據**，系統將自動為您繪製 Cap/DF/ESR/LC 變化趨勢圖與統計表。")

# -----------------------------------------------------------------------------
# 功能 6：跨批號電性數據比較
# -----------------------------------------------------------------------------
elif menu == "📊 跨批號電性數據比較":
    st.header("📊 多批號 / 實驗組電性平均值對比分析")
    
    if not projects_list:
        st.warning("目前尚無投測項目可供比較。")
    else:
        valid_projects = [p for p in projects_list if (p['id'] in test_data_dict) and ("0H" in test_data_dict[p['id']])]
        
        if not valid_projects:
            st.warning("目前尚未有專案上傳 0H 數據，請先至少建立並填寫一個專案的 0H 數據。")
        else:
            project_options = [f"#{p['id']} - {p['spec']} ({p['condition']})" for p in valid_projects]
            selected_options = st.multiselect(
                "🔍 請選擇要進行平均值對比的批號 / 專案 (可複選)：",
                options=project_options,
                default=project_options[:min(3, len(project_options))]
            )
            
            selected_ids = [opt.split(" - ")[0].replace("#", "") for opt in selected_options]
            
            if not selected_ids:
                st.info("請至少選擇一個批號進行比較。")
            else:
                st.markdown("---")
                tab_comp_cap, tab_comp_esr, tab_comp_df, tab_comp_lc = st.tabs([
                    "⚡ 平均 Cap 變化率 (%)", 
                    "🔌 平均 ESR 變化率 (%)", 
                    "📉 平均 DF (%)", 
                    "💧 平均 LC (uA)"
                ])

                with tab_comp_cap:
                    fig_comp_cap = go.Figure()
                    table_rows = []
                    
                    for p_id in selected_ids:
                        p_info = next(p for p in projects_list if p['id'] == p_id)
                        p_data = test_data_dict[p_id]
                        
                        df_0h = p_data["0H"]
                        avg_cap_0 = df_0h["Cap (uF)"].mean()
                        
                        avail_h = sorted([int(h.replace("H", "")) for h in p_data.keys() if h.endswith("H")])
                        
                        hours_x = []
                        avg_rates_y = []
                        row_dict = {"專案編號/批號": f"#{p_id}", "負責人": p_info['owner'], "條件描述": p_info['condition'], "0H 平均電容 (uF)": round(avg_cap_0, 2)}
                        
                        for h in avail_h:
                            hour_key = f"{h}H"
                            avg_cap_h = p_data[hour_key]["Cap (uF)"].mean()
                            rate = ((avg_cap_h - avg_cap_0) / avg_cap_0) * 100
                            hours_x.append(h)
                            avg_rates_y.append(rate)
                            if h != 0:
                                row_dict[f"{h}H 平均變化率(%)"] = round(rate, 2)
                                
                        fig_comp_cap.add_trace(go.Scatter(
                            x=hours_x, y=avg_rates_y, mode='lines+markers', name=f"#{p_id} ({p_info['spec']})"
                        ))
                        table_rows.append(row_dict)
                        
                    fig_comp_cap.add_hline(y=-20, line_dash="dash", line_color="red", annotation_text="Cap 下限 (-20%)")
                    fig_comp_cap.update_layout(title="跨批號平均 Cap 變化率對比趨勢 (%)", xaxis_title="時數 (H)", yaxis_title="平均 ΔCap (%)")
                    st.plotly_chart(fig_comp_cap, use_container_width=True)
                    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

                with tab_comp_esr:
                    fig_comp_esr = go.Figure()
                    table_rows_esr = []
                    
                    for p_id in selected_ids:
                        p_info = next(p for p in projects_list if p['id'] == p_id)
                        p_data = test_data_dict[p_id]
                        
                        df_0h = p_data["0H"]
                        avg_esr_0 = df_0h["ESR (mΩ)"].mean()
                        
                        avail_h = sorted([int(h.replace("H", "")) for h in p_data.keys() if h.endswith("H")])
                        
                        hours_x = []
                        avg_rates_y = []
                        row_dict = {"專案編號/批號": f"#{p_id}", "負責人": p_info['owner'], "條件描述": p_info['condition'], "0H 平均 ESR (mΩ)": round(avg_esr_0, 2)}
                        
                        for h in avail_h:
                            hour_key = f"{h}H"
                            avg_esr_h = p_data[hour_key]["ESR (mΩ)"].mean()
                            rate = ((avg_esr_h - avg_esr_0) / avg_esr_0) * 100
                            hours_x.append(h)
                            avg_rates_y.append(rate)
                            if h != 0:
                                row_dict[f"{h}H 平均變化率(%)"] = round(rate, 2)
                                
                        fig_comp_esr.add_trace(go.Scatter(
                            x=hours_x, y=avg_rates_y, mode='lines+markers', name=f"#{p_id} ({p_info['spec']})"
                        ))
                        table_rows_esr.append(row_dict)
                        
                    fig_comp_esr.add_hline(y=200, line_dash="dash", line_color="red", annotation_text="ESR 上限 (+200%)")
                    fig_comp_esr.update_layout(title="跨批號平均 ESR 變化率對比趨勢 (%)", xaxis_title="時數 (H)", yaxis_title="平均 ΔESR (%)")
                    st.plotly_chart(fig_comp_esr, use_container_width=True)
                    st.dataframe(pd.DataFrame(table_rows_esr), use_container_width=True, hide_index=True)

                with tab_comp_df:
                    fig_comp_df = go.Figure()
                    table_rows_df = []
                    
                    for p_id in selected_ids:
                        p_info = next(p for p in projects_list if p['id'] == p_id)
                        p_data = test_data_dict[p_id]
                        
                        avail_h = sorted([int(h.replace("H", "")) for h in p_data.keys() if h.endswith("H")])
                        
                        hours_x = []
                        avg_vals_y = []
                        row_dict = {"專案編號/批號": f"#{p_id}", "負責人": p_info['owner'], "條件描述": p_info['condition']}
                        
                        for h in avail_h:
                            hour_key = f"{h}H"
                            avg_df_h = p_data[hour_key]["DF (%)"].mean()
                            hours_x.append(h)
                            avg_vals_y.append(avg_df_h)
                            row_dict[f"{h}H 平均 DF(%)"] = round(avg_df_h, 2)
                                
                        fig_comp_df.add_trace(go.Scatter(
                            x=hours_x, y=avg_vals_y, mode='lines+markers', name=f"#{p_id} ({p_info['spec']})"
                        ))
                        table_rows_df.append(row_dict)
                        
                    fig_comp_df.update_layout(title="跨批號平均 DF 損耗角對比趨勢 (%)", xaxis_title="時數 (H)", yaxis_title="平均 DF (%)")
                    st.plotly_chart(fig_comp_df, use_container_width=True)
                    st.dataframe(pd.DataFrame(table_rows_df), use_container_width=True, hide_index=True)

                with tab_comp_lc:
                    fig_comp_lc = go.Figure()
                    table_rows_lc = []
                    
                    for p_id in selected_ids:
                        p_info = next(p for p in projects_list if p['id'] == p_id)
                        p_data = test_data_dict[p_id]
                        
                        avail_h = sorted([int(h.replace("H", "")) for h in p_data.keys() if h.endswith("H")])
                        
                        hours_x = []
                        avg_vals_y = []
                        row_dict = {"專案編號/批號": f"#{p_id}", "負責人": p_info['owner'], "條件描述": p_info['condition']}
                        
                        for h in avail_h:
                            hour_key = f"{h}H"
                            avg_lc_h = p_data[hour_key]["LC (uA)"].mean()
                            hours_x.append(h)
                            avg_vals_y.append(avg_lc_h)
                            row_dict[f"{h}H 平均 LC(uA)"] = round(avg_lc_h, 2)
                                
                        fig_comp_lc.add_trace(go.Scatter(
                            x=hours_x, y=avg_vals_y, mode='lines+markers', name=f"#{p_id} ({p_info['spec']})"
                        ))
                        table_rows_lc.append(row_dict)
                        
                    fig_comp_lc.update_layout(title="跨批號平均 LC 漏電流對比趨勢 (uA)", xaxis_title="時數 (H)", yaxis_title="平均 LC (uA)")
                    st.plotly_chart(fig_comp_lc, use_container_width=True)
                    st.dataframe(pd.DataFrame(table_rows_lc), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# 功能 7：甘特圖排程檢視 (多色色階與完成進度表)
# -----------------------------------------------------------------------------
elif menu == "📅 甘特圖排程檢視":
    st.header("📅 信賴性投測甘特圖與時間軸")
    
    if not projects_list:
        st.warning("目前尚無投測項目排程。")
    else:
        gantt_data = []
        timetable_data = []
        
        for p in projects_list:
            p_id = p['id']
            start = p['start_time']
            sorted_hours = sorted(p['hours_list']) if p['hours_list'] else [0]
            max_target_h = max(sorted_hours)
            
            current_done_h = 0
            if p_id in test_data_dict:
                for h in sorted_hours:
                    if f"{h}H" in test_data_dict[p_id]:
                        current_done_h = h
                        
            progress_pct = round((current_done_h / max_target_h * 100), 1) if max_target_h > 0 else 0
            
            row_detail = {
                "專案編號": p['id'],
                "負責人": p['owner'],
                "產品規格": p['spec'],
                "投入時間": start.strftime('%Y-%m-%d %H:%M'),
                "目標總時數": f"{max_target_h}H",
                "已完成時數": f"{current_done_h}H",
                "完成百分比": f"{progress_pct}%"
            }
            
            prev_time = start
            for h in sorted_hours:
                target_dt = start + timedelta(hours=h)
                
                gantt_data.append({
                    "Task": f"#{p['id']} ({p['spec']})",
                    "Start": prev_time,
                    "Finish": target_dt,
                    "Stage": f"{h}H 取測",
                    "Owner": p['owner'],
                    "預計取測時間": target_dt.strftime('%Y-%m-%d %H:%M')
                })
                prev_time = target_dt
                
                row_detail[f"{h}H 取測時間"] = target_dt.strftime('%m/%d %H:%M')
                
            timetable_data.append(row_detail)
                
        df_gantt = pd.DataFrame(gantt_data)
        
        fig_gantt = px.timeline(
            df_gantt, 
            x_start="Start", 
            x_end="Finish", 
            y="Task", 
            color="Stage", 
            hover_data=["Owner", "預計取測時間"],
            title="投測項目時間軸甘特圖"
        )
        
        calc_height = max(350, len(projects_list) * 80)
        fig_gantt.update_yaxes(autorange="reversed")
        fig_gantt.update_layout(
            height=calc_height, 
            xaxis_title="時間 (Date/Time)", 
            yaxis_title="投測專案",
            hoverlabel=dict(bgcolor="white", font_size=13)
        )
        st.plotly_chart(fig_gantt, use_container_width=True)

        st.markdown("---")
        
        st.subheader("📋 各專案取測時間與進度對照總表")
        st.caption("💡 包含目標總時數、已完成最高時數與自動計算之完成百分比（%）：")
        
        df_timetable = pd.DataFrame(timetable_data)
        st.dataframe(df_timetable, use_container_width=True, hide_index=True)
