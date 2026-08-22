import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client

# -----------------------------------------------------------------------------
# 頁面基本配置
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="可靠度實驗室 (SPCAP) 投測管理系統",
    page_icon="🧪",
    layout="wide"
)

# -----------------------------------------------------------------------------
# Supabase 連線初始化
# -----------------------------------------------------------------------------
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    if not url or not key:
        st.error("❌ 找不到 Supabase 連線設定！請檢查 .streamlit/secrets.toml 設定檔。")
        st.stop()
    return create_client(url, key)

supabase = init_supabase()

# -----------------------------------------------------------------------------
# 資料載入與處理邏輯
# -----------------------------------------------------------------------------
def load_projects():
    try:
        res = supabase.table("projects").select("*").execute()
        raw = res.data or []
        projects = []
        for r in raw:
            hours = [int(h.strip()) for h in str(r.get("hours_list", "")).split(",") if h.strip().isdigit()]
            
            start_str = str(r.get("start_time", "")).replace("T", " ").strip()
            start_dt = None
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
                try:
                    start_dt = datetime.strptime(start_str.split(".")[0], fmt)
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

def load_test_data():
    try:
        res = supabase.table("test_data").select("*").execute()
        raw = res.data or []
        data_map = {}
        for r in raw:
            p_id = str(r.get("project_id", ""))
            hour_node = str(r.get("hour_node", ""))
            if p_id not in data_map:
                data_map[p_id] = {}
            data_map[p_id][hour_node] = r
        return data_map
    except Exception as e:
        st.sidebar.error(f"⚠️ 測試數據讀取異常：{e}")
        return {}

# 載入當前資料
projects_list = load_projects()
test_data_dict = load_test_data()

