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

# --- 2. ดึงข้อมูลตัวเลข (รวม Cash Check) ---
try:
    sheet = spreadsheet.worksheet(selected_month)
    data = sheet.get_all_values()

    def val(r, c):
        try:
            v = data[r][c].replace(',', '').strip()
            return float(v) if v else 0.0
        except: return 0.0

    # งบที่ใช้ไป
    used_food     = val(2, 1)   # B3
    used_personal = val(3, 1)   # B4
    used_other    = val(4, 1)   # B5
    
    # เงินโอน เงินสด ส่วนต่าง (Cash Check)
    cash_in_hand = val(10, 1)   # B11 (เงินสดที่มี)
    money_transferred = val(11, 1) # B12 (เงินโอนที่มี)
    separated_saving = val(12, 1)  # B13 (เงินเก็บสำรองที่แยกออกมา)
    total_cash_bank = val(13, 1)   # B14 (รวมงบที่มีจริงตอนนี้)
    
    # งบประมาณกลางจากที่บ้าน
    monthly_allowance_val = val(16, 1) # B17
    accumulated_allowance_val = val(17, 1) # B18
    central_remain = val(18, 1) # B19
    
    # งบรายเดือนตายตัว
    budget_food     = val(22, 1) # B23
    budget_personal = val(23, 1) # B24
    budget_other    = val(24, 1) # B25
    emergency_fund  = val(25, 1) # B26

except Exception:
    used_food = used_personal = used_other = 0.0
    cash_in_hand = money_transferred = separated_saving = total_cash_bank = 0.0
    monthly_allowance_val = accumulated_allowance_val = central_remain = 0.0
    budget_food = budget_personal = budget_other = emergency_fund = 0.0
    
# --- 3. แถบข้าง (Sidebar) ---
with st.sidebar:
    st.title("⚙️ การตั้งค่าคงที่")
    st.subheader("📥 เงินสนับสนุนจากที่บ้าน")
    
    # ใช้ค่าที่ดึงมาจาก Sheets (ถ้าดึงไม่ได้จะเป็น 0)
    monthly_allowance = st.number_input("รับเงินจากที่บ้านเดือนนี้", min_value=0.0, step=100.0, value=monthly_allowance_val)
    accumulated_allowance = st.number_input("เงินที่รับมาสะสมแล้ว (จากบ้าน)", min_value=0.0, step=1000.0, value=accumulated_allowance_val)
    
    with st.expander("รายการตายตัวและเงินเก็บ (Fixed & Saving)"):
        st.write(f"- เงินเก็บสำรองฉุกเฉิน: {emergency_fund:,.0f} ฿")
        st.write("- ค่าหอพัก: 4,500 ฿")
        st.write(f"- งบกิน: {budget_food:,.0f} ฿")
        st.write(f"- งบส่วนตัว: {budget_personal:,.0f} ฿")
        st.write(f"- อื่นๆ: {budget_other:,.0f} ฿")

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

# ส่วนที่เพิ่มเข้ามา: ตรวจสอบเงินในมือ (Cash Check)
st.markdown("---")
st.subheader("💵 ตรวจสอบเงินในมือ (Cash Check)")
cc1, cc2, cc3 = st.columns(3)
with cc1:
    st.metric(label="เงินสดที่มี", value=f"{cash_in_hand:,.2f} ฿")
with cc2:
    st.metric(label="เงินโอนที่มี", value=f"{money_transferred:,.2f} ฿")
with cc3:
    st.metric(label="รวมเงินจริงที่มี", value=f"{total_cash_bank:,.2f} ฿")

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
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")
