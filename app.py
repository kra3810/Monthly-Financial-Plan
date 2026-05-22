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
    st.error(f"ระบบขัดข้องในการเชื่อมต่อ Google Sheets: {e}")
    st.stop()

# --- 3. ดึงข้อมูลตัวเลข (ดึงตรงๆ ถ้าไม่มีค่าให้เป็น 0) ---
try:
    sheet = spreadsheet.worksheet(selected_month)
    data = sheet.get_all_values()

    # ฟังก์ชันสั้นๆ สำหรับดึงค่า: ดัก Error แล้ว Print ออก Console
    def val(r, c):
        try:
            v = data[r][c].replace(',', '').strip()
            return float(v) if v else 0.0
        except Exception as e:
            print(f"Warning: ไม่สามารถดึงค่าจากพิกัด ({r},{c}) ได้ -> {e}")
            return 0.0

    # ดึงค่าตามพิกัด
    used_food     = val(2, 1)   # เซลล์ B3
    used_personal = val(3, 1)   # เซลล์ B4
    used_other    = val(4, 1)   # เซลล์ B5
    
    cash_on_hand  = val(10, 1)  # เซลล์ B11
    bank_transfer = val(11, 1)  # เซลล์ B12
    sep_emergency = val(12, 1)  # เซลล์ B13
    actual_total  = val(13, 1)  # เซลล์ B14

    monthly_allowance = val(1, 5) # เซลล์ F2
    accumulated_allowance = val(17, 1) # เซลล์ B18
    central_remain = val(18, 1) # เซลล์ B19
    
    budget_food     = val(22, 1) # เซลล์ B23
    budget_personal = val(23, 1) # เซลล์ B24
    budget_other    = val(24, 1) # เซลล์ B25
    emergency_fund  = val(12, 1) # เซลล์ B13
    budget_emergency = val(25, 1) # เซลล์ B26

except Exception as e:
    # เก็บ Log + แจ้งเตือนหน้าเว็บ
    st.warning(f"⚠️ ไม่พบข้อมูลของเดือนนี้ หรือตารางยังไม่สมบูรณ์ (ระบบใช้ค่าเริ่มต้นเป็น 0) | Error: {e}")
    print(f"Sheet Initialization Error: {e}")
    
    used_food = used_personal = used_other = 0.0
    budget_food = budget_personal = budget_other = 0.0
    central_remain = emergency_fund = 0.0
    monthly_allowance = 8000.0 
    accumulated_allowance = 0.0
    cash_on_hand = bank_transfer = sep_emergency = actual_total = 0.0

# --- ฟังก์ชันกรองความปลอดภัยก่อนคำนวณ ---
def safe_eval(expr_str):
    # ลบช่องว่างและคอมม่าออก
    clean_str = str(expr_str).replace(',', '').replace(' ', '')
    
    # ถ้าช่องว่างเปล่า ให้คืนค่า 0.0
    if not clean_str:
        return 0.0
        
    # ด่านตรวจความปลอดภัย: อนุญาตเฉพาะตัวเลข 0-9, จุดทศนิยม และเครื่องหมาย + - * / ( )
    if not re.fullmatch(r'[0-9+\-*/().]+', clean_str):
        raise ValueError("ตรวจพบตัวอักษรหรือสัญลักษณ์ที่ไม่อนุญาต")
        
    # ถ้าสมการพิมพ์ผิดหลักคณิตศาสตร์ (เช่น 100++50, 1/0) Python จะโยน Error ให้ except จับเอง
    return float(eval(clean_str))

def auto_calc(key):
    try:
        val = safe_eval(st.session_state[key])
        st.session_state[key] = f"{val:g}"
    except Exception as e:
        print(f"auto_calc error ({key}): {e}") 

def auto_update(key, cell):
    try:
        # ใช้ safe_eval ประมวลผลแทน เพื่อป้องกัน Code Injection และตัวอักษรขยะ
        val = safe_eval(st.session_state[key])
        
        sheet.update_acell(cell, val)
        st.session_state[key] = str(val)
        st.toast(f"✅ อัปเดตข้อมูลช่อง {cell} เรียบร้อย!")
    except Exception as e:
        st.toast(f"❌ รูปแบบสมการไม่ถูกต้อง หรือมีตัวอักษรปนอยู่")
        print(f"auto_update error ({key}): {e}")

# --- 2. แถบข้าง (Sidebar) ---
with st.sidebar:
    st.title("⚙️ การตั้งค่าคงที่")
    st.subheader("📥 เงินสนับสนุนจากที่บ้าน")
    
    m_key = f"m_allow_{selected_month}"
    a_key = f"a_allow_{selected_month}"
    
    if m_key not in st.session_state: st.session_state[m_key] = str(monthly_allowance)
    if a_key not in st.session_state: st.session_state[a_key] = str(accumulated_allowance)
        
    st.text_input("รับเงินจากบ้าน (พิมพ์สมการแล้วกด Enter)", key=m_key, on_change=auto_update, args=(m_key, 'F2'))
    st.text_input("เงินสะสม (พิมพ์สมการแล้วกด Enter)", key=a_key, on_change=auto_update, args=(a_key, 'B18'))
    
    st.markdown("---")
    
    with st.expander("รายการตายตัวและเงินเก็บ (Fixed & Saving)"):
        st.write(f"- เงินเก็บสำรองฉุกเฉิน: {budget_emergency:,.0f} ฿")
        st.write("- ค่าหอพัก: 4,500 ฿")
        st.write(f"- งบกิน: {budget_food:,.0f} ฿")
        st.write(f"- งบส่วนตัว: {budget_personal:,.0f} ฿")
        st.write(f"- อื่นๆ: {budget_other:,.0f} ฿")
        
