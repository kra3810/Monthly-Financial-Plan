import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import datetime
import re
import plotly.express as px
import plotly.graph_objects as go


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
    month_list = [ws.title for ws in spreadsheet.worksheets() if ws.title != "Summary_Data"]
    
    # จำหน้าผ่าน URL
    query_params = st.query_params
    thai_months = {1:"ม.ค.", 2:"ก.พ.", 3:"มี.ค.", 4:"เม.ย.", 5:"พ.ค.", 6:"มิ.ย.", 7:"ก.ค.", 8:"ส.ค.", 9:"ก.ย.", 10:"ต.ค.", 11:"พ.ย.", 12:"ธ.ค."}
    now = datetime.datetime.now()
    default_month = f"{thai_months[now.month]} {str(now.year + 543)[-2:]}"
    
    saved_month = query_params.get("month", default_month)
    start_index = month_list.index(saved_month) if saved_month in month_list else 0

    selected_month = st.selectbox("📅 เลือกเดือนที่ต้องการบันทึก", month_list, index=start_index)
    st.query_params["month"] = selected_month

    st.query_params["month"] = selected_month

    # =====================================================================
    # --- ฟีเจอร์สร้างเดือนถัดไป ---
    parts = selected_month.split()
    if len(parts) == 2:
        m_str, y_str = parts[0], parts[1]
        thai_months_rev = {v: k for k, v in thai_months.items()}
        
        if m_str in thai_months_rev:
            m_num = thai_months_rev[m_str]
            y_num = int(y_str)
            
            next_m_num = m_num + 1
            next_y_num = y_num
            if next_m_num > 12:
                next_m_num = 1
                next_y_num += 1
            
            next_month_name = f"{thai_months[next_m_num]} {next_y_num}"
            
            if next_month_name not in month_list:
                if st.button(f"➕ ปิดยอดและขึ้นเดือนใหม่ ({next_month_name})", use_container_width=True):
                    with st.spinner(f"กำลังสรุปยอดและสร้างเดือนใหม่..."):
                        try:
                            prev_sheet = spreadsheet.worksheet(selected_month)
                            prev_data = prev_sheet.get_all_values()

                            def get_v(r, c):
                                try: return float(prev_data[r][c].replace(',', '').strip())
                                except: return 0.0

                            # 1. รวบรวมข้อมูลสรุปของเดือนที่กำลังจะปิด
                            acc_val = get_v(17, 1)    # เงินสะสม (B18)
                            emg_val = get_v(12, 1)    # เงินสำรองฉุกเฉิน (B13)
                            used_total = get_v(2, 1) + get_v(3, 1) + get_v(4, 1) # ยอดใช้จ่ายรวม
                            carry_cash = get_v(10, 1) + get_v(11, 1) # เงินเหลือในมือ
                            personal_inc = get_v(15, 5) # ดึงรายได้ส่วนตัวจาก F16 (Row 16->15, Col F->5)

                            # 2. บันทึกลงหน้า Summary_Data
                            try:
                                summary_sheet = spreadsheet.worksheet("Summary_Data")
                            except:
                                # ถ้าเผลอลบหน้า Summary ไป ให้ระบบสร้างใหม่ให้ (เพิ่มหัวข้อคอลัมน์ F)
                                summary_sheet = spreadsheet.add_worksheet(title="Summary_Data", rows="100", cols="10")
                                summary_sheet.append_row(["Month", "Accumulated", "Emergency", "Used", "Carry_Cash", "Personal_Income"])

                            # เพิ่มตัวแปร personal_inc ไว้ท้ายสุด เพื่อให้บันทึกลงคอลัมน์ F (คอลัมน์ที่ 6)
                            summary_sheet.append_row([selected_month, acc_val, emg_val, used_total, carry_cash, personal_inc])

                            # 3. ขึ้นเดือนใหม่ (แก้ไขเพื่อรักษาสูตร B24 และส่งยอดไป F4)
                            spreadsheet.duplicate_sheet(source_sheet_id=prev_sheet.id, new_sheet_name=next_month_name)
                            new_sheet = spreadsheet.worksheet(next_month_name)

                            # เอา B3, B4, B5 ออก เพื่อป้องกันไม่ให้ไปเขียนทับสูตร SUMIFS ตัวใหม่ด้านบน
                            updates = [
                                {'range': 'F2', 'values': [[0]]},   # รีเซ็ตเงินที่รับจากบ้านเป็น 0
                                {'range': 'B11', 'values': [[0]]},  # รีเซ็ตเงินสดในมือ
                                {'range': 'B12', 'values': [[0]]},  # รีเซ็ตเงินโอน
                                {'range': 'F4', 'values': [[carry_cash]]}, # นำเงินเหลือมาใส่ F4
                                {'range': 'F16', 'values': [[0]]},   # รีเซ็ตช่องรายได้ส่วนตัวเป็น 0
                                {'range': 'C26', 'values': [['']]}  # ล้างค่า C26 ให้ว่างเปล่า
                            ]
                            new_sheet.batch_update(updates)

                            # เปลี่ยนมาเริ่มลบข้อมูลเก่าตั้งแต่แถวที่ 30 ลงไป เพื่อรักษาหัวตารางประวัติในแถว 29 ไว้
                            # เปลี่ยนจากลบแถว เป็นการล้างเฉพาะค่าข้อมูล เพื่อรักษา Dropdown และฟอร์แมตไว้
                            if len(prev_data) >= 30:
                                range_to_clear = f"A30:D{len(prev_data)}"
                                new_sheet.batch_clear([range_to_clear])
                            
                            # เพิ่มคำสั่งนี้ต่อท้าย เพื่อบังคับให้เดือนใหม่มีแถวสแตนด์บายรอไว้อย่างน้อย 100 แถวเสมอ
                            current_rows = new_sheet.row_count
                            if current_rows < 100:
                                new_sheet.add_rows(100 - current_rows)

                            st.success(f"✅ บันทึกสถิติและขึ้นเดือนใหม่สำเร็จ!")
                            st.query_params["month"] = next_month_name
                            st.rerun()

                        except Exception as e:
                            st.error(f"❌ เกิดข้อผิดพลาด: {e}")

    # =====================================================================

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

