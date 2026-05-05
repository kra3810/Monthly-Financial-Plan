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

# --- 3. ดึงข้อมูลตัวเลข (ดึงตรงๆ ถ้าไม่มีค่าให้เป็น 0) ---
try:
    sheet = spreadsheet.worksheet(selected_month)
    data = sheet.get_all_values()

    # ฟังก์ชันสั้นๆ สำหรับดึงค่า: ถ้าว่าง/Error ให้เป็น 0
    def val(r, c):
        try:
            v = data[r][c].replace(',', '').strip()
            return float(v) if v else 0.0
        except: return 0.0

    # ดึงค่าตามพิกัดที่คุณทำไว้ในไฟล์ แผนการเงินรายเดือน(1).xlsx
    used_food     = val(2, 1)   # เซลล์ B3
    used_personal = val(3, 1)   # เซลล์ B4
    used_other    = val(4, 1)   # เซลล์ B5
    
    # ดึงค่าส่วนเงินในมือ (เพิ่มใหม่)
    cash_on_hand  = val(10, 1)  # เซลล์ B11 (เงินสดที่มี)
    bank_transfer = val(11, 1)  # เซลล์ B12 (เงินโอนที่มี)
    sep_emergency = val(12, 1)  # เซลล์ B13 (เงินเก็บสำรองที่แยกออกมา)
    actual_total  = val(13, 1)  # เซลล์ B14 (รวมงบที่มีจริงตอนนี้)

    monthly_allowance = val(16, 1) # เซลล์ B17
    accumulated_allowance = val(17, 1) # เซลล์ B18
    central_remain = val(18, 1) # เซลล์ B19
    
    budget_food     = val(22, 1) # เซลล์ B23
    budget_personal = val(23, 1) # เซลล์ B24
    budget_other    = val(24, 1) # เซลล์ B25
    emergency_fund  = val(25, 1) # เซลล์ B26

except Exception:
    # กรณีสลับเดือนแล้วพัง (เช่น ยังไม่มีการสร้างตารางในเดือนนั้น) ให้ล้างเป็น 0 ทั้งหมด
    used_food = used_personal = used_other = 0.0
    budget_food = budget_personal = budget_other = 0.0
    central_remain = emergency_fund = 0.0
    monthly_allowance = 8000.0 # ค่าตั้งต้น
    accumulated_allowance = 0.0
    cash_on_hand = bank_transfer = sep_emergency = actual_total = 0.0
    
# --- 2. แถบข้าง (Sidebar) ---
with st.sidebar:
    st.title("⚙️ การตั้งค่าคงที่")
    st.subheader("📥 เงินสนับสนุนจากที่บ้าน")
    # ดึงค่าจากชีตมาใส่เป็นค่าเริ่มต้น
    m_allow = st.number_input("รับเงินจากที่บ้านเดือนนี้", min_value=0.0, step=100.0, value=monthly_allowance)
    a_allow = st.number_input("เงินที่รับมาสะสมแล้ว (จากบ้าน)", min_value=0.0, step=1000.0, value=accumulated_allowance)
    
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

st.markdown("---")

# --- 5. ตรวจสอบเงินในมือ (เพิ่มใหม่แบบแก้ไขได้) ---
st.subheader("💵 ตรวจสอบเงินในมือ")

# ทำเป็นคอลัมน์ให้ดูมินิมอล
col_cash1, col_cash2 = st.columns(2)
with col_cash1:
    cash_in = st.number_input("เงินสดที่มี", value=cash_on_hand, min_value=0.0, step=10.0)
with col_cash2:
    bank_in = st.number_input("เงินโอนที่มี", value=bank_transfer, min_value=0.0, step=10.0)

# คำนวณเงินที่มีจริง และส่วนต่าง
new_actual_total = cash_in + bank_in
expected_cash = remaining_balance
diff = new_actual_total - expected_cash

# โชว์ยอดรวมและส่วนต่าง
col_tot1, col_tot2 = st.columns(2)
with col_tot1:
    st.metric("เงินที่มีจริงตอนนี้", f"{new_actual_total:,.2f} ฿")
with col_tot2:
    st.metric("ส่วนต่าง", f"{diff:,.2f} ฿", delta=f"{diff:,.2f} ฿")

# ปุ่มบันทึกเฉพาะส่วนเงินในมือ
if st.button("อัปเดตเงินในมือ", use_container_width=True):
    try:
        # อัปเดตลงช่อง B11 (เงินสด) และ B12 (เงินโอน)
        sheet.update_acell('B11', cash_in)
        sheet.update_acell('B12', bank_in)
        st.success("อัปเดตยอดเงินในมือเรียบร้อย!")
        st.rerun()
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")