# --- 4. Dashboard & Input ---
total_used = used_food + used_personal + used_other
remaining_balance = val(2, 5) 
remaining_time = str(data[18][2]).strip()

# ในเมื่อ F3 คือยอดที่เหลือให้ใช้จริงๆ แบบไม่รวมเงินฉุกเฉินอยู่แล้ว
# ฐานงบ 100% จึงเท่ากับ (ยอดที่ใช้ไปแล้ว + ยอดที่เหลือให้ใช้) ได้เลย ไม่ต้องลบซ้ำ
actual_total_budget = total_used + remaining_balance

# คำนวณเปอร์เซ็นต์
percent_used = min((total_used / actual_total_budget) * 100, 100.0) if actual_total_budget > 0 else 0

try:
    emergency_status = str(data[12][2]).strip()
except Exception as e:
    print(f"Warning: ดึงสถานะฉุกเฉินไม่ได้ -> {e}")
    emergency_status = ""

st.title("💰 สรุปสถานะเงิน")
st.markdown(f"**การใช้งบรายวันเดือนนี้ ({percent_used:.0f}%)**")
st.progress(percent_used / 100.0)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="เงินเหลือใช้จ่าย", value=f"{remaining_balance:,.0f} ฿")
with col2:
    st.metric(label="เงินสำรองที่แยกไว้", value=f"{sep_emergency:,.0f} ฿", delta=emergency_status, delta_color="off")
with col3:
    st.metric(label="งบกลางคงเหลือ", value=f"{central_remain:,.0f} ฿", delta=remaining_time)
st.markdown("---")

def get_text(r, c):
    try: 
        return str(data[r][c]).strip()
    except Exception as e: 
        print(f"Warning: ดึงข้อความ ({r},{c}) ไม่ได้ -> {e}")
        return ""

food_remain_text = get_text(2, 2)  
pers_remain_text = get_text(3, 2)  
oth_remain_text  = get_text(4, 2)  

food_color = "green" if (budget_food - used_food) >= 0 else "red"
pers_color = "green" if (budget_personal - used_personal) >= 0 else "red"
oth_color  = "green" if (budget_other - used_other) >= 0 else "red"

st.subheader(f"📝 บันทึกรายจ่ายใหม่ ({selected_month})")

food_in = st.number_input(f"ค่ากิน - :{food_color}[{food_remain_text}]", min_value=0.0, step=1.0)
pers_in = st.number_input(f"ใช้ส่วนตัว - :{pers_color}[{pers_remain_text}]", min_value=0.0, step=1.0)
oth_in  = st.number_input(f"อื่นๆ - :{oth_color}[{oth_remain_text}]", min_value=0.0, step=1.0)

# เปลี่ยน Placeholder เพื่อสื่อสารว่าจะใช้ "-" ถ้าปล่อยว่าง
note = st.text_input("หมายเหตุ (หากไม่ใส่ ระบบจะบันทึกเป็น '-')")

if st.button("บันทึกข้อมูล", use_container_width=True):
    # ป้องกันการเผลอกดบันทึกตอนยอดเงินเป็น 0 ทั้งหมด
    if food_in > 0 or pers_in > 0 or oth_in > 0:
        try:
            # 1. จัดรูปแบบเป็น Batch Update เพื่อลดการเรียก API ไปยัง Google Sheets
            updates = []
            if food_in > 0: updates.append({'range': 'B3', 'values': [[used_food + food_in]]})
            if pers_in > 0: updates.append({'range': 'B4', 'values': [[used_personal + pers_in]]})
            if oth_in > 0: updates.append({'range': 'B5', 'values': [[used_other + oth_in]]})
            
            if updates:
                sheet.batch_update(updates)

            # 2. ตั้งค่า Default หมายเหตุและบันทึกประวัติทุกครั้ง
            final_note = note.strip() if note.strip() else "-"
            time_stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_row = [time_stamp, food_in, pers_in, oth_in, final_note]
            
            sheet.append_row(new_row)
            
            st.success("✅ อัปเดตเงิน และบันทึกประวัติลง Sheets เรียบร้อย!")
            st.rerun()
            
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการเชื่อมต่อ Google Sheets: {e}")
            print(f"Update/Append Error: {e}")
    else:
        st.warning("⚠️ กรุณาระบุจำนวนเงินอย่างน้อย 1 รายการก่อนกดบันทึก")

st.markdown("---")

# --- 5. ตรวจสอบเงินในมือ (เพิ่มใหม่แบบแก้ไขได้) ---
st.subheader("💵 ตรวจสอบเงินในมือ")

c_key = f"cash_{selected_month}"
b_key = f"bank_{selected_month}"

if c_key not in st.session_state: st.session_state[c_key] = str(cash_on_hand)
if b_key not in st.session_state: st.session_state[b_key] = str(bank_transfer)

col_cash1, col_cash2 = st.columns(2)
with col_cash1:
    st.text_input("เงินสด (พิมพ์แล้วกด Enter)", key=c_key, on_change=auto_update, args=(c_key, 'B11'))
with col_cash2:
    st.text_input("เงินโอน (พิมพ์แล้วกด Enter)", key=b_key, on_change=auto_update, args=(b_key, 'B12'))

try: cash_val = float(st.session_state[c_key])
except: cash_val = cash_on_hand

try: bank_val = float(st.session_state[b_key])
except: bank_val = bank_transfer

new_actual_total = cash_val + bank_val
expected_cash = remaining_balance
diff = new_actual_total - expected_cash

col_tot1, col_tot2 = st.columns(2)
with col_tot1:
    st.metric("เงินที่มีจริงตอนนี้", f"{new_actual_total:,.2f} ฿")
with col_tot2:
    st.metric("ส่วนต่าง", f"{diff:,.2f} ฿", delta=f"{diff:,.2f} ฿")