def emergency_update_func(key, current_b13_val):
    try:
        raw_str = str(st.session_state[key])
        total_val = safe_eval(raw_str) # ยอดสะสมรวมทั้งหมด

        # ดึงเฉพาะตัวเลขหลังเครื่องหมาย + (ค่าที่คุณกรอกจริงในเดือนนี้)
        if '+' in raw_str:
            added_val = safe_eval(raw_str.split('+')[-1])
        else:
            # กรณีพิมพ์ตัวเลขทับไปตรงๆ ให้เอา (ยอดใหม่ - ยอดเดิม)
            added_val = total_val - float(current_b13_val)

        # ยิงข้อมูล 2 ช่องพร้อมกัน: B13 (ยอดสะสมรวม) และ C26 (ยอดของเดือนนี้)
        updates = [
            {'range': 'B13', 'values': [[total_val]]},
            {'range': 'C26', 'values': [[added_val]]}
        ]
        sheet.batch_update(updates)

        st.session_state[key] = str(total_val)
        st.toast(f"✅ บันทึกยอดรวมลง B13 และยอดที่เพิ่ม ({added_val}) ลง C26 เรียบร้อย!")
    except Exception as e:
        st.toast(f"❌ รูปแบบไม่ถูกต้อง")
        print(f"emg_update error: {e}")

