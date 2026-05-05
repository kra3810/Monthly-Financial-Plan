import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import datetime
import re

st.set_page_config(page_title="Kla Finance v1.0", layout="centered")

def get_gspread_client():
    credentials_dict = st.secrets["gcp_service_account"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    return gspread.authorize(creds)

# --- 1. ระบบดึงชื่อเดือนและจำหน้าผ่าน URL (Persistent UI) ---
try:
    client = get_gspread_client()
    spreadsheet = client.open("แผนการเงินรายเดือน")
    month_list = [ws.title for ws in spreadsheet.worksheets()]
    
    # ดึงค่าเดือนจาก URL ถ้าไม่มีให้ใช้เดือนปัจจุบัน
    query_params = st.query_params
    thai_months = {1:"ม.ค.", 2:"ก.พ.", 3:"มี.ค.", 4:"เม.ย.", 5:"พ.ค.", 6:"มิ.ย.", 7:"ก.ค.", 8:"ส.ค.", 9:"ก.ย.", 10:"ต.ค.", 11:"พ.ย.", 12:"ธ.ค."}
    now = datetime.datetime.now()
    default_month_name = f"{thai_months[now.month]} {str(now.year + 543)[-2:]}"
    
    saved_month = query_params.get("month", default_month_name)
    start_index = month_list.index(saved_month) if saved_month in month_list else 0

    selected_month = st.selectbox("📅 เลือกเดือนที่ต้องการบันทึก", month_list, index=start_index)
    
    # อัปเดต URL ทันทีเมื่อเปลี่ยนเดือน
    if st.query_params.get("month") != selected_month:
        st.query_params["month"] = selected_month

except Exception as e:
    st.error(f"เชื่อมต่อ Sheets ไม่สำเร็จ: {e}")
    st.stop()

# --- 2. การคำนวณข้อมูล (แก้ Bug ยอดสี่แสน) ---
used_food, used_personal, used_other = 0.0, 0.0, 0.0
central_remain, allowance = 0.0, 0.0

try:
    sheet = spreadsheet.worksheet(selected_month)
    records = sheet.get_all_values()
    
    if len(records) > 1:
        # แปลงเป็น DataFrame เพื่อให้จัดการง่าย
        df = pd.DataFrame(records)
        
        # ค้นหาแถวที่เริ่มมีคำว่า "งบกลาง" หรือ "Fixed" เพื่อเป็นจุดหยุดบวกเลข
        # ป้องกันไม่ให้ไปบวกเลข 138,000 เข้ามาในยอดใช้จ่ายรายวัน
        stop_row = len(df)
        for i, row in df.iterrows():
            if "งบกลาง" in str(row[0]) or "Fixed" in str(row[0]):
                stop_row = i
                break
        
        # ตัดมาเฉพาะช่วงที่เป็นรายการใช้จ่ายรายวัน (แถวที่ 2 จนถึงก่อนแถวหยุด)
        expense_data = df.iloc[1:stop_row]
        
        # บวกรวมยอดแต่ละคอลัมน์ (B=1, C=2, D=3)
        def clean_sum(series):
            return pd.to_numeric(series.replace('[,฿]', '', regex=True), errors='coerce').fillna(0).sum()

        used_food = clean_sum(expense_data[1])
        used_personal = clean_sum(expense_data[2])
        used_other = clean_sum(expense_data[3])

        # ดึงค่าคงที่จากเซลล์ที่กำหนดไว้ในไฟล์ (อ้างอิงจาก แผนการเงินรายเดือน(1).xlsx)
        # เซลล์ F1 (Index 0,5) = เงินจากบ้าน
        allowance = pd.to_numeric(str(df.iloc[0, 5]).replace(',', ''), errors='coerce') or 8000.0
        # เซลล์ B18 (Index 17,1) = งบกลางคงเหลือ
        central_remain = pd.to_numeric(str(df.iloc[17, 1]).replace(',', ''), errors='coerce') or 0.0

except Exception as e:
    st.warning(f"คำนวณยอดผิดพลาด (โครงสร้างชีตอาจเปลี่ยน): {e}")

# ตั้งค่า Budget (อ้างอิงจากไฟล์คุณ)
budget = {"food": 2000, "personal": 900, "other": 300}
total_budget = sum(budget.values())
total_used = used_food + used_personal + used_other
remaining_balance = total_budget - total_used
percent_used = min((total_used / total_budget) * 100, 100.0) if total_budget > 0 else 0

# --- 3. Dashboard ---
st.title("💰 Kla Finance v1.0")
st.markdown(f"**การใช้งบรายวันเดือนนี้ ({percent_used:.0f}%)**")
st.progress(percent_used / 100.0)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="เงินเหลือใช้จ่าย", value=f"{remaining_balance:,.0f} ฿")
with col2:
    st.metric(label="สำรองฉุกเฉิน", value="1,000 ฿") # ค่าคงที่ตามไฟล์คุณ
with col3:
    st.metric(label="งบกลางคงเหลือ", value=f"{central_remain:,.0f} ฿")

st.markdown("---")

# --- 4. ส่วนบันทึก (Input) ---
def get_label(name, b, u):
    diff = b - u
    return f"{name} (เหลือ {diff:,.0f} ฿)" if diff >= 0 else f"{name} (⚠️ เกิน {-diff:,.0f} ฿)"

st.subheader(f"📝 บันทึกรายจ่าย ({selected_month})")
with st.container():
    food_in = st.number_input(get_label("กิน", budget['food'], used_food), min_value=0.0, step=1.0)
    pers_in = st.number_input(get_label("ส่วนตัว", budget['personal'], used_personal), min_value=0.0, step=1.0)
    oth_in = st.number_input(get_label("อื่นๆ", budget['other'], used_other), min_value=0.0, step=1.0)
    note_in = st.text_input("หมายเหตุ")

    if st.button("บันทึกลง Google Sheets", use_container_width=True):
        try:
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            # หาแถวว่างถัดไปก่อนส่วน "งบกลาง" (เพื่อไม่ให้ไปบันทึกทับข้างล่าง)
            # ในที่นี้ใช้ append_row ตามปกติ แต่ในชีตควรมีแถวว่างรองรับไว้
            new_row = [today_str, food_in, pers_in, oth_in, note_in]
            sheet.append_row(new_row, value_input_option='USER_ENTERED')
            st.rerun() 
        except Exception as e:
            st.error(f"บันทึกไม่ได้: {e}")
