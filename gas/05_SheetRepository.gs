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
  const range = sheet.getRange(2, 1, lastRow - 1, headers.length);
  const values = range.getValues();
  const displayValues = range.getDisplayValues();
  return values.map((row, rowIndex) => Object.fromEntries(
    headers.map((header, i) => [
      header,
      serializeCell_(row[i], header, displayValues[rowIndex][i]),
    ]),
  ));
}

function replaceRows_(name, rows) {
  const sheet = getSheet_(name);
  const headers = HEADERS[name];
  if (sheet.getLastRow() > 1) sheet.getRange(2, 1, sheet.getLastRow() - 1, headers.length).clearContent();
  if (!rows.length) return;
  const values = rows.map(row => headers.map(header => normalizeCell_(row[header], header)));
  prepareTextColumns_(sheet, headers, 2, values.length);
  sheet.getRange(2, 1, values.length, headers.length).setValues(values);
}

function appendRows_(name, rows) {
  if (!rows.length) return;
  const sheet = getSheet_(name);
  const headers = HEADERS[name];
  const values = rows.map(row => headers.map(header => normalizeCell_(row[header], header)));
  const startRow = sheet.getLastRow() + 1;
  prepareTextColumns_(sheet, headers, startRow, values.length);
  sheet.getRange(startRow, 1, values.length, headers.length).setValues(values);
}

// Ghi snapshot theo khoa trading_date + time_slot + symbol.
// Neu job tu dong va job thu cong cung chay mot khung gio, dong cu se duoc
// cap nhat thay vi noi them. Lock ngan hai request GAS ghi chen vao nhau.
function upsertSnapshotRows_(rows) {
  if (!rows.length) {
    return {total: 0, inserted: 0, updated: 0, duplicatesRemoved: 0};
  }

  const name = CONFIG.SHEETS.SNAPSHOTS;
  const headers = HEADERS[name];
  const keyHeaders = ['trading_date', 'time_slot', 'symbol'];
  const keyIndexes = keyHeaders.map(header => headers.indexOf(header));
  if (keyIndexes.some(index => index < 0)) {
    throw new Error('Intraday_Snapshots thieu cot khoa: ' + keyHeaders.join(', '));
  }

  // Neu payload tu Python tu lap khoa, chi giu ban ghi cuoi cung.
  const incomingByKey = new Map();
  rows.forEach(row => {
    const key = snapshotKeyFromObject_(row);
    if (!key) throw new Error('Snapshot thieu trading_date, time_slot hoac symbol');
    incomingByKey.set(key, row);
  });

  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const sheet = getSheet_(name);
    const lastRow = sheet.getLastRow();
    const existingByKey = new Map();
    const duplicateRows = [];

    if (lastRow >= 2) {
      const keyValues = sheet.getRange(2, 1, lastRow - 1, 3).getDisplayValues();
      keyValues.forEach((values, index) => {
        const key = snapshotKeyFromValues_(values);
        if (!key || !incomingByKey.has(key)) return;
        const rowNumber = index + 2;
        if (existingByKey.has(key)) duplicateRows.push(rowNumber);
        else existingByKey.set(key, rowNumber);
      });
    }

    const updates = [];
    const inserts = [];
    incomingByKey.forEach((row, key) => {
      const values = headers.map(header => normalizeCell_(row[header], header));
      if (existingByKey.has(key)) {
        updates.push({rowNumber: existingByKey.get(key), values});
      } else {
        inserts.push(values);
      }
    });

    // Cac dong cua mot lan scan thuong lien tiep; gom thanh tung khoi de giam
    // so lan goi Spreadsheet service.
    prepareTextColumns_(sheet, headers, 2, Math.max(lastRow - 1, 0));
    writeRowBlocks_(sheet, updates, headers.length);

    // Xoa cac ban sao cu (neu da tung bi ghi trung) tu duoi len de khong lech dong.
    deleteRowBlocks_(sheet, duplicateRows);

    if (inserts.length) {
      const insertRow = sheet.getLastRow() + 1;
      prepareTextColumns_(sheet, headers, insertRow, inserts.length);
      sheet.getRange(insertRow, 1, inserts.length, headers.length).setValues(inserts);
    }

    return {
      total: incomingByKey.size,
      inserted: inserts.length,
      updated: updates.length,
      duplicatesRemoved: duplicateRows.length,
    };
  } finally {
    lock.releaseLock();
  }
}