# --- 2. แถบข้าง (Sidebar) ---
with st.sidebar:
    st.title("⚙️ การตั้งค่าคงที่")
    st.subheader("📥 เงินสนับสนุนจากที่บ้าน")
    
    m_key = f"m_allow_{selected_month}"
    a_key = f"a_allow_{selected_month}"
    e_key = f"e_allow_{selected_month}"
    
    if m_key not in st.session_state: st.session_state[m_key] = str(monthly_allowance)
    if a_key not in st.session_state: st.session_state[a_key] = str(accumulated_allowance)
    if e_key not in st.session_state: st.session_state[e_key] = str(emergency_fund)
        
    st.text_input("รับเงินจากบ้าน (พิมพ์สมการแล้วกด Enter)", key=m_key, on_change=auto_update, args=(m_key, 'F2'))
    st.text_input("เงินสะสม (พิมพ์สมการแล้วกด Enter)", key=a_key, on_change=auto_update, args=(a_key, 'B18'))
    st.text_input("เงินสำรองฉุกเฉิน (พิมพ์สมการแล้วกด Enter)", key=e_key, on_change=emergency_update_func, args=(e_key, sep_emergency))
    
    # --- หมวดหมู่ใหม่: รายได้ส่วนตัว ---
    st.sidebar.markdown("---")
    st.sidebar.markdown("💼 **รายได้ส่วนตัว (Personal Income)**")
        
    # ดึงค่าปัจจุบัน
    current_personal_income = val(16, 6) 
        
    # เปลี่ยนเป็นช่องพิมพ์ข้อความ/สมการ
    personal_income_input = st.sidebar.text_input(
        "รายได้ส่วนตัว (พิมพ์สมการแล้วกด Enter)", 
        value=str(current_personal_income) if current_personal_income else "0"
    )

    # ระบบคำนวณและบันทึกอัตโนมัติเมื่อกด Enter
    try:
        new_income_val = eval(str(personal_income_input))
        old_income_val = float(current_personal_income) if current_personal_income else 0.0
            
        if new_income_val != old_income_val:
            cell_update(16, 6, new_income_val)
            st.rerun()
    except Exception:
        pass  # กรณีพิมพ์สมการยังไม่เสร็จหรือผิดพลาด ให้ระบบข้ามไปก่อน

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

# สร้างวงแหวน 360 องศา (Donut Progress Ring)
st.markdown("**🎯 สถานะการใช้งบประมาณเดือนนี้**")

# คำนวณส่วนที่เหลือ (ถ้าใช้เกิน 100% ให้ส่วนที่เหลือเป็น 0)
remainder = 100 - percent_used if percent_used < 100 else 0

# กำหนดสีแถบตาม "เปอร์เซ็นต์ที่เหลือ"
if remainder <= 10:
    ring_color = "#FF6B6B"  # โซนอันตราย (สีแดง) เมื่อเหลืองบน้อยกว่าหรือเท่ากับ 10%
elif remainder <= 30:
    ring_color = "#FFD166"  # โซนเฝ้าระวัง (สีเหลือง) เมื่อเหลืองบน้อยกว่าหรือเท่ากับ 30%
else:
    ring_color = "#4ECDC4"  # โซนปลอดภัย (สีเขียว) เมื่อยังเหลือเงินเยอะ

# สลับลำดับ: เอา "งบที่เหลือ (สีเทา)" ขึ้นมาวาดก่อน 
fig_circle = go.Figure(data=[go.Pie(
    values=[remainder, percent_used],
    labels=["งบที่เหลือ", "ใช้ไปแล้ว"],
    marker=dict(colors=["#EFEFEF", ring_color]), # สลับให้สีเทาอยู่ค่าแรก
    hole=0.9,         # ปรับจาก 0.8 เป็น 0.9 เพื่อให้ "เส้นบางลง"
    textinfo='none',  
    hoverinfo='label+percent',
    direction='clockwise', # ให้ระบบเดินตามเข็มปกติ
    sort=False             # ห้ามสลับตำแหน่งเอง
)])

# ใส่ตัวเลขเปอร์เซ็นต์ไว้ตรงกลางวงแหวน และปรับขนาดรวมให้เล็กลง
fig_circle.update_layout(
    showlegend=False,
    annotations=[dict(text=f"{percent_used:.0f}%", x=0.5, y=0.5, font_size=60, showarrow=False)],
    height=375,       # ปรับลดความสูงเพื่อให้วงกลมโดยรวมเล็กลง
    margin=dict(l=20, r=20, t=20, b=20)
)

st.plotly_chart(fig_circle, use_container_width=True)


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

# =====================================================================
# --- จัดการรายจ่าย (รอดำเนินการ + บันทึกเพิ่ม) แบบรวมปุ่มเดียว ---
st.subheader("📝 จัดการรายจ่ายประจำเดือน")

