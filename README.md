# Kla Finance — Static Web Migration

เว็บเวอร์ชัน HTML/CSS/Vanilla JavaScript สำหรับ GitHub Pages ใช้ Google OAuth 2.0 และ Google Sheets API โดยตรง

## ไฟล์

- `index.html` — หน้าเว็บ
- `style.css` — รูปแบบและ Responsive UI
- `script.js` — OAuth, Sheets API, Dashboard, การคำนวณ, รายจ่าย, ปิดเดือน และกราฟ
- `config.js` — ค่า Google OAuth Client ID และ Spreadsheet ID

## ตั้งค่า Google OAuth และ Google Sheets

1. เปิด [Google Cloud Console](https://console.cloud.google.com/) แล้วเลือกหรือสร้าง Project สำหรับเว็บนี้
2. ไปที่ **APIs & Services → Library** แล้วเปิด **Google Sheets API**
3. ไปที่ **Google Auth Platform → Branding** ตั้งชื่อแอปและอีเมลติดต่อ
4. ไปที่ **Google Auth Platform → Audience** เลือก External สำหรับบัญชี Google ทั่วไป แล้วเพิ่มบัญชีที่จะใช้ทดสอบใน Test users (ถ้าเป็น Google Workspace อาจเลือก Internal ตามนโยบายองค์กร)
5. ไปที่ **Google Auth Platform → Clients → Create client → Web application**
6. ใน **Authorized JavaScript origins** เพิ่ม `http://localhost:8000` สำหรับทดสอบในเครื่อง และเพิ่ม `https://USERNAME.github.io` เมื่อทราบ GitHub Pages URL จริง (ใส่เฉพาะ origin ไม่ใส่ path เช่น `/repository/`)
7. สำหรับ Google Identity Services Token Client ที่ใช้ในเว็บนี้ ไม่ต้องเพิ่ม Authorized redirect URI และไม่ต้องใช้ Client Secret
8. สร้าง Client แล้วคัดลอกเฉพาะ **Client ID** ลง `GOOGLE_CLIENT_ID` ใน `config.js`
9. คัดลอก Spreadsheet ID จากส่วนระหว่าง `/d/` และ `/edit` ใน URL ของชีต แล้วใส่ใน `SPREADSHEET_ID`
10. บัญชี Google ที่ Login ต้องมีสิทธิ์ Editor ใน Spreadsheet เป้าหมาย

เอกสารทางการ: [สร้าง OAuth credentials](https://developers.google.com/workspace/guides/create-credentials) · [Google Sheets JavaScript quickstart](https://developers.google.com/workspace/sheets/api/quickstart/js)

## ทดสอบในเครื่องอย่างปลอดภัย

1. เปิด Terminal ในโฟลเดอร์โปรเจกต์ แล้วรัน `python3 -m http.server 8000`
2. เปิด `http://localhost:8000` ในเบราว์เซอร์ (อย่าเปิด `index.html` ด้วย `file://`)
3. สร้างสำเนา Spreadsheet สำหรับทดสอบจาก Google Sheets ด้วย **File → Make a copy** ห้ามใช้ชีตเงินจริงเป็นเป้าหมายการทดสอบเขียนข้อมูล/ปิดเดือน
4. ใช้ Spreadsheet ID ของสำเนาใน `config.js` และให้บัญชี Google ที่จะ Login เป็น Editor ของสำเนานั้น
5. Login แล้วตรวจว่าหน้าเว็บโหลดชื่อ Worksheet, Summary_Data และข้อมูลเดือนที่เลือกได้
6. ทดสอบการแก้ไขค่าเล็กน้อยในสำเนา ตรวจค่าที่หน้าเว็บและใน Google Sheets ว่าตรงกัน
7. ทดสอบเพิ่มรายการ Manual Input และการแยกบิลในสำเนา ตรวจแถว/ยอดรวม/หมวดหมู่/หมายเหตุ
8. ก่อนทดสอบปิดเดือน ให้ตรวจว่าสำเนามีเดือนถัดไปยังไม่มีอยู่ และจดค่าต้นทาง F5/F6, F4, A30:D และ Summary_Data ไว้เปรียบเทียบ
9. ปิดเดือนในสำเนา แล้วตรวจ Summary_Data, Worksheet เดือนใหม่, F4=ยอด F5+F6, F5/F6 ต้องไม่ถูกล้าง, A30:D ต้องถูกล้างเฉพาะในเดือนใหม่ และค่าที่ตั้งใจ reset ต้องถูกต้อง
10. ทดสอบซ้ำไม่ได้ด้วยเดือนเดิมหากเดือนถัดไปถูกสร้างแล้ว ระบบควรป้องกันการสร้าง Worksheet ซ้ำ

หยุดเซิร์ฟเวอร์ใน Terminal ด้วย `Ctrl+C` เมื่อทดสอบเสร็จ

**ข้อมูลที่ต้องเตรียมเพื่อให้ทดสอบจริงต่อได้:** Client ID จากขั้นตอน 8 และ URL/ID ของ Spreadsheet สำเนาทดสอบ (ไม่ใช่ Client Secret, รหัสผ่าน หรือ Access Token)

## หน้าประวัติรายการ

เมนู **ประวัติรายการ** แสดงธุรกรรมจาก Worksheet รายเดือนทั้งหมด โดยอ่านข้อมูลช่วง `A30:D1000` (วันที่, จำนวนเงิน, หมวดหมู่, หมายเหตุ) และรองรับค้นหา/กรองเดือน/กรองหมวดหมู่/เรียงลำดับ, แก้ไขรายการ, แยกบิลเป็น 2–3 หมวดโดยตรวจยอดรวม, รวมหลายรายการในเดือนเดียวกัน, ลบรายการโดยล้างเฉพาะเซลล์ `A:D` ของแถวนั้น และส่งออก CSV

การแก้ไขจะเขียนกลับ Google Sheets โดยตรง ต้องตรวจสอบกับ **สำเนา Spreadsheet สำหรับทดสอบ** ก่อนใช้กับข้อมูลจริงเสมอ การรวมบิลจะเก็บยอดรวมไว้ในแถวแรกและล้างแถวที่เลือกที่เหลือ ส่วนการแยกบิลจะแทรกแถวใหม่ถัดจากรายการต้นทาง

## ความปลอดภัย

- ห้ามใส่ Client Secret หรือ Service Account Private Key ในไฟล์ Frontend
- OAuth access token เก็บไว้ในหน่วยความจำของหน้าเว็บเท่านั้น ไม่เขียนลง localStorage/sessionStorage
- Scope ใช้เฉพาะ `spreadsheets` เท่าที่จำเป็น
- จำกัด OAuth Authorized JavaScript origins ให้ตรงโดเมนจริง
- `config.js` เป็นไฟล์สาธารณะ: Client ID และ Spreadsheet ID ไม่ใช่รหัสลับ แต่การเข้าถึงข้อมูลยังถูกควบคุมด้วยสิทธิ์ Google OAuth และสิทธิ์แชร์ Spreadsheet

## เผยแพร่ GitHub Pages

1. Push ไฟล์ทั้ง 5 ไฟล์นี้ไปยัง repository
2. เปิด Repository Settings → Pages
3. เลือก Deploy from a branch และเลือก branch/folder ที่เก็บไฟล์
4. เพิ่ม origin ของเว็บไซต์ที่ได้ลงใน OAuth Client ID
5. เปิด URL เว็บไซต์และ Login ด้วยบัญชีที่มีสิทธิ์ใน Spreadsheet

## ขอบเขตที่ควรทดสอบก่อนใช้กับข้อมูลจริง

- การอ่านชื่อ Worksheet และเปลี่ยนเดือนผ่าน URL query parameter
- การบันทึก F2, B18, B13, C26, F16, F5, F6
- การปรับยอด C26 แล้วคำนวณผลต่างกับ B13
- การจัดหมวดรายการรอดำเนินการ
- การแยกบิล 1–3 หมวด โดยตรวจยอดคลาดเคลื่อนไม่เกิน 0.01 บาท
- การแทรกแถวจากล่างขึ้นบนและเพิ่มรายการ Manual Input
- การปิดเดือน สร้าง Summary_Data เมื่อยังไม่มี และสร้าง Worksheet เดือนถัดไป
- ยืนยันว่า F5/F6 ไม่ถูกล้าง และ F4 รับยอด F5+F6
- ยืนยันว่ารายการ A30:D ถูกล้างเฉพาะใน Worksheet เดือนใหม่
- ตรวจสอบกราฟ Carry_Cash, expense share, Personal_Income และ Emergency fund

## ขั้นตอนตั้งค่าและทดสอบ (แนะนำให้ทำตามลำดับ)

### A. สร้าง OAuth Client สำหรับเว็บ

1. เปิด [Google Cloud Console](https://console.cloud.google.com/) และเลือกโปรเจกต์ที่ต้องการใช้ (จะใช้โปรเจกต์เดิมก็ได้)
2. ไปที่ Google Auth Platform → Branding ตั้งชื่อแอปและอีเมลติดต่อให้เรียบร้อย
3. ไปที่ Audience เลือก External หากเป็นบัญชี Gmail ทั่วไป และเพิ่มบัญชี Google ที่จะใช้ทดสอบใน Test users
4. ไปที่ Clients → Create client → เลือก Web application
5. ตั้งชื่อ เช่น `Kla Finance Local Test`
6. เพิ่ม Authorized JavaScript origins เป็น `http://localhost:8000` (ห้ามใส่ path ต่อท้าย)
7. สร้าง Client แล้วคัดลอกเฉพาะ Client ID ซึ่งลงท้ายด้วย `.apps.googleusercontent.com`
8. ใน APIs & Services → Library เปิดใช้ Google Sheets API ในโปรเจกต์เดียวกัน

ไม่ต้องสร้าง Client Secret สำหรับโค้ดหน้าเว็บนี้ และห้ามนำ Client Secret หรือ Service Account Private Key มาใส่ใน `config.js`

### B. เตรียมสำเนา Spreadsheet สำหรับทดสอบ

1. เปิด Spreadsheet ต้นฉบับ `แผนการเงินรายเดือน`
2. เลือก File → Make a copy ตั้งชื่อ `แผนการเงินรายเดือน - WEB TEST`
3. ตรวจสอบว่าสำเนามี Worksheet รายเดือนและ `Summary_Data` เหมือนต้นฉบับ
4. ใช้ ID จาก URL ของสำเนาเท่านั้น โดยเป็นข้อความระหว่าง `/d/` และ `/edit`
5. แชร์สำเนาให้บัญชี Google ที่จะ Login เป็น Editor (หากเป็นเจ้าของอยู่แล้วไม่ต้องแชร์เพิ่ม)

### C. ใส่ค่าตั้งค่าและเปิดเว็บในเครื่อง

1. เปิด `config.js` แล้วใส่ Client ID ใน `GOOGLE_CLIENT_ID` และ ID ของสำเนาใน `SPREADSHEET_ID`
2. เปิด Terminal ในโฟลเดอร์โปรเจกต์ แล้วรัน `python3 -m http.server 8000`
3. เปิด `http://localhost:8000` ในเบราว์เซอร์ (อย่าเปิด `index.html` ด้วย `file://`)
4. กดเข้าสู่ระบบ Google เลือกบัญชีทดสอบ และอนุญาตการเข้าถึง Google Sheets
5. หากขึ้น `origin_mismatch` ให้ตรวจว่า OAuth Client มี `http://localhost:8000` ตรงทุกตัวอักษร
6. หากขึ้น `access_denied` ให้ตรวจ Test users และสถานะ Audience

### D. ทดสอบการอ่านและเขียนในสำเนาเท่านั้น

1. **Read test:** หลัง Login หน้า Dashboard ต้องโหลดชื่อ Spreadsheet, รายชื่อเดือน, ค่าในเซลล์ และ `Summary_Data` ได้
2. **Write test:** เลือกเดือนทดสอบที่มีอยู่ จดค่า F2 เดิมไว้ แล้วเปลี่ยน F2 เป็นค่าทดสอบที่แตกต่าง กดบันทึก ตรวจค่าใน Google Sheets ว่าตรงกัน จากนั้นคืนค่าเดิมและบันทึกอีกครั้ง
3. **Expense test:** เพิ่มรายการทดสอบจำนวนเล็กน้อย แบ่งหมวด 1–3 หมวดให้ยอดรวมตรงกับยอดเดิม ตรวจ A30:D ในสำเนา แล้วลบรายการทดสอบออกหลังตรวจเสร็จ
4. **Close-month test:** ก่อนกดปิดเดือน ตรวจชื่อเดือนถัดไปว่ายังไม่มีอยู่ และยืนยันว่ากำลังใช้สำเนา `WEB TEST` เท่านั้น จากนั้นกดปิดยอด
5. ตรวจว่า `Summary_Data` มีข้อมูลเดือนเดิมหนึ่งแถว, มี Worksheet เดือนถัดไป, F4 เท่ากับยอด F5+F6 ที่ยกมา, F5/F6 ไม่ถูกล้าง, F2/B11/B12/F16 ถูก reset ตาม logic และ A30:D ในเดือนใหม่ว่าง
6. เปิดหน้าเว็บใหม่และเลือกเดือนที่สร้าง ตรวจว่าค่าและ Dashboard โหลดกลับมาได้

หากขั้นตอนใดผิดพลาด ให้หยุดก่อน อย่ากดปิดยอดซ้ำทันที เพราะกระบวนการปิดเดือนเป็นหลาย API calls และไม่ใช่ transaction เดียว

### E. ก่อนเปลี่ยนไปใช้ Spreadsheet จริง

เมื่อผ่านทุกข้อในสำเนาแล้ว ค่อยเปลี่ยน `SPREADSHEET_ID` เป็น ID ของ Spreadsheet จริง และทดสอบเฉพาะการอ่านก่อน ห้ามทดสอบปิดเดือนจริงเพื่อยืนยันระบบอีกครั้ง

## ข้อจำกัดที่ทราบ

- ต้องกรอก Client ID และ Spreadsheet ID ก่อนใช้งานจริง
- ผู้ใช้ต้อง Login ใหม่เมื่อ Access Token หมดอายุหรือ Reload หน้าเว็บ
- การทำงานขึ้นกับ Google Sheets API quota, network และสิทธิ์ของบัญชีผู้ใช้
- การดำเนินการปิดเดือนเป็นหลายคำขอ API ไม่ใช่ transaction เดียว ควรสำรอง Spreadsheet ก่อนทดสอบปิดเดือนจริง
- ยังไม่ได้ทดสอบกับ Spreadsheet จริง เพราะยังไม่มี Spreadsheet ID และ OAuth Client ID ในโปรเจกต์
