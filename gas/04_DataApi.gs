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
        appendRows_(CONFIG.SHEETS.SNAPSHOTS, body.snapshots || []);
        replaceRows_(CONFIG.SHEETS.DASHBOARD, body.dashboard || []);
        appendRunLog_(body.run_log || {});
        updateMeta_(body.dashboard || [], body.run_log || {});
        return json_({ok: true, snapshots: (body.snapshots || []).length, dashboard: (body.dashboard || []).length});
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
    const rows = readRows_(CONFIG.SHEETS.DASHBOARD);
    return json_({ok: true, meta: getMeta_(), rows});
  } catch (error) {
    return json_({ok: false, error: String(error && error.stack || error)});
  }
}

function validateSecret_(secret) {
  const expected = PropertiesService.getScriptProperties().getProperty('GAS_API_SECRET');
  if (!expected) throw new Error('Chua cau hinh GAS_API_SECRET');
  if (!secret || secret !== expected) throw new Error('Unauthorized');
}

function getRvolReference_(body) {
  const currentSlot = String(body.current_slot || '');
  const startSlot = String(body.start_slot || '');
  if (!currentSlot || !startSlot) return [];
  const rows = readRows_(CONFIG.SHEETS.SNAPSHOTS);
  const dates = [...new Set(rows.map(r => String(r.trading_date || '')).filter(Boolean))].sort().slice(-12);
  const allowedDates = new Set(dates);
  return rows.filter(r => allowedDates.has(String(r.trading_date)) && (r.time_slot === currentSlot || r.time_slot === startSlot));
}