# --- 1. เตรียมข้อมูลรายการ (กรองเฉพาะ "รอดำเนินการ") ---
pending_items_to_save = []
transactions = []

# ข้อมูลเริ่มที่แถว 30 (index 29)
if len(data) >= 30:
    for i in range(29, len(data)):
        row = data[i]
        # ตรวจสอบแถวที่ไม่ว่างและกรองเฉพาะหมวด "รอดำเนินการ"
        if row[0] and (row[2] == "รอดำเนินการ"):
            transactions.append({
                "sheet_row": i + 1,
                "วันที่": row[0],
                "จำนวนเงิน": float(str(row[1]).replace(',', '')) if row[1] else 0.0,
                "หมวดหมู่": row[2],
                "หมายเหตุ": row[3] if len(row) > 3 else "-"
            })

# --- 2. แสดงผลรายการ ---
if transactions:
    for idx, t in enumerate(transactions):
        col1, col2, col3, col4 = st.columns([1.5, 1, 2, 2])

        with col1:
            st.write(t['วันที่'])
        with col2:
            st.write(f"{t['จำนวนเงิน']:,.2f}")
        with col3:
            new_note = st.text_input("หมายเหตุ", value=t.get('หมายเหตุ', ''), key=f"note_{idx}", label_visibility="collapsed")
        with col4:
            cat_options = ["รอดำเนินการ", "ค่ากิน", "ค่าใช้จ่ายส่วนตัว", "ค่าอื่นๆ", "แยกบิล"]
            # ใช้ current_cat เป็นค่าเริ่มต้นเพื่อให้ปุ่มเลือกตัวนั้นไว้ตั้งแต่เปิดหน้าจอ
            current_cat = t.get("หมวดหมู่", "รอดำเนินการ")
            
            new_cat = st.segmented_control(
                "หมวดหมู่",
                options=cat_options,
                selection_mode="single",
                default=current_cat,
                key=f"cat_{idx}",
                label_visibility="collapsed"
            )


        # เก็บค่าเพื่อรอเซฟ
        pending_items_to_save.append({
            "sheet_row": t["sheet_row"],
            "is_split": (new_cat == "แยกบิล"),
            "edit_amt": t["จำนวนเงิน"],
            "edit_cat": new_cat,
            "edit_note": new_note
        })

        st.markdown("<div style='margin-bottom: 10px; border-bottom: 1px solid #f0f2f6;'></div>", unsafe_allow_html=True)
else:
    st.success("🎉 ไม่มีรายการรอดำเนินการค้างอยู่")


st.write("")

# 2. ฟอร์มบันทึกเพิ่ม (ดึงโค้ดเดิมของคุณกลับมาใช้เป๊ะๆ ตามสั่ง) พับเก็บใน st.expander ต่อท้ายรายการรอดำเนินการทันที
with st.expander("➕ บันทึกรายจ่ายใหม่แบบกรอกเอง (Manual Input)"):
    food_in = st.number_input(f"ค่ากิน - :{food_color}[{food_remain_text}]", min_value=0.0, step=1.0)
    pers_in = st.number_input(f"ใช้ส่วนตัว - :{pers_color}[{pers_remain_text}]", min_value=0.0, step=1.0)
    oth_in  = st.number_input(f"อื่นๆ - :{oth_color}[{oth_remain_text}]", min_value=0.0, step=1.0)
    note = st.text_input("หมายเหตุ (หากไม่ใส่ ระบบจะบันทึกเป็น '-')")

st.write("")

