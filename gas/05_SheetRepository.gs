function getSheet_(name) {
  const sheet = SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID).getSheetByName(name);
  if (!sheet) throw new Error(`Khong tim thay sheet ${name}. Hay chay setupNewBackend().`);
  ensureHeaders_(sheet, name);
  return sheet;
}

function ensureHeaders_(sheet, name) {
  const headers = HEADERS[name];
  if (!headers || !headers.length) return;
  const current = sheet.getRange(1, 1, 1, headers.length).getDisplayValues()[0];
  const needsUpdate = headers.some((header, index) => current[index] !== header);
  if (!needsUpdate) return;
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length)
    .setFontWeight('bold')
    .setBackground('#17365D')
    .setFontColor('#FFFFFF');
  sheet.setFrozenRows(1);
}

function readRows_(name) {
  const sheet = getSheet_(name);
  const lastRow = sheet.getLastRow();
  const headers = HEADERS[name];
  if (lastRow < 2) return [];
  const values = sheet.getRange(2, 1, lastRow - 1, headers.length).getValues();
  return values.map(row => Object.fromEntries(headers.map((header, i) => [header, serializeCell_(row[i])])));
}

function replaceRows_(name, rows) {
  const sheet = getSheet_(name);
  const headers = HEADERS[name];
  if (sheet.getLastRow() > 1) sheet.getRange(2, 1, sheet.getLastRow() - 1, headers.length).clearContent();
  if (!rows.length) return;
  const values = rows.map(row => headers.map(header => normalizeCell_(row[header])));
  sheet.getRange(2, 1, values.length, headers.length).setValues(values);
}

function appendRows_(name, rows) {
  if (!rows.length) return;
  const sheet = getSheet_(name);
  const headers = HEADERS[name];
  const values = rows.map(row => headers.map(header => normalizeCell_(row[header])));
  sheet.getRange(sheet.getLastRow() + 1, 1, values.length, headers.length).setValues(values);
}

function appendRunLog_(row) {
  appendRows_(CONFIG.SHEETS.LOG, [row]);
}

function cleanupSnapshots_() {
  const name = CONFIG.SHEETS.SNAPSHOTS;
  const rows = readRows_(name);
  if (!rows.length) return;
  const dates = [...new Set(rows.map(r => String(r.trading_date || '')).filter(Boolean))].sort();
  const keep = new Set(dates.slice(-CONFIG.SNAPSHOT_DAYS_TO_KEEP));
  replaceRows_(name, rows.filter(r => keep.has(String(r.trading_date))));
}

function updateMeta_(dashboardRows, runLog) {
  const latest = dashboardRows.length ? dashboardRows[0].updated_at : '';
  PropertiesService.getScriptProperties().setProperties({
    LAST_DASHBOARD_UPDATED_AT: String(latest || ''),
    LAST_RUN_ID: String(runLog.run_id || ''),
    LAST_RUN_STATUS: String(runLog.status || ''),
  }, false);
}

function getMeta_() {
  const props = PropertiesService.getScriptProperties();
  return {
    updated_at: props.getProperty('LAST_DASHBOARD_UPDATED_AT') || '',
    run_id: props.getProperty('LAST_RUN_ID') || '',
    status: props.getProperty('LAST_RUN_STATUS') || '',
    scan_interval_minutes: 10,
  };
}

function normalizeCell_(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return value;
}

function serializeCell_(value) {
  if (value instanceof Date) return value.toISOString();
  return value;
}

function json_(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON);
}
