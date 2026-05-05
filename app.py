import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import datetime

st.set_page_config(page_title="Kla Finance v1.0", layout="centered")

def get_gspread_client():
    credentials_dict = st.secrets["gcp_service_account"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    return gspread.authorize(creds)

# --- 1. ระบบดึงชื่อเดือนและ "จำหน้า" ผ่าน URL ---
try:
    client = get_gspread_client()
    spreadsheet = client.open("แผนการเงินรายเดือน")
    month_list = [ws.title for ws in spreadsheet.worksheets()]
    
    # อ่านค่าจาก URL (ถ้าไม่มีให้ใช้เดือนปัจจุบัน)
    query_params = st.query_params
    thai_months = {1:"ม.ค.", 2:"ก.พ.", 3:"มี.ค.", 4:"เม.ย.", 5:"พ.ค.", 6:"มิ.ย.", 7:"ก.ค.", 8:"ส.ค.", 9:"ก.ย.", 10:"ต.ค.", 11:"พ.ย.", 12:"ธ.ค."}
    now = datetime.datetime.now()
    default_month = f"{thai_months[now.month]} {str(now.year + 543)[-2:]}"
    
    saved_month = query_params.get("month", default_month)
    start_index = month_list.index(saved_month) if saved_month in month_list else 0

    # Selectbox ที่จะอัปเดต URL ทันทีที่เปลี่ยน
    selected_month = st.selectbox("📅 เลือกเดือน", month_list, index=start_index)
    st.query_params["month"] = selected_month

except Exception as e:
    st.error(f"Error: {e}")
    st.stop()

# --- 2. ดึงข้อมูลจาก "เซลล์เฉพาะจุด" (ตามไฟล์ Excel ของคุณ) ---
try:
    sheet = spreadsheet.worksheet(selected_month)
    # ดึงค่ามาเป็นลิสต์ของลิสต์ (get_all_values)
    data = sheet.get_all_values()

    # ระบุพิกัดเซลล์ตามโครงสร้างใน แผนการเงินรายเดือน(1).xlsx
    # หมายเหตุ: ใน Python Index เริ่มที่ 0 (แถว 1 คือ 0, คอลัมน์ A คือ 0)
    used_food = float(data[1][1].replace(',', '')) if data[1][1] else 0.0      # เซลล์ B2
    used_personal = float(data[2][1].replace(',', '')) if data[2][1] else 0.0  # เซลล์ B3
    used_other = float(data[3][1].replace(',', '')) if data[3][1] else 0.0     # เซลล์ B4
    
    allowance = float(data[0][5].replace(',', '')) if data[0][5] else 8000.0   # เซลล์ F1
    central_remain = float(data[17][1].replace(',', '')) if data[17][1] else 0.0 # เซลล์ B18
    
    # ดึงงบประมาณตั้งต้นจากด้านล่าง (ตารางค่าใช้จ่ายตายตัว)
    budget_food = float(data[21][1].replace(',', '')) if data[21][1] else 2000.0     # เซลล์ B22
    budget_personal = float(data[22][1].replace(',', '')) if data[22][1] else 900.0  # เซลล์ B23
    budget_other = float(data[23][1].replace(',', '')) if data[23][1] else 300.0     # เซลล์ B24
    emergency_fund = float(data[24][1].replace(',', '')) if data[24][1] else 300.0   # เซลล์ B25

except Exception as e:
    st.warning(f"โครงสร้างชีต {selected_month} อาจไม่ตรง: {e}")
    used_food, used_personal, used_other = 0, 0, 0
    budget_food, budget_personal, budget_other, emergency_fund = 2000, 900, 300, 300
    allowance, central_remain = 8000, 138000

# --- 3. ส่วน Dashboard ---
total_budget = budget_food + budget_personal + budget_other
total_used = used_food + used_personal + used_other
remaining_balance = total_budget - total_used
percent_used = min((total_used / total_budget) * 100, 100.0) if total_budget > 0 else 0

st.title("💰 สรุปสถานะเงิน")
st.markdown(f"**การใช้งบรายวันเดือนนี้ ({percent_used:.0f}%)**")
st.progress(percent_used / 100.0)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="เงินเหลือใช้จ่าย", value=f"{remaining_balance:,.0f} ฿")
with col2:
    st.metric(label="สำรองฉุกเฉิน", value=f"{emergency_fund:,.0f} ฿")
with col3:
    st.metric(label="งบกลางคงเหลือ", value=f"{central_remain:,.0f} ฿")

st.markdown("---")

# --- 4. ส่วนบันทึกข้อมูล ---
st.subheader(f"📝 บันทึกรายจ่าย ({selected_month})")
food_input = st.number_input(f"ค่ากิน (วันนี้) - เหลือ {budget_food-used_food:,.0f} ฿", min_value=0.0, step=1.0)
pers_input = st.number_input(f"ใช้ส่วนตัว (วันนี้) - เหลือ {budget_personal-used_personal:,.0f} ฿", min_value=0.0, step=1.0)
oth_input = st.number_input(f"อื่นๆ - เหลือ {budget_other-used_other:,.0f} ฿", min_value=0.0, step=1.0)
note = st.text_input("หมายเหตุ")

if st.button("บันทึกลง Google Sheets", use_container_width=True):
    try:
        # บันทึกต่อท้ายในชีตเดิม (หรือคุณจะแยกชีต Log ก็ได้)
        new_row = [datetime.datetime.now().strftime("%Y-%m-%d"), food_input, pers_input, oth_input, note]
        sheet.append_row(new_row)
        st.success("บันทึกสำเร็จ!")
        st.rerun()
    except Exception as e:
        st.error(f"Error: {e}")
