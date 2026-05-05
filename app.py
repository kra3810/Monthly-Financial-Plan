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

    monthly_allowance = val(1, 5) # เซลล์ F2
    accumulated_allowance = val(17, 1) # เซลล์ B18
    central_remain = val(18, 1) # เซลล์ B19
    
    budget_food     = val(22, 1) # เซลล์ B23
    budget_personal = val(23, 1) # เซลล์ B24
    budget_other    = val(24, 1) # เซลล์ B25
    emergency_fund  = val(12, 1) # เซลล์ B13
    budget_emergency = val(25, 1) # เซลล์ B26

except Exception:
    # กรณีสลับเดือนแล้วพัง (เช่น ยังไม่มีการสร้างตารางในเดือนนั้น) ให้ล้างเป็น 0 ทั้งหมด
    used_food = used_personal = used_other = 0.0
    budget_food = budget_personal = budget_other = 0.0
    central_remain = emergency_fund = 0.0
    monthly_allowance = 8000.0 # ค่าตั้งต้น
    accumulated_allowance = 0.0
    cash_on_hand = bank_transfer = sep_emergency = actual_total = 0.0

def auto_calc(key):
    try:
        # ดึงข้อความในช่องมาคำนวณ แล้วเขียนทับด้วยผลลัพธ์เป็นเลขตัวเดียวทันที
        val = float(eval(str(st.session_state[key]).replace(',', '')))
        st.session_state[key] = f"{val:g}"
    except:
        pass # ถ้าสมการผิด ปล่อยไว้เหมือนเดิม
# --- 2. แถบข้าง (Sidebar) ---
with st.sidebar:
    st.title("⚙️ การตั้งค่าคงที่")
    st.subheader("📥 เงินสนับสนุนจากที่บ้าน")
    
    # สร้าง Key เฉพาะของแต่ละเดือน ป้องกันค่าค้างเวลาสลับเดือน
    m_key = f"m_allow_{selected_month}"
    a_key = f"a_allow_{selected_month}"
    
    # ดึงค่าเริ่มต้นมาใส่
    if m_key not in st.session_state: st.session_state[m_key] = str(monthly_allowance)
    if a_key not in st.session_state: st.session_state[a_key] = str(accumulated_allowance)
    
    # ช่องกรอก: พิมพ์สมการได้ พอกด Enter หรือคลิกที่อื่น มันจะยุบเป็นเลขตัวเดียวทันที
    st.text_input("รับเงินจากบ้านเดือนนี้", key=m_key, on_change=auto_calc, args=(m_key,))
    st.text_input("เงินที่รับมาสะสมแล้ว", key=a_key, on_change=auto_calc, args=(a_key,))
    
    if st.button("อัปเดตเงินสนับสนุน", use_container_width=True):
        try:
            sheet.update_acell('F2', float(st.session_state[m_key]))
            sheet.update_acell('B18', float(st.session_state[a_key]))
            st.success("✅ อัปเดตลง Sheets แล้ว!")
            st.rerun() 
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาด: {e}")
    
    st.markdown("---")
    
    with st.expander("รายการตายตัวและเงินเก็บ (Fixed & Saving)"):
        st.write(f"- เงินเก็บสำรองฉุกเฉิน: {budget_emergency:,.0f} ฿")
        st.write("- ค่าหอพัก: 4,500 ฿")
        st.write(f"- งบกิน: {budget_food:,.0f} ฿")
        st.write(f"- งบส่วนตัว: {budget_personal:,.0f} ฿")
        st.write(f"- อื่นๆ: {budget_other:,.0f} ฿")
    
    st.markdown("---")
    
    with st.expander("รายการตายตัวและเงินเก็บ (Fixed & Saving)"):
        st.write(f"- เงินเก็บสำรองฉุกเฉิน: {budget_emergency:,.0f} ฿")
        st.write("- ค่าหอพัก: 4,500 ฿")
        st.write(f"- งบกิน: {budget_food:,.0f} ฿")
        st.write(f"- งบส่วนตัว: {budget_personal:,.0f} ฿")
        st.write(f"- อื่นๆ: {budget_other:,.0f} ฿")
        
# --- 4. Dashboard & Input ---
total_used = used_food + used_personal + used_other

# ดึงค่าเงินเหลือใช้จ่ายโดยตรงจากเซลล์ F3 ตามไฟล์
remaining_balance = val(2, 5) 

# คำนวณฐานงบที่แท้จริง โดยหัก "งบฉุกเฉินที่ตั้งไว้ (B26)" ออกจากเงินเหลือ 
actual_total_budget = total_used + (remaining_balance - budget_emergency)

# คำนวณเปอร์เซ็นต์
percent_used = min((total_used / actual_total_budget) * 100, 100.0) if actual_total_budget > 0 else 0

# สร้างตัวแปรดึงข้อความสถานะจากช่อง C13 ป้องกัน Error
try:
    emergency_status = str(data[12][2]).strip()
except Exception:
    emergency_status = ""