# 3. ปุ่มบันทึกข้อมูลทั้งหมด อยู่ล่างสุดตัวเดียว (ใต้กล่องบันทึกเพิ่ม)
if st.button("💾 บันทึกข้อมูลทั้งหมด", type="primary", use_container_width=True):
    batch_updates = []
    new_rows = []
    
    # ตรวจสอบการอัปเดตรายการรอดำเนินการ
    for item in pending_items_to_save:
        if item["is_split"] or item["edit_cat"] != "รอดำเนินการ":
            row_num = item["sheet_row"]
            batch_updates.append({
                'range': f'B{row_num}:D{row_num}',
                'values': [[item["edit_amt"], item["edit_cat"], item["edit_note"]]]
            })
            
    # ตรวจสอบการกรอกข้อมูลเพิ่มจากฟอร์ม Manual (ใช้ตัวแปรตามโค้ดเดิมของคุณ)
    if food_in > 0 or pers_in > 0 or oth_in > 0:
        final_note = note.strip() if note.strip() else "-"
        time_stamp = datetime.datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
        if food_in > 0: new_rows.append([time_stamp, food_in, "ค่ากิน", final_note])
        if pers_in > 0: new_rows.append([time_stamp, pers_in, "ค่าใช้จ่ายส่วนตัว", final_note])
        if oth_in > 0: new_rows.append([time_stamp, oth_in, "ค่าอื่นๆ", final_note])

    # ส่งข้อมูลเข้า Google Sheets พร้อมกันทีเดียว
    if batch_updates or new_rows:
        try:
            with st.spinner("กำลังบันทึกข้อมูลทั้งหมด..."):
                if batch_updates:
                    sheet.batch_update(batch_updates, value_input_option='USER_ENTERED')
                if new_rows:
                    col_a_data = sheet.col_values(1)
                    next_row = len(col_a_data) + 1
                    end_row = next_row + len(new_rows) - 1
                    sheet.batch_update([{'range': f'A{next_row}:D{end_row}', 'values': new_rows}], value_input_option='USER_ENTERED')
            
            st.success("✅ บันทึกข้อมูลทั้งหมดเรียบร้อยแล้ว!")
            st.rerun()
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการเชื่อมต่อ Google Sheets: {e}")
    else:
        st.warning("⚠️ ไม่มีข้อมูลการเปลี่ยนแปลงหรือรายจ่ายใหม่เพื่อบันทึก")

st.markdown("---")
# =====================================================================



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

