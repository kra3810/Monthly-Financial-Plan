/* Public browser configuration. These values are identifiers, not secrets. */
window.FINANCE_CONFIG = Object.freeze({
  GOOGLE_CLIENT_ID: "832916905011-acqsujd78fk8jr7snng60rvf8pr4a7u2.apps.googleusercontent.com",
  SPREADSHEET_ID: "17h3a_6-ENOf87k7RbHIHiUGW8sF6v5Kizi91PqaQoZc",
  // Keep the scope narrow: this app only needs to read and write the selected spreadsheet.
  SCOPES: "https://www.googleapis.com/auth/spreadsheets",
  APP_NAME: "Kla Finance",
  DEFAULT_MONTHLY_ALLOWANCE: 8000,
  FIXED_RENT: 4500
});