# -----------------------------------------------------------------------------
# 側邊欄與選單
# -----------------------------------------------------------------------------
st.sidebar.title("🧪 SPCAP 投測管理")
menu = st.sidebar.radio(
    "選單功能",
    [
        "📌 提醒與逾期看板",
        "📋 投測總表與查詢",
        "➕ 新增投測專案",
        "✏️ 修改 / 刪除專案",
        "📝 錄入時數數據",
        "📊 數據分析與匯出"
    ]
)

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
    
    past_14_days = now - timedelta(days=14)
    future_30_days = now + timedelta(days=30)
    
    for p in projects_list:
        p_id = p['id']
        start = p['start_time']
        
        for h in p['hours_list']:
            target_dt = start + timedelta(hours=h)
            date_str = target_dt.strftime("%Y-%m-%d")
            hour_key = f"{h}H"
            
            has_data = (p_id in test_data_dict) and (hour_key in test_data_dict[p_id])
            
            if past_14_days.date() <= target_dt.date() <= future_30_days.date():
                sort_p_id = int(p_id) if str(p_id).isdigit() else p_id
                month_schedule.append({
                    "sort_p_id": sort_p_id,
                    "取測日期": target_dt.strftime("%Y-%m-%d"),
                    "預計時間": target_dt.strftime("%H:%M"),
                    "項目編號": p['id'],
                    "負責人": p['owner'],
                    "產品規格": p['spec'],
                    "投測條件": p['condition'],
                    "取測時數": hour_key,
                    "狀態": "✅ 已完成" if has_data else ("🔴 逾期未完成" if target_dt < now else "⏳ 待取測")
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
    st.subheader("📅 近一個月取測日程表 (包含過往與未來排程)")
    if month_schedule:
        df_month = pd.DataFrame(month_schedule)
        df_month = df_month.sort_values(by=["取測日期", "預計時間", "sort_p_id"]).drop(columns=["sort_p_id"]).reset_index(drop=True)
        st.caption("💡 提示：點擊表格上方名稱欄位即可手動切換正向或反向排序。")
        st.dataframe(df_month, use_container_width=True, hide_index=True)
    else:
        st.info("近一個月內無排定任何取測項目。")

# -----------------------------------------------------------------------------
# 功能 2：投測總表與查詢
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
            sort_key = int(p_id) if str(p_id).isdigit() else p_id
            
            table_rows.append({
                'sort_key': sort_key,
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
        df_projects = df_projects.sort_values(by="sort_key", ascending=True).drop(columns=['sort_key'])
        
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
        
        st.caption("💡 提示：點擊欄位標頭（如：項目編號）可自由排序。")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# 功能 3：新增投測專案
# -----------------------------------------------------------------------------
elif menu == "➕ 新增投測專案":
    st.header("➕ 新增投測專案")
    
    with st.form("add_project_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            p_id = st.text_input("項目編號 / 批號 (Unique ID)*：", placeholder="例如: 1 或 ACKL-202608-01")
            owner = st.text_input("負責人 (Owner)*：", value="Eric")
            spec = st.text_input("產品規格 (Spec)*：", placeholder="例如: ACLL2R0S561E03")
            sample_size = st.number_input("投測數量 (顆)*：", min_value=1, value=10)
        
        with col2:
            condition = st.text_input("投測條件*：", placeholder="例如: 155°C - DC(1.6V) | MSL3: 無")
            start_date = st.date_input("投入日期*", datetime.now().date())
            start_time = st.time_input("投入時間*", datetime.now().time())
            hours_str = st.text_input("測試時數節點 (小時，以逗號隔開)*：", value="0, 72, 200, 500, 1000")
            
        description = st.text_area("備註說明：", placeholder="填寫產品細節、實驗目的或補充說明")
        
        submitted = st.form_submit_button("🚀 建立投測專案並上傳雲端", use_container_width=True)
        
        if submitted:
            if not p_id or not owner or not spec or not condition or not hours_str:
                st.error("❌ 請填寫所有必填欄位 (*)")
            else:
                try:
                    parsed_hours = [int(h.strip()) for h in hours_str.replace("，", ",").split(",") if h.strip().isdigit()]
                    if not parsed_hours:
                        st.error("❌ 請提供至少一個有效的數字時數節點！")
                    else:
                        start_datetime = datetime.combine(start_date, start_time)
                        time_formatted = start_datetime.strftime("%Y-%m-%d %H:%M:%S")
                        
                        insert_data = {
                            "id": p_id.strip(),
                            "owner": owner.strip(),
                            "spec": spec.strip(),
                            "sample_size": sample_size,
                            "condition": condition.strip(),
                            "start_time": time_formatted,
                            "hours_list": ",".join(map(str, parsed_hours)),
                            "status": "進行中",
                            "description": description.strip()
                        }
                        
                        supabase.table("projects").insert(insert_data).execute()
                        st.cache_data.clear()
                        st.success(f"✅ 專案 #{p_id} 已成功建立並上傳至雲端！")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ 建立專案失敗：{e}")

# -----------------------------------------------------------------------------
# 功能 4：修改 / 刪除專案
# -----------------------------------------------------------------------------
elif menu == "✏️ 修改 / 刪除專案":
    st.header("✏️ 修改 / 刪除既有投測專案")
    
    if not projects_list:
        st.info("目前尚無任何可修改的專案。")
    else:
        project_ids = [p['id'] for p in projects_list]
        selected_id = st.selectbox("請選擇要編輯的專案編號：", project_ids)
        
        target_p = next((p for p in projects_list if p['id'] == selected_id), None)
        
        if target_p:
            st.divider()
            st.subheader(f"正在編輯專案：#{target_p['id']}")
            
            init_start = target_p['start_time'] if isinstance(target_p['start_time'], datetime) else datetime.now()
            
            edit_owner = st.text_input("負責人：", value=target_p['owner'], key=f"owner_{selected_id}")
            edit_spec = st.text_input("產品規格：", value=target_p['spec'], key=f"spec_{selected_id}")
            edit_sample_size = st.number_input("投測數量 (顆)：", min_value=1, value=target_p['sample_size'], key=f"size_{selected_id}")
            edit_condition = st.text_input("投測條件：", value=target_p['condition'], key=f"cond_{selected_id}")
            
            col_d, col_t = st.columns(2)
            with col_d:
                edit_start_date = st.date_input("投入日期 (如 72H 取測為 08/18，請設為 2026/08/15)：", value=init_start.date(), key=f"date_{selected_id}")
            with col_t:
                edit_start_time = st.time_input("投入時間：", value=init_start.time(), key=f"time_{selected_id}")
            
            hours_str_init = ", ".join([str(h) for h in target_p['hours_list']])
            edit_hours_str = st.text_input("測試時數節點 (以逗號分隔)：", value=hours_str_init, key=f"hours_{selected_id}")
            
            status_options = ["進行中", "已完成", "已暫停", "異常終止"]
            status_index = status_options.index(target_p['status']) if target_p['status'] in status_options else 0
            edit_status = st.selectbox("專案狀態：", status_options, index=status_index, key=f"status_{selected_id}")
            
            edit_description = st.text_area("詳細描述 / 備註：", value=target_p['description'], key=f"desc_{selected_id}")
            
            if st.button("💾 儲存修改並更新雲端資料庫", type="primary", use_container_width=True, key=f"btn_save_{selected_id}"):
                try:
                    parsed_hours = [int(h.strip()) for h in edit_hours_str.replace("，", ",").split(",") if h.strip().isdigit()]
                    if not parsed_hours:
                        st.error("❌ 請至少輸入一個有效的時數節點！")
                    else:
                        combined_start = datetime.combine(edit_start_date, edit_start_time)
                        time_formatted = combined_start.strftime("%Y-%m-%d %H:%M:%S")
                        
                        update_data = {
                            "owner": edit_owner,
                            "spec": edit_spec,
                            "sample_size": edit_sample_size,
                            "condition": edit_condition,
                            "start_time": time_formatted,
                            "hours_list": ",".join(map(str, parsed_hours)),
                            "status": edit_status,
                            "description": edit_description
                        }
                        
                        supabase.table("projects").update(update_data).eq("id", selected_id).execute()
                        st.cache_data.clear()
                        st.success(f"✅ 專案 #{selected_id} 已成功將投入時間更新為：{time_formatted}！")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ 更新失敗：{e}")
            
            st.divider()
            st.subheader("🗑️ 刪除專案")
            confirm_del = st.checkbox(f"我確定要永久刪除專案 #{selected_id}", key=f"del_chk_{selected_id}")
            if st.button("❌ 確認刪除專案", type="primary", disabled=not confirm_del, key=f"del_btn_{selected_id}"):
                try:
                    supabase.table("test_data").delete().eq("project_id", selected_id).execute()
                    supabase.table("projects").delete().eq("id", selected_id).execute()
                    st.cache_data.clear()
                    st.success(f"🗑️ 專案 #{selected_id} 已完全刪除！")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 刪除失敗：{e}")

# -----------------------------------------------------------------------------
# 功能 5：錄入時數數據
# -----------------------------------------------------------------------------
elif menu == "📝 錄入時數數據":
    st.header("📝 錄入/更新測試數據 (Cap, DF, LC, ESR)")
    
    if not projects_list:
        st.info("目前尚無專案可錄入數據。")
    else:
        project_ids = [p['id'] for p in projects_list]
        selected_id = st.selectbox("請選擇專案編號：", project_ids)
        
        target_p = next((p for p in projects_list if p['id'] == selected_id), None)
        
        if target_p:
            hours_options = [f"{h}H" for h in target_p['hours_list']]
            selected_hour = st.selectbox("請選擇測試時數節點：", hours_options)
            
            existing_record = None
            if selected_id in test_data_dict and selected_hour in test_data_dict[selected_id]:
                existing_record = test_data_dict[selected_id][selected_hour]
                st.info(f"ℹ️ 專案 #{selected_id} 在 {selected_hour} 已有紀錄，儲存將覆蓋舊數據。")
            
            n_samples = target_p['sample_size']
            st.markdown(f"**專案規格：** `{target_p['spec']}` | **測試顆數：** `{n_samples} 顆`")
            
            default_cap = existing_record.get('cap_values', '') if existing_record else ''
            default_df = existing_record.get('df_values', '') if existing_record else ''
            default_lc = existing_record.get('lc_values', '') if existing_record else ''
            default_esr = existing_record.get('esr_values', '') if existing_record else ''
            
            with st.form("input_data_form"):
                st.subheader(f"數據錄入 - #{selected_id} ({selected_hour})")
                st.caption("請貼上以「逗號」、「空格」或「換行」分隔的數值陣列：")
                
                raw_cap = st.text_area("Cap (電容量 µF)：", value=default_cap, placeholder="例如: 560.1, 562.3, 558.9 ...")
                raw_df = st.text_area("DF (損失角正切 %)：", value=default_df, placeholder="例如: 1.2, 1.1, 1.3 ...")
                raw_lc = st.text_area("LC (漏電流 µA)：", value=default_lc, placeholder="例如: 3.2, 4.1, 2.9 ...")
                raw_esr = st.text_area("ESR (等效串聯電阻 mΩ)：", value=default_esr, placeholder="例如: 8.5, 8.2, 8.8 ...")
                
                tester = st.text_input("測試人員：", value=existing_record.get('tester', 'Eric') if existing_record else 'Eric')
                note = st.text_area("測試備註 / 異常現象記錄：", value=existing_record.get('note', '') if existing_record else '')
                
                btn_save = st.form_submit_button("💾 儲存並上傳測試數據", use_container_width=True)
                
                if btn_save:
                    try:
                        record_payload = {
                            "project_id": selected_id,
                            "hour_node": selected_hour,
                            "cap_values": raw_cap.strip(),
                            "df_values": raw_df.strip(),
                            "lc_values": raw_lc.strip(),
                            "esr_values": raw_esr.strip(),
                            "tester": tester.strip(),
                            "note": note.strip(),
                            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        supabase.table("test_data").upsert(
                            record_payload,
                            on_conflict="project_id,hour_node"
                        ).execute()
                        
                        st.cache_data.clear()
                        st.success(f"✅ 專案 #{selected_id} 在 {selected_hour} 的測試數據已成功儲存！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 數據儲存失敗：{e}")

# -----------------------------------------------------------------------------
# 功能 6：數據分析與匯出
# -----------------------------------------------------------------------------
elif menu == "📊 數據分析與匯出":
    st.header("📊 投測數據分析與 Excel 報表匯出")
    
    if not projects_list:
        st.info("目前尚無專案可供分析。")
    else:
        project_ids = [p['id'] for p in projects_list]
        selected_id = st.selectbox("請選擇要分析的專案：", project_ids)
        
        target_p = next((p for p in projects_list if p['id'] == selected_id), None)
        p_records = test_data_dict.get(selected_id, {})
        
        if not p_records:
            st.warning("⚠️ 該專案目前尚未錄入任何時數的測試數據。")
        else:
            st.subheader(f"專案資訊：#{target_p['id']} - {target_p['spec']}")
            
            hours_sorted = sorted(target_p['hours_list'])
            recorded_hours = [f"{h}H" for h in hours_sorted if f"{h}H" in p_records]
            
            selected_param = st.selectbox("請選擇分析參數：", ["ESR (mΩ)", "Cap (µF)", "DF (%)", "LC (µA)"])
            param_key_map = {
                "ESR (mΩ)": "esr_values",
                "Cap (µF)": "cap_values",
                "DF (%)": "df_values",
                "LC (µA)": "lc_values"
            }
            target_key = param_key_map[selected_param]
            
            summary_list = []
            for h_str in recorded_hours:
                rec = p_records[h_str]
                raw_str = rec.get(target_key, "")
                vals = [float(v.strip()) for v in raw_str.replace(",", " ").split() if v.strip().replace('.', '', 1).isdigit()]
                
                if vals:
                    s_vals = pd.Series(vals)
                    summary_list.append({
                        "時數節點": h_str,
                        "測試顆數": len(vals),
                        "平均值 (Mean)": round(s_vals.mean(), 3),
                        "最大值 (Max)": round(s_vals.max(), 3),
                        "最小值 (Min)": round(s_vals.min(), 3),
                        "標準差 (Std)": round(s_vals.std(), 3) if len(vals) > 1 else 0.0
                    })
            
            if summary_list:
                df_summary = pd.DataFrame(summary_list)
                st.write(f"### 📈 {selected_param} 趨勢統計表")
                st.dataframe(df_summary, use_container_width=True, hide_index=True)
                
                st.line_chart(df_summary.set_index("時數節點")["平均值 (Mean)"])