# =====================================================================
# --- กราฟสรุปรายจ่ายแบบ Dropdown (รวมครบทุกกราฟและเงินยกยอดหลายเดือน) ---
st.markdown("---")
with st.expander("📊 สัดส่วนและกราฟสรุปรายจ่าย (คลิกเพื่อเปิด/ปิด)"):

    # 1. กราฟเส้นแสดงแนวโน้มเงินยกยอดข้ามเดือน (ดึงจาก Summary_Data)
    try:
        sum_sheet = spreadsheet.worksheet("Summary_Data")
        sum_data = sum_sheet.get_all_values()

        if len(sum_data) > 1:
            df_sum = pd.DataFrame(sum_data[1:], columns=sum_data[0])
            df_sum["Carry_Cash"] = pd.to_numeric(df_sum["Carry_Cash"], errors='coerce').fillna(0)
            df_sum.set_index("Month", inplace=True)

            st.markdown("**📈 แนวโน้มเงินยกยอดจากเดือนก่อน (กราฟเส้นสะสม)**")
            st.line_chart(df_sum["Carry_Cash"])
            st.markdown("---")
    except Exception:
        # หากยังไม่เคยมีข้อมูล Summary_Data ระบบจะไม่แสดง Error แต่จะข้ามไป
        pass

    # ตรวจสอบว่ามีการใช้จ่ายในเดือนนี้หรือไม่
    if total_used > 0:
                # 2. กราฟวงกลม: สัดส่วนเงินที่จ่ายไปเดือนนี้
        st.markdown("**🍕 สัดส่วนเงินที่จ่ายไปเดือนนี้**")
        df_pie = pd.DataFrame({
            "หมวดหมู่": ["ค่ากิน", "ใช้ส่วนตัว", "อื่นๆ"],
            "ยอดเงิน": [used_food, used_personal, used_other]
        })
        df_pie = df_pie[df_pie["ยอดเงิน"] > 0]
        
        # กำหนดสีเฉพาะเจาะจงให้แต่ละหมวด (เปลี่ยนโค้ดสี Hex ได้ตามต้องการ)
        pie_colors = {"ค่ากิน": "#FF6B6B", "ใช้ส่วนตัว": "#4ECDC4", "อื่นๆ": "#FFE66D"}
        
        fig_pie = px.pie(
            df_pie, 
            values="ยอดเงิน", 
            names="หมวดหมู่", 
            hole=0.3,
            color="หมวดหมู่",
            color_discrete_map=pie_colors # สั่งให้ใช้สีตามที่กำหนด
        )
        st.plotly_chart(fig_pie, use_container_width=True)
        
        st.markdown("---")
        st.markdown("**💼 สถิติรายได้ส่วนตัวรายเดือน**")

        income_records = []
        try:
            sum_sheet = spreadsheet.worksheet("Summary_Data")
            sum_data = sum_sheet.get_all_values()
            if len(sum_data) > 1:
                start_tracking = False
                for row in sum_data[1:]:
                    # เริ่มเก็บประวัติเพื่อวาดกราฟตั้งแต่เดือนมิถุนายนเป็นต้นไป
                    if "มิ.ย." in row[0] or "มิถุนายน" in row[0]:
                        start_tracking = True
                    
                    if start_tracking:
                        val_income = float(row[5].replace(',', '')) if len(row) > 5 and row[5] else 0.0
                        income_records.append({"เดือน": row[0], "รายได้ส่วนตัว": val_income})
        except Exception:
            pass

        live_income = val(16, 6)
        if not any(r["เดือน"] == selected_month for r in income_records):
            # ป้องกันไม่ให้เพิ่มเดือนลงในกราฟ หากกดกลับไปดูเดือนที่เก่ากว่ามิถุนา
            if "มิ.ย." in selected_month or "มิถุนายน" in selected_month or len(income_records) > 0:
                income_records.append({"เดือน": selected_month, "รายได้ส่วนตัว": live_income})
        else:
            for r in income_records:
                if r["เดือน"] == selected_month:
                    r["รายได้ส่วนตัว"] = live_income

        df_income = pd.DataFrame(income_records)

        if not df_income.empty:
            max_y_axis = df_income["รายได้ส่วนตัว"].max() * 1.2 if df_income["รายได้ส่วนตัว"].max() > 0 else 5000
            fig_inc = px.line(
                df_income,
                x="เดือน",
                y="รายได้ส่วนตัว",
                markers=True,
                range_y=[0, max_y_axis],
                color_discrete_sequence=["#FF9F1C"]
            )
            fig_inc.update_traces(fill='tozeroy', fillcolor='rgba(255, 159, 28, 0.2)')
            fig_inc.update_layout(xaxis_title=None, height=400, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig_inc, use_container_width=True)

        st.markdown("---")

        # 3. กราฟแท่ง: เทียบงบที่ตั้ง vs ของจริง
        st.markdown("**📊 เปรียบเทียบยอดใช้จ่ายจริงกับงบประมาณที่ตั้งไว้**")
        df_bar = pd.DataFrame({
            "หมวดหมู่": ["ค่ากิน", "ใช้ส่วนตัว", "อื่นๆ"],
            "งบที่ตั้งไว้": [budget_food, budget_personal, budget_other],
            "เงินที่ใช้ไปแล้ว": [used_food, used_personal, used_other]
        })

        # กำหนดสีแยกชัดเจน: งบ (สีฟ้าอ่อน/เทา) vs ใช้จริง (สีแดง/ส้ม)
        bar_colors = {"งบที่ตั้งไว้": "#7895CB", "เงินที่ใช้ไปแล้ว": "#FF7676"}
        
        fig_bar = px.bar(
            df_bar, 
            x="หมวดหมู่", 
            y=["งบที่ตั้งไว้", "เงินที่ใช้ไปแล้ว"], 
            barmode="group",
            labels={"value": "จำนวนเงิน (฿)", "variable": "ประเภทยอดเงิน"},
            color_discrete_map=bar_colors # สั่งให้ใช้สีตามที่กำหนด
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        
                # (โค้ดเดิม) fig_bar = px.bar(...)
        # (โค้ดเดิม) st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")
        
                # 4. กราฟเส้น: สถิติและการเติบโตของเงินสำรองฉุกเฉิน
        st.markdown("**🛡️ สถิติและเป้าหมายเงินสำรองฉุกเฉิน**")
        
        # ดึงค่าพิกัดเซลล์จริงมาคำนวณฐานยอดรวม SUM(B22, B23, B25)
        base_expenses = val(21, 1) + val(22, 1) + val(24, 1)

        # ตั้งค่าเกณฑ์เส้นแบ่งตามจำนวนเท่า
        level_red = base_expenses          # ต่ำกว่า 1 เท่า = วิกฤต
        level_yellow = base_expenses * 3   # ต่ำกว่า 3 เท่า = เริ่มตึง
        level_green = base_expenses * 6    # 6 เท่าขึ้นไป = ปลอดภัย

        # --- ส่วนที่เพิ่มใหม่: ดึงประวัติจาก Summary_Data ---
        history_records = []
        try:
            sum_sheet = spreadsheet.worksheet("Summary_Data")
            sum_data = sum_sheet.get_all_values()
            if len(sum_data) > 1:
                for row in sum_data[1:]:
                    # row[2] คือคอลัมน์ Emergency ใน Summary_Data
                    history_records.append({"เดือน": row[0], "เงินฉุกเฉิน": float(row[2].replace(',', ''))})
        except Exception:
            pass

        # นำเดือนปัจจุบันต่อท้ายเข้าไปด้วย เพื่อให้กราฟอัปเดตแบบเรียลไทม์
        if not any(r["เดือน"] == selected_month for r in history_records):
            history_records.append({"เดือน": selected_month, "เงินฉุกเฉิน": emergency_fund})
        else:
            for r in history_records:
                if r["เดือน"] == selected_month:
                    r["เงินฉุกเฉิน"] = emergency_fund

        df_emg = pd.DataFrame(history_records)

        # เช็คเพดานกราฟ
        max_history_val = df_emg["เงินฉุกเฉิน"].max() if not df_emg.empty else 0
        max_y_axis = max(level_green * 1.2, max_history_val * 1.2)
        if max_y_axis == 0: max_y_axis = 10000 

        # สร้างกราฟเส้น (Line Chart) แสดงการเติบโต
        fig_emg = px.line(
            df_emg,
            x="เดือน",
            y="เงินฉุกเฉิน",
            markers=True, # ใส่จุดที่แต่ละเดือน
            range_y=[0, max_y_axis], 
            color_discrete_sequence=["#4ECDC4"]
        )
        
        # ระบายสีใต้กราฟเส้นให้ดูสวยและเห็นมวลของเงิน (ตัวเลือกเพิ่มเติม)
        fig_emg.update_traces(fill='tozeroy', fillcolor='rgba(78, 205, 196, 0.2)')

        # ตีเส้นเกณฑ์แนวนอนแบ่งระดับ
        fig_emg.add_hline(y=level_red, line_dash="dash", line_color="#FF6B6B", 
                          annotation_text=f"🔴 วิกฤต ({level_red:,.0f} ฿)", annotation_position="top left")
        
        fig_emg.add_hline(y=level_yellow, line_dash="dash", line_color="#FFD166", 
                          annotation_text=f"🟡 เริ่มตึง ({level_yellow:,.0f} ฿)", annotation_position="top left")
        
        fig_emg.add_hline(y=level_green, line_dash="solid", line_color="#4EA8DE", 
                          annotation_text=f"🔵 ปลอดภัย ({level_green:,.0f} ฿)", annotation_position="top left")

        # ปรับแต่งการแสดงผล
        fig_emg.update_layout(xaxis_title=None, height=400, margin=dict(l=20, r=20, t=30, b=20))
        
        st.plotly_chart(fig_emg, use_container_width=True)


    else:
        # จะแสดงข้อความนี้ก็ต่อเมื่อยอดใช้จ่ายรวม (total_used) เป็น 0 จริงๆ
        st.info("💡 ยังไม่มีบันทึกรายจ่ายในเดือนนี้ กราฟจะแสดงผลเมื่อมีการใช้เงินครับ")
# =====================================================================

