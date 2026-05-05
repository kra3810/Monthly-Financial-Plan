import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import datetime

st.set_page_config(page_title="Kla Finance v1.0", layout="centered")

def get_gspread_client():
    credentials_dict = st.secrets["gcp_service_account"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    return gspread.authorize(creds)

# ==========================================
# 1. ระบบดึงรายชื่อเดือน (แท็บ) อัตโนมัติ
# ==========================================
try:
    client = get_gspread_client()
    spreadsheet = client.open("แผนการเงินรายเดือน")
    worksheets = spreadsheet.worksheets()
    month_list = [ws.title for ws in worksheets]
except Exception as e:
    st.error(f"เชื่อมต่อ Sheets ไม่สำเร็จ: {e}")
    month_list = ["เกิดข้อผิดพลาด"]

selected_month = st.selectbox("📅 เลือกเดือนที่ต้องการบันทึก", month_list)

with st.sidebar:
    st.title("⚙️ การตั้งค่าคงที่")
    monthly_allowance = st.number_input("รับเงินจากที่บ้านเดือนนี้", min_value=0.0, step=100.0, value=8000.0)
    accumulated_allowance = st.number_input("เงินที่รับมาสะสมแล้ว (จากบ้าน)", min_value=0.0, step=1000.0, value=0.0)
    
    with st.expander("รายการตายตัวและเงินเก็บ (Fixed & Saving)"):
        st.write("- เงินเก็บสำรองฉุกเฉิน: 1,000 ฿") 
        st.write("- ค่าหอพัก: 4,500 ฿")
        st.write("- งบกิน: 2,000 ฿")
        st.write("- งบส่วนตัว: 900 ฿")
        st.write("- อื่นๆ: 300 ฿")

central_budget_total = 138000 
central_budget_remaining = central_budget_total - accumulated_allowance 
emergency_fund = 1000 
budget = {"food": 2000, "personal": 900, "other": 300}

# ==========================================
# 2. อ่านข้อมูล + เปิดโหมด Debug แอบดูตาราง
# ==========================================
used_food, used_personal, used_other = 0.0, 0.0, 0.0

if selected_month != "เกิดข้อผิดพลาด":
    sheet = spreadsheet.worksheet(selected_month)
    records = sheet.get_all_values()
    
    if len(records) > 0:
        df = pd.DataFrame(records) 
        
        # 🔴 โชว์ตารางข้อมูลดิบบนเว็บ
        st.warning("👇 ตารางข้อมูลดิบที่บอทมองเห็น (เอาไว้หาตำแหน่ง Index)")
        st.dataframe(df)
        
        # โค้ดดึงข้อมูลชั่วคราว (ยังไม่ได้แก้ตำแหน่ง Index)
        if len(df) > 1:
            used_food = pd.to_numeric(df[1][1:], errors='coerce').fillna(0).sum()
            used_personal = pd.to_numeric(df[2][1:], errors='coerce').fillna(0).sum()
            used_other = pd.to_numeric(df[3][1:], errors='coerce').fillna(0).sum()

used = {"food": used_food, "personal": used_personal, "other": used_other}
total_budget = sum(budget.values())
total_used = sum(used.values())
remaining_balance = total_budget - total_used
percent_used = min((total_used / total_budget) * 100, 100.0) if total_budget > 0 else 0

if monthly_allowance > 0:
    total_months_left = int(central_budget_remaining // monthly_allowance)
    years_left = total_months_left // 12
    months_left = total_months_left % 12
    time_left_str = f"ใช้ได้อีก {years_left} ปี {months_left} เดือน"
else:
    time_left_str = "ยังไม่ได้ระบุยอดรับรายเดือน"

st.title("💰 สรุปสถานะเงิน")
st.markdown(f"**การใช้งบรายวันเดือนนี้ ({percent_used:.0f}%)**")
st.progress(percent_used / 100.0)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="เงินเหลือใช้จ่าย", value=f"{remaining_balance:,.0f} ฿", delta="On Track")
with col2:
    st.metric(label="เงินเก็บสำรองฉุกเฉิน", value=f"{emergency_fund:,.0f} ฿")
with col3:
    st.metric(label="งบกลางคงเหลือ", value=f"{central_budget_remaining:,.0f} ฿", delta=time_left_str, delta_color="off")

st.markdown("---")

def get_label(name, b, u):
    diff = b - u
    if diff >= 0:
        return f"{name} (เหลือ {diff:,.0f} ฿)"
    else:
        return f"{name} (⚠️ เกิน {-diff:,.0f} ฿)"

st.subheader(f"📝 บันทึกรายจ่ายใหม่ ({selected_month})")
with st.container():
    food = st.number_input(get_label("ค่ากิน (วันนี้)", budget['food'], used['food']), min_value=0.0, step=1.0, value=0.0)
    personal = st.number_input(get_label("ใช้ส่วนตัว (วันนี้)", budget['personal'], used['personal']), min_value=0.0, step=1.0, value=0.0)
    other = st.number_input(get_label("อื่นๆ", budget['other'], used['other']), min_value=0.0, step=1.0, value=0.0)
    note = st.text_input("หมายเหตุ (ถ้ามี)")

    if st.button("บันทึกลง Google Sheets", use_container_width=True):
        try:
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            new_row = [today_str, food, personal, other, note]
            sheet.append_row(new_row)
            st.rerun() 
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")

st.markdown("---")
with st.expander("🔍 ตรวจสอบส่วนต่างเงินจริง (Cash Check)"):
    actual_cash = st.number_input("เงินสดในมือ", min_value=0.0, step=1.0, value=0.0)
    actual_bank = st.number_input("เงินในบัญชี", min_value=0.0, step=1.0, value=0.0)
    theoretical_balance = remaining_balance + emergency_fund 
    diff = (actual_cash + actual_bank) - theoretical_balance
    if diff == 0:
        st.write("✅ ยอดตรงเป๊ะ!")
    else:
        st.write(f"⚠️ ส่วนต่าง: {diff:,.2f} ฿")