function snapshotKeyFromObject_(row) {
  return snapshotKeyFromValues_([
    row.trading_date,
    row.time_slot,
    row.symbol,
  ]);
}

function snapshotKeyFromValues_(values) {
  const parts = [
    normalizeTradingDate_(values[0]),
    normalizeTimeSlot_(values[1]),
    String(values[2] || '').trim().toUpperCase(),
  ];
  return parts.every(Boolean) ? parts.join('|') : '';
}

function writeRowBlocks_(sheet, updates, width) {
  if (!updates.length) return;
  updates.sort((a, b) => a.rowNumber - b.rowNumber);

  let blockStart = updates[0].rowNumber;
  let blockValues = [updates[0].values];
  for (let index = 1; index < updates.length; index += 1) {
    const previous = updates[index - 1].rowNumber;
    const current = updates[index];
    if (current.rowNumber === previous + 1) {
      blockValues.push(current.values);
      continue;
    }
    sheet.getRange(blockStart, 1, blockValues.length, width).setValues(blockValues);
    blockStart = current.rowNumber;
    blockValues = [current.values];
  }
  sheet.getRange(blockStart, 1, blockValues.length, width).setValues(blockValues);
}

function deleteRowBlocks_(sheet, rowNumbers) {
  if (!rowNumbers.length) return;
  const sorted = [...new Set(rowNumbers)].sort((a, b) => b - a);
  let highest = sorted[0];
  let lowest = sorted[0];

  for (let index = 1; index < sorted.length; index += 1) {
    const row = sorted[index];
    if (row === lowest - 1) {
      lowest = row;
      continue;
    }
    sheet.deleteRows(lowest, highest - lowest + 1);
    highest = row;
    lowest = row;
  }
  sheet.deleteRows(lowest, highest - lowest + 1);
}

function appendRunLog_(row) {
  appendRows_(CONFIG.SHEETS.LOG, [row]);
}

function cleanupSnapshots_() {
  const name = CONFIG.SHEETS.SNAPSHOTS;
  const rows = readRows_(name);
  if (!rows.length) return;
  const dates = [...new Set(
    rows.map(row => normalizeTradingDate_(row.trading_date)).filter(Boolean),
  )].sort();
  const keep = new Set(dates.slice(-CONFIG.SNAPSHOT_DAYS_TO_KEEP));

  // Chuan hoa va giu ban ghi cuoi cung neu du lieu cu tung bi trung khoa.
  const uniqueByKey = new Map();
  rows.forEach(row => {
    row.trading_date = normalizeTradingDate_(row.trading_date);
    // Cac snapshot cu tung bi Sheets doi gio nen co gia tri nhu 08:53, 09:03.
    // updated_at van dung (09:09, 09:19...), vi vay dung timestamp nay de khoi
    // phuc time_slot va lam tron xuong dung khung quet 10 phut.
    row.time_slot = snapshotTimeSlotFromUpdatedAt_(row.updated_at, row.time_slot);
    const key = snapshotKeyFromObject_(row);
    if (key && keep.has(row.trading_date)) uniqueByKey.set(key, row);
  });
  replaceRows_(name, [...uniqueByKey.values()]);
}

