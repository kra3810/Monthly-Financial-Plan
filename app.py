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

# --- 1. ระบบดึงชื่อเดือนและจำหน้าล่าสุด (URL) ---
try:
    client = get_gspread_client()
    spreadsheet = client.open("แผนการเงินรายเดือน")
    month_list = [ws.title for ws in spreadsheet.worksheets()]
    
    # จำหน้าผ่าน URL
    query_params = st.query_params
    thai_months = {1:"ม.ค.", 2:"ก.พ.", 3:"มี.ค.", 4:"เม.ย.", 5:"พ.ค.", 6:"มิ.ย.", 7:"ก.ค.", 8:"ส.ค.", 9:"ก.ย.", 10:"ต.ค.", 11:"พ.ย.", 12:"ธ.ค."}
    now = datetime.datetime.now()
    default_month = f"{thai_months[now.month]} {str(now.year + 543)[-2:]}"
    
    saved_month = query_params.get("month", default_month)
    start_index = month_list.index(saved_month) if saved_month in month_list else 0

    selected_month = st.selectbox("📅 เลือกเดือนที่ต้องการบันทึก", month_list, index=start_index)
    st.query_params["month"] = selected_month

except Exception as e:
    st.error(f"Error: {e}")
    st.stop()

# --- 2. แถบข้าง (Sidebar) ที่หายไป ---
with st.sidebar:
    st.title("⚙️ การตั้งค่าคงที่")
    st.subheader("📥 เงินสนับสนุนจากที่บ้าน")
    # ดึงค่าจากชีตมาใส่เป็นค่าเริ่มต้น (ถ้ามี)
    monthly_allowance = st.number_input("รับเงินจากที่บ้านเดือนนี้", min_value=0.0, step=100.0, value=8000.0)
    accumulated_allowance = st.number_input("เงินที่รับมาสะสมแล้ว (จากบ้าน)", min_value=0.0, step=1000.0, value=0.0)
    
    with st.expander("รายการตายตัวและเงินเก็บ (Fixed & Saving)"):
        st.write("- เงินเก็บสำรองฉุกเฉิน: 300 ฿") 
        st.write("- ค่าหอพัก: 4,500 ฿")
        st.write("- งบกิน: 2,000 ฿")
        st.write("- งบส่วนตัว: 900 ฿")
        st.write("- อื่นๆ: 300 ฿")

# --- 3. ดึงข้อมูลตัวเลข (เจาะจงเซลล์เพื่อไม่ให้มั่ว) ---
try:
    sheet = spreadsheet.worksheet(selected_month)
    data = sheet.get_all_values()

    # พิกัดตามไฟล์ แผนการเงินรายเดือน(1).xlsx
    used_food = float(data[0][1].replace(',', '')) if data[0][1] else 0.0      # เซลล์ B1 (ค่ากินที่ใช้ไป)
    used_personal = float(data[1][1].replace(',', '')) if data[1][1] else 0.0  # เซลล์ B2 (ใช้ส่วนตัวที่ใช้ไป)
    used_other = float(data[2][1].replace(',', '')) if data[2][1] else 0.0     # เซลล์ B3 (อื่นๆ ที่ใช้ไป)
    
    central_remain = float(data[17][1].replace(',', '')) if data[17][1] else 0.0 # เซลล์ B18 (งบกลาง)
    
    # งบประมาณตั้งต้น (ตารางล่าง)
    budget_food = float(data[21][1].replace(',', '')) if data[21][1] else 2000.0
    budget_personal = float(data[22][1].replace(',', '')) if data[22][1] else 900.0
    budget_other = float(data[23][1].replace(',', '')) if data[23][1] else 300.0
    emergency_fund = float(data[24][1].replace(',', '')) if data[24][1] else 300.0

except:
    used_food, used_personal, used_other = 0.0, 0.0, 0.0
    budget_food, budget_personal, budget_other, emergency_fund = 2000.0, 900.0, 300.0, 300.0
    central_remain = 138000.0

# --- 4. Dashboard & Input ---
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

st.subheader(f"📝 บันทึกรายจ่ายใหม่ ({selected_month})")
food_in = st.number_input(f"ค่ากิน (วันนี้) - เหลือ {budget_food-used_food:,.0f} ฿", min_value=0.0, step=1.0)
pers_in = st.number_input(f"ใช้ส่วนตัว (วันนี้) - เหลือ {budget_personal-used_personal:,.0f} ฿", min_value=0.0, step=1.0)
oth_in = st.number_input(f"อื่นๆ - เหลือ {budget_other-used_other:,.0f} ฿", min_value=0.0, step=1.0)
note = st.text_input("หมายเหตุ")

if st.button("บันทึกลง Google Sheets", use_container_width=True):
    try:
        new_row = [datetime.datetime.now().strftime("%Y-%m-%d"), food_in, pers_in, oth_in, note]
        sheet.append_row(new_row)
        st.rerun()
    except Exception as e:
        # ถ้าดึงข้อมูลพลาด หรือหาไม่เจอ ให้เซตทุกอย่างเป็น 0 ให้หมด
        used_food = 0.0
        used_personal = 0.0
        used_other = 0.0
        
        # ส่วนงบประมาณตั้งต้น จะใส่เป็น 0 หรือค่าที่คุณตั้งไว้ก็ได้
        budget_food = 2000.0 
        budget_personal = 900.0
        budget_other = 300.0
        
        # พิมพ์ error ออกมาดูเบาๆ ว่าทำไมมันถึงหลุดมาที่นี่
        print(f"Error logic: {e}")
