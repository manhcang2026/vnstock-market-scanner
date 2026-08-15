function doPost(e) {
  try {
    const body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    validateSecret_(body.secret);
    switch (body.action) {
      case 'replace_daily_baseline':
        replaceRows_(CONFIG.SHEETS.DAILY, body.rows || []);
        appendRunLog_(body.run_log || {});
        cleanupSnapshots_();
        return json_({ok: true, rows: (body.rows || []).length});
      case 'get_daily_baseline':
        return json_({ok: true, rows: readRows_(CONFIG.SHEETS.DAILY)});
      case 'get_rvol_reference':
        return json_({ok: true, rows: getRvolReference_(body)});
      case 'update_intraday_scan':
        const snapshotResult = upsertSnapshotRows_(body.snapshots || []);
        replaceRows_(CONFIG.SHEETS.DASHBOARD, body.dashboard || []);
        appendRunLog_(body.run_log || {});
        updateMeta_(body.dashboard || [], body.run_log || {});
        clearDashboardCache_();
        return json_({
          ok: true,
          snapshots: snapshotResult.total,
          snapshots_inserted: snapshotResult.inserted,
          snapshots_updated: snapshotResult.updated,
          snapshots_duplicates_removed: snapshotResult.duplicatesRemoved,
          dashboard: (body.dashboard || []).length,
        });
      default:
        throw new Error(`Action khong hop le: ${body.action}`);
    }
  } catch (error) {
    return json_({ok: false, error: String(error && error.stack || error)});
  }
}

function doGet(e) {
  try {
    const params = (e && e.parameter) || {};
    if (params.action === 'meta') return json_({ok: true, meta: getMeta_()});
    return dashboardJson_();
  } catch (error) {
    return json_({ok: false, error: String(error && error.stack || error)});
  }
}

// Cache chung cho moi nguoi xem. CacheService gioi han 100 KB/key, vi vay
// payload Dashboard duoc chia thanh cac manh nho va manifest duoc ghi sau cung.
const DASHBOARD_CACHE_PREFIX_ = 'dashboard_json_v1_';
const DASHBOARD_CACHE_MANIFEST_ = DASHBOARD_CACHE_PREFIX_ + 'manifest';
const DASHBOARD_CACHE_CHUNK_CHARS_ = 30000;
const DASHBOARD_CACHE_SECONDS_ = 540;
const DASHBOARD_CACHE_MAX_CHUNKS_ = 30;

function dashboardJson_() {
  const cached = readDashboardCache_();
  if (cached) return jsonText_(cached);

  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    // Nguoi dung dau tien da co the vua tao cache trong luc request nay doi lock.
    const cachedAfterLock = readDashboardCache_();
    if (cachedAfterLock) return jsonText_(cachedAfterLock);

    const payload = JSON.stringify({
      ok: true,
      meta: getMeta_(),
      rows: readRows_(CONFIG.SHEETS.DASHBOARD),
    });
    writeDashboardCache_(payload);
    return jsonText_(payload);
  } finally {
    lock.releaseLock();
  }
}

function readDashboardCache_() {
  const cache = CacheService.getScriptCache();
  const manifestRaw = cache.get(DASHBOARD_CACHE_MANIFEST_);
  if (!manifestRaw) return '';

  try {
    const manifest = JSON.parse(manifestRaw);
    const count = Number(manifest && manifest.count);
    if (!Number.isInteger(count) || count < 1 || count > DASHBOARD_CACHE_MAX_CHUNKS_) return '';

    const keys = Array.from({length: count}, (_, index) => DASHBOARD_CACHE_PREFIX_ + 'part_' + index);
    const parts = cache.getAll(keys);
    if (keys.some(key => typeof parts[key] !== 'string')) return '';
    return keys.map(key => parts[key]).join('');
  } catch (error) {
    return '';
  }
}

function writeDashboardCache_(payload) {
  const cache = CacheService.getScriptCache();
  const chunks = [];
  for (let offset = 0; offset < payload.length; offset += DASHBOARD_CACHE_CHUNK_CHARS_) {
    chunks.push(payload.slice(offset, offset + DASHBOARD_CACHE_CHUNK_CHARS_));
  }
  if (!chunks.length || chunks.length > DASHBOARD_CACHE_MAX_CHUNKS_) return;

  const entries = {};
  chunks.forEach((chunk, index) => {
    entries[DASHBOARD_CACHE_PREFIX_ + 'part_' + index] = chunk;
  });
  cache.putAll(entries, DASHBOARD_CACHE_SECONDS_);
  cache.put(
    DASHBOARD_CACHE_MANIFEST_,
    JSON.stringify({count: chunks.length}),
    DASHBOARD_CACHE_SECONDS_,
  );
}

function clearDashboardCache_() {
  const cache = CacheService.getScriptCache();
  const keys = [DASHBOARD_CACHE_MANIFEST_];
  for (let index = 0; index < DASHBOARD_CACHE_MAX_CHUNKS_; index += 1) {
    keys.push(DASHBOARD_CACHE_PREFIX_ + 'part_' + index);
  }
  cache.removeAll(keys);
}

function jsonText_(text) {
  return ContentService.createTextOutput(text).setMimeType(ContentService.MimeType.JSON);
}

function validateSecret_(secret) {
  const expected = PropertiesService.getScriptProperties().getProperty('GAS_API_SECRET');
  if (!expected) throw new Error('Chua cau hinh GAS_API_SECRET');
  if (!secret || secret !== expected) throw new Error('Unauthorized');
}

function getRvolReference_(body) {
  const currentSlot = normalizeTimeSlot_(body.current_slot);
  const startSlot = normalizeTimeSlot_(body.start_slot);
  const tradingDate = normalizeTradingDate_(body.trading_date);
  if (!currentSlot || !startSlot || !tradingDate) return [];

  const rows = readRows_(CONFIG.SHEETS.SNAPSHOTS);
  const historicalDates = [...new Set(
    rows
      .map(row => normalizeTradingDate_(row.trading_date))
      .filter(date => date && date < tradingDate),
  )].sort().slice(-10);

  const allowedDates = new Set([tradingDate, ...historicalDates]);
  return rows.filter(row => {
    const rowDate = normalizeTradingDate_(row.trading_date);
    const rowSlot = normalizeTimeSlot_(row.time_slot);
    return allowedDates.has(rowDate)
      && (rowSlot === currentSlot || rowSlot === startSlot);
  });
}