// Chay thu cong mot lan sau khi ghi de file nay de sua lich su cu ngay lap tuc,
// khong can doi hoac chay lai workflow Daily Baseline dai hon.
function repairIntradaySnapshotTimes() {
  const sheet = getSheet_(CONFIG.SHEETS.SNAPSHOTS);
  const rowsBefore = Math.max(sheet.getLastRow() - 1, 0);
  cleanupSnapshots_();
  SpreadsheetApp.flush();
  const rowsAfter = Math.max(sheet.getLastRow() - 1, 0);
  const result = {
    ok: true,
    rows_before: rowsBefore,
    rows_after: rowsAfter,
    message: 'Da khoi phuc time_slot tu updated_at va don trung snapshot.',
  };
  Logger.log(JSON.stringify(result));
  return result;
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

const DATA_TIMEZONE_ = 'Asia/Ho_Chi_Minh';
const TEXT_HEADERS_ = new Set([
  'trading_date',
  'time_slot',
  'updated_at',
  'started_at',
  'finished_at',
]);

function normalizeCell_(value, header) {
  if (value === null || value === undefined) return '';
  if (header === 'trading_date') return normalizeTradingDate_(value);
  if (header === 'time_slot') return normalizeTimeSlot_(value);
  if (header === 'updated_at' || header === 'started_at' || header === 'finished_at') {
    return normalizeTimestamp_(value);
  }
  if (typeof value === 'object') return JSON.stringify(value);
  return value;
}

function serializeCell_(value, header, displayValue) {
  if (header === 'trading_date') {
    return normalizeTradingDate_(value instanceof Date ? value : (displayValue || value));
  }
  if (header === 'time_slot') return normalizeTimeSlot_(displayValue || value);
  if (header === 'updated_at' || header === 'started_at' || header === 'finished_at') {
    return normalizeTimestamp_(value);
  }
  if (value instanceof Date) return normalizeTimestamp_(value);
  return value;
}

function normalizeTradingDate_(value) {
  if (value === null || value === undefined || value === '') return '';
  if (value instanceof Date) return Utilities.formatDate(value, DATA_TIMEZONE_, 'yyyy-MM-dd');

  const text = String(value).trim();
  const canonical = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (canonical) return text;

  const vietnamese = text.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})$/);
  if (vietnamese) {
    return vietnamese[3]
      + '-' + vietnamese[2].padStart(2, '0')
      + '-' + vietnamese[1].padStart(2, '0');
  }

  const parsed = new Date(text);
  if (!Number.isNaN(parsed.getTime())) {
    return Utilities.formatDate(parsed, DATA_TIMEZONE_, 'yyyy-MM-dd');
  }
  throw new Error('trading_date khong hop le: ' + text);
}

function normalizeTimeSlot_(value) {
  if (value === null || value === undefined || value === '') return '';
  if (value instanceof Date) {
    // Cac o chi chua gio cua Sheets dung ngay nen nam 1899. Dung mui gio lich
    // su co the tao sai lech vai phut, nen quy doi co dinh UTC+7 cho truong hop nay.
    if (value.getUTCFullYear() < 1970) {
      const totalMinutes = (
        value.getUTCHours() * 60 + value.getUTCMinutes() + 7 * 60
      ) % (24 * 60);
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;
      return String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0');
    }
    return Utilities.formatDate(value, DATA_TIMEZONE_, 'HH:mm');
  }

  if (typeof value === 'number' && Number.isFinite(value)) {
    const totalMinutes = Math.round((value % 1) * 24 * 60);
    const hours = Math.floor(totalMinutes / 60) % 24;
    const minutes = totalMinutes % 60;
    return String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0');
  }

  const text = String(value).trim();
  const clock = text.match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
  if (clock) {
    const hours = Number(clock[1]);
    const minutes = Number(clock[2]);
    if (hours < 24 && minutes < 60) {
      return String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0');
    }
  }

  const parsed = new Date(text);
  if (!Number.isNaN(parsed.getTime())) {
    return normalizeTimeSlot_(parsed);
  }
  throw new Error('time_slot khong hop le: ' + text);
}

function snapshotTimeSlotFromUpdatedAt_(updatedAt, fallbackSlot) {
  const parsed = updatedAt instanceof Date
    ? updatedAt
    : new Date(String(updatedAt || '').trim());
  if (Number.isNaN(parsed.getTime())) return normalizeTimeSlot_(fallbackSlot);

  const hours = Number(Utilities.formatDate(parsed, DATA_TIMEZONE_, 'HH'));
  const minutes = Number(Utilities.formatDate(parsed, DATA_TIMEZONE_, 'mm'));
  const flooredMinutes = Math.floor(minutes / 10) * 10;
  return String(hours).padStart(2, '0')
    + ':' + String(flooredMinutes).padStart(2, '0');
}

function normalizeTimestamp_(value) {
  if (value === null || value === undefined || value === '') return '';
  const parsed = value instanceof Date ? value : new Date(String(value).trim());
  if (Number.isNaN(parsed.getTime())) return String(value).trim();
  return Utilities.formatDate(parsed, DATA_TIMEZONE_, "yyyy-MM-dd'T'HH:mm:ss") + '+07:00';
}

function prepareTextColumns_(sheet, headers, startRow, rowCount) {
  if (rowCount < 1) return;
  headers.forEach((header, index) => {
    if (TEXT_HEADERS_.has(header)) {
      sheet.getRange(startRow, index + 1, rowCount, 1).setNumberFormat('@');
    }
  });
}

function json_(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON);
}
