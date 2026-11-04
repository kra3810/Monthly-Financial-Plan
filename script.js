/* Kla Finance — static browser app using Google OAuth + Google Sheets API.
   No service-account credentials, client secret, or backend are used in this file. */
(() => {
  "use strict";

  const CONFIG = window.FINANCE_CONFIG || {};
  const AUTH_SESSION_KEY = "kla-finance-google-session";
  const saveAuthSession = () => { try { sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify({ token: state.token, expiresAt: state.tokenExpiresAt })); } catch (_) {} };
  const clearAuthSession = () => { try { sessionStorage.removeItem(AUTH_SESSION_KEY); } catch (_) {} };
  const restoreAuthSession = () => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(AUTH_SESSION_KEY) || "null");
      if (saved?.token && Number(saved.expiresAt) > Date.now() + 5000) { state.token = saved.token; state.tokenExpiresAt = Number(saved.expiresAt); return true; }
    } catch (_) {}
    clearAuthSession();
    return false;
  };
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."];
  const CATEGORIES = ["ค่ากิน", "ค่าใช้จ่ายส่วนตัว", "ค่าอื่นๆ"];
  const CATEGORY_LABELS = { "ค่ากิน": "ค่ากิน", "ค่าใช้จ่ายส่วนตัว": "ใช้ส่วนตัว", "ค่าอื่นๆ": "อื่นๆ" };
  const state = { token: null, tokenExpiresAt: 0, tokenClient: null, user: null, spreadsheet: null, worksheets: [], month: null, data: [], history: [], summary: [], busy: false, activeView: "overview", historyFilters: { query: "", month: "all", category: "all", sort: "newest" }, historyEditor: null, mergeSelection: [], sidebarSettingsOpen: null, sidebarSettingsTouched: false };

  const money = value => new Intl.NumberFormat("th-TH", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(number(value));
  const money0 = value => new Intl.NumberFormat("th-TH", { maximumFractionDigits: 0 }).format(number(value));
  const number = value => {
    if (typeof value === "number") return Number.isFinite(value) ? value : 0;
    const parsed = Number(String(value ?? "").replace(/,/g, "").trim());
    return Number.isFinite(parsed) ? parsed : 0;
  };
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const cell = (row, col) => number(state.data[row]?.[col] ?? 0);
  const textCell = (row, col) => String(state.data[row]?.[col] ?? "").trim();
  const sheetRange = (title, range) => "'" + String(title).replace(/'/g, "''") + "'!" + range;
  const configured = () => CONFIG.GOOGLE_CLIENT_ID && !CONFIG.GOOGLE_CLIENT_ID.startsWith("YOUR_") &&
    CONFIG.SPREADSHEET_ID && !CONFIG.SPREADSHEET_ID.startsWith("YOUR_");

  function toast(message, type = "info", duration = 3800) {
    const node = document.createElement("div");
    node.className = "toast " + (type === "error" ? "error" : type === "success" ? "success" : "");
    node.textContent = message;
    $("#toast-region").append(node);
    window.setTimeout(() => node.remove(), duration);
  }

  function setConnection(connected, label) {
    const el = $("#connection-state");
    el.classList.toggle("connected", connected);
    el.innerHTML = "<i></i>" + escapeHtml(label || (connected ? "เชื่อมต่อแล้ว" : "ยังไม่ได้เชื่อมต่อ"));
    $("#auth-button").textContent = connected ? "เปลี่ยนบัญชี Google" : "เข้าสู่ระบบ Google";
    $("#auth-button").dataset.originalLabel = $("#auth-button").textContent;
  }

  function showApp(connected) {
    $("#welcome-panel").classList.toggle("hidden", connected);
    $("#app-panel").classList.toggle("hidden", !connected);
  }

  function parseExpression(input) {
    const source = String(input ?? "").replace(/,/g, "").replace(/\s+/g, "");
    if (!source) return 0;
    if (!/^[0-9.+*/()\-]+$/.test(source)) throw new Error("อนุญาตเฉพาะตัวเลขและเครื่องหมาย + - * / ( )");
    let pos = 0;
    const peek = () => source[pos];
    const consume = char => { if (peek() === char) { pos++; return true; } return false; };
    function primary() {
      if (consume("+")) return primary();
      if (consume("-")) return -primary();
      if (consume("(")) {
        const value = expression();
        if (!consume(")")) throw new Error("วงเล็บไม่ครบ");
        return value;
      }
      const start = pos;
      while (/[0-9.]/.test(peek() || "")) pos++;
      if (start === pos) throw new Error("รูปแบบสมการไม่ถูกต้อง");
      const token = source.slice(start, pos);
      if ((token.match(/\./g) || []).length > 1) throw new Error("ตัวเลขไม่ถูกต้อง");
      const value = Number(token);
      if (!Number.isFinite(value)) throw new Error("ตัวเลขไม่ถูกต้อง");
      return value;
    }
    function term() {
      let value = primary();
      while (peek() === "*" || peek() === "/") {
        const op = source[pos++];
        const rhs = primary();
        if (op === "/" && rhs === 0) throw new Error("ไม่สามารถหารด้วยศูนย์ได้");
        value = op === "*" ? value * rhs : value / rhs;
      }
      return value;
    }
    function expression() {
      let value = term();
      while (peek() === "+" || peek() === "-") {
        const op = source[pos++];
        const rhs = term();
        value = op === "+" ? value + rhs : value - rhs;
      }
      return value;
    }
    const result = expression();
    if (pos !== source.length || !Number.isFinite(result)) throw new Error("รูปแบบสมการไม่ถูกต้อง");
    return result;
  }

  function initAuth() {
    if (!configured()) {
      toast("กรุณาตั้งค่า GOOGLE_CLIENT_ID และ SPREADSHEET_ID ใน config.js ก่อนใช้งาน", "error", 7000);
      return;
    }
    const waitForGoogle = () => {
      if (!window.google?.accounts?.oauth2) return window.setTimeout(waitForGoogle, 120);
      state.tokenClient = google.accounts.oauth2.initTokenClient({
        client_id: CONFIG.GOOGLE_CLIENT_ID,
        scope: CONFIG.SCOPES || "https://www.googleapis.com/auth/spreadsheets",
        callback: async response => {
          state.authPending = false;
          setAuthPending(false);
          if (response.error || !response.access_token) {
            if (!state.silentAuth) toast("เข้าสู่ระบบไม่สำเร็จ: " + (response.error || "ไม่ได้รับ Access Token"), "error");
            state.silentAuth = false;
            return;
          }
          state.silentAuth = false;
          state.token = response.access_token;
          state.tokenExpiresAt = Date.now() + (Number(response.expires_in || 3600) - 60) * 1000;
          saveAuthSession();
          setConnection(true, "เชื่อมต่อ Google Sheets แล้ว");
          showApp(true);
          await bootstrap();
        },
        error_callback: error => {
          state.authPending = false;
          setAuthPending(false);
          if (!state.silentAuth) toast("Google OAuth: " + (error.message || error.type), "error");
          state.silentAuth = false;
        }
      });
      if (restoreAuthSession()) {
        setConnection(true, "เชื่อมต่อ Google Sheets แล้ว");
        showApp(true);
        bootstrap();
      } else {
        state.silentAuth = true;
        try { state.tokenClient.requestAccessToken({ prompt: "" }); }
        catch (_) { state.silentAuth = false; }
      }
    };
    waitForGoogle();
  }

  function setAuthPending(pending) {
    const buttons = [$("#auth-button"), $("#welcome-login")].filter(Boolean);
    buttons.forEach(button => {
      if (pending) {
        button.dataset.originalLabel ||= button.textContent.trim();
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
        button.textContent = "กำลังเชื่อมต่อ...";
      } else {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        if (button.dataset.originalLabel) button.textContent = button.dataset.originalLabel;
      }
    });
  }

  function login() {
    if (state.authPending) return;
    if (!configured()) { toast("ยังไม่ได้ตั้งค่า Client ID หรือ Spreadsheet ID ใน config.js", "error"); return; }
    if (!state.tokenClient) { toast("Google Identity Services ยังโหลดไม่เสร็จ กรุณารอสักครู่แล้วลองใหม่", "error"); return; }
    try {
      state.authPending = true;
      setAuthPending(true);
      state.tokenClient.requestAccessToken({ prompt: "select_account" });
    } catch (error) {
      state.authPending = false;
      setAuthPending(false);
      toast("ไม่สามารถเปิดหน้าต่างเชื่อมต่อ Google: " + error.message, "error");
    }
  }

  function logout() {
    if (state.token && window.google?.accounts?.oauth2) google.accounts.oauth2.revoke(state.token, () => {});
    clearAuthSession();
    state.token = null; state.tokenExpiresAt = 0; state.user = null; state.data = []; state.history = []; state.summary = []; state.activeView = "overview";
    showApp(false); setConnection(false);
    toast("ออกจากระบบแล้ว", "success");
  }

  async function api(path, options = {}) {
    if (!state.token) throw new Error("กรุณาเข้าสู่ระบบ Google ใหม่");
    if (Date.now() > state.tokenExpiresAt) { clearAuthSession(); state.token = null; showApp(false); setConnection(false, "เซสชันหมดอายุ"); throw new Error("Access Token หมดอายุ กรุณาเข้าสู่ระบบใหม่"); }
    const response = await fetch("https://sheets.googleapis.com/v4/spreadsheets/" + CONFIG.SPREADSHEET_ID + path, {
      ...options,
      headers: { Authorization: "Bearer " + state.token, "Content-Type": "application/json", ...(options.headers || {}) }
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const reason = payload.error?.message || response.statusText || "Google Sheets API error";
      if (response.status === 401) { clearAuthSession(); state.token = null; showApp(false); setConnection(false, "ต้องเข้าสู่ระบบใหม่"); }
      throw new Error(reason);
    }
    return payload;
  }

  async function getMetadata() {
    return api("?fields=spreadsheetId,properties(title),sheets(properties(sheetId,title,index,gridProperties(rowCount,columnCount)))");
  }

  async function getValues(range, render = "FORMATTED_VALUE") {
    const query = new URLSearchParams({ valueRenderOption: render });
    const result = await api("/values/" + encodeURIComponent(range) + "?" + query.toString());
    return result.values || [];
  }

  async function batchGet(ranges) {
    const query = new URLSearchParams({ valueRenderOption: "FORMATTED_VALUE" });
    ranges.forEach(range => query.append("ranges", range));
    const result = await api("/values:batchGet?" + query.toString());
    return result.valueRanges || [];
  }

  async function loadHistoryData() {
    const sheets = state.worksheets.filter(item => item.title !== "Summary_Data");
    if (!sheets.length) { state.history = []; return; }
    const ranges = sheets.map(item => sheetRange(item.title, "A30:D1000"));
    const values = await batchGet(ranges);
    const history = [];
    sheets.forEach((sheet, index) => {
      (values[index]?.values || []).forEach((row, offset) => {
        if (!row[0] || !String(row[0]).trim()) return;
        history.push({ id: sheet.title + ":" + (offset + 30), month: sheet.title, sheetRow: offset + 30, date: String(row[0]), amount: number(row[1]), category: String(row[2] || "รอดำเนินการ"), note: String(row[3] || "-") });
      });
    });
    state.history = history;
  }

  async function batchWrite(data) {
    if (!data.length) return;
    return api("/values:batchUpdate", { method: "POST", body: JSON.stringify({ valueInputOption: "USER_ENTERED", data }) });
  }

  async function clearRanges(ranges) {
    if (!ranges.length) return;
    return api("/values:batchClear", { method: "POST", body: JSON.stringify({ ranges }) });
  }

  async function spreadsheetBatchUpdate(requests) {
    if (!requests.length) return;
    return api(":batchUpdate", { method: "POST", body: JSON.stringify({ requests }) });
  }

  async function bootstrap() {
    try {
      setBusy(true);
      state.spreadsheet = await getMetadata();
      state.worksheets = (state.spreadsheet.sheets || []).map(item => item.properties).filter(item => item.title !== "Summary_Data").sort((a,b) => a.index - b.index);
      const summarySheet = (state.spreadsheet.sheets || []).find(item => item.properties.title === "Summary_Data");
      state.summary = summarySheet ? await getValues(sheetRange("Summary_Data", "A1:F1000")) : [];
      const params = new URLSearchParams(location.search);
      const requested = params.get("month");
      const currentDefault = currentMonthName();
      state.month = state.worksheets.some(item => item.title === requested) ? requested :
        state.worksheets.some(item => item.title === currentDefault) ? currentDefault : (state.worksheets[0]?.title || "");
      if (!state.month) throw new Error("ไม่พบ Worksheet รายเดือนใน Spreadsheet");
      renderMonthOptions();
      await loadMonth();
      await loadHistoryData();
      $("#welcome-user").textContent = "เชื่อมต่อกับ " + (state.spreadsheet.properties?.title || "Google Sheets") + " แล้ว";
      showApp(true);
    } catch (error) {
      toast("โหลดข้อมูลไม่สำเร็จ: " + error.message, "error", 6500);
    } finally { setBusy(false); }
  }

  function currentMonthName(date = new Date()) {
    return MONTHS[date.getMonth()] + " " + String(date.getFullYear() + 543).slice(-2);
  }

  function nextMonthName(name) {
    const parts = String(name).trim().split(/\s+/);
    if (parts.length !== 2) throw new Error("รูปแบบชื่อ Worksheet เดือนไม่ถูกต้อง: " + name);
    const index = MONTHS.indexOf(parts[0]);
    const year = Number(parts[1]);
    if (index < 0 || !Number.isInteger(year)) throw new Error("ไม่สามารถคำนวณเดือนถัดไปจาก " + name);
    return MONTHS[(index + 1) % 12] + " " + (year + (index === 11 ? 1 : 0));
  }

  function renderMonthOptions() {
    const select = $("#month-select");
    select.innerHTML = state.worksheets.map(item => "<option value=\"" + escapeHtml(item.title) + "\">" + escapeHtml(item.title) + "</option>").join("");
    select.value = state.month;
    const url = new URL(location.href); url.searchParams.set("month", state.month); history.replaceState({}, "", url);
  }

  async function loadMonth() {
    if (!state.month) return;
    setBusy(true);
    try {
      const values = await getValues(sheetRange(state.month, "A1:Z1000"));
      state.data = values;
      await loadHistoryData();
      renderDashboard();
      const url = new URL(location.href); url.searchParams.set("month", state.month); history.replaceState({}, "", url);
      $("#close-month-button").disabled = state.worksheets.some(item => item.title === nextMonthName(state.month));
    } finally { setBusy(false); }
  }

  function setBusy(busy) {
    state.busy = busy;
    const button = $("#close-month-button");
    if (button) button.disabled = busy || (state.month && state.worksheets.some(item => item.title === nextMonthName(state.month)));
  }

  function statusPill(text, tone = "") { return '<span class="status-pill ' + tone + '">' + escapeHtml(text) + "</span>"; }

  function renderDashboard() {
    if (state.activeView === "history") { renderHistoryWorkspace(); return; }
    const monthTools = $("#month-select")?.closest(".select-wrap");
    if (monthTools) monthTools.hidden = false;
    $("#close-month-button").hidden = false;
    const heading = $("#app-panel .page-heading h1"), eyebrow = $("#app-panel .page-heading .eyebrow");
    if (heading) heading.textContent = "ภาพรวมการเงิน";
    if (eyebrow) eyebrow.textContent = "MONTHLY OVERVIEW";
    if ($("#welcome-user") && state.spreadsheet) $("#welcome-user").textContent = "เชื่อมต่อกับ " + (state.spreadsheet.properties?.title || "Google Sheets") + " แล้ว";
    const usedFood = cell(2,1), usedPersonal = cell(3,1), usedOther = cell(4,1);
    // C26 is the emergency amount reserved from this month's allowance; it is not a personal expense.
    const monthlyEmergency = cell(25,2);
    const usedTotal = usedFood + usedPersonal + usedOther;
    const remaining = cell(2,5), budgetTotal = usedTotal + remaining;
    const percent = budgetTotal > 0 ? Math.min(usedTotal / budgetTotal * 100, 100) : 0;
    const ringColor = percent >= 90 ? "#cf5555" : percent >= 70 ? "#c58a35" : "#356fce";
    const emergency = cell(12,1), central = cell(18,1);
    const budgets = [cell(22,1), cell(23,1), cell(24,1)];
    const categories = [
      { key:"food", name:"ค่ากิน", used:usedFood, budget:budgets[0] },
      { key:"personal", name:"ใช้ส่วนตัว", used:usedPersonal, budget:budgets[1] },
      { key:"other", name:"อื่นๆ", used:usedOther, budget:budgets[2] }
    ];
    const emergencyStatus = textCell(12,2), centralStatus = textCell(18,2);
    const html = `
      <div class="finance-layout">
        <aside class="finance-sidebar" aria-label="เมนูและการตั้งค่าการเงิน">
          <div class="sidebar-brand">
            <span class="sidebar-brand-mark">K</span>
            <div class="sidebar-brand-copy"><strong>Kla Finance</strong><small>PERSONAL FINANCE</small></div>
            <button id="sidebar-collapse-toggle" class="sidebar-collapse-toggle" type="button" aria-label="ย่อแถบเมนู" aria-expanded="true" title="ย่อแถบเมนู">‹</button>
          </div>
          <nav class="sidebar-nav" aria-label="เมนูหลัก">
            <span class="sidebar-caption">WORKSPACE</span>
            <a class="sidebar-link active" href="./index.html" data-app-view="overview" aria-current="page"><span class="nav-icon" aria-hidden="true">▦</span><span class="nav-copy"><strong>ภาพรวมการเงิน</strong><small>สรุปงบและยอดคงเหลือ</small></span><span class="nav-current"></span></a>
            <a class="sidebar-link" href="./index.html#history" data-app-view="history"><span class="nav-icon" aria-hidden="true">◷</span><span class="nav-copy"><strong>ประวัติรายการ</strong><small>ค้นหาและจัดการรายจ่าย</small></span><span class="nav-link-count">ALL</span></a>
          </nav>
          <div class="sidebar-divider"></div>
          <details class="sidebar-settings" open>
            <summary class="sidebar-settings-toggle">
              <span class="settings-mark">⚙</span>
              <span class="sidebar-settings-label"><small>FINANCIAL SETTINGS</small><strong>ข้อมูลการเงิน</strong></span>
              <span class="settings-chevron" aria-hidden="true">⌄</span>
            </summary>
            <div class="sidebar-settings-content">
          <section class="sidebar-panel">
            <div class="sidebar-panel-title"><span class="setting-number">01</span><div><h3>เงินสนับสนุนจากที่บ้าน</h3><small>เงินรับรายเดือนและยอดสะสม</small></div></div>
            <form id="allowance-form" class="sidebar-form">
              <div class="field"><label>เงินสนับสนุนรายเดือน</label><input name="allowance" value="${escapeHtml(cell(1,5) || 0)}" inputmode="decimal"></div>
              <div class="field"><label>เงินสะสม</label><input name="accumulated" value="${escapeHtml(cell(17,1) || 0)}" inputmode="decimal"></div>
              <button class="button button-primary" type="submit">บันทึกข้อมูล</button>
            </form>
          </section>
          <section class="sidebar-panel">
            <div class="sidebar-panel-title"><span class="setting-number">02</span><div><h3>เงินสำรองฉุกเฉิน</h3><small>ยอดสะสมและยอดกันในเดือนนี้</small></div></div>
            <form id="emergency-form" class="sidebar-form">
              <div class="field"><label>ยอดสะสมรวม</label><input name="emergencyTotal" value="${escapeHtml(emergency)}" inputmode="decimal"></div>
              <div class="field"><label>กันเงินเดือนนี้</label><input name="emergencyMonthly" value="${escapeHtml(monthlyEmergency)}" inputmode="decimal"></div>
              <button class="button button-primary" type="submit">บันทึกเงินสำรอง</button>
            </form>
          </section>
          <section class="sidebar-panel">
            <div class="sidebar-panel-title"><span class="setting-number">03</span><div><h3>รายได้ส่วนตัว</h3><small>รายได้อื่นนอกเหนือจากเงินสนับสนุน</small></div></div>
            <form id="income-form" class="sidebar-form">
              <div class="field"><label>รายได้ส่วนตัว</label><input name="income" value="${escapeHtml(cell(15,5))}" inputmode="decimal"></div>
              <button class="button button-primary" type="submit">บันทึกรายได้</button>
            </form>
          </section>
          <section class="sidebar-panel fixed-panel">
            <div class="sidebar-panel-title"><span class="setting-number">04</span><div><h3>รายการตายตัวและเงินเก็บ</h3><small>Fixed & Saving</small></div></div>
            <div class="fixed-list">
              <div><span>งบสำรองฉุกเฉิน</span><b>${money(cell(25,1))} ฿</b></div>
              <div class="fixed-emergency-monthly"><span>กันเงินเดือนนี้</span><b>${money(monthlyEmergency)} ฿</b></div>
              <div><span>ค่าหอพัก</span><b>${money(4500)} ฿</b></div>
              <div><span>งบกิน</span><b>${money(budgets[0])} ฿</b></div>
              <div><span>งบส่วนตัว</span><b>${money(budgets[1])} ฿</b></div>
              <div><span>งบอื่นๆ</span><b>${money(budgets[2])} ฿</b></div>
            </div>
          </section>
            </div>
          </details>
          <div class="sidebar-foot"><span class="sidebar-foot-dot"></span><span><strong>เชื่อมต่อแล้ว</strong><small>ข้อมูลจัดเก็บใน Google Sheets</small></span><span class="sidebar-foot-check" aria-hidden="true">✓</span></div>
        </aside>

        <div class="finance-main">
          <section class="overview-section">
            <div class="overview-balance">
              <div class="overview-label"><span>เงินคงเหลือที่ใช้ได้</span><span class="overview-label-en">AVAILABLE BALANCE</span></div>
              <div class="overview-amount">${money(remaining)} <small>บาท</small></div>
              <div class="overview-foot">ยอดเงินที่ยังใช้ได้ในเดือนนี้</div>
            </div>
            <div class="overview-stat"><span>เงินสำรองฉุกเฉิน</span><strong>${money(emergency)} ฿</strong><small>${escapeHtml(emergencyStatus || "ยอดสะสมปัจจุบัน")}</small><small class="overview-stat-detail">กันเดือนนี้ ${money(monthlyEmergency)} ฿</small></div>
            <div class="overview-stat"><span>งบกลางคงเหลือ</span><strong>${money(central)} ฿</strong><small>${escapeHtml(centralStatus || "ยอดคงเหลือ")}</small></div>
            <div class="overview-stat"><span>ใช้จ่ายไปแล้ว</span><strong>${money(usedTotal)} ฿</strong><small>จากงบรวม ${money(budgetTotal)} ฿</small></div>
          </section>

          <section class="budget-overview">
            <div class="section-title"><div><span class="eyebrow">BUDGET OVERVIEW</span><h2>สถานะงบประมาณ</h2></div>${statusPill(percent >= 90 ? "ใกล้เต็มงบ" : percent >= 70 ? "ควรเฝ้าระวัง" : "อยู่ในเกณฑ์", percent >= 90 ? "danger" : percent >= 70 ? "warn" : "")}</div>
            <div class="budget-overview-content">
              <div class="donut" style="--progress:${percent}%;--ring-color:${ringColor}"><div class="donut-center"><strong>${percent.toFixed(0)}%</strong><small>ใช้ไปแล้ว</small></div></div>
              <div class="budget-breakdown">
                <div class="budget-total-line"><span>ใช้ไปแล้ว</span><strong>${money(usedTotal)} ฿</strong></div>
                <div class="budget-total-line"><span>คงเหลือ</span><strong>${money(remaining)} ฿</strong></div>
                <div class="budget-total-line budget-total-final"><span>งบรวม</span><strong>${money(budgetTotal)} ฿</strong></div>
              </div>
              <div class="category-breakdown">${categories.map(item => { const difference = item.budget - item.used; const over = difference < -0.005; const ratio = item.budget > 0 ? item.used / item.budget * 100 : item.used > 0 ? 100 : 0; const balanceLabel = over ? "เกินมา" : "เหลือ"; return `<div class="category-row category-row-${item.key} ${over ? "is-over" : "is-within"}"><div class="category-row-main"><strong>${item.name}</strong><span>${money(item.used)} / ${money(item.budget)} ฿</span></div><div class="progress-track"><div class="progress-fill ${over ? "over" : ""}" style="width:${Math.min(ratio,100)}%"></div></div><div class="category-balance ${over ? "over" : "within"}"><span>${balanceLabel}</span><strong>${money(Math.abs(difference))} ฿</strong></div></div>`; }).join("")}</div>
            </div>
          </section>

          <section class="expense-hub">
            <div class="section-title expense-title"><div><span class="eyebrow">EXPENSE MANAGEMENT</span><h2>จัดการรายจ่ายประจำเดือน</h2><p>ตรวจสอบบิลค้างและบันทึกรายจ่ายใหม่ในที่เดียว</p></div></div>
            <div class="pending-area"><div class="subsection-title"><div><h3>บิลที่รอจัดหมวดหมู่</h3><small>ตรวจสอบและเลือกหมวดรายจ่ายก่อนบันทึก</small></div><span>PENDING BILLS</span></div>${renderExpenses()}</div>
            <div class="entry-area"><div class="subsection-title"><div><h3>บันทึกรายจ่ายใหม่</h3><small>กรอกยอดตามหมวดที่ต้องการบันทึก</small></div><span>NEW EXPENSE</span></div>${renderExpenseEntry()}</div>
          </section>

          <section class="balance-section">
            <div class="section-title"><div><span class="eyebrow">ACCOUNT RECONCILIATION</span><h2>ตรวจสอบสมดุลบัญชี</h2><p>เปรียบเทียบยอดเงินในระบบกับเงินจริงที่มีอยู่</p></div></div>
            ${renderBalance(remaining)}
          </section>

          <section class="analytics-section">
            <div class="section-title"><div><span class="eyebrow">FINANCIAL INSIGHTS</span><h2>สถิติและแนวโน้ม</h2><p>ภาพรวมรายจ่ายและการเปลี่ยนแปลงของข้อมูลทางการเงิน</p></div></div>
            ${renderCharts({usedFood,usedPersonal,usedOther,budgets,emergency})}
          </section>
        </div>
      </div>
    `;
    const layoutTemplate = document.createElement("template");
    layoutTemplate.innerHTML = html.trim();
    const renderedSidebar = layoutTemplate.content.querySelector(".finance-sidebar");
    const renderedMain = layoutTemplate.content.querySelector(".finance-main");
    const sidebarSlot = $("#finance-sidebar-slot");
    const dashboardContent = $("#dashboard-content");
    if (!renderedSidebar || !renderedMain || !sidebarSlot || !dashboardContent) {
      throw new Error("ไม่พบพื้นที่ Sidebar หรือ Dashboard ที่ต้องการแสดงผล");
    }
    sidebarSlot.className = "app-sidebar finance-sidebar";
    sidebarSlot.innerHTML = renderedSidebar.innerHTML;
    const sidebarSettings = sidebarSlot.querySelector(".sidebar-settings");
    if (sidebarSettings) {
      sidebarSettings.open = state.sidebarSettingsTouched ? state.sidebarSettingsOpen : !window.matchMedia("(max-width: 900px)").matches;
      sidebarSettings.querySelector(".sidebar-settings-toggle")?.addEventListener("click", () => { state.sidebarSettingsTouched = true; });
      sidebarSettings.addEventListener("toggle", () => {
        if (state.sidebarSettingsTouched) state.sidebarSettingsOpen = sidebarSettings.open;
      });
    }
    dashboardContent.innerHTML = renderedMain.outerHTML;
    bindDashboardEvents();
    bindExpenseEvents();
  }


  function bindDashboardNavigation() {
    const root = $("#dashboard-content");
    const activate = view => {
      state.activeView = view;
      $$("[data-dashboard-view]", root).forEach(button => {
        const active = button.dataset.dashboardView === view;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", String(active));
      });
      $$("[data-dashboard-page]", root).forEach(page => page.classList.toggle("hidden", page.dataset.dashboardPage !== view));
    };
    $$("[data-dashboard-view]", root).forEach(button => button.addEventListener("click", () => activate(button.dataset.dashboardView)));
    activate(state.activeView || "overview");
  }

  function renderExpenseEntry() {
    return `<div class="entry-card">
      <form id="manual-expense-form" class="form-grid">
        <div class="field"><label>ค่ากิน (บาท)</label><input name="food" type="number" min="0" step="0.01" value="0"></div>
        <div class="field"><label>ใช้ส่วนตัว (บาท)</label><input name="personal" type="number" min="0" step="0.01" value="0"></div>
        <div class="field"><label>ค่าอื่นๆ (บาท)</label><input name="other" type="number" min="0" step="0.01" value="0"></div>
        <div class="field"><label>หมายเหตุ</label><input name="note" placeholder="เช่น อาหารกลางวัน, ค่าเดินทาง" value=""></div>
      </form>
      <div class="entry-total"><span>ยอดที่กรอกทั้งหมด</span><strong id="entry-total">0.00 ฿</strong></div>
      <div class="save-row"><small>กรอกเฉพาะหมวดที่มีค่าใช้จ่าย ระบบจะบันทึกเป็นรายการแยกตามหมวด</small><button id="save-expenses-button" class="button button-primary button-large" type="button">บันทึกรายจ่าย</button></div>
    </div>`;
  }

  function renderExpenses() {
    const transactions = [];
    for (let i = 29; i < state.data.length; i++) {
      const row = state.data[i] || [];
      if (row[0] && row[2] === "รอดำเนินการ") transactions.push({ sheetRow:i+1, date:row[0], amount:number(row[1]), note:row[3] || "-" });
    }
    const total = transactions.reduce((sum,item) => sum + item.amount, 0);
    const rows = transactions.map((item,index) => `
      <tr data-expense-index="${index}" data-sheet-row="${item.sheetRow}" data-date="${escapeHtml(item.date)}" data-amount="${item.amount}">
        <td>${escapeHtml(item.date)}</td><td class="amount-cell"><strong>${money(item.amount)}</strong><small>บาท</small></td>
        <td><input class="expense-note" aria-label="หมายเหตุ" value="${escapeHtml(item.note)}"></td>
        <td><select class="expense-category" aria-label="หมวดหมู่"><option>รอดำเนินการ</option><option>ค่ากิน</option><option>ค่าใช้จ่ายส่วนตัว</option><option>ค่าอื่นๆ</option><option>แยกบิล</option></select></td>
      </tr>
      <tr class="split-row hidden" data-split-for="${index}"><td colspan="4"><div class="split-panel"><div class="split-grid">
        <div class="field"><label>ค่ากิน</label><input class="split-kin" type="number" min="0" step="0.01" value="0"></div>
        <div class="field"><label>ค่าใช้จ่ายส่วนตัว</label><input class="split-suan" type="number" min="0" step="0.01" value="0"></div>
        <div class="field"><label>ค่าอื่นๆ</label><input class="split-other" type="number" min="0" step="0.01" value="0"></div>
      </div><div class="split-status">กรอกยอดแยกให้เท่ากับยอดบิล ${money(item.amount)} บาท</div></div></td></tr>`).join("");
    return `<div class="pending-card"><div class="card-heading"><div><h3>บิลที่รอจัดหมวด</h3><small>${transactions.length} รายการ · รวม ${money(total)} ฿</small></div>${statusPill(transactions.length ? "รอดำเนินการ" : "เรียบร้อย", transactions.length ? "warn" : "")}</div>
      <div class="expense-table-scroll-hint" role="note">↔ ปัดหรือเลื่อนตารางในแนวนอนเพื่อดูข้อมูลเพิ่มเติม</div><div class="expense-table-wrap"><table class="expense-table"><thead><tr><th>วันที่</th><th>จำนวนเงิน</th><th>หมายเหตุ</th><th>จัดหมวดหมู่</th></tr></thead><tbody>${rows || '<tr><td colspan="4" class="table-empty">ไม่มีรายการรอดำเนินการในเดือนนี้</td></tr>'}</tbody></table></div>
      ${transactions.length ? '<div class="save-row pending-save"><small>เลือกหมวดหมู่ให้บิลที่ต้องการ แล้วกดบันทึก</small><button id="save-pending-button" class="button button-primary" type="button">บันทึกการจัดหมวดหมู่</button></div>' : ''}
    </div>`;
  }

  function renderExpenseHistory() {
    const transactions = [];
    for (let i = 29; i < state.data.length; i++) {
      const row = state.data[i] || [];
      if (row[0] && row[2] && row[2] !== "รอดำเนินการ") {
        transactions.push({date:row[0], amount:number(row[1]), category:row[2], note:row[3] || "-"});
      }
    }
    transactions.reverse();
    const total = transactions.reduce((sum,item) => sum + item.amount, 0);
    const rows = transactions.map(item => `<tr><td>${escapeHtml(item.date)}</td><td class="amount-cell"><strong>${money(item.amount)}</strong><small>บาท</small></td><td>${escapeHtml(item.category)}</td><td>${escapeHtml(item.note)}</td></tr>`).join("");
    return `<article class="card"><div class="history-summary"><div><span>รายการที่บันทึกแล้ว</span><strong>${transactions.length} รายการ</strong></div><div><span>ยอดรวมในเดือนนี้</span><strong>${money(total)} ฿</strong></div></div><div class="expense-table-wrap"><table class="expense-table history-table"><thead><tr><th>วันที่</th><th>จำนวนเงิน</th><th>หมวดหมู่</th><th>หมายเหตุ</th></tr></thead><tbody>${rows || '<tr><td colspan="4" class="table-empty">ยังไม่มีประวัติรายการในเดือนนี้</td></tr>'}</tbody></table></div></article>`;
  }

  function normalizeHistorySearch(value) {
    return String(value ?? "").toLocaleLowerCase("th-TH")
      .replace(/[๐-๙]/g, digit => String("๐๑๒๓๔๕๖๗๘๙".indexOf(digit)))
      .normalize("NFKC").replace(/[฿,\s]/g, "").replace(/[–—]/g, "-");
  }

  function historySearchMatches(item, rawQuery) {
    const query = String(rawQuery || "").trim();
    if (!query) return true;
    const fields = {
      note: normalizeHistorySearch(item.note),
      category: normalizeHistorySearch(item.category),
      month: normalizeHistorySearch(item.month),
      date: normalizeHistorySearch(item.date),
      amount: normalizeHistorySearch(Number(item.amount || 0).toFixed(2))
    };
    const aliases = {
      "อาหาร": ["ค่ากิน", "กิน", "ข้าว", "เครื่องดื่ม"], "กิน": ["ค่ากิน", "อาหาร"],
      "ส่วนตัว": ["ค่าใช้จ่ายส่วนตัว", "ใช้ส่วนตัว"], "ใช้ส่วนตัว": ["ค่าใช้จ่ายส่วนตัว"],
      "อื่น": ["ค่าอื่นๆ", "อื่นๆ"], "อื่นๆ": ["ค่าอื่นๆ"], "รอ": ["รอดำเนินการ", "pending"]
    };
    const searchable = Object.values(fields).join(" ");
    const fuzzyIncludes = (needle, haystack) => {
      if (!needle) return true;
      if (haystack.includes(needle)) return true;
      // One-character typo tolerance for longer Latin/numeric terms; Thai substring matching stays exact.
      if (needle.length < 4 || /[\u0E00-\u0E7F]/.test(needle) || /^\d+(?:\.\d+)?$/.test(needle)) return false;
      return haystack.split(/[^a-z0-9.]+/i).some(word => {
        if (Math.abs(word.length - needle.length) > 1) return false;
        let i=0,j=0,edits=0;
        while(i<needle.length && j<word.length){if(needle[i]===word[j]){i++;j++;continue;}if(++edits>1)return false;if(needle.length>word.length)i++;else if(word.length>needle.length)j++;else{i++;j++;}}
        return edits + (needle.length-i) + (word.length-j) <= 1;
      });
    };
    const parts = query.match(/(?:\"[^\"]+\"|\S+)/g) || [];
    return parts.every(part => {
      const token = part.replace(/^\"|\"$/g, "");
      const range = token.match(/^(?:ยอด|amount)?(>=|<=|>|<)([\d,]+(?:\.\d+)?)$/i);
      if (range) { const value=Number(range[2].replace(/,/g,"")); return range[1]===">" ? item.amount>value : range[1]==="<" ? item.amount<value : range[1]===">=" ? item.amount>=value : item.amount<=value; }
      const qualified = token.match(/^(โน้ต|หมายเหตุ|note|หมวด|หมวดหมู่|category|เดือน|month|วันที่|วัน|date|ยอด|เงิน|amount):(.*)$/i);
      if (qualified) {
        const key = /^(โน้ต|หมายเหตุ|note)$/i.test(qualified[1]) ? "note" : /^(หมวด|หมวดหมู่|category)$/i.test(qualified[1]) ? "category" : /^(เดือน|month)$/i.test(qualified[1]) ? "month" : /^(วันที่|วัน|date)$/i.test(qualified[1]) ? "date" : "amount";
        const term=normalizeHistorySearch(qualified[2]);
        const options=[term, ...(key==="category" ? (aliases[term]||[]).map(normalizeHistorySearch) : [])];
        return options.some(option=>fuzzyIncludes(option, fields[key]));
      }
      const normalized = normalizeHistorySearch(token);
      const candidates = [normalized, ...(aliases[normalized] || []).map(normalizeHistorySearch)];
      return candidates.some(candidate => fuzzyIncludes(candidate, searchable));
    });
  }

  function historyFilteredItems() {
    const filters = state.historyFilters;
    const order = new Map(state.worksheets.map((item,index) => [item.title,index]));
    const items = state.history.filter(item => (filters.month === "all" || item.month === filters.month) && (filters.category === "all" || item.category === filters.category) && historySearchMatches(item, filters.query));
    const timestamp = value => {
      const match = String(value).match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:,?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?)?/);
      if (match) return Date.UTC(Number(match[3]),Number(match[2])-1,Number(match[1]),Number(match[4]||0),Number(match[5]||0),Number(match[6]||0));
      const parsed = Date.parse(value); return Number.isFinite(parsed) ? parsed : 0;
    };
    items.sort((a,b) => filters.sort === "oldest" ? (timestamp(a.date)-timestamp(b.date) || order.get(a.month)-order.get(b.month) || a.sheetRow-b.sheetRow) : filters.sort === "amount-high" ? b.amount-a.amount : filters.sort === "amount-low" ? a.amount-b.amount : (timestamp(b.date)-timestamp(a.date) || order.get(b.month)-order.get(a.month) || b.sheetRow-a.sheetRow));
    return items;
  }

  function renderHistoryWorkspace() {
    const sidebar = $("#finance-sidebar-slot");
    sidebar?.querySelectorAll(".sidebar-link[data-app-view]").forEach(link => {
      const active = link.dataset.appView === "history";
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
    });
    const heading = $("#app-panel .page-heading h1"), eyebrow = $("#app-panel .page-heading .eyebrow");
    if (heading) heading.textContent = "ประวัติรายการ";
    if (eyebrow) eyebrow.textContent = "TRANSACTION HISTORY";
    if ($("#welcome-user")) $("#welcome-user").textContent = "ตรวจสอบและจัดการรายจ่ายจากทุกเดือน";
    const monthTools = $("#month-select")?.closest(".select-wrap");
    if (monthTools) monthTools.hidden = true;
    $("#close-month-button").hidden = true;
    $("#dashboard-content").innerHTML = `<div class="finance-main history-main">${renderHistoryPage()}</div>`;
    bindHistoryEvents();
  }

  function historyCategoryTone(category) {
    const value=String(category||"").toLocaleLowerCase("th-TH");
    if(value.includes("กิน")||value.includes("อาหาร"))return "food";
    if(value.includes("ส่วนตัว")||value.includes("personal"))return "personal";
    if(value.includes("อื่น")||value.includes("other"))return "other";
    if(value.includes("รอ")||value.includes("pending"))return "pending";
    return "neutral";
  }

  function renderHistoryPage() {
    const items = historyFilteredItems(), total = items.reduce((sum,item)=>sum+item.amount,0);
    const categories = [...new Set(state.history.map(item=>item.category))].sort((a,b)=>a.localeCompare(b,"th"));
    const rows = items.map(item => `<tr data-history-id="${escapeHtml(item.id)}"><td><label class="history-select-hit"><input type="checkbox" class="history-select" aria-label="เลือกรายการ"><span></span></label></td><td><strong>${escapeHtml(item.date)}</strong><small class="history-month">${escapeHtml(item.month)}</small></td><td class="amount-cell"><strong>${money(item.amount)}</strong><small>บาท</small></td><td><span class="history-category tone-${historyCategoryTone(item.category)}"><i aria-hidden="true"></i>${escapeHtml(item.category)}</span></td><td class="history-note">${escapeHtml(item.note)}</td><td class="history-actions"><button class="history-action" data-history-action="edit" type="button">แก้ไข</button><button class="history-action" data-history-action="split" type="button">แยกบิล</button><button class="history-action danger" data-history-action="delete" type="button">ลบ</button></td></tr>`).join("");
    const months = state.worksheets.slice().reverse().map(item=>`<option value="${escapeHtml(item.title)}" ${state.historyFilters.month===item.title?"selected":""}>${escapeHtml(item.title)}</option>`).join("");
    const categoryOptions = categories.map(item=>`<option value="${escapeHtml(item)}" ${state.historyFilters.category===item?"selected":""}>${escapeHtml(item)}</option>`).join("");
    return `<section id="history-page" class="history-page">
      <div class="history-hero"><div><span class="eyebrow">YOUR TRANSACTIONS</span><h2>จัดการทุกธุรกรรมในที่เดียว</h2><p>ข้อมูลจาก Google Sheets ทุกเดือน · แก้ไขแล้วบันทึกกลับไปยังชีตต้นทาง</p></div><button id="history-export" class="button button-quiet" type="button">↓ ส่งออก CSV</button></div>
      <div class="history-metrics"><article><span>รายการที่พบ</span><strong>${items.length.toLocaleString("th-TH")} <small>รายการ</small></strong></article><article><span>ยอดรวมตามตัวกรอง</span><strong>${money(total)} <small>บาท</small></strong></article><article><span>เฉลี่ยต่อรายการ</span><strong>${money(items.length?total/items.length:0)} <small>บาท</small></strong></article><article><span>เดือนในระบบ</span><strong>${state.worksheets.length.toLocaleString("th-TH")} <small>เดือน</small></strong></article></div>
      <div class="history-toolbar"><form id="history-filter-form"><label class="history-search"><span>ค้นหารายการ</span><input name="query" type="search" value="${escapeHtml(state.historyFilters.query)}" placeholder="ลองค้นหา: กาแฟ · หมวด:อาหาร · ยอด>500 · โน้ต:ข้าว"></label><label><span>เดือน</span><select name="month"><option value="all">ทุกเดือน</option>${months}</select></label><label><span>หมวดหมู่</span><select name="category"><option value="all">ทุกหมวดหมู่</option>${categoryOptions}</select></label><label><span>เรียงลำดับ</span><select name="sort"><option value="newest" ${state.historyFilters.sort==="newest"?"selected":""}>ใหม่ล่าสุด</option><option value="oldest" ${state.historyFilters.sort==="oldest"?"selected":""}>เก่าที่สุด</option><option value="amount-high" ${state.historyFilters.sort==="amount-high"?"selected":""}>ยอดสูงสุด</option><option value="amount-low" ${state.historyFilters.sort==="amount-low"?"selected":""}>ยอดต่ำสุด</option></select></label><button class="button button-primary" type="submit">ค้นหา</button><button id="history-reset" class="history-filter-reset" type="button">ล้างตัวกรอง</button></form></div>
      <div class="history-bulkbar"><span>เลือกหลายรายการเพื่อรวมบิล</span><button id="history-merge" class="button button-quiet" type="button" disabled>รวมรายการที่เลือก</button><small id="history-selection-count">ยังไม่ได้เลือกรายการ</small></div>
      <div class="history-table-card"><div class="history-table-head"><div><h3>รายการธุรกรรม</h3><small>แสดง ${items.length.toLocaleString("th-TH")} รายการ</small></div><span class="history-live"><i></i> GOOGLE SHEETS SYNC</span></div><div class="history-table-scroll-hint" role="note">↔ ปัดหรือเลื่อนตารางในแนวนอนเพื่อดูข้อมูลเพิ่มเติม</div><div class="expense-table-wrap"><table class="expense-table history-table-full"><thead><tr><th></th><th>วันที่ / เดือน</th><th>จำนวนเงิน</th><th>หมวดหมู่</th><th>หมายเหตุ</th><th>จัดการ</th></tr></thead><tbody>${rows || '<tr><td colspan="6" class="table-empty">ไม่พบรายการที่ตรงกับเงื่อนไข</td></tr>'}</tbody></table></div></div>
      <dialog id="history-edit-dialog" class="history-dialog"><form id="history-edit-form"><span class="eyebrow">TRANSACTION EDITOR</span><h3 id="history-dialog-title">แก้ไขรายการ</h3><p class="history-dialog-hint">บันทึกกลับไปยัง Google Sheets ของเดือนที่เลือก</p><div class="history-editor-fields"><label><span>วันที่ / เวลา</span><input name="date" required maxlength="80"></label><label><span>จำนวนเงิน (บาท)</span><input name="amount" type="number" min="0.01" step="0.01" required></label><label><span>หมวดหมู่</span><select name="category"><option>ค่ากิน</option><option>ค่าใช้จ่ายส่วนตัว</option><option>ค่าอื่นๆ</option><option>รอดำเนินการ</option></select></label><label class="history-editor-note"><span>หมายเหตุ</span><input name="note" maxlength="250"></label></div><div id="history-split-fields" class="history-split-fields" hidden><strong>แบ่งยอดเป็นหมวดหมู่</strong><small>ยอดรวมต้องเท่ากับยอดบิลเดิม</small><label>ค่ากิน<input name="splitFood" type="number" min="0" step="0.01" value="0"></label><label>ใช้ส่วนตัว<input name="splitPersonal" type="number" min="0" step="0.01" value="0"></label><label>ค่าอื่นๆ<input name="splitOther" type="number" min="0" step="0.01" value="0"></label><p id="history-split-total">รวม 0.00 บาท</p></div><div class="dialog-actions"><button class="button button-quiet" type="button" data-history-close>ยกเลิก</button><button class="button button-primary" type="submit">บันทึกการเปลี่ยนแปลง</button></div></form></dialog>
      <dialog id="history-merge-dialog" class="history-dialog"><form id="history-merge-form"><span class="eyebrow">MERGE TRANSACTIONS</span><h3>รวมรายการที่เลือก</h3><p class="history-dialog-hint">รวมยอดไว้ในแถวแรกและล้างแถวอื่น ต้องเป็นเดือนเดียวกัน</p><label><span>หมวดหมู่ของรายการรวม</span><select name="category"><option>ค่ากิน</option><option>ค่าใช้จ่ายส่วนตัว</option><option>ค่าอื่นๆ</option></select></label><label><span>หมายเหตุใหม่</span><input name="note" maxlength="250"></label><div class="dialog-actions"><button class="button button-quiet" type="button" data-history-close>ยกเลิก</button><button class="button button-primary" type="submit">ยืนยันรวมบิล</button></div></form></dialog>
    </section>`;
  }

  function bindHistoryEvents() {
    const root = $("#history-page"); if (!root) return;
    const filter = $("#history-filter-form",root);
    filter.addEventListener("submit",event=>{ event.preventDefault(); const f=event.currentTarget; state.historyFilters={query:f.elements.query.value,month:f.elements.month.value,category:f.elements.category.value,sort:f.elements.sort.value}; renderHistoryWorkspace(); });
    let searchTimer;
    filter.elements.query.addEventListener("input",event=>{
      const input=event.currentTarget, value=input.value, cursor=input.selectionStart;
      clearTimeout(searchTimer);
      searchTimer=setTimeout(()=>{
        state.historyFilters.query=value;
        renderHistoryWorkspace();
        const next=$("#history-filter-form")?.elements.query;
        if(next){next.focus();next.setSelectionRange(cursor,cursor);}
      },180);
    });
    $("#history-reset",root).addEventListener("click",()=>{state.historyFilters={query:"",month:"all",category:"all",sort:"newest"};renderHistoryWorkspace();});
    ["month","category","sort"].forEach(name=>filter.elements[name].addEventListener("change",()=>filter.requestSubmit()));
    root.querySelectorAll("[data-history-close]").forEach(button=>button.addEventListener("click",()=>button.closest("dialog").close()));
    root.querySelectorAll(".history-select").forEach(input=>input.addEventListener("change",()=>{const n=root.querySelectorAll(".history-select:checked").length;$("#history-selection-count").textContent=n?`เลือกแล้ว ${n} รายการ`:"ยังไม่ได้เลือกรายการ";$("#history-merge").disabled=n<2;}));
    root.querySelectorAll("[data-history-action]").forEach(button=>button.addEventListener("click",()=>{const tr=button.closest("tr"),item=state.history.find(entry=>entry.id===tr.dataset.historyId);if(!item)return;if(button.dataset.historyAction==="delete")deleteHistoryItem(item);else openHistoryEditor(item,button.dataset.historyAction);}));
    $("#history-export",root).addEventListener("click",exportHistoryCsv);
    $("#history-merge",root).addEventListener("click",()=>{const selected=[...root.querySelectorAll(".history-select:checked")].map(input=>state.history.find(item=>item.id===input.closest("tr").dataset.historyId)).filter(Boolean);if(selected.length<2){toast("กรุณาเลือกอย่างน้อย 2 รายการ","info");return;}if(new Set(selected.map(item=>item.month)).size!==1){toast("รวมบิลได้เฉพาะรายการในเดือนเดียวกัน","error");return;}state.mergeSelection=selected;$("#history-merge-dialog").showModal();});
    $("#history-edit-form",root).addEventListener("submit",saveHistoryEditor);
    $("#history-merge-form",root).addEventListener("submit",saveMergedHistory);
    ["splitFood","splitPersonal","splitOther"].forEach(name=>$("#history-edit-form",root).elements[name].addEventListener("input",updateHistorySplitTotal));
  }

  function openHistoryEditor(item,mode) {
    state.historyEditor={...item,mode};const form=$("#history-edit-form");
    form.elements.date.value=item.date;form.elements.amount.value=item.amount;form.elements.category.value=item.category;form.elements.note.value=item.note==="-"?"":item.note;
    $("#history-split-fields").hidden=mode!=="split";$("#history-dialog-title").textContent=mode==="split"?"แยกบิลออกเป็นหลายหมวด":"แก้ไขรายการ";
    form.elements.amount.readOnly=mode==="split";
    if(mode==="split"){form.elements.splitFood.value=0;form.elements.splitPersonal.value=0;form.elements.splitOther.value=0;updateHistorySplitTotal();}
    $("#history-edit-dialog").showModal();
  }

  function updateHistorySplitTotal(){const f=$("#history-edit-form");const total=number(f.elements.splitFood.value)+number(f.elements.splitPersonal.value)+number(f.elements.splitOther.value);$("#history-split-total").textContent="รวม "+money(total)+" บาท";}

  async function saveHistoryEditor(event){
    event.preventDefault();const item=state.historyEditor;if(!item)return;const f=event.currentTarget,date=f.elements.date.value.trim(),amount=number(f.elements.amount.value),note=f.elements.note.value.trim()||"-";
    if(!date||amount<=0){toast("กรุณาตรวจสอบวันที่และจำนวนเงิน","error");return;}
    const dateMatch=date.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/), isoMatch=date.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
    if(date!==item.date&&!dateMatch&&!isoMatch){toast("กรุณากรอกวันที่เป็น DD/MM/YYYY หรือ YYYY-MM-DD","error");return;}
    const dateMonth=dateMatch?Number(dateMatch[2]):isoMatch?Number(isoMatch[2]):null,dateYear=dateMatch?Number(dateMatch[3]):isoMatch?Number(isoMatch[1]):null;
    if(dateMonth!==null){const parts=item.month.split(" "),expectedMonth=MONTHS.indexOf(parts[0])+1,expectedYear=1957+Number(parts[1]);if(dateMonth!==expectedMonth||dateYear!==expectedYear){toast("วันที่ต้องอยู่ภายในเดือน "+item.month,"error");return;}}
    await runSave(async()=>{
      if(item.mode==="split"){
        const parts=[[number(f.elements.splitFood.value),"ค่ากิน"],[number(f.elements.splitPersonal.value),"ค่าใช้จ่ายส่วนตัว"],[number(f.elements.splitOther.value),"ค่าอื่นๆ"]].filter(part=>part[0]>0),sum=parts.reduce((n,p)=>n+p[0],0);
        if(parts.length<2||Math.abs(sum-item.amount)>.01)throw new Error("ต้องแบ่งอย่างน้อย 2 หมวด และยอดรวมต้องเท่ากับ "+money(item.amount)+" บาท");
        const extra=parts.slice(1).map(p=>[date,p[0],p[1],note]);
        await spreadsheetBatchUpdate([{insertDimension:{range:{sheetId:sheetId(item.month),dimension:"ROWS",startIndex:item.sheetRow,endIndex:item.sheetRow+extra.length},inheritFromBefore:true}}]);
        await batchWrite([{range:sheetRange(item.month,"A"+item.sheetRow+":D"+item.sheetRow),values:[[date,parts[0][0],parts[0][1],note]]},{range:sheetRange(item.month,"A"+(item.sheetRow+1)+":D"+(item.sheetRow+extra.length)),values:extra}]);
      }else await batchWrite([{range:sheetRange(item.month,"A"+item.sheetRow+":D"+item.sheetRow),values:[[date,amount,f.elements.category.value,note]]}]);
      $("#history-edit-dialog").close();state.historyEditor=null;
      if(item.month===state.month)await loadMonth();else{await loadHistoryData();renderHistoryWorkspace();}
      toast(item.mode==="split"?"แยกบิลและบันทึกแล้ว":"แก้ไขรายการเรียบร้อยแล้ว","success");
    });
  }

  async function deleteHistoryItem(item){
    if(!window.confirm("ยืนยันลบรายการ "+item.note+" จำนวน "+money(item.amount)+" บาท จาก "+item.month+"?"))return;
    await runSave(async()=>{await clearRanges([sheetRange(item.month,"A"+item.sheetRow+":D"+item.sheetRow)]);if(item.month===state.month)await loadMonth();else{await loadHistoryData();renderHistoryWorkspace();}toast("ลบรายการเรียบร้อยแล้ว","success");});
  }

  async function saveMergedHistory(event){
    event.preventDefault();const selected=state.mergeSelection||[];if(selected.length<2)return;const f=event.currentTarget,month=selected[0].month,total=selected.reduce((n,item)=>n+item.amount,0),first=selected.slice().sort((a,b)=>a.sheetRow-b.sheetRow)[0];
    const note=f.elements.note.value.trim()||selected.map(item=>item.note).filter(value=>value&&value!=="-").join(" + ")||"รวมบิล";
    await runSave(async()=>{await batchWrite([{range:sheetRange(month,"A"+first.sheetRow+":D"+first.sheetRow),values:[[first.date,total,f.elements.category.value,note]]},...selected.filter(item=>item.id!==first.id).map(item=>({range:sheetRange(month,"A"+item.sheetRow+":D"+item.sheetRow),values:[["","","",""]]}))]);$("#history-merge-dialog").close();state.mergeSelection=[];if(month===state.month)await loadMonth();else{await loadHistoryData();renderHistoryWorkspace();}toast("รวม "+selected.length+" รายการเป็นบิลเดียวแล้ว","success");});
  }

  function exportHistoryCsv(){
    const items=historyFilteredItems(),rows=[["เดือน","วันที่","จำนวนเงิน","หมวดหมู่","หมายเหตุ"],...items.map(item=>[item.month,item.date,item.amount,item.category,item.note])];
    const csv=String.fromCharCode(0xFEFF)+rows.map(row=>row.map(value=>'"'+String(value??"").replace(/"/g,'""')+'"').join(",")).join(String.fromCharCode(13,10));
    const blob=new Blob([csv],{type:"text/csv;charset=utf-8;"}),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download="kla-finance-history.csv";document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);toast("ส่งออก "+items.length+" รายการเป็น CSV แล้ว","success");
  }

  function renderBalance(remaining) {
    const bank = cell(4,5), cash = cell(5,5), actual = bank + cash, diff = actual - remaining;
    const tone = Math.abs(diff) <= .01 ? "" : diff < 0 ? "danger" : "warn";
    const status = Math.abs(diff) <= .01 ? "ยอดตรงกัน" : diff < 0 ? "เงินขาด" : "เงินเกิน";
    return `<article class="card"><div class="card-heading"><div><h3>ยอดเงินในมือ</h3><small>เงินโอน F5 + เงินสด F6 เทียบกับยอดคงเหลือ F3</small></div>${statusPill(status,tone)}</div>
      <div class="balance-grid"><div class="balance-box"><small>เงินในระบบ (ควรมี)</small><strong>${money(remaining)} ฿</strong></div><div class="balance-box"><small>เงินจริง (โอน + สด)</small><strong>${money(actual)} ฿</strong></div><div class="balance-box"><small>ส่วนต่าง</small><strong style="color:${Math.abs(diff)<=.01?"var(--green)":diff<0?"var(--red)":"var(--orange)"}">${diff > 0 ? "+" : ""}${money(diff)} ฿</strong></div></div>
      <p class="muted">${Math.abs(diff) <= .01 ? "ยอดเงินตรงกันภายในค่าคลาดเคลื่อน 0.01 บาท" : diff < 0 ? "เงินขาดไป " + money(Math.abs(diff)) + " บาท อาจมีรายจ่ายตกหล่น" : "เงินเกินมา " + money(diff) + " บาท อาจมีเงินเข้าหรือรายการซ้ำ"}</p>
      <form id="balance-form" class="form-grid"><div class="field"><label>เงินสด (F6)</label><input name="cash" value="${escapeHtml(cash)}" inputmode="decimal"></div><div class="field"><label>เงินโอน (F5)</label><input name="bank" value="${escapeHtml(bank)}" inputmode="decimal"></div><div class="field field-wide"><button class="button button-primary" type="submit">บันทึกยอดเงินจริง</button></div></form>
    </article>`;
  }

  function renderSpendingShareCard({used,labels,expenseTotal,pieGradient,pieSum}) {
    const colors = ["#ef858b","#54bba6","#f0bd69"];
    const legend = labels.map((label,index) => {
      const percentage = pieSum ? used[index] / pieSum * 100 : 0;
      return '<div class="legend-row">' +
        '<span class="legend-name"><i class="legend-dot" style="background:' + colors[index] + '"></i>' + escapeHtml(label) + '</span>' +
        '<b>' + money(used[index]) + ' ฿</b>' +
        '<div class="legend-track"><i style="width:' + percentage + '%;background:' + colors[index] + '"></i></div>' +
        '<small>' + percentage.toFixed(1) + '%</small></div>';
    }).join("");
    return [
      '<article class="card spending-share-card">',
      '<div class="card-heading"><div><span class="insight-kicker">MONTHLY BREAKDOWN</span><h3>สัดส่วนรายจ่ายเดือนนี้</h3><small>เปรียบเทียบสัดส่วนของแต่ละหมวด</small></div>',
      '<div class="spend-total-wrap"><small>ยอดรายจ่าย</small><strong class="spend-total">' + money(expenseTotal) + ' <i>฿</i></strong></div></div>',
      '<div class="budget-layout"><div class="donut spend-donut" style="background:conic-gradient(' + pieGradient + ')"><div class="donut-center"><strong>' + (pieSum ? "100%" : "—") + '</strong><small>สัดส่วนรวม</small></div></div>',
      '<div class="budget-legend">' + legend + '</div></div>',
      '<div class="share-card-foot"><span><i></i>สัดส่วนคำนวณจากยอดใช้จ่ายทั้ง 3 หมวด</span><span>' + (pieSum ? "100%" : "ยังไม่มีรายการ") + '</span></div>',
      '</article>'
    ].join("");
  }

  function renderSpendingInsights() {
    const parseExpenseDate = value => {
      const raw = String(value ?? "").trim();
      const datePart = raw.split(",")[0].trim().split(" ")[0];
      let parts, day, month, year;
      if (datePart.includes("/")) {
        parts = datePart.split("/");
        if (parts.length !== 3) return null;
        day = Number(parts[0]); month = Number(parts[1]); year = Number(parts[2]);
      } else if (datePart.includes("-")) {
        parts = datePart.split("-");
        if (parts.length !== 3) return null;
        year = Number(parts[0]); month = Number(parts[1]); day = Number(parts[2]);
      } else {
        return null;
      }
      if (year >= 2400) year -= 543;
      const check = new Date(year, month - 1, day);
      if (!Number.isInteger(day) || !Number.isInteger(month) || !Number.isInteger(year) ||
          check.getFullYear() !== year || check.getMonth() !== month - 1 || check.getDate() !== day) return null;
      return {day,month,year};
    };

    const monthParts = String(state.month || "").trim().split(" ");
    const monthIndex = MONTHS.indexOf(monthParts[0]);
    const yearToken = Number(monthParts[1]);
    const targetYear = yearToken >= 2400 ? yearToken - 543 : yearToken >= 100 ? yearToken : 1957 + yearToken;
    const nowParts = new Intl.DateTimeFormat("en-US", {
      timeZone:"Asia/Bangkok",year:"numeric",month:"numeric",day:"numeric"
    }).formatToParts(new Date()).reduce((result,part) => {
      if (part.type !== "literal") result[part.type] = Number(part.value);
      return result;
    }, {});
    const isFutureMonth = targetYear > nowParts.year || (targetYear === nowParts.year && monthIndex > nowParts.month - 1);
    const isCurrentMonth = targetYear === nowParts.year && monthIndex === nowParts.month - 1;
    const elapsedDays = monthIndex < 0 || !Number.isFinite(targetYear) || isFutureMonth ? 0 :
      isCurrentMonth ? nowParts.day : new Date(targetYear, monthIndex + 1, 0).getDate();

    const transactions = [];
    for (let index = 29; index < state.data.length; index++) {
      const row = state.data[index] || [];
      const date = parseExpenseDate(row[0]);
      const amount = number(row[1]);
      if (date && date.month === monthIndex + 1 && date.year === targetYear &&
          date.day <= elapsedDays && amount > 0 && row[2]) {
        transactions.push({
          day:date.day,
          amount,
          category:String(row[2]),
          note:String(row[3] || ""),
          dateLabel:String(date.day).padStart(2,"0") + " " + MONTHS[monthIndex]
        });
      }
    }

    const activeDaySet = new Set(transactions.map(item => item.day));
    const missingDays = Array.from({length:elapsedDays},(_,index)=>index+1).filter(day=>!activeDaySet.has(day));
    const dailyTotals = {};
    transactions.forEach(item => dailyTotals[item.day] = (dailyTotals[item.day] || 0) + item.amount);
    const peak = Object.entries(dailyTotals).sort((a,b)=>Number(b[1])-Number(a[1]))[0];
    const biggest = transactions.reduce((best,item)=>!best || item.amount > best.amount ? item : best,null);
    const activeDays = activeDaySet.size;
    const totalSpend = transactions.reduce((sum,item)=>sum+item.amount,0);
    const dailyAverage = activeDays ? totalSpend / activeDays : 0;

    const missingDateCards = missingDays.map(day =>
      '<span class="no-spend-date-chip"><b>' + String(day).padStart(2,"0") +
      '</b><small>' + escapeHtml(MONTHS[monthIndex]) + '</small></span>'
    ).join("");
    const noSpendDescription = isFutureMonth
      ? "เดือนนี้ยังมาไม่ถึง"
      : "ตั้งแต่วันที่ 1 ถึง " + elapsedDays + " " + MONTHS[monthIndex];
    const noSpendDetail = missingDays.length
      ? missingDays.length + " วันที่ไม่มีบิลที่บันทึกไว้"
      : isFutureMonth ? "ยังไม่เริ่มนับวัน" : "มีรายการใช้จ่ายครบทุกวันแล้ว";
    const peakDate = peak ? String(peak[0]).padStart(2,"0") + " " + MONTHS[monthIndex] : "—";
    const biggestLabel = biggest
      ? biggest.category === "รอดำเนินการ" ? "รอจัดหมวด" : biggest.category
      : "ยังไม่มีข้อมูล";

    return [
      '<div class="spend-preview-grid">',
      '<div class="spend-preview-highlight spend-insight-bill"><span class="spend-insight-icon" aria-hidden="true">↗</span><span>บิลที่สูงที่สุด</span><strong>' + escapeHtml(biggestLabel) + '</strong><b>' + (biggest ? money(biggest.amount) + " ฿" : "—") + '</b><small>' + (biggest ? escapeHtml(biggest.note || biggest.dateLabel) : "บันทึกรายจ่ายเพื่อเริ่มดูสถิติ") + '</small></div>',
      '<div class="spend-preview-highlight spend-insight-peak"><span class="spend-insight-icon" aria-hidden="true">◷</span><span>วันที่ใช้จ่ายสูงสุด</span><strong>' + peakDate + '</strong><b>' + (peak ? money(peak[1]) + " ฿" : "—") + '</b><small>' + (peak ? "ยอดรวมของวันนั้น" : "ยังไม่มีรายการในเดือนนี้") + '</small></div>',
      '<div class="spend-preview-highlight spend-insight-average"><span class="spend-insight-icon" aria-hidden="true">◉</span><span>เฉลี่ยต่อวันที่มีรายจ่าย</span><strong>' + (activeDays ? money(dailyAverage) + " ฿" : "—") + '</strong><small>' + (activeDays ? "คำนวณจาก " + activeDays + " วันที่มีรายการ" : "ยังไม่มีวันที่มีรายการ") + '</small></div>',
      '<div class="spend-no-activity-wrap">',
      '<button type="button" class="spend-preview-highlight spend-no-activity" data-no-spend-trigger aria-expanded="false" aria-controls="no-spend-dates-panel">',
      '<span class="spend-insight-icon" aria-hidden="true">☼</span><span>วันที่ไม่มีรายการใช้จ่าย</span>',
      '<strong>' + missingDays.length + ' <i>วัน</i></strong><small>' + noSpendDetail + '</small>',
      '<em>ชี้หรือคลิกเพื่อดูวันที่ <b aria-hidden="true">↗</b></em></button>',
      '<div class="no-spend-popover" id="no-spend-dates-panel" hidden>',
      '<div class="no-spend-popover-head"><div><strong>วันที่ไม่มีรายการ</strong><small>' + escapeHtml(noSpendDescription) + '</small></div><span>' + missingDays.length + ' วัน</span></div>',
      missingDays.length
        ? '<div class="no-spend-date-grid">' + missingDateCards + '</div>'
        : '<div class="no-spend-empty">' + (isFutureMonth ? "เดือนที่เลือกยังไม่เริ่มต้น" : "ยอดเยี่ยม! มีรายการใช้จ่ายครบทุกวัน") + '</div>',
      '<div class="no-spend-popover-foot">วันที่แสดงอ้างอิงจากรายการบิลที่บันทึกในชีตเดือนนี้</div></div></div>',
      '</div>'
    ].join("");
  }

  function renderCharts({usedFood,usedPersonal,usedOther,budgets,emergency}) {
    const summaryRows = state.summary.slice(1);
    const carry = summaryRows.map(row => ({label:row[0] || "",value:number(row[4])}));
    const income = [];
    let trackIncome = false;
    for (const row of summaryRows) {
      const label = String(row[0] || "");
      if (label.includes("มิ.ย.") || label.includes("มิถุนายน")) trackIncome = true;
      if (trackIncome) income.push({label, value:number(row[5])});
    }
    const emergencyHistory = summaryRows.map(row => ({label:row[0] || "",value:number(row[2])}));
    if (!emergencyHistory.some(row => row.label === state.month)) emergencyHistory.push({label:state.month,value:emergency});
    else emergencyHistory.forEach(row => { if (row.label === state.month) row.value = emergency; });
    if (!income.some(row => row.label === state.month) && (state.month.includes("มิ.ย.") || income.length)) income.push({label:state.month,value:cell(15,5)});
    const used = [usedFood,usedPersonal,usedOther];
    const labels = ["ค่ากิน","ใช้ส่วนตัว","อื่นๆ"];
    const expenseTotal = used.reduce((a,b)=>a+b,0);
    const pieParts = used.map((value,index) => ({value,label:labels[index]})).filter(item => item.value > 0);
    const pieSum = pieParts.reduce((sum,item)=>sum+item.value,0);
    let cursor = 0;
    const pieGradient = pieSum ? pieParts.map((item,index) => { const start=cursor; cursor += item.value/pieSum*100; return `${["#ef858b","#54bba6","#f0bd69"][labels.indexOf(item.label)]} ${start}% ${cursor}%`; }).join(",") : "#edf0f5 0 100%";
    const baseExpenses = cell(21,1) + cell(22,1) + cell(23,1) + cell(24,1);
    return `<div class="grid chart-grid">
      ${renderSpendingShareCard({used,labels,expenseTotal,pieGradient,pieSum})}
      <article class="card spending-insights-card"><div class="card-heading"><div><span class="insight-kicker">SMART SPENDING INSIGHTS</span><h3>สรุปการใช้จ่าย</h3><small>มุมมองพฤติกรรมการใช้เงินในเดือนที่เลือก</small></div><span class="insight-header-mark" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d="M4 19.5h16M6.5 16V11m5 5V5m5 11V8m-10 0 5-3 5 3 3-2"/></svg></span></div><div class="spend-preview">${renderSpendingInsights()}</div></article>
      <article class="card"><div class="card-heading"><div><h3>แนวโน้มเงินยกยอด</h3><small>Carry_Cash จาก Summary_Data</small></div></div>${lineChart(carry)}</article>
      <article class="card"><div class="card-heading"><div><h3>รายได้ส่วนตัวรายเดือน</h3><small>เริ่มแสดงตั้งแต่เดือนมิถุนายนตามระบบเดิม</small></div></div>${lineChart(income)}</article>
      <article class="card"><div class="card-heading"><div><h3>การเติบโตของเงินสำรองฉุกเฉิน</h3><small>ยอดปัจจุบัน ${money(emergency)} ฿</small></div></div>${lineChart(emergencyHistory, [{value:baseExpenses,color:"#e45b66"},{value:baseExpenses*3,color:"#e9b34c"},{value:baseExpenses*6,color:"#4263eb"}])}<div class="chart-legend"><span><i style="background:#e45b66"></i>1 เท่า: ${money0(baseExpenses)} ฿</span><span><i style="background:#e9b34c"></i>3 เท่า: ${money0(baseExpenses*3)} ฿</span><span><i style="background:#4263eb"></i>6 เท่า: ${money0(baseExpenses*6)} ฿</span></div></article>
    </div>`;
  }

  function lineChart(records, thresholds = []) {
    const valid = records.filter(item => Number.isFinite(item.value));
    if (!valid.length) return '<div class="table-empty">ยังไม่มีข้อมูลสถิติ</div>';
    const width=520,height=190,left=38,right=12,top=14,bottom=34;
    const max=Math.max(...valid.map(item=>item.value),...thresholds.map(item=>item.value),1)*1.12;
    const x=index=>left+(valid.length===1?0:index/(valid.length-1))*(width-left-right);
    const y=value=>top+(height-top-bottom)*(1-value/max);
    const points=valid.map((item,index)=>[x(index),y(item.value)]);
    const poly=points.map(point=>point.join(",")).join(" ");
    const area=`${left},${height-bottom} ${poly} ${points[points.length-1][0]},${height-bottom}`;
    const grid=[0,.5,1].map(f=>{const gy=top+(height-top-bottom)*f;return `<line class="chart-gridline" x1="${left}" y1="${gy}" x2="${width-right}" y2="${gy}"/>`;}).join("");
    const circles=points.map((point,index)=>`<circle class="chart-point chart-data-trigger" cx="${point[0]}" cy="${point[1]}" r="5" tabindex="0" role="button" aria-label="${escapeHtml(valid[index].label)}: ${money(valid[index].value)} บาท" data-chart-tip="${escapeHtml(valid[index].label)}: ${money(valid[index].value)} ฿"/>`).join("");
    const thresholdLines=thresholds.filter(item=>item.value>0).map(item=>`<line x1="${left}" y1="${y(item.value)}" x2="${width-right}" y2="${y(item.value)}" stroke="${item.color}" stroke-width="1.2" stroke-dasharray="5 4" opacity=".85"/>`).join("");
    const labels=valid.map((item,index)=>index===0||index===valid.length-1||valid.length<=5?`<text x="${x(index)}" y="${height-9}" text-anchor="middle" fill="#8b96a6" font-size="9">${escapeHtml(item.label)}</text>`:"").join("");
    return `<div class="chart-wrap"><svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="กราฟแนวโน้ม">${grid}<polygon class="chart-area" points="${area}"/>${thresholdLines}<polyline class="chart-line" points="${poly}"/>${circles}${labels}</svg></div>`;
  }

  function bindDashboardEvents() {
    const sidebarToggle = $("#sidebar-collapse-toggle");
    const appShell = $(".app-shell");
    let chartTip = document.querySelector("#chart-data-tooltip");
    if (!chartTip) { chartTip = document.createElement("div"); chartTip.id = "chart-data-tooltip"; chartTip.className = "chart-data-tooltip"; chartTip.setAttribute("role", "status"); document.body.appendChild(chartTip); }
    const hideChartTip = () => { chartTip.classList.remove("is-visible"); };
    const showChartTip = target => { if (!target?.dataset.chartTip) return; chartTip.textContent = target.dataset.chartTip; const rect = target.getBoundingClientRect(); chartTip.style.left = `${Math.min(window.innerWidth - 230, Math.max(8, rect.left + rect.width / 2))}px`; chartTip.style.top = `${Math.max(8, rect.top - 42)}px`; chartTip.classList.add("is-visible"); };
    $("#dashboard-content")?.querySelectorAll(".chart-data-trigger").forEach(target => { target.addEventListener("mouseenter", () => showChartTip(target)); target.addEventListener("mouseleave", hideChartTip); target.addEventListener("focus", () => showChartTip(target)); target.addEventListener("blur", hideChartTip); target.addEventListener("click", () => showChartTip(target)); });
    const dashboardRoot = $("#dashboard-content");
    dashboardRoot?.querySelectorAll(".spend-no-activity-wrap").forEach(wrapper => {
      const trigger = wrapper.querySelector("[data-no-spend-trigger]");
      const panel = wrapper.querySelector(".no-spend-popover");
      if (!trigger || !panel) return;
      let pinned = false;
      let dismissedWhileHovered = false;
      const setOpen = open => {
        panel.hidden = !open;
        trigger.setAttribute("aria-expanded", String(open));
        wrapper.classList.toggle("is-open", open);
      };
      wrapper.addEventListener("no-spend-close", () => {
        pinned = false;
        dismissedWhileHovered = true;
        setOpen(false);
        if (document.activeElement === trigger) trigger.blur();
      });
      wrapper.addEventListener("mouseenter", () => {
        if (!pinned && !dismissedWhileHovered) setOpen(true);
      });
      wrapper.addEventListener("mouseleave", () => {
        dismissedWhileHovered = false;
        if (!pinned) setOpen(false);
      });
      trigger.addEventListener("focus", () => {
        dismissedWhileHovered = false;
        setOpen(true);
      });
      trigger.addEventListener("blur", event => {
        if (!wrapper.contains(event.relatedTarget) && !pinned) setOpen(false);
      });
      trigger.addEventListener("click", () => {
        pinned = !pinned;
        if (pinned) {
          dismissedWhileHovered = false;
          setOpen(true);
        } else {
          dismissedWhileHovered = true;
          setOpen(false);
        }
      });
      trigger.addEventListener("keydown", event => {
        if (event.key === "Escape") {
          pinned = false;
          dismissedWhileHovered = true;
          setOpen(false);
          trigger.blur();
        }
      });
    });
    if (!document.documentElement.dataset.noSpendOutsideHandler) {
      document.addEventListener("pointerdown", event => {
        document.querySelectorAll(".spend-no-activity-wrap.is-open").forEach(wrapper => {
          if (wrapper.contains(event.target)) return;
          wrapper.dispatchEvent(new Event("no-spend-close"));
        });
      });
      document.documentElement.dataset.noSpendOutsideHandler = "true";
    }
    let sidebarCollapsed = false;
    try { sidebarCollapsed = localStorage.getItem("kla-sidebar-collapsed") === "true"; } catch (_) {}
    appShell?.classList.toggle("sidebar-collapsed", sidebarCollapsed);
    if (sidebarToggle) {
      sidebarToggle.setAttribute("aria-expanded", String(!sidebarCollapsed));
      sidebarToggle.setAttribute("aria-label", sidebarCollapsed ? "ขยายแถบเมนู" : "ย่อแถบเมนู");
      sidebarToggle.title = sidebarCollapsed ? "ขยายแถบเมนู" : "ย่อแถบเมนู";
      sidebarToggle.textContent = sidebarCollapsed ? "›" : "‹";
      sidebarToggle.addEventListener("click", () => {
        const collapsed = appShell?.classList.toggle("sidebar-collapsed") ?? false;
        sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
        sidebarToggle.setAttribute("aria-label", collapsed ? "ขยายแถบเมนู" : "ย่อแถบเมนู");
        sidebarToggle.title = collapsed ? "ขยายแถบเมนู" : "ย่อแถบเมนู";
        sidebarToggle.textContent = collapsed ? "›" : "‹";
        try { localStorage.setItem("kla-sidebar-collapsed", String(collapsed)); } catch (_) {}
      });
    }
    $("#allowance-form")?.addEventListener("submit", async event => {
      event.preventDefault();
      await runSave(async () => {
        const allowance = parseExpression(event.currentTarget.elements.allowance.value);
        const accumulated = parseExpression(event.currentTarget.elements.accumulated.value);
        await batchWrite([{range:sheetRange(state.month,"F2"),values:[[allowance]]},{range:sheetRange(state.month,"B18"),values:[[accumulated]]}]);
        toast("บันทึกเงินสนับสนุนและเงินสะสมแล้ว", "success"); await loadMonth();
      });
    });
    $("#emergency-form")?.addEventListener("submit", async event => {
      event.preventDefault();
      await runSave(async () => {
        const total = parseExpression(event.currentTarget.elements.emergencyTotal.value);
        const monthly = parseExpression(event.currentTarget.elements.emergencyMonthly.value);
        const oldMonthly = cell(25,2);
        const updatedTotal = total + (monthly - oldMonthly);
        await batchWrite([{range:sheetRange(state.month,"B13"),values:[[updatedTotal]]},{range:sheetRange(state.month,"C26"),values:[[monthly]]}]);
        toast("บันทึกยอดเงินสำรองฉุกเฉินแล้ว", "success"); await loadMonth();
      });
    });
    $("#income-form")?.addEventListener("submit", async event => {
      event.preventDefault();
      await runSave(async () => {
        const income = parseExpression(event.currentTarget.elements.income.value);
        await batchWrite([{range:sheetRange(state.month,"F16"),values:[[income]]}]);
        toast("บันทึกรายได้ส่วนตัวแล้ว", "success"); await loadMonth();
      });
    });
    $("#balance-form")?.addEventListener("submit", async event => {
      event.preventDefault();
      await runSave(async () => {
        const cash = parseExpression(event.currentTarget.elements.cash.value);
        const bank = parseExpression(event.currentTarget.elements.bank.value);
        await batchWrite([{range:sheetRange(state.month,"F5"),values:[[bank]]},{range:sheetRange(state.month,"F6"),values:[[cash]]}]);
        toast("บันทึกยอดเงินสดและเงินโอนแล้ว", "success"); await loadMonth();
      });
    });
  }

  function bindExpenseEvents() {
    $$(".expense-category").forEach(select => select.addEventListener("change", event => {
      const row = event.currentTarget.closest("tr");
      const index = row.dataset.expenseIndex;
      const split = $('[data-split-for="' + index + '"]');
      split.classList.toggle("hidden", event.currentTarget.value !== "แยกบิล");
    }));
    $$(".split-kin,.split-suan,.split-other").forEach(input => input.addEventListener("input", () => {
      const panel = input.closest(".split-panel");
      const row = panel.closest("tr").previousElementSibling;
      const total = number($(".split-kin",panel).value) + number($(".split-suan",panel).value) + number($(".split-other",panel).value);
      const expected = number(row.dataset.amount);
      const status = $(".split-status",panel);
      const diff = total - expected;
      status.className = "split-status " + (Math.abs(diff) <= .01 ? "good" : "bad");
      status.textContent = Math.abs(diff) <= .01 ? "✓ ยอดแยกตรงกับยอดบิล" : diff > 0 ? "ยอดเกิน " + money(diff) + " บาท" : "ขาดอีก " + money(-diff) + " บาท";
    }));
    $("#save-expenses-button")?.addEventListener("click", saveExpenses);
    $("#save-pending-button")?.addEventListener("click", saveExpenses);
    const manualForm = $("#manual-expense-form");
    manualForm?.querySelectorAll("input[type=number]").forEach(input => input.addEventListener("input", () => {
      const total = ["food","personal","other"].reduce((sum,name) => sum + number(manualForm.elements[name].value), 0);
      const output = $("#entry-total");
      if (output) output.textContent = money(total) + " ฿";
    }));
  }

  async function saveExpenses() {
    const rows = $$("tr[data-expense-index]");
    const updates = [], insertActions = [], appendRows = [];
    const splitErrors = [];
    for (const row of rows) {
      const category = $(".expense-category",row).value;
      if (category === "แยกบิล") {
        const splitRow = $('[data-split-for="' + row.dataset.expenseIndex + '"]');
        const values = [number($(".split-kin",splitRow).value),number($(".split-suan",splitRow).value),number($(".split-other",splitRow).value)];
        const total = values.reduce((a,b)=>a+b,0);
        if (Math.abs(total-number(row.dataset.amount)) > .01) splitErrors.push("แถว " + row.dataset.sheetRow + " ยอดแยกไม่เท่ากับยอดบิล");
      }
    }
    if (splitErrors.length) { toast(splitErrors.join(" · "), "error", 6500); return; }
    const pending = rows.map(row => ({
      row:number(row.dataset.sheetRow), date:row.dataset.date, amount:number(row.dataset.amount),
      category:$(".expense-category",row).value, note:$(".expense-note",row).value.trim() || "-",
      split:row.dataset.expenseIndex
    })).sort((a,b)=>b.row-a.row);
    for (const item of pending) {
      if (item.category === "แยกบิล") {
        const splitRow = $('[data-split-for="' + item.split + '"]');
        const parts = [
          [number($(".split-kin",splitRow).value),"ค่ากิน"],
          [number($(".split-suan",splitRow).value),"ค่าใช้จ่ายส่วนตัว"],
          [number($(".split-other",splitRow).value),"ค่าอื่นๆ"]
        ].filter(part=>part[0]>0);
        if (parts.length) {
          const note = item.note === "-" ? "(แยกบิล)" : item.note + " (แยกบิล)";
          updates.push({range:sheetRange(state.month,"B"+item.row+":D"+item.row),values:[[parts[0][0],parts[0][1],note]]});
          if (parts.length > 1) insertActions.push({at:item.row+1,values:parts.slice(1).map(part=>[item.date,part[0],part[1],note])});
        }
      } else if (item.category !== "รอดำเนินการ") {
        updates.push({range:sheetRange(state.month,"B"+item.row+":D"+item.row),values:[[item.amount,item.category,item.note]]});
      }
    }
    const manual = $("#manual-expense-form");
    const food = number(manual.elements.food.value), personal = number(manual.elements.personal.value), other = number(manual.elements.other.value);
    const note = manual.elements.note.value.trim() || "-";
    const timestamp = new Intl.DateTimeFormat("en-GB",{timeZone:"Asia/Bangkok",day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23"}).format(new Date()).replace(",",",");
    if (food>0) appendRows.push([timestamp,food,"ค่ากิน",note]);
    if (personal>0) appendRows.push([timestamp,personal,"ค่าใช้จ่ายส่วนตัว",note]);
    if (other>0) appendRows.push([timestamp,other,"ค่าอื่นๆ",note]);
    if (!updates.length && !insertActions.length && !appendRows.length) { toast("ไม่มีข้อมูลที่เปลี่ยนแปลงหรือรายจ่ายใหม่", "info"); return; }
    await runSave(async () => {
      // Preserve original row references: update existing cells first, then insert from bottom to top.
      if (updates.length) await batchWrite(updates);
      for (const action of insertActions) {
        await spreadsheetBatchUpdate([{insertDimension:{range:{sheetId:sheetId(state.month),dimension:"ROWS",startIndex:action.at-1,endIndex:action.at-1+action.values.length},inheritFromBefore:true}}]);
        const end = action.at + action.values.length - 1;
        await batchWrite([{range:sheetRange(state.month,"A"+action.at+":D"+end),values:action.values}]);
      }
      if (appendRows.length) {
        const colA = await getValues(sheetRange(state.month,"A1:A1000"));
        let last = colA.length;
        while (last>0 && !String(colA[last-1]?.[0] || "").trim()) last--;
        const start = Math.max(30,last+1);
        await batchWrite([{range:sheetRange(state.month,"A"+start+":D"+(start+appendRows.length-1)),values:appendRows}]);
      }
      toast("บันทึกรายจ่ายทั้งหมดเรียบร้อยแล้ว", "success");
      await loadMonth();
    });
  }

  function sheetId(title) {
    const item = state.worksheets.find(sheet => sheet.title === title) ||
      (state.spreadsheet.sheets || []).map(sheet=>sheet.properties).find(sheet=>sheet.title===title);
    if (!item) throw new Error("ไม่พบ Worksheet: " + title);
    return item.sheetId;
  }

  async function runSave(task) {
    if (state.busy) { toast("กำลังดำเนินการอยู่ กรุณารอสักครู่", "info"); return; }
    setBusy(true);
    try {
      await task();
    } catch (error) {
      toast("บันทึกไม่สำเร็จ: " + error.message, "error", 6500);
    } finally {
      setBusy(false);
      const closeButton = $("#close-month-button");
      if (closeButton && state.month) closeButton.disabled = state.worksheets.some(item => item.title === nextMonthName(state.month));
    }
  }

  async function closeMonth() {
    if (state.busy) return;
    const nextName = nextMonthName(state.month);
    if (state.worksheets.some(item=>item.title===nextName)) { toast("มี Worksheet " + nextName + " อยู่แล้ว ระบบจะไม่สร้างซ้ำ", "error"); return; }
    await runSave(async () => {
      const data = state.data;
      const getAt = (r,c) => number(data[r]?.[c] ?? 0);
      const accumulated = getAt(17,1), emergency = getAt(12,1);
      const used = getAt(2,1)+getAt(3,1)+getAt(4,1);
      const carry = getAt(4,5)+getAt(5,5);
      const personalIncome = getAt(15,5);
      let summaryProps = (state.spreadsheet.sheets || []).map(item=>item.properties).find(item=>item.title==="Summary_Data");
      if (!summaryProps) {
        const created = await spreadsheetBatchUpdate([{addSheet:{properties:{title:"Summary_Data",gridProperties:{rowCount:100,columnCount:10}}}}]);
        summaryProps = created.replies?.[0]?.addSheet?.properties;
        if (!summaryProps) throw new Error("สร้าง Summary_Data ไม่สำเร็จ");
        await batchWrite([{range:sheetRange("Summary_Data","A1:F1"),values:[["Month","Accumulated","Emergency","Used","Carry_Cash","Personal_Income"]]}]);
        state.spreadsheet.sheets.push({properties:summaryProps});
      }
      const existingSummary = await getValues(sheetRange("Summary_Data","A1:F1000"));
      const existingIndex = existingSummary.findIndex((row,index)=>index>0 && row[0]===state.month);
      const summaryValues = [[state.month,accumulated,emergency,used,carry,personalIncome]];
      if (existingIndex >= 1) {
        await batchWrite([{range:sheetRange("Summary_Data","A"+(existingIndex+1)+":F"+(existingIndex+1)),values:summaryValues}]);
      } else {
        const start = Math.max(2,existingSummary.length+1);
        await batchWrite([{range:sheetRange("Summary_Data","A"+start+":F"+start),values:summaryValues}]);
      }
      await spreadsheetBatchUpdate([{duplicateSheet:{sourceSheetId:sheetId(state.month),newSheetName:nextName}}]);
      const newProps = (await getMetadata()).sheets.map(item=>item.properties).find(item=>item.title===nextName);
      if (!newProps) throw new Error("สร้าง Worksheet เดือนใหม่แล้ว แต่ไม่สามารถตรวจสอบข้อมูลได้");
      const resets = [
        {range:sheetRange(nextName,"F2"),values:[[0]]},
        {range:sheetRange(nextName,"B11"),values:[[0]]},
        {range:sheetRange(nextName,"B12"),values:[[0]]},
        {range:sheetRange(nextName,"F4"),values:[[carry]]},
        {range:sheetRange(nextName,"F16"),values:[[0]]},
        {range:sheetRange(nextName,"C26"),values:[[""]]}
      ];
      await batchWrite(resets);
      // F5 and F6 are deliberately preserved in the duplicated sheet.
      const sourceRows = state.data.length;
      if (sourceRows >= 30) await clearRanges([sheetRange(nextName,"A30:D"+sourceRows)]);
      if ((newProps.gridProperties?.rowCount || 0) < 100) {
        await spreadsheetBatchUpdate([{updateSheetProperties:{properties:{sheetId:newProps.sheetId,gridProperties:{rowCount:100}},fields:"gridProperties.rowCount"}}]);
      }
      toast("ปิดยอดสำเร็จและสร้าง " + nextName + " แล้ว", "success", 6000);
      state.spreadsheet = await getMetadata();
      state.worksheets = state.spreadsheet.sheets.map(item=>item.properties).filter(item=>item.title!=="Summary_Data").sort((a,b)=>a.index-b.index);
      state.summary = await getValues(sheetRange("Summary_Data", "A1:F1000"));
      state.month = nextName;
      renderMonthOptions();
      await loadMonth();
    });
  }

  function bindGlobalEvents() {
    $("#app-panel").addEventListener("click", event => {
      const link = event.target.closest(".sidebar-link[data-app-view]");
      if (!link) return;
      event.preventDefault();
      state.activeView = link.dataset.appView;
      if (state.activeView === "history") renderHistoryWorkspace();
      else renderDashboard();
    });
    let sidebarResizeFrame = 0;
    window.addEventListener("resize", () => {
      if (state.sidebarSettingsTouched) return;
      cancelAnimationFrame(sidebarResizeFrame);
      sidebarResizeFrame = requestAnimationFrame(() => {
        const settings = $("#finance-sidebar-slot .sidebar-settings");
        if (settings) settings.open = !window.matchMedia("(max-width: 900px)").matches;
      });
    }, { passive: true });
    $("#auth-button").addEventListener("click", login);
    $("#welcome-login")?.addEventListener("click", login);
    $("#refresh-button").addEventListener("click",()=>runSave(async()=>{await bootstrap();toast("โหลดข้อมูลล่าสุดแล้ว","success");}));
    $("#month-select").addEventListener("change",async event=>{
      state.month=event.target.value;
      await loadMonth().catch(error=>toast("โหลดข้อมูลไม่สำเร็จ: "+error.message,"error"));
    });
    $("#close-month-button").addEventListener("click",()=>{
      const next=nextMonthName(state.month);
      $("#confirm-message").textContent="ระบบจะบันทึกสถิติของ "+state.month+" ลง Summary_Data และสร้าง Worksheet "+next+" โดยยกยอดเงินสดและเงินโอนเดิมไปต่อ ข้อมูล F5/F6 จะไม่ถูกล้าง";
      $("#confirm-dialog").showModal();
    });
    $("#confirm-close-month").addEventListener("click",event=>{
      event.preventDefault();
      $("#confirm-dialog").close();
      closeMonth();
    });
  }

  function start() {
    bindGlobalEvents();
    setConnection(false);
    initAuth();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded",start);
  else start();
})();