st.title("💰 สรุปสถานะเงิน")
st.markdown(f"**การใช้งบรายวันเดือนนี้ ({percent_used:.0f}%)**")
st.progress(percent_used / 100.0)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="เงินเหลือใช้จ่าย", value=f"{remaining_balance:,.0f} ฿")
with col2:
    st.metric(label="สำรองที่แยกไว้", value=f"{sep_emergency:,.0f} ฿", delta=emergency_status, delta_color="off")
with col3:
    st.metric(label="งบกลางคงเหลือ", value=f"{central_remain:,.0f} ฿")
st.markdown("---")
# ฟังก์ชันดึงข้อความจากคอลัมน์ C (Index 2)
def get_text(r, c):
    try: return str(data[r][c]).strip()
    except: return ""

# ดึงข้อความจากเซลล์ C3, C4, C5
food_remain_text = get_text(2, 2)  
pers_remain_text = get_text(3, 2)  
oth_remain_text  = get_text(4, 2)  

# ก่อนแก้ (เก็บแค่วันที่)
datetime.datetime.now().strftime("%Y-%m-%d")

# หลังแก้ (เก็บครบ วัน-เดือน-ปี เวลา-นาที-วินาที)
datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# คำนวณส่วนต่างเพื่อกำหนดสี (เขียว = เหลือ, แดง = เกิน)
food_color = "green" if (budget_food - used_food) >= 0 else "red"
pers_color = "green" if (budget_personal - used_personal) >= 0 else "red"
oth_color  = "green" if (budget_other - used_other) >= 0 else "red"

st.subheader(f"📝 บันทึกรายจ่ายใหม่ ({selected_month})")

# ช่องกรอกตัวเลข
food_in = st.number_input(f"ค่ากิน - :{food_color}[{food_remain_text}]", min_value=0.0, step=1.0)
pers_in = st.number_input(f"ใช้ส่วนตัว - :{pers_color}[{pers_remain_text}]", min_value=0.0, step=1.0)
oth_in  = st.number_input(f"อื่นๆ - :{oth_color}[{oth_remain_text}]", min_value=0.0, step=1.0)

# ช่องหมายเหตุ (เงื่อนไขหลักในการบันทึก)
note = st.text_input("หมายเหตุ (ต้องระบุเพื่อบันทึก)")

if st.button("บันทึกข้อมูล", use_container_width=True):
    try:
        # 1. อัปเดตเงินรวม (ทำทุกครั้งที่มีการกรอกเลข)
        if food_in > 0:
            sheet.update_acell('B3', used_food + food_in)
        if pers_in > 0:
            sheet.update_acell('B4', used_personal + pers_in)
        if oth_in > 0:
            sheet.update_acell('B5', used_other + oth_in)

        # 2. บันทึกประวัติ (เช็กเงื่อนไข: จะ append_row เฉพาะตอนที่มี "หมายเหตุ" เท่านั้น)
        if note.strip():
            time_stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_row = [time_stamp, food_in, pers_in, oth_in, note]
            sheet.append_row(new_row)
            st.success("✅ อัปเดตเงิน และบันทึกประวัติเรียบร้อย!")
        else:
            st.success("✅ อัปเดตเงินเรียบร้อย! (ไม่ได้ลงประวัติเพราะไม่มีหมายเหตุ)")

        st.rerun()
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")

st.markdown("---")

# --- 5. ตรวจสอบเงินในมือ (เพิ่มใหม่แบบแก้ไขได้) ---
st.subheader("💵 ตรวจสอบเงินในมือ")

c_key = f"cash_{selected_month}"
b_key = f"bank_{selected_month}"

if c_key not in st.session_state: st.session_state[c_key] = str(cash_on_hand)
if b_key not in st.session_state: st.session_state[b_key] = str(bank_transfer)

col_cash1, col_cash2 = st.columns(2)
with col_cash1:
    st.text_input("เงินสด", key=c_key, on_change=auto_calc, args=(c_key,))
with col_cash2:
    st.text_input("เงินโอน", key=b_key, on_change=auto_calc, args=(b_key,))

# คำนวณเงินที่มีจริง และส่วนต่าง
try:
    cash_in_val = float(st.session_state[c_key])
    bank_in_val = float(st.session_state[b_key])
except:
    cash_in_val = cash_on_hand
    bank_in_val = bank_transfer

new_actual_total = cash_in_val + bank_in_val
expected_cash = remaining_balance
diff = new_actual_total - expected_cash

col_tot1, col_tot2 = st.columns(2)
with col_tot1:
    st.metric("เงินที่มีจริงตอนนี้", f"{new_actual_total:,.2f} ฿")
with col_tot2:
    st.metric("ส่วนต่าง", f"{diff:,.2f} ฿", delta=f"{diff:,.2f} ฿")

if st.button("อัปเดตเงินในมือ", use_container_width=True):
    try:
        sheet.update_acell('B11', cash_in_val)
        sheet.update_acell('B12', bank_in_val)
        st.success("✅ อัปเดตยอดเงินในมือเรียบร้อย!")
        st.rerun()
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")
