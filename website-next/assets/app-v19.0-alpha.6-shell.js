(function () {
  "use strict";

  var SUPABASE_URL = "https://wevtlkowpbmpdggcfbvn.supabase.co";
  var SUPABASE_KEY = "sb_publishable_qN__TQuoNBRUFhxuY5CtNw_88WZDdJw";
  var API_URL = SUPABASE_URL + "/rest/v1/stock_snapshot?select=*&order=symbol.asc";
  var FINANCIAL_API_URL = SUPABASE_URL + "/rest/v1/financial_latest?select=*&order=symbol.asc";
  var METADATA_API_URL = SUPABASE_URL + "/rest/v1/stock_metadata?select=*&order=symbol.asc";
  var CACHE_KEY = "vnstock_dashboard_raw_v19_0_alpha_4_staging_supabase_800";
  var LEGACY_CACHE_KEY = "vnstock_dashboard_cache_v1";
  var THEME_KEY = "vnstock_dashboard_theme_v17";
  var LATEST_API_URL = SUPABASE_URL + "/rest/v1/stock_snapshot?select=updated_at&order=updated_at.desc&limit=1";
  var EXPECTED_UNIVERSE_COUNT = 800;
  var AUTO_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
  var VERSION_POLL_INTERVAL_MS = 15 * 1000;
  var LOGO_BASE_URL = "/assets/logos/";
  var LOGO_ASSET_VERSION = "1741";
  // STAGING ONLY: UX preview. This is not authentication, billing or a security boundary.
  // Nothing in this mock state is persisted to Supabase.
  var MOCK_PLAN_CONFIG = {
    FREE: { label:"Free", viewLimit:10, watchlistLimit:10, changeLimit:10, email:false, telegram:false, fullMarket:false, price:"0đ" },
    BASIC: { label:"Basic", viewLimit:20, watchlistLimit:20, changeLimit:20, email:false, telegram:false, fullMarket:false, price:"100.000đ/tháng" },
    PLUS: { label:"Plus", viewLimit:50, watchlistLimit:50, changeLimit:50, email:true, telegram:true, fullMarket:false, price:"300.000đ/tháng", recommended:true },
    PRO: { label:"Pro", viewLimit:100, watchlistLimit:100, changeLimit:100, email:true, telegram:true, fullMarket:false, price:"500.000đ/tháng", inherits:"Toàn bộ tính năng Plus" },
    FULL: { label:"Full Market", viewLimit:null, watchlistLimit:null, changeLimit:null, email:true, telegram:true, fullMarket:true, price:"1.000.000đ/tháng", inherits:"Toàn bộ tính năng Pro" }
  };
  var app = document.getElementById("app");
  var savedTheme = null;
  try { savedTheme = localStorage.getItem(THEME_KEY); } catch (_) {}
  var initialTheme = savedTheme === "light" || savedTheme === "dark" ? savedTheme : "dark";
  document.documentElement.setAttribute("data-theme", initialTheme);
  var pageSize = window.matchMedia && window.matchMedia("(max-width: 767px)").matches ? 20 : 50;
  var initialSearchQuery = new URLSearchParams(location.search).get("q") || "";
  var state = {
    rows: [], meta: null, error: "", fetching: false,
    route: location.pathname === "/danh-sach" ? "list" : location.pathname === "/so-sanh-theo-nganh" ? "industry" : location.pathname === "/sang-loc-co-ban" ? "fundamental" : "overview",
    query: initialSearchQuery, globalQuery: initialSearchQuery, exchange: "all", signal: new URLSearchParams(location.search).get("signal") || "",
    sort: "signal", page: 1, selected: null, nextRefresh: null, theme: initialTheme,
    latestUpdateMs: null, waitingForNewData: false, lastVersionPollAt: 0, versionPolling: false,
    financialRows: [], financialBySymbol: {}, financialLoaded: false, financialError: "",
    metadataRows: [], metadataBySymbol: {}, metadataLoaded: false, metadataError: "",
    industryGroup: new URLSearchParams(location.search).get("group") || "",
    fundamentalMinScore: 0, fundamentalProfitGrowth: "all", fundamentalRoe: "all",
    quarterlyBySymbol: {}, quarterlyLoading: {}, quarterlyError: {},
    mockPlan: "FREE", mockChangeUsed: 3,
    scannerMode: "market", scannerFiltersOpen: false, scannerDialog: "", scannerDialogSymbol: "",
    detailTab: "overview", detailReturnScroll: 0, accountOpen: false, accountReturnScroll: 0
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function num(value) {
    if (value === null || value === undefined || value === "") return null;
    var n = typeof value === "number" ? value : Number(String(value).replace(/[,%\s]/g, ""));
    return Number.isFinite(n) ? n : null;
  }
  function bool(value) {
    if (typeof value === "boolean") return value;
    if (typeof value === "number") return value === 1;
    return ["TRUE", "1", "YES", "X", "ĐẠT"].indexOf(String(value || "").trim().toUpperCase()) >= 0;
  }
  function ratio(a, b) { return a !== null && b !== null && b !== 0 ? a / b * 100 : null; }
  function normalize(row) {
    var current = num(row.current_price != null ? row.current_price : row.currentPrice);
    var previous = num(row.previous_close != null ? row.previous_close : row.prevClose);
    var ma10 = num(row.ma10);
    var ma200 = num(row.ma200);
    var volume = num(row.volume_accumulated != null ? row.volume_accumulated : row.cumVolume);
    var avg10 = num(row.avg_volume_10 != null ? row.avg_volume_10 : row.avgVolume10);
    var sessions30 = num(row.rvol30_sessions != null ? row.rvol30_sessions : row.rvol30Sessions) || 0;
    var change = num(row.price_change_pct != null ? row.price_change_pct : row.changePct);
    var dayVolume = num(row.daily_volume_pct != null ? row.daily_volume_pct : row.dayVolumeRatioPct);
    var rvol = num(row.rvol30_pct != null ? row.rvol30_pct : row.rvol30Pct);
    var ma10Distance = num(row.ma10_distance_pct != null ? row.ma10_distance_pct : row.ma10DistancePct);
    var ma200Distance = num(row.ma200_distance_pct != null ? row.ma200_distance_pct : row.ma200DistancePct);
    if (change === null) change = ratio(current !== null && previous !== null ? current - previous : null, previous);
    if (dayVolume === null) dayVolume = ratio(volume, avg10);
    if (ma10Distance === null) ma10Distance = ratio(current !== null && ma10 !== null ? current - ma10 : null, ma10);
    if (ma200Distance === null) ma200Distance = ratio(current !== null && ma200 !== null ? current - ma200 : null, ma200);
    if (sessions30 <= 0) rvol = null;
    var sPrice = row.signal_price_3pct != null ? bool(row.signal_price_3pct) : !!row.signalPrice3pct;
    var sVolume = row.signal_daily_volume_200pct != null ? bool(row.signal_daily_volume_200pct) : !!row.signalVolume200pct;
    var sMa200 = row.signal_above_ma200 != null ? bool(row.signal_above_ma200) : !!row.signalAboveMa200;
    var sRvol = sessions30 > 0 && (row.signal_rvol30_200pct != null ? bool(row.signal_rvol30_200pct) : !!row.signalRvol30_200pct);
    var calculated = [sPrice, sVolume, sMa200, sRvol].filter(Boolean).length;
    var signalCount = num(row.signal_count != null ? row.signal_count : row.signalCount);
    if (signalCount === null) signalCount = calculated;
    signalCount = Math.max(0, Math.min(4, Math.round(signalCount)));
    var missing = current === null || previous === null || ma200 === null || volume === null || avg10 === null || ["MISSING_MARKET_DATA", "MISSING", "ERROR"].indexOf(row.data_status || row.dataStatus) >= 0;
    return {
      symbol: String(row.symbol || "—").toUpperCase(), exchange: String(row.exchange || "—").toUpperCase(),
      currentPrice: current, prevClose: previous, changePct: change, ma10: ma10, ma10DistancePct: ma10Distance,
      ma10Sessions: num(row.ma10_sessions != null ? row.ma10_sessions : row.ma10Sessions), ma200: ma200,
      ma200DistancePct: ma200Distance, ma200Sessions: num(row.ma200_sessions != null ? row.ma200_sessions : row.ma200Sessions),
      cumVolume: volume, avgVolume10: avg10, avgVolume10Sessions: num(row.avg_volume_sessions != null ? row.avg_volume_sessions : row.avgVolume10Sessions),
      dayVolumeRatioPct: dayVolume, volume30m: num(row.volume_30m != null ? row.volume_30m : row.volume30m),
      avgVolume30mSameSlot: num(row.avg_volume_30m_10 != null ? row.avg_volume_30m_10 : row.avgVolume30mSameSlot),
      rvol30Pct: rvol, rvol30Sessions: sessions30, signalPrice3pct: sPrice, signalVolume200pct: sVolume,
      signalAboveMa200: sMa200, signalRvol30_200pct: sRvol, signalCount: signalCount, hasMissingData: missing,
      tradingDate: row.trading_date || row.tradingDate || "—", timeSlot: row.time_slot || row.timeSlot || "—",
      updatedAt: row.updated_at || row.updatedAt || "—", dataStatus: row.data_status || row.dataStatus || "OK",
      dataSource: row.data_source || row.dataSource || "Supabase", note: row.note || ""
    };
  }
  function formatNumber(v, digits) {
    if (v === null || !Number.isFinite(v)) return "—";
    return v.toLocaleString("vi-VN", { minimumFractionDigits: digits || 0, maximumFractionDigits: digits || 0 });
  }
  function formatPrice(v) { return formatNumber(v, 0); }
  function logoHtml(symbol, extraClass) {
    var safe = String(symbol || "?").toUpperCase().replace(/[^A-Z0-9]/g, "");
    var label = safe.slice(0, 3) || "?";
    var cls = "company-logo" + (extraClass ? " " + extraClass : "");
    return '<span class="' + cls + '"><img class="company-logo-img" decoding="async" src="' + LOGO_BASE_URL + esc(safe) + '.jpg?v=' + LOGO_ASSET_VERSION + '" alt="Logo ' + esc(safe) + '"><span class="company-logo-fallback">' + esc(label) + '</span></span>';
  }
  function pct(v, digits) { return v === null || !Number.isFinite(v) ? "—" : (v > 0 ? "+" : "") + formatNumber(v, digits == null ? 2 : digits) + "%"; }
  function plainPct(v, digits) { return v === null || !Number.isFinite(v) ? "—" : formatNumber(v, digits == null ? 0 : digits) + "%"; }
  function shortVolume(v) {
    if (v === null || !Number.isFinite(v)) return "—";
    if (v >= 1000000) return formatNumber(v / 1000000, 2) + " triệu";
    if (v >= 1000) return formatNumber(v / 1000, 1) + " nghìn";
    return formatNumber(v, 0);
  }
  function metricClass(v) { return v > 0 ? "positive" : v < 0 ? "negative" : ""; }
  function signalClass(n) { return "sig" + n; }
  function signalTone(n) { return "tone" + n; }
  function signalItems(r) {
    return [
      ["Giá ≥ 3%", r.signalPrice3pct],
      ["KL ngày ≥ 200%", r.signalVolume200pct],
      ["Trên MA200", r.signalAboveMa200],
      ["RVOL30 ≥ 200%", r.signalRvol30_200pct]
    ];
  }
  function signalRailHtml(row) {
    var labels = ["Giá: tăng từ 3%", "Khối lượng: từ 200% KLTB10", "Xu hướng: trên MA200", "RVOL: từ 200%"];
    var values = [row.signalPrice3pct, row.signalVolume200pct, row.signalAboveMa200, row.signalRvol30_200pct];
    var tones = ["price", "volume", "trend", "rvol"];
    var segments = values.map(function (passed, index) {
      return '<span class="ccc-segment ccc-' + tones[index] + ' ' + (passed ? 'is-on' : 'is-off') + '" title="' + esc(labels[index] + ': ' + (passed ? 'đạt' : 'chưa đạt')) + '"><span class="sr-only">' + esc(labels[index] + ': ' + (passed ? 'đạt' : 'chưa đạt')) + '</span></span>';
    }).join('');
    var stateLabel = row.signalCount === 4 ? '<em>Hội tụ mạnh</em>' : row.signalCount === 3 ? '<em>Đang hội tụ</em>' : '';
    return '<span class="ccc-rail ' + (row.signalCount === 4 ? 'is-confluent' : row.signalCount === 3 ? 'is-converging' : '') + '" aria-label="' + row.signalCount + ' trên 4 tín hiệu CCC đang đạt"><span class="ccc-segments">' + segments + '</span><b>' + row.signalCount + '/4</b>' + stateLabel + '</span>';
  }
  function signalLockedHtml() {
    return '<span class="ccc-locked">' + iconSvg('lock') + '<span>Ngoài phạm vi</span></span>';
  }
  function companyDisplayName(symbol) {
    var metadata = state.metadataBySymbol[String(symbol || "").toUpperCase()] || {};
    return metadata.display_name || metadata.company_name || "";
  }
  function notableReasons(row) {
    var reasons = [];
    if (row.signalRvol30_200pct) reasons.push("RVOL30 " + plainPct(row.rvol30Pct));
    if (row.signalVolume200pct) reasons.push("KL ngày " + plainPct(row.dayVolumeRatioPct) + " KLTB10");
    if (row.signalPrice3pct) reasons.push("Giá tăng " + pct(row.changePct));
    if (row.signalAboveMa200) reasons.push("Trên MA200 " + pct(row.ma200DistancePct));
    if (!reasons.length && row.ma200DistancePct !== null) reasons.push("Cách MA200 " + pct(row.ma200DistancePct));
    if (reasons.length < 2 && row.ma10DistancePct !== null) reasons.push("MA10 tham khảo " + pct(row.ma10DistancePct));
    return reasons.slice(0, 2);
  }
  function overviewStockCard(row) {
    var company = companyDisplayName(row.symbol);
    var reasons = notableReasons(row);
    return '<article class="overview-stock-card" data-symbol="'+esc(row.symbol)+'">'+
      '<div class="overview-stock-head">'+logoHtml(row.symbol,'card-logo')+'<div class="overview-stock-id"><div><b>'+esc(row.symbol)+'</b><span>'+esc(row.exchange)+'</span></div>'+(company?'<p title="'+esc(company)+'">'+esc(company)+'</p>':'<p class="company-pending">Tên công ty đang cập nhật</p>')+'</div></div>'+
      '<div class="overview-price"><strong>'+formatPrice(row.currentPrice)+'</strong><span class="'+metricClass(row.changePct)+'">'+pct(row.changePct)+'</span></div>'+
      signalRailHtml(row)+
      '<div class="reason-list">'+reasons.map(function(reason){return '<span>'+esc(reason)+'</span>';}).join('')+'</div>'+
    '</article>';
  }
  function overviewStockRowHtml(row) {
    var company = companyDisplayName(row.symbol) || "Tên công ty đang cập nhật";
    return '<article class="lovable-stock-row" data-symbol="' + esc(row.symbol) + '">' +
      '<div class="stock-row-identity">' + logoHtml(row.symbol, 'row-logo') + '<div><strong>' + esc(row.symbol) + '</strong><span title="' + esc(company) + '">' + esc(company) + '</span><small>' + esc(row.exchange) + '</small></div></div>' +
      '<div class="stock-row-price"><strong>' + formatPrice(row.currentPrice) + '</strong><span class="' + metricClass(row.changePct) + '">' + pct(row.changePct) + '</span></div>' +
      '<div class="stock-row-volume"><small>KL hiện tại</small><strong>' + shortVolume(row.cumVolume) + '</strong></div>' +
      '<div class="stock-row-ccc">' + signalRailHtml(row) + '</div>' +
    '</article>';
  }
  function railCardHtml(title, meta, body, extraClass) {
    return '<section class="rail-card ' + esc(extraClass || '') + '"><header><h3>' + esc(title) + '</h3>' + (meta ? '<span>' + esc(meta) + '</span>' : '') + '</header><div class="rail-card-body">' + body + '</div></section>';
  }
  function signalLegendHtml() {
    var rows = [
      ["price", "Giá", "Tăng ≥ 3%"],
      ["volume", "Khối lượng", "KL ngày ≥ 200% KLTB10"],
      ["trend", "Xu hướng", "Trên MA200"],
      ["rvol", "RVOL", "RVOL30 ≥ 200%"]
    ];
    return '<dl class="signal-legend">' + rows.map(function (item) { return '<div><span class="ccc-segment ccc-' + item[0] + ' is-on"></span><dt>' + esc(item[1]) + '</dt><dd>' + esc(item[2]) + '</dd></div>'; }).join('') + '</dl><div class="signal-state-list"><div><b>0–2/4</b><span>Trạng thái thường</span></div><div><b>3/4</b><span>Đang hội tụ</span></div><div><b>4/4</b><span>Hội tụ mạnh</span></div></div>';
  }
  function planScopeCardHtml() {
    var plan = mockPlan();
    var watchlist = mockWatchlistRows();
    var remaining = plan.changeLimit === null ? "Không giới hạn" : Math.max(0, plan.changeLimit - state.mockChangeUsed) + "/" + plan.changeLimit;
    var rows = '<dl class="rail-kv"><div><dt>Giá gói</dt><dd>' + esc(plan.price) + '</dd></div><div><dt>Phạm vi kỹ thuật</dt><dd>' + (plan.fullMarket ? 'Toàn bộ ' + state.rows.length + ' mã' : plan.viewLimit + ' mã') + '</dd></div><div><dt>Watchlist capacity</dt><dd>' + (plan.watchlistLimit === null ? 'Ưu tiên cá nhân' : watchlist.length + '/' + plan.watchlistLimit) + '</dd></div><div><dt>Quota thay đổi</dt><dd>' + remaining + '</dd></div><div><dt>Email / Telegram</dt><dd>' + (plan.email && plan.telegram ? 'Có' : 'Không') + '</dd></div></dl>';
    return railCardHtml("Gói & phạm vi", plan.label, rows + '<p class="rail-note">' + iconSvg('lock') + '<span>Mã ngoài phạm vi chỉ hiển thị số lượng, không tiết lộ danh tính.</span></p><button type="button" class="rail-action scanner-upgrade-trigger">Mở rộng phạm vi</button>', 'plan-scope-card');
  }
  function dataTrustCardHtml() {
    var trust = trustModel(Date.now());
    return railCardHtml("Data Trust", "", '<div class="rail-trust ' + trust.tone + '"><div><i></i><strong>' + esc(trust.label) + '</strong></div><p>' + esc(trust.detail) + '</p></div><dl class="rail-kv"><div><dt>Cập nhật</dt><dd>' + esc(trust.time) + '</dd></div><div><dt>Vũ trụ quét</dt><dd>' + esc(trust.count) + '</dd></div><div><dt>Nguồn</dt><dd>' + esc(trust.source) + '</dd></div><div><dt>Môi trường</dt><dd>STAGING</dd></div></dl><p class="rail-note">' + iconSvg('shield') + '<span>Tín hiệu CCC tính trên snapshot dữ liệu, không dự đoán giá.</span></p>', 'data-trust-card');
  }
  function commonContextRailHtml(extra) {
    return '<aside class="context-rail">' + (extra || '') + planScopeCardHtml() + dataTrustCardHtml() + '</aside>';
  }
  function marketPulseHtml() {
    var instruments = [
      ["VN-INDEX", "VN-INDEX", true, "Việt Nam"],
      ["S&P 500", "S&P 500", false, "Hoa Kỳ"],
      ["HANG SENG", "HANG SENG", false, "Hong Kong"],
      ["DXY", "DXY", false, "USD Index"],
      ["GOLD", "GOLD", false, "Vàng"],
      ["WTI", "WTI", false, "Dầu thô"],
      ["BTC", "BTC", false, "Bitcoin"]
    ];
    var cards = instruments.map(function (item) {
      return '<article class="market-tile ' + (item[2] ? 'is-primary' : '') + '"><header><strong>' + esc(item[0]) + '</strong>' + (item[2] ? '<span>CHỦ ĐẠO</span>' : '') + '<em>Không có dữ liệu</em></header><div class="market-unavailable"><b>—</b><span>Chưa kết nối nguồn chỉ số</span></div><footer>' + esc(item[3]) + ' · trạng thái không khả dụng</footer></article>';
    }).join('');
    return '<section class="market-pulse panel-anatomy" aria-labelledby="market-pulse-title"><header class="section-bar"><div><i class="status-dot"></i><h2 id="market-pulse-title">Market Pulse</h2><span>Cập nhật ' + esc(compactTime(state.meta && state.meta.marketUpdatedAt)) + '</span></div><small>7 chỉ số · không dùng dữ liệu giả</small></header><div class="market-pulse-grid">' + cards + '</div></section>';
  }
  function mockPlan() { return MOCK_PLAN_CONFIG[state.mockPlan] || MOCK_PLAN_CONFIG.FREE; }
  function mockWatchlistRows() {
    var plan = mockPlan();
    var limit = plan.fullMarket ? Math.min(10, state.rows.length) : plan.watchlistLimit;
    return state.rows.slice().sort(priority).slice(0, limit);
  }
  // STAGING MOCK ONLY — NOT A SECURITY BOUNDARY.
  // Production must enforce entitlement before returning protected rows. This
  // renderer only proves that locked market identities are not enumerated in DOM.
  function isMockEntitled(row) {
    if (mockPlan().fullMarket) return true;
    return mockWatchlistRows().some(function (item) { return item.symbol === row.symbol; });
  }
  function exactSearchRow() {
    var q = state.query.trim().toUpperCase();
    if (!q) return null;
    return state.rows.find(function (row) { return row.symbol === q; }) || null;
  }
  function discoveryRows(key) {
    if (key === "4of4") return state.rows.filter(function(row){return row.signalCount === 4;}).sort(priority);
    if (key === "3plus") return state.rows.filter(function(row){return row.signalCount >= 3;}).sort(priority);
    if (key === "2plus") return state.rows.filter(function(row){return row.signalCount >= 2;}).sort(priority);
    if (key === "rvol30") return state.rows.filter(function(row){return row.signalRvol30_200pct;}).sort(priority);
    return [];
  }
  function discoveryLabel(key) {
    return key === "4of4" ? "mã đạt 4/4" : key === "3plus" ? "mã đạt từ 3 tín hiệu" : key === "2plus" ? "mã đạt từ 2 tín hiệu" : "mã có RVOL30 sớm";
  }
  function discoveryData(key) {
    var plan = mockPlan();
    var marketRows = discoveryRows(key);
    var watchlistRows = mockWatchlistRows();
    var visibleItems = plan.fullMarket ? marketRows : watchlistRows.filter(function(row){return key === "4of4" ? row.signalCount === 4 : key === "3plus" ? row.signalCount >= 3 : key === "2plus" ? row.signalCount >= 2 : row.signalRvol30_200pct;});
    return { totalCount:marketRows.length, visibleItems:visibleItems, visibleCount:visibleItems.length, lockedCount:Math.max(0,marketRows.length-visibleItems.length) };
  }
  function signalPass(row, key) {
    if (!key) return true;
    if (key === "4of4") return row.signalCount === 4;
    if (key === "3plus") return row.signalCount >= 3;
    if (key === "2plus") return row.signalCount >= 2;
    if (key === "exactly2") return row.signalCount === 2;
    if (key === "exactly1") return row.signalCount === 1;
    if (key === "rvol30") return row.signalRvol30_200pct;
    if (key === "price3") return row.signalPrice3pct;
    if (key === "vol200") return row.signalVolume200pct;
    if (key === "abovema200") return row.signalAboveMa200;
    if (key === "missing") return row.hasMissingData;
    return true;
  }
  function priority(a, b) {
    return Number(b.signalRvol30_200pct) - Number(a.signalRvol30_200pct) || b.signalCount - a.signalCount || value(b.rvol30Pct, -Infinity) - value(a.rvol30Pct, -Infinity) || value(b.changePct, -Infinity) - value(a.changePct, -Infinity) || a.symbol.localeCompare(b.symbol);
  }
  function value(v, missing) { return v === null || !Number.isFinite(v) ? missing : v; }
  function metricSort(key, ascending) {
    return function (a, b) {
      var av = value(a[key], ascending ? Infinity : -Infinity);
      var bv = value(b[key], ascending ? Infinity : -Infinity);
      return (ascending ? av - bv : bv - av) || priority(a, b);
    };
  }
  function absoluteMetricSort(key) {
    return function (a, b) {
      var av = a[key] === null || !Number.isFinite(a[key]) ? Infinity : Math.abs(a[key]);
      var bv = b[key] === null || !Number.isFinite(b[key]) ? Infinity : Math.abs(b[key]);
      return av - bv || priority(a, b);
    };
  }
  function filteredRows(sourceRows, includeQuery) {
    var q = includeQuery ? state.query.trim().toUpperCase() : "";
    var rows = (sourceRows || state.rows).filter(function (r) {
      return (!q || r.symbol.indexOf(q) >= 0) && (state.exchange === "all" || r.exchange.toLowerCase() === state.exchange) && signalPass(r, state.signal);
    });
    var sorters = {
      rvol30: metricSort("rvol30Pct", false), rvol30Asc: metricSort("rvol30Pct", true),
      change: metricSort("changePct", false), changeAsc: metricSort("changePct", true),
      volume: metricSort("dayVolumeRatioPct", false), volumeAsc: metricSort("dayVolumeRatioPct", true),
      ma10Near: absoluteMetricSort("ma10DistancePct"),
      ma200Near: absoluteMetricSort("ma200DistancePct"),
      symbol: function (a, b) { return a.symbol.localeCompare(b.symbol); }, signal: priority
    };
    return rows.sort(sorters[state.sort] || priority);
  }
  function parseTime(value) {
    if (!value || value === "—") return "—";
    var d = new Date(value);
    if (!Number.isNaN(d.getTime())) return new Intl.DateTimeFormat("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(d);
    return String(value);
  }
  function getMeta(raw, rows) {
    var m = raw.meta || {};
    var newest = rows.reduce(function (best, r) { return !best || new Date(r.updatedAt) > new Date(best.updatedAt) ? r : best; }, null);
    return {
      systemStatus: m.systemStatus || (m.status === "SUCCESS" ? "OK" : m.status) || "OK",
      marketUpdatedAt: parseTime(m.marketUpdatedAt || m.updated_at || (newest && newest.updatedAt)),
      dashboardCheckedAt: parseTime(m.dashboardCheckedAt || m.checked_at || new Date()),
      totalSymbols: m.totalSymbols || rows.length,
      dataSource: m.dataSource || "Supabase",
      mode: "LIVE"
    };
  }

  function median(values) {
    var xs = values.filter(function(v){return v !== null && Number.isFinite(v);}).sort(function(a,b){return a-b;});
    if (!xs.length) return null;
    var mid = Math.floor(xs.length/2);
    return xs.length % 2 ? xs[mid] : (xs[mid-1]+xs[mid])/2;
  }
  function scoreBand(value, bands) {
    if (value === null || !Number.isFinite(value)) return null;
    for (var i=0;i<bands.length;i++) if (bands[i][0](value)) return bands[i][1];
    return bands.length ? bands[bands.length-1][1] : 0;
  }
  function valuationScore(value, med, maxPoint) {
    if (value === null || med === null || value <= 0 || med <= 0) return null;
    var r = value / med;
    if (r <= .8) return maxPoint;
    if (r <= 1) return Math.round(maxPoint*.8);
    if (r <= 1.2) return Math.round(maxPoint*.6);
    if (r <= 1.5) return Math.round(maxPoint*.35);
    return Math.max(1, Math.round(maxPoint*.15));
  }
  function financialScore(row) {
    if (!row || row.data_status === "NO_FINANCIAL_DATA") return {earned:0,available:0,coverage:0,label:"Chưa có dữ liệu",parts:[],badges:["Chưa có BCTC"]};
    var parts=[], earned=0, available=0;
    function add(name,max,value,detail){ if(value===null || value===undefined || !Number.isFinite(value)) return; available+=max; earned+=value; parts.push({name:name,earned:value,max:max,detail:detail}); }
    var py=num(row.profit_yoy_pct), iy=num(row.income_yoy_pct), pq=num(row.profit_qoq_pct), roe=num(row.roea_pct), roa=num(row.roaa_pct), de=num(row.debt_equity_pct), da=num(row.debt_assets_pct), pe=num(row.pe), pb=num(row.pb);
    add("Lợi nhuận sau thuế so với cùng kỳ",20,scoreBand(py,[[function(v){return v>=30},20],[function(v){return v>=20},16],[function(v){return v>=10},12],[function(v){return v>=0},7],[function(){return true},0]]),py===null?"—":pct(py));
    add("Doanh thu / thu nhập so với cùng kỳ",10,scoreBand(iy,[[function(v){return v>=20},10],[function(v){return v>=10},8],[function(v){return v>=5},5],[function(v){return v>=0},3],[function(){return true},0]]),iy===null?"—":pct(iy));
    add("Lợi nhuận sau thuế so với quý trước",5,scoreBand(pq,[[function(v){return v>=20},5],[function(v){return v>=10},4],[function(v){return v>=0},3],[function(v){return v>=-10},1],[function(){return true},0]]),pq===null?"—":pct(pq));
    add("ROE – Lợi nhuận trên vốn chủ sở hữu",20,scoreBand(roe,[[function(v){return v>=20},20],[function(v){return v>=15},16],[function(v){return v>=10},11],[function(v){return v>=5},6],[function(v){return v>=0},2],[function(){return true},0]]),roe===null?"—":pct(roe));
    add("ROA – Lợi nhuận trên tổng tài sản",10,scoreBand(roa,[[function(v){return v>=10},10],[function(v){return v>=7},8],[function(v){return v>=5},6],[function(v){return v>=2},3],[function(v){return v>=0},1],[function(){return true},0]]),roa===null?"—":pct(roa));
    if (row.financial_model === "NORMAL") {
      add("Nợ vay trên vốn chủ sở hữu",10,scoreBand(de,[[function(v){return v<30},10],[function(v){return v<60},8],[function(v){return v<100},5],[function(v){return v<150},2],[function(){return true},0]]),de===null?"—":plainPct(de));
      add("Nợ trên tổng tài sản",10,scoreBand(da,[[function(v){return v<30},10],[function(v){return v<45},8],[function(v){return v<60},5],[function(v){return v<75},2],[function(){return true},0]]),da===null?"—":plainPct(da));
    }
    var peers=state.financialRows.filter(function(x){return x.website_group===row.website_group;});
    var medPe=median(peers.map(function(x){return num(x.pe);})), medPb=median(peers.map(function(x){return num(x.pb);}));
    var peScore=valuationScore(pe,medPe,8), pbScore=valuationScore(pb,medPb,7);
    add("P/E – Giá so với lợi nhuận, so cùng ngành",8,peScore,pe===null?"—":pe.toFixed(2)+"x"+(medPe?" · trung vị "+medPe.toFixed(2)+"x":""));
    add("P/B – Giá so với giá trị sổ sách, so cùng ngành",7,pbScore,pb===null?"—":pb.toFixed(2)+"x"+(medPb?" · trung vị "+medPb.toFixed(2)+"x":""));
    var coverage=available;
    var badges=[];
    if(py!==null){if(py>=30)badges.push("Tăng trưởng mạnh");else if(py>=10)badges.push("Tăng trưởng tốt");else if(py<0)badges.push("LNST suy giảm");}
    if(roe!==null){if(roe>=20)badges.push("Hiệu quả vốn chủ sở hữu cao");else if(roe>=15)badges.push("Hiệu quả vốn chủ sở hữu khá");}
    if(peScore!==null && peScore>=6)badges.push("Định giá P/E hấp dẫn so với ngành");
    if(pbScore!==null && pbScore>=5)badges.push("Định giá P/B hấp dẫn so với ngành");
    if(row.financial_model !== "NORMAL") badges.push("Chưa đủ chỉ tiêu chuyên biệt để chấm sức khỏe tài chính ngành");
    if(available<100) badges.push("Chưa đủ dữ liệu để chấm trọn 100 điểm");
    return {earned:earned,available:available,coverage:coverage,label:available?earned+"/"+available:"Chưa đủ dữ liệu",parts:parts,badges:badges};
  }
  function scoreClass(s){ if(!s.available)return "score-na"; var r=s.earned/s.available*100; return r>=75?"score-good":r>=55?"score-mid":"score-low"; }
  function financialBySymbol(symbol){return state.financialBySymbol[String(symbol||"").toUpperCase()]||null;}
  function moneyBil(v){var n=num(v);return n===null?"—":new Intl.NumberFormat("vi-VN",{maximumFractionDigits:0}).format(n)+" tỷ";}
  function scoreBadgeHtml(row){var s=financialScore(row);return '<span class="fund-score '+scoreClass(s)+'" title="Điểm đạt '+esc(s.earned)+' trên '+esc(s.available)+' điểm có thể chấm">'+esc(s.label)+'</span>';}
  function freshnessLabel(value){
    var v=String(value||"").toUpperCase();
    if(v==="CURRENT") return "Mới nhất";
    if(v==="LAGGING") return "Chậm 1 kỳ";
    if(v==="STALE") return "Dữ liệu cũ";
    if(v==="NO_DATA") return "Chưa có dữ liệu";
    return value||"—";
  }
  function scoreCoverageText(row){
    var s=financialScore(row);
    if(!s.available) return "Chưa đủ dữ liệu để chấm";
    return "Chấm được "+s.available+"/100 điểm tối đa";
  }
  function metricHead(title,sub){return '<span class="th-main">'+esc(title)+'</span>'+(sub?'<span class="th-sub">'+esc(sub)+'</span>':'');}
  function groupList(){
    var map={}; state.financialRows.forEach(function(r){var g=r.website_group||"Khác";map[g]=(map[g]||0)+1;});
    return Object.keys(map).sort(function(a,b){return map[b]-map[a]||a.localeCompare(b,"vi");}).map(function(g){return [g,map[g]];});
  }
  function financialCard(row){
    var s=financialScore(row);
    return '<article class="fund-card" data-symbol="'+esc(row.symbol)+'">'+
      '<div class="fund-card-top"><div><b class="fund-symbol">'+esc(row.symbol)+'</b><span>'+esc(row.website_group||'—')+'</span></div>'+scoreBadgeHtml(row)+'</div>'+
      '<div class="fund-card-grid">'+
        '<div><small>Lợi nhuận sau thuế<br>so với cùng kỳ</small><b class="'+metricClass(num(row.profit_yoy_pct))+'">'+pct(num(row.profit_yoy_pct))+'</b></div>'+
        '<div><small>ROE<br>Lợi nhuận / vốn chủ</small><b>'+pct(num(row.roea_pct))+'</b></div>'+
        '<div><small>P/E<br>Giá / lợi nhuận</small><b>'+(num(row.pe)===null?'—':num(row.pe).toFixed(2)+'x')+'</b></div>'+
        '<div><small>P/B<br>Giá / giá trị sổ sách</small><b>'+(num(row.pb)===null?'—':num(row.pb).toFixed(2)+'x')+'</b></div>'+
      '</div>'+
      '<div class="fund-card-foot"><span>'+esc(scoreCoverageText(row))+'</span></div>'+
    '</article>';
  }
  function researchTabsHtml(){
    return '<nav class="research-tabs" aria-label="Điều hướng Nghiên cứu"><a href="/so-sanh-theo-nganh" class="'+(state.route==='industry'?'active':'')+'"'+(state.route==='industry'?' aria-current="page"':'')+'>Theo ngành</a><a href="/sang-loc-co-ban" class="'+(state.route==='fundamental'?'active':'')+'"'+(state.route==='fundamental'?' aria-current="page"':'')+'>Sàng lọc cơ bản</a></nav>';
  }
  function scoreMethodHtml(){
    return '<section class="score-method panel">'+
      '<div class="score-method-head"><div><h2>Cách tính Điểm cơ bản</h2><p>Mỗi điểm đều xuất phát từ chỉ tiêu tài chính cụ thể. Mã thiếu dữ liệu sẽ chỉ được chấm trên phần có dữ liệu và <b>không tự quy đổi thành 100 điểm</b>.</p></div><span class="method-total">Tối đa 100 điểm</span></div>'+
      '<div class="method-grid">'+
        '<div class="method-card"><b>1. Tăng trưởng · tối đa 35 điểm</b><p><strong>20đ</strong> Lợi nhuận sau thuế so với cùng kỳ năm trước.<br><strong>10đ</strong> Doanh thu hoặc thu nhập so với cùng kỳ.<br><strong>5đ</strong> Lợi nhuận sau thuế so với quý trước.</p></div>'+
        '<div class="method-card"><b>2. Hiệu quả sinh lời · tối đa 30 điểm</b><p><strong>20đ</strong> ROE – lợi nhuận tạo ra trên vốn chủ sở hữu.<br><strong>10đ</strong> ROA – lợi nhuận tạo ra trên tổng tài sản.</p></div>'+
        '<div class="method-card"><b>3. Sức khỏe tài chính · tối đa 20 điểm</b><p>Với doanh nghiệp thông thường: <strong>10đ</strong> Nợ vay trên vốn chủ sở hữu và <strong>10đ</strong> Nợ trên tổng tài sản.<br>Ngân hàng, chứng khoán và bảo hiểm chưa có đủ chỉ tiêu chuyên ngành nên phần này có thể chưa được chấm.</p></div>'+
        '<div class="method-card"><b>4. Định giá · tối đa 15 điểm</b><p><strong>8đ</strong> P/E – giá cổ phiếu so với lợi nhuận.<br><strong>7đ</strong> P/B – giá cổ phiếu so với giá trị sổ sách.<br>Hai chỉ số được so tương đối với trung vị của các doanh nghiệp cùng ngành.</p></div>'+
      '</div>'+
      '<div class="term-glossary"><div><b>ROE là gì?</b><span>Cho biết 100 đồng vốn chủ sở hữu tạo ra bao nhiêu đồng lợi nhuận.</span></div><div><b>ROA là gì?</b><span>Cho biết doanh nghiệp sử dụng toàn bộ tài sản hiệu quả đến mức nào.</span></div><div><b>P/E là gì?</b><span>So sánh giá cổ phiếu với lợi nhuận doanh nghiệp tạo ra.</span></div><div><b>P/B là gì?</b><span>So sánh giá cổ phiếu với giá trị sổ sách trên mỗi cổ phần.</span></div></div>'+
      '<details class="score-rules"><summary>Xem toàn bộ ngưỡng chấm điểm chi tiết</summary><div class="rule-grid">'+
        '<p><b>Lợi nhuận sau thuế so cùng kỳ · 20đ:</b><br>≥30%: 20đ · 20–29,99%: 16đ · 10–19,99%: 12đ · 0–9,99%: 7đ · giảm so cùng kỳ: 0đ.</p>'+
        '<p><b>Doanh thu / thu nhập so cùng kỳ · 10đ:</b><br>≥20%: 10đ · 10–19,99%: 8đ · 5–9,99%: 5đ · 0–4,99%: 3đ · giảm: 0đ.</p>'+
        '<p><b>Lợi nhuận sau thuế so quý trước · 5đ:</b><br>≥20%: 5đ · 10–19,99%: 4đ · 0–9,99%: 3đ · giảm dưới 10%: 1đ · giảm từ 10% trở lên: 0đ.</p>'+
        '<p><b>ROE · 20đ:</b><br>≥20%: 20đ · 15–19,99%: 16đ · 10–14,99%: 11đ · 5–9,99%: 6đ · 0–4,99%: 2đ · âm: 0đ.</p>'+
        '<p><b>ROA · 10đ:</b><br>≥10%: 10đ · 7–9,99%: 8đ · 5–6,99%: 6đ · 2–4,99%: 3đ · 0–1,99%: 1đ · âm: 0đ.</p>'+
        '<p><b>Nợ vay / vốn chủ sở hữu · 10đ:</b><br>&lt;30%: 10đ · 30–59,99%: 8đ · 60–99,99%: 5đ · 100–149,99%: 2đ · ≥150%: 0đ.</p>'+
        '<p><b>Nợ / tổng tài sản · 10đ:</b><br>&lt;30%: 10đ · 30–44,99%: 8đ · 45–59,99%: 5đ · 60–74,99%: 2đ · ≥75%: 0đ.</p>'+
        '<p><b>P/E và P/B · 15đ:</b><br>≤80% trung vị ngành: điểm tối đa · 80–100%: khoảng 80% điểm · 100–120%: khoảng 60% · 120–150%: khoảng 35% · trên 150%: khoảng 15% điểm.</p>'+
      '</div></details>'+
      '<p class="score-note"><b>Lưu ý:</b> Điểm số dùng để học và sàng lọc ban đầu. Cần đọc thêm báo cáo tài chính, chất lượng lợi nhuận và đặc thù ngành trước khi đưa ra quyết định.</p>'+
    '</section>';
  }
  function industryHtml(){
    var groups=groupList(); if(!state.industryGroup && groups.length) state.industryGroup=groups[0][0];
    var selected=state.financialRows.filter(function(r){return r.website_group===state.industryGroup;}).sort(function(a,b){var sa=financialScore(a),sb=financialScore(b);return (sb.available?sb.earned/sb.available:0)-(sa.available?sa.earned/sa.available:0);});
    var groupButtons=groups.map(function(g){return '<button class="industry-chip '+(state.industryGroup===g[0]?'active':'')+'" data-industry="'+esc(g[0])+'"><span>'+esc(g[0])+'</span><b>'+g[1]+' mã</b></button>';}).join('');
    var rows=selected.map(function(r){
      var s=financialScore(r);
      return '<tr data-symbol="'+esc(r.symbol)+'">'+
        '<td class="center symbol"><b>'+esc(r.symbol)+'</b></td>'+
        '<td class="center"><div>'+scoreBadgeHtml(r)+'</div><small class="score-coverage">'+esc(scoreCoverageText(r))+'</small></td>'+
        '<td class="center '+metricClass(num(r.profit_yoy_pct))+'">'+pct(num(r.profit_yoy_pct))+'</td>'+
        '<td class="center">'+pct(num(r.roea_pct))+'</td>'+
        '<td class="center">'+(num(r.pe)===null?'—':num(r.pe).toFixed(2)+'x')+'</td>'+
        '<td class="center">'+(num(r.pb)===null?'—':num(r.pb).toFixed(2)+'x')+'</td>'+
        '<td class="center"><span class="freshness-tag freshness-'+String(r.freshness_status||'').toLowerCase()+'">'+esc(freshnessLabel(r.freshness_status))+'</span></td>'+
      '</tr>';
    }).join('');
    return '<main class="wrap fund-main"><section class="page-intro"><span class="eyebrow">NGHIÊN CỨU CƠ BẢN CÔNG KHAI</span><h1>So sánh theo ngành</h1><p>Chọn một ngành để đặt các doanh nghiệp cạnh nhau theo tăng trưởng lợi nhuận, khả năng sinh lời và định giá.</p></section>'+researchTabsHtml()+secondarySourceWarningHtml(true)+'<section class="industry-picker">'+groupButtons+'</section><section class="panel industry-panel"><div class="section-title"><div><h2>'+esc(state.industryGroup||'Ngành')+'</h2><p>'+selected.length+' mã · sắp xếp theo Điểm cơ bản trên phần dữ liệu có thể chấm.</p></div></div><div class="desktop-table"><div class="table-shell fund-table-shell"><table class="fundamental-table industry-table"><thead><tr><th>'+metricHead('Mã cổ phiếu','')+'</th><th>'+metricHead('Điểm cơ bản','Điểm đạt / điểm có thể chấm')+'</th><th>'+metricHead('Tăng trưởng lợi nhuận','So với cùng kỳ năm trước')+'</th><th>'+metricHead('ROE','Lợi nhuận / vốn chủ sở hữu')+'</th><th>'+metricHead('P/E','Giá / lợi nhuận')+'</th><th>'+metricHead('P/B','Giá / giá trị sổ sách')+'</th><th>'+metricHead('Dữ liệu','Mức độ cập nhật')+'</th></tr></thead><tbody>'+rows+'</tbody></table></div></div><div class="mobile-list fund-mobile-list">'+selected.map(financialCard).join('')+'</div></section><p class="disclaimer">Điểm số hỗ trợ sàng lọc và học phân tích, không phải khuyến nghị mua/bán.</p></main>';
  }
  function fundamentalHtml(){
    var rows=state.financialRows.slice().filter(function(r){var s=financialScore(r);if(state.fundamentalMinScore && (!s.available || s.earned/s.available*100<state.fundamentalMinScore))return false;var py=num(r.profit_yoy_pct),roe=num(r.roea_pct);if(state.fundamentalProfitGrowth==='positive' && !(py!==null&&py>0))return false;if(state.fundamentalProfitGrowth==='20plus' && !(py!==null&&py>=20))return false;if(state.fundamentalRoe==='15plus' && !(roe!==null&&roe>=15))return false;if(state.fundamentalRoe==='20plus' && !(roe!==null&&roe>=20))return false;return true;}).sort(function(a,b){var sa=financialScore(a),sb=financialScore(b);return (sb.available?sb.earned/sb.available:0)-(sa.available?sa.earned/sa.available:0);});
    var scoreBtns=[[0,'Tất cả'],[55,'Từ 55% mức điểm có thể chấm'],[70,'Từ 70% mức điểm có thể chấm'],[80,'Từ 80% mức điểm có thể chấm']].map(function(x){return '<button class="chip '+(state.fundamentalMinScore===x[0]?'active':'')+'" data-fund-filter="score" data-value="'+x[0]+'">'+x[1]+'</button>';}).join('');
    var growthBtns=[['all','Tất cả'],['positive','Lợi nhuận tăng so cùng kỳ'],['20plus','Lợi nhuận tăng từ 20% so cùng kỳ']].map(function(x){return '<button class="chip '+(state.fundamentalProfitGrowth===x[0]?'active':'')+'" data-fund-filter="growth" data-value="'+x[0]+'">'+x[1]+'</button>';}).join('');
    var roeBtns=[['all','Tất cả'],['15plus','ROE từ 15%'],['20plus','ROE từ 20%']].map(function(x){return '<button class="chip '+(state.fundamentalRoe===x[0]?'active':'')+'" data-fund-filter="roe" data-value="'+x[0]+'">'+x[1]+'</button>';}).join('');
    var tableRows=rows.map(function(r){
      return '<tr data-symbol="'+esc(r.symbol)+'">'+
        '<td class="center symbol"><b>'+esc(r.symbol)+'</b></td>'+
        '<td class="center"><span class="industry-name-cell">'+esc(r.website_group||'—')+'</span></td>'+
        '<td class="center"><div>'+scoreBadgeHtml(r)+'</div><small class="score-coverage">'+esc(scoreCoverageText(r))+'</small></td>'+
        '<td class="center '+metricClass(num(r.profit_yoy_pct))+'">'+pct(num(r.profit_yoy_pct))+'</td>'+
        '<td class="center">'+pct(num(r.roea_pct))+'</td>'+
        '<td class="center">'+(num(r.pe)===null?'—':num(r.pe).toFixed(2)+'x')+'</td>'+
        '<td class="center">'+(num(r.pb)===null?'—':num(r.pb).toFixed(2)+'x')+'</td>'+
        '<td class="center"><span class="freshness-tag freshness-'+String(r.freshness_status||'').toLowerCase()+'">'+esc(freshnessLabel(r.freshness_status))+'</span></td>'+
      '</tr>';
    }).join('');
    return '<main class="wrap fund-main"><section class="page-intro"><span class="eyebrow">NGHIÊN CỨU CƠ BẢN CÔNG KHAI</span><h1>Sàng lọc cơ bản</h1><p>Dùng các chỉ tiêu tài chính để tìm doanh nghiệp phù hợp với tiêu chí của bạn. Mỗi mã vẫn được giữ nếu thiếu dữ liệu và website ghi rõ phần nào chưa thể chấm.</p></section>'+researchTabsHtml()+secondarySourceWarningHtml(true)+scoreMethodHtml()+'<section class="panel fund-filters"><div class="filter-block"><p class="filter-label">Mức Điểm cơ bản</p><div class="filter-help">Ví dụ 70% nghĩa là doanh nghiệp đạt ít nhất 70% số điểm trên những chỉ tiêu hiện có.</div><div class="chips">'+scoreBtns+'</div></div><div class="filter-block"><p class="filter-label">Tăng trưởng lợi nhuận sau thuế</p><div class="chips">'+growthBtns+'</div></div><div class="filter-block"><p class="filter-label">ROE – lợi nhuận trên vốn chủ sở hữu</p><div class="chips">'+roeBtns+'</div></div></section><p class="result-info">Đang hiển thị <strong>'+rows.length+'</strong> / '+state.financialRows.length+' mã trong danh sách theo dõi. Mã thiếu dữ liệu vẫn được giữ để bạn nhận biết.</p><section class="panel screener-table-panel"><div class="desktop-table"><div class="table-shell screener-table-shell"><table class="fundamental-table screener-table"><thead><tr><th>'+metricHead('Mã cổ phiếu','')+'</th><th>'+metricHead('Ngành','Nhóm hoạt động chính')+'</th><th>'+metricHead('Điểm cơ bản','Điểm đạt / điểm có thể chấm')+'</th><th>'+metricHead('Tăng trưởng lợi nhuận','So với cùng kỳ năm trước')+'</th><th>'+metricHead('ROE','Lợi nhuận / vốn chủ sở hữu')+'</th><th>'+metricHead('P/E','Giá / lợi nhuận')+'</th><th>'+metricHead('P/B','Giá / giá trị sổ sách')+'</th><th>'+metricHead('Dữ liệu','Mức độ cập nhật')+'</th></tr></thead><tbody>'+tableRows+'</tbody></table></div></div><div class="mobile-list fund-mobile-list">'+rows.map(financialCard).join('')+'</div></section><p class="disclaimer">Điểm số hỗ trợ sàng lọc và học phân tích, không phải khuyến nghị mua/bán.</p></main>';
  }
  function secondarySourceDetail() {
    var details = [];
    if (state.financialError) details.push("Dữ liệu cơ bản chưa tải được");
    if (state.metadataError) details.push("Tên công ty chưa tải được");
    return details.join(" · ");
  }
  function secondarySourceWarningHtml(includeFinancial) {
    var details = [];
    if (includeFinancial && state.financialError) details.push("Dữ liệu cơ bản chưa tải được; kết quả bên dưới có thể trống hoặc chưa đầy đủ.");
    if (state.metadataError) details.push("Tên công ty chưa tải được; mã cổ phiếu vẫn được giữ.");
    if (!details.length) return "";
    return '<div class="source-warning" role="alert"><strong>Dữ liệu có cảnh báo</strong><span>' + esc(details.join(" ")) + '</span></div>';
  }
  function iconSvg(name) {
    var paths = {
      trend: '<path d="M4 17l5-5 4 4 7-8"/><path d="M15 8h5v5"/>',
      home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10"/><path d="M9.5 20v-6h5v6"/>',
      list: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 9h8M8 13h8M8 17h5"/>',
      industry: '<path d="M4 20V9l5-3v14M9 11l6-3v12M15 5l5 3v12M2 20h20"/>',
      watchlist: '<path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z"/>',
      bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/>',
      fundamental: '<circle cx="10" cy="10" r="6"/><path d="m14.5 14.5 5 5M7 11l2-2 2 2 3-4"/>',
      sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"/>',
      moon: '<path d="M20 15.5A8 8 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z"/>',
      refresh: '<path d="M20 11a8 8 0 1 0-2.34 5.66"/><path d="M20 4v7h-7"/>',
      search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
      bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/>',
      user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 21a7.5 7.5 0 0 1 15 0"/>',
      lock: '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
      shield: '<path d="M12 3 5 6v5c0 4.6 2.8 8 7 10 4.2-2 7-5.4 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-4"/>',
      chart: '<path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/>',
      arrow: '<path d="m9 18 6-6-6-6"/>',
      check: '<path d="m5 12 4 4L19 6"/>'
    };
    return '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (paths[name] || '') + '</svg>';
  }
  function routeLabel() {
    return state.route === "list" ? "Danh sách cổ phiếu" : state.route === "industry" ? "So sánh theo ngành" : state.route === "fundamental" ? "Sàng lọc cơ bản" : "Tổng quan";
  }
  function compactTime(value) {
    var text = String(value || "—");
    var match = text.match(/\b(\d{2}:\d{2})(?::\d{2})?\b/);
    return match ? match[1] : text;
  }
  function trustModel(now) {
    var m = state.meta || {};
    var hasRows = state.rows.length > 0;
    var total = m.totalSymbols || state.rows.length;
    var hasMissing = hasRows && state.rows.some(function (row) { return row.hasMissingData; });
    var completeness = hasMissing ? "Có mã thiếu dữ liệu" : "Dữ liệu đầy đủ";
    var base = {
      tone: "trust-checking",
      label: "Đang kiểm tra dữ liệu",
      detail: "Đang kết nối nguồn dữ liệu",
      time: compactTime(m.marketUpdatedAt),
      count: hasRows ? total + " mã" : "Chưa có dữ liệu",
      source: m.dataSource || "Chuyện Chợ Chứng"
    };
    if (!hasRows) {
      if (state.error) return Object.assign(base, { tone: "trust-empty", label: "Không có dữ liệu", detail: state.error });
      return base;
    }
    if (state.error) return Object.assign(base, { tone: "trust-error", label: "Lỗi nguồn · đang dùng cache", detail: "Đang giữ bản cập nhật gần nhất" });
    var secondaryDetail = secondarySourceDetail();
    if (m.systemStatus && m.systemStatus !== "OK") return Object.assign(base, { tone: "trust-warning", label: "Dữ liệu có cảnh báo", detail: secondaryDetail ? "Một số mã cần kiểm tra · " + secondaryDetail : "Một số mã cần kiểm tra" });
    if (secondaryDetail) return Object.assign(base, { tone: "trust-warning", label: "Dữ liệu có cảnh báo", detail: secondaryDetail });
    if (!inAutoRefreshWindow(now)) return Object.assign(base, { tone: "trust-outside", label: "Ngoài giờ thị trường", detail: completeness });
    if (state.waitingForNewData) return Object.assign(base, { tone: "trust-waiting", label: "Đang chờ dữ liệu mới", detail: "Snapshot hiện tại vẫn được giữ" });
    return Object.assign(base, { tone: "trust-live", label: "Dữ liệu hoạt động bình thường", detail: completeness });
  }
  function navLink(href, route, icon, label, compactLabel) {
    var active = Array.isArray(route) ? route.indexOf(state.route) >= 0 : state.route === route;
    return '<a href="' + href + '" class="shell-nav-link ' + (active ? 'active' : '') + '"' + (active ? ' aria-current="page"' : '') + '><span class="nav-ico">' + iconSvg(icon) + '</span><span class="nav-label">' + esc(label) + '</span><small>' + esc(compactLabel || label) + '</small></a>';
  }
  function navPlaceholder(icon, label, compactLabel) {
    return '<span class="shell-nav-link shell-nav-placeholder" aria-disabled="true" title="Chưa khả dụng trong staging"><span class="nav-ico">' + iconSvg(icon) + '</span><span class="nav-label">' + esc(label) + '</span><small>' + esc(compactLabel || label) + '</small><span class="nav-soon">STAGING</span></span>';
  }
  function headerHtml() {
    var trust = trustModel(Date.now());
    var targetTheme = state.theme === "light" ? "tối" : "sáng";
    var globalQuery = state.globalQuery;
    var nav = navLink('/', 'overview', 'home', 'Tổng quan') + navLink('/danh-sach', 'list', 'list', 'Bộ quét') + navLink('/so-sanh-theo-nganh', ['industry','fundamental'], 'industry', 'Nghiên cứu', 'Nghiên cứu') + navPlaceholder('watchlist', 'Watchlist') + navPlaceholder('bell', 'Cảnh báo');
    return '<header class="app-header"><div class="app-header-inner">' +
      '<a class="app-brand" href="/" aria-label="Chuyện Chợ Chứng — Trang tổng quan"><span class="brand-mark">' + iconSvg('chart') + '</span><span class="brand-copy"><strong>CHUYỆN CHỢ CHỨNG</strong><small>Stock Intelligence</small></span></a>' +
      '<form id="global-search-form" class="global-search" role="search" action="/danh-sach" method="get"><label class="sr-only" for="global-stock-search">Tìm mã cổ phiếu</label><span class="global-search-icon">' + iconSvg('search') + '</span><input id="global-stock-search" name="q" type="search" inputmode="search" autocomplete="off" autocorrect="off" autocapitalize="characters" spellcheck="false" placeholder="Tìm mã chứng khoán" value="' + esc(globalQuery) + '"><button class="global-search-submit" type="submit" aria-label="Thực hiện tìm kiếm mã cổ phiếu">' + iconSvg('search') + '</button></form>' +
      '<div class="header-right"><section id="data-trust" class="data-trust ' + trust.tone + '" role="status" aria-live="polite" aria-atomic="true" title="' + esc(trust.detail + ' · Nguồn: ' + trust.source) + '"><div class="trust-primary"><i class="trust-dot"></i><strong id="trust-status">' + esc(trust.label) + '</strong></div><span class="trust-separator" aria-hidden="true">·</span><span id="trust-time" class="trust-item">' + esc(trust.time) + '</span><span class="trust-separator" aria-hidden="true">·</span><span id="trust-count" class="trust-item">' + esc(trust.count) + '</span><span id="trust-detail" class="trust-detail">' + esc(trust.detail) + '</span><span class="trust-source">Nguồn: ' + esc(trust.source) + '</span><span class="trust-countdown">Kiểm tra tiếp: <b id="countdown">—</b></span></section>' +
      '<div class="top-actions"><button id="refresh-btn" class="icon-action refresh-btn" type="button" aria-label="' + (state.fetching ? 'Đang làm mới dữ liệu' : 'Làm mới dữ liệu') + '" title="Làm mới dữ liệu" ' + (state.fetching ? 'disabled' : '') + '>' + iconSvg('refresh') + '</button><button class="icon-action alert-action" type="button" aria-label="Cảnh báo chưa khả dụng trong staging" title="Cảnh báo chưa khả dụng trong staging" disabled>' + iconSvg('bell') + '</button><button id="theme-toggle" class="icon-action theme-toggle" type="button" aria-pressed="' + (state.theme === 'dark') + '" aria-label="Chuyển sang giao diện ' + targetTheme + '" title="Chuyển sang giao diện ' + targetTheme + '">' + iconSvg(state.theme === 'light' ? 'moon' : 'sun') + '</button><button id="account-open" class="account-action" type="button" aria-label="Mở tài khoản staging"><span class="account-avatar">' + iconSvg('user') + '</span><span><strong>Tài khoản</strong><small>' + esc(mockPlan().label) + '</small></span></button></div></div></div>' +
      '<div class="mobile-search-row"><span class="mobile-route">' + esc(routeLabel()) + '</span><form id="mobile-global-search-form" class="mobile-global-search" role="search" action="/danh-sach" method="get"><label class="sr-only" for="mobile-global-stock-search">Tìm mã cổ phiếu</label><span>' + iconSvg('search') + '</span><input id="mobile-global-stock-search" name="q" type="search" inputmode="search" autocomplete="off" placeholder="Tìm mã chứng khoán" value="' + esc(globalQuery) + '"></form></div></header>' +
      '<aside class="desktop-nav"><nav aria-label="Điều hướng chính">' + nav + '</nav><button id="desktop-account-open" class="shell-nav-link account-nav" type="button"><span class="nav-ico">' + iconSvg('user') + '</span><span class="nav-label">Tài khoản</span><small>Tài khoản</small></button><div class="nav-stage"><span>STAGING</span><small>alpha.6</small></div></aside>' +
      '<nav class="mobile-bottom" aria-label="Điều hướng chính trên thiết bị di động">' + nav + '</nav>';
  }
  var signals = [
    ["", "Tất cả tín hiệu"], ["4of4", "Đủ 4/4"], ["3plus", "Từ 3 tín hiệu"], ["2plus", "Từ 2 tín hiệu"],
    ["rvol30", "RVOL30 ≥ 200%"], ["price3", "Giá tăng ≥ 3%"], ["vol200", "KL ngày ≥ 200%"], ["abovema200", "Trên MA200"], ["missing", "Thiếu dữ liệu"]
  ];
  var sorts = [
    ["signal", "Ưu tiên tín hiệu"], ["rvol30", "RVOL30 cao nhất"], ["rvol30Asc", "RVOL30 thấp nhất"],
    ["change", "% tăng cao nhất"], ["changeAsc", "% tăng thấp nhất"], ["volume", "KL ngày cao nhất"], ["volumeAsc", "KL ngày thấp nhất"],
    ["ma10Near", "Gần MA10 nhất"], ["ma200Near", "Gần MA200 nhất"], ["symbol", "Mã A–Z"]
  ];
  function scannerStockCard(r) {
    var company = companyDisplayName(r.symbol);
    return '<article class="scanner-stock-card" data-symbol="' + esc(r.symbol) + '"><header>' + logoHtml(r.symbol, 'card-logo') + '<div><strong>' + esc(r.symbol) + '</strong><span>' + esc(r.exchange) + '</span><p>' + esc(company || 'Tên công ty đang cập nhật') + '</p></div></header><div class="scanner-card-quote"><div><small>Giá</small><strong>' + formatPrice(r.currentPrice) + '</strong></div><div><small>Thay đổi</small><strong class="' + metricClass(r.changePct) + '">' + pct(r.changePct) + '</strong></div><div><small>KL hiện tại</small><strong>' + shortVolume(r.cumVolume) + '</strong></div></div><footer>' + signalRailHtml(r) + '<span class="data-status ' + (r.hasMissingData ? 'is-warning' : '') + '">' + (r.hasMissingData ? 'Thiếu dữ liệu' : 'Dữ liệu đầy đủ') + '</span></footer></article>';
  }
  function selectOptions(items, selected) {
    return items.map(function (item) { return '<option value="' + esc(item[0]) + '" ' + (selected === item[0] ? 'selected' : '') + '>' + esc(item[1]) + '</option>'; }).join('');
  }
  function exactSearchHtml() {
    var q = state.query.trim().toUpperCase();
    if (!q) return "";
    var row = exactSearchRow();
    if (!row) return '<section class="exact-search-result empty"><strong>Không tìm thấy mã ' + esc(q) + '</strong><span>Hãy kiểm tra lại mã cổ phiếu rồi tìm lại.</span></section>';
    var company = companyDisplayName(row.symbol) || "Tên công ty đang cập nhật";
    return '<section class="exact-search-result exact-public"><div class="public-identity">' + logoHtml(row.symbol, 'card-logo') + '<div><span>Kết quả công khai</span><h2>' + esc(row.symbol) + '</h2><p>' + esc(company) + ' · ' + esc(row.exchange) + '</p></div></div><div class="exact-public-quote"><div><small>Giá hiện tại</small><strong>' + formatPrice(row.currentPrice) + '</strong></div><div><small>Thay đổi</small><strong class="' + metricClass(row.changePct) + '">' + pct(row.changePct) + '</strong></div><div><small>KL hiện tại</small><strong>' + shortVolume(row.cumVolume) + '</strong></div></div><div class="exact-public-action"><span>Fundamental Research và BCTC luôn công khai. Số liệu kỹ thuật vẫn theo phạm vi gói.</span><button type="button" class="primary-action" data-symbol="' + esc(row.symbol) + '">Mở chi tiết</button></div></section>';
  }
  function legacyListHtml() {
    var plan = mockPlan();
    var watchlist = mockWatchlistRows();
    var marketMatches = filteredRows(state.rows, false);
    var visibleMatches = plan.fullMarket ? marketMatches : filteredRows(watchlist, false);
    if (state.scannerMode === "watchlist") {
      marketMatches = filteredRows(watchlist, false);
      visibleMatches = marketMatches;
    }
    var lockedCount = state.scannerMode === "market" ? Math.max(0, marketMatches.length - visibleMatches.length) : 0;
    var pages = Math.max(1, Math.ceil(visibleMatches.length / pageSize));
    if (state.page > pages) state.page = pages;
    var shown = visibleMatches.slice((state.page - 1) * pageSize, state.page * pageSize);
    var remaining = plan.changeLimit === null ? null : Math.max(0, plan.changeLimit - state.mockChangeUsed);
    var planOptions = Object.keys(MOCK_PLAN_CONFIG).map(function (code) { return '<option value="' + code + '" ' + (state.mockPlan === code ? 'selected' : '') + '>' + esc(MOCK_PLAN_CONFIG[code].label) + '</option>'; }).join('');
    var exchanges = [["all","Tất cả sàn"],["hose","HOSE"],["hnx","HNX"],["upcom","UPCoM"]];
    var quickSignals = [["","Toàn bộ"],["4of4","4/4"],["3plus","≥3"],["rvol30","RVOL30"]].map(function (item) { return '<button type="button" class="quick-filter ' + (state.signal === item[0] ? 'active' : '') + '" data-filter="signal" data-value="' + esc(item[0]) + '" aria-pressed="' + (state.signal === item[0]) + '">' + esc(item[1]) + '</button>'; }).join('');
    var tableRows = shown.map(function (r) {
      var company = companyDisplayName(r.symbol);
      return '<tr data-symbol="' + esc(r.symbol) + '"><td class="scanner-identity"><div class="table-company">' + logoHtml(r.symbol, 'table-logo') + '<div><b>' + esc(r.symbol) + '</b><span title="' + esc(company) + '">' + esc(company || 'Tên công ty đang cập nhật') + '</span></div></div></td><td class="center muted">' + esc(r.exchange) + '</td><td class="num">' + formatPrice(r.currentPrice) + '</td><td class="num ' + metricClass(r.changePct) + '">' + pct(r.changePct) + '</td><td class="num">' + plainPct(r.dayVolumeRatioPct) + '</td><td class="num ' + metricClass(r.ma10DistancePct) + '">' + pct(r.ma10DistancePct) + '</td><td class="num ' + metricClass(r.ma200DistancePct) + '">' + pct(r.ma200DistancePct) + '</td><td class="num">' + plainPct(r.rvol30Pct) + '</td><td class="center">' + signalRailHtml(r) + '</td><td class="center"><span class="data-status ' + (r.hasMissingData ? 'is-warning' : '') + '">' + (r.hasMissingData ? 'Thiếu dữ liệu' : 'Đầy đủ') + '</span></td></tr>';
    }).join('');
    var results = shown.length ? '<div class="desktop-table panel scanner-table-panel"><div class="table-shell"><table class="scanner-table scanner-v19-table"><thead><tr><th class="scanner-identity">Công ty</th><th class="center">Sàn</th><th class="num">Giá</th><th class="num">% thay đổi</th><th class="num">KL ngày / KLTB10</th><th class="num">Cách MA10</th><th class="num">Cách MA200</th><th class="num">RVOL30</th><th class="center">Tín hiệu</th><th class="center">Dữ liệu</th></tr></thead><tbody>' + tableRows + '</tbody></table></div></div><div class="mobile-list scanner-mobile-list">' + shown.map(scannerStockCard).join('') + '</div>' : '<div class="empty scanner-empty"><strong>Chưa có mã trong quyền xem phù hợp</strong><span>Thử đổi bộ lọc hoặc chuyển sang Toàn bộ tín hiệu để xem aggregate thị trường.</span></div>';
    var lockedBlock = lockedCount ? '<section class="locked-market-summary"><div class="locked-market-icon">' + iconSvg('lock') + '</div><div><span>Ngoài quyền xem</span><strong>' + lockedCount + ' mã phù hợp đang được khóa</strong><p>Scanner vẫn quét toàn thị trường. Khối này chỉ hiển thị số lượng, không liệt kê danh tính mã bị khóa.</p></div><div class="locked-actions">' + (remaining > 0 ? '<button type="button" class="secondary-action scanner-replace-trigger">Thay một mã</button>' : '') + '<button type="button" class="primary-action scanner-upgrade-trigger">Tăng phạm vi theo dõi</button></div></section>' : '';
    var capacity = plan.fullMarket ? '<div><small>Quyền xem</small><strong>Toàn scanner universe</strong></div><div><small>Watchlist ưu tiên</small><strong>' + watchlist.length + ' mã mock</strong></div>' : '<div><small>Watchlist</small><strong>' + watchlist.length + '/' + plan.watchlistLimit + ' mã</strong></div><div><small>Lượt đổi còn lại</small><strong>' + remaining + '/' + plan.changeLimit + '</strong></div>';
    var fullCapacityActions = !plan.fullMarket && watchlist.length >= plan.watchlistLimit && remaining > 0 ? '<div class="capacity-actions"><span>Watchlist đã đủ chỗ, nhưng bạn vẫn còn lượt đổi.</span><button type="button" class="secondary-action scanner-replace-trigger">Thay một mã</button><button type="button" class="text-action scanner-upgrade-trigger">Nâng cấp</button></div>' : '';
    return '<main class="wrap scanner-main"><section class="scanner-hero"><div><span class="eyebrow">SCANNER · STAGING MOCK</span><h1>Bộ quét cổ phiếu</h1><p>Tìm mã chính xác, xem aggregate toàn thị trường hoặc phân tích các mã trong quyền xem hiện tại.</p></div><label class="mock-plan-control"><span>Gói đang xem thử</span><select id="mock-plan-select" aria-label="Chọn gói giả lập staging">' + planOptions + '</select></label><div class="scanner-head-stats"><div><small>Scanner universe</small><strong>' + state.rows.length + ' mã</strong></div><div><small>Quyền xem hiện tại</small><strong>' + (plan.fullMarket ? 'Toàn thị trường' : watchlist.length + '/' + plan.viewLimit + ' mã') + '</strong></div><div><small>Gói</small><strong>' + esc(plan.label) + '</strong></div></div></section>' + secondarySourceWarningHtml(false) +
      '<section class="scanner-command panel"><div class="scanner-mode" role="group" aria-label="Phạm vi kết quả"><button type="button" data-scanner-mode="market" class="' + (state.scannerMode === 'market' ? 'active' : '') + '" aria-pressed="' + (state.scannerMode === 'market') + '">Toàn bộ tín hiệu</button><button type="button" data-scanner-mode="watchlist" class="' + (state.scannerMode === 'watchlist' ? 'active' : '') + '" aria-pressed="' + (state.scannerMode === 'watchlist') + '">Watchlist của tôi</button></div><div class="scanner-search-row"><div class="search-box"><span class="search-icon" aria-hidden="true">⌕</span><input id="stock-search" type="text" inputmode="search" autocomplete="off" autocorrect="off" autocapitalize="characters" spellcheck="false" aria-label="Tìm chính xác mã cổ phiếu" placeholder="Nhập chính xác mã cổ phiếu" value="' + esc(state.query) + '"></div><button id="search-btn" class="search-btn" type="button">Tìm mã</button><button id="clear-btn" class="clear-btn" type="button">Xóa</button><button id="scanner-filter-toggle" class="filter-toggle" type="button" aria-expanded="' + state.scannerFiltersOpen + '" aria-controls="scanner-filter-panel">Bộ lọc</button></div>' +
      '<div class="quick-filters" aria-label="Bộ lọc nhanh">' + quickSignals + '</div><div id="scanner-filter-panel" class="scanner-filter-controls ' + (state.scannerFiltersOpen ? 'is-open' : '') + '"><label><span>Sàn giao dịch</span><select data-select-filter="exchange">' + selectOptions(exchanges, state.exchange) + '</select></label><label><span>Tín hiệu</span><select data-select-filter="signal">' + selectOptions(signals, state.signal) + '</select></label><label><span>Sắp xếp</span><select data-select-filter="sort">' + selectOptions(sorts, state.sort) + '</select></label><button id="reset-filters" type="button" class="clear-filters">Đặt lại bộ lọc</button></div></section>' +
      exactSearchHtml() + '<section class="watchlist-capacity panel"><div class="capacity-values">' + capacity + '</div>' + fullCapacityActions + '</section><div class="scanner-result-head"><div><span>' + (state.scannerMode === 'market' ? 'Kết quả toàn thị trường' : 'Kết quả Watchlist') + '</span><strong>Tổng ' + marketMatches.length + ' · Hiện ' + visibleMatches.length + ' · Khóa ' + lockedCount + '</strong></div><p>' + (state.query ? 'Kết quả tìm chính xác ở phía trên; bảng vẫn giữ bộ lọc thị trường.' : 'Bộ lọc aggregate không làm thay đổi scanner universe.') + '</p></div>' + results + lockedBlock +
      (pages > 1 ? '<div class="pager"><button id="prev-page" type="button" ' + (state.page === 1 ? 'disabled' : '') + '>Trang trước</button><span>Trang ' + state.page + '/' + pages + '</span><button id="next-page" type="button" ' + (state.page === pages ? 'disabled' : '') + '>Trang sau</button></div>' : '') + '<p class="disclaimer">STAGING MOCK · Frontend không phải security boundary. Công cụ quét dữ liệu, không đưa ra khuyến nghị mua/bán.</p></main>';
  }
  function listHtml() {
    var plan = mockPlan();
    var watchlist = mockWatchlistRows();
    var marketMatches = filteredRows(state.rows, false);
    var visibleMatches = plan.fullMarket ? marketMatches : filteredRows(watchlist, false);
    if (state.scannerMode === "watchlist") {
      marketMatches = filteredRows(watchlist, false);
      visibleMatches = marketMatches;
    }
    var lockedCount = state.scannerMode === "market" ? Math.max(0, marketMatches.length - visibleMatches.length) : 0;
    var pages = Math.max(1, Math.ceil(visibleMatches.length / pageSize));
    if (state.page > pages) state.page = pages;
    var shown = visibleMatches.slice((state.page - 1) * pageSize, state.page * pageSize);
    var remaining = plan.changeLimit === null ? null : Math.max(0, plan.changeLimit - state.mockChangeUsed);
    var planOptions = Object.keys(MOCK_PLAN_CONFIG).map(function (code) { return '<option value="' + code + '" ' + (state.mockPlan === code ? 'selected' : '') + '>' + esc(MOCK_PLAN_CONFIG[code].label) + '</option>'; }).join('');
    var exchanges = [["all","Tất cả sàn"],["hose","HOSE"],["hnx","HNX"],["upcom","UPCoM"]];
    var quickSignals = [["","Toàn bộ"],["4of4","4/4"],["3plus","≥3"],["rvol30","RVOL30"]].map(function (item) { return '<button type="button" class="quick-filter ' + (state.signal === item[0] ? 'active' : '') + '" data-filter="signal" data-value="' + esc(item[0]) + '" aria-pressed="' + (state.signal === item[0]) + '">' + esc(item[1]) + '</button>'; }).join('');
    var tableRows = shown.map(function (r) {
      var company = companyDisplayName(r.symbol) || "Tên công ty đang cập nhật";
      return '<tr data-symbol="' + esc(r.symbol) + '"><td><div class="scanner-company">' + logoHtml(r.symbol, 'table-logo') + '<div><strong>' + esc(r.symbol) + '</strong><span title="' + esc(company) + '">' + esc(company) + '</span><small>' + esc(r.exchange) + '</small></div></div></td><td class="num"><strong>' + formatPrice(r.currentPrice) + '</strong></td><td class="num ' + metricClass(r.changePct) + '"><strong>' + pct(r.changePct) + '</strong></td><td class="num"><strong>' + shortVolume(r.cumVolume) + '</strong></td><td>' + signalRailHtml(r) + '</td></tr>';
    }).join('');
    var results = shown.length ? '<div class="scanner-table-wrap"><table class="lovable-scanner-table"><colgroup><col class="col-identity"><col class="col-price"><col class="col-change"><col class="col-volume"><col class="col-ccc"></colgroup><thead><tr><th>Công ty</th><th class="num">Giá</th><th class="num">Thay đổi</th><th class="num">KL hiện tại</th><th>CCC</th></tr></thead><tbody>' + tableRows + '</tbody></table></div><div class="scanner-mobile-list">' + shown.map(scannerStockCard).join('') + '</div>' : '<div class="empty-state"><strong>Không có mã phù hợp trong phạm vi</strong><span>Thử đổi bộ lọc hoặc chọn Toàn bộ tín hiệu.</span></div>';
    var lockedBlock = lockedCount ? '<section class="locked-remainder"><div class="locked-remainder-icon">' + iconSvg('lock') + '</div><div><span>NGOÀI PHẠM VI</span><strong>' + lockedCount + ' mã phù hợp đang được bảo vệ</strong><p>Scanner vẫn quét toàn thị trường. Danh tính và Signal Rail của nhóm này không được liệt kê.</p></div><div class="locked-actions">' + (remaining > 0 ? '<button type="button" class="secondary-action scanner-replace-trigger">Thay một mã</button>' : '') + '<button type="button" class="primary-action scanner-upgrade-trigger">Mở rộng phạm vi</button></div></section>' : '';
    var contextBody = '<dl class="rail-kv"><div><dt>Khớp bộ lọc</dt><dd>' + marketMatches.length + '</dd></div><div><dt>Trong phạm vi</dt><dd>' + visibleMatches.length + '</dd></div><div><dt>Ngoài phạm vi</dt><dd>' + lockedCount + '</dd></div><div><dt>Đang hiển thị</dt><dd>' + shown.length + '</dd></div></dl><p class="rail-note">' + iconSvg('shield') + '<span>Bộ lọc frontend không làm thay đổi scanner universe.</span></p>';
    var context = railCardHtml("Ngữ cảnh kết quả", state.scannerMode === "market" ? "Toàn thị trường" : "Watchlist", contextBody, "scanner-context-card");
    return '<main class="wrap scanner-main lovable-scanner"><section class="page-heading"><div><span class="eyebrow">CCC TECHNICAL INTELLIGENCE</span><h1>Bộ quét cổ phiếu</h1><p>Tìm kiếm, lọc và sắp xếp dữ liệu thật; tín hiệu kỹ thuật chỉ hiển thị trong phạm vi gói.</p></div><div class="page-heading-meta"><span>Scanner · ' + state.rows.length + ' mã</span><label><span>Gói staging</span><select id="mock-plan-select" aria-label="Chọn gói giả lập staging">' + planOptions + '</select></label></div></section>' + secondarySourceWarningHtml(false) +
      '<section class="scanner-controls panel-anatomy"><div class="scanner-mode" role="group" aria-label="Phạm vi kết quả"><button type="button" data-scanner-mode="market" class="' + (state.scannerMode === 'market' ? 'active' : '') + '" aria-pressed="' + (state.scannerMode === 'market') + '">Toàn bộ tín hiệu</button><button type="button" data-scanner-mode="watchlist" class="' + (state.scannerMode === 'watchlist' ? 'active' : '') + '" aria-pressed="' + (state.scannerMode === 'watchlist') + '">Watchlist của tôi</button></div><div class="scanner-search-row"><div class="search-box"><span class="search-icon" aria-hidden="true">' + iconSvg('search') + '</span><input id="stock-search" type="search" inputmode="search" autocomplete="off" autocorrect="off" autocapitalize="characters" spellcheck="false" aria-label="Tìm chính xác mã cổ phiếu" placeholder="Nhập chính xác mã cổ phiếu" value="' + esc(state.query) + '"></div><button id="search-btn" class="primary-action" type="button">Tìm mã</button><button id="clear-btn" class="secondary-action" type="button">Xóa</button><button id="scanner-filter-toggle" class="filter-toggle" type="button" aria-expanded="' + state.scannerFiltersOpen + '" aria-controls="scanner-filter-panel">Bộ lọc</button></div><div class="quick-filters" aria-label="Bộ lọc nhanh">' + quickSignals + '</div><div id="scanner-filter-panel" class="scanner-filter-controls ' + (state.scannerFiltersOpen ? 'is-open' : '') + '"><label><span>Sàn giao dịch</span><select data-select-filter="exchange">' + selectOptions(exchanges, state.exchange) + '</select></label><label><span>Tín hiệu</span><select data-select-filter="signal">' + selectOptions(signals, state.signal) + '</select></label><label><span>Sắp xếp</span><select data-select-filter="sort">' + selectOptions(sorts, state.sort) + '</select></label><button id="reset-filters" type="button" class="secondary-action clear-filters">Đặt lại</button></div></section>' +
      exactSearchHtml() + '<section class="scanner-results panel-anatomy"><header class="section-bar"><div><h2>' + (state.scannerMode === 'market' ? 'Kết quả toàn thị trường' : 'Kết quả Watchlist') + '</h2><span>Tổng ' + marketMatches.length + ' · Trong phạm vi ' + visibleMatches.length + ' · Khóa ' + lockedCount + '</span></div><small>Trang ' + state.page + '/' + pages + '</small></header>' + results + '</section>' + lockedBlock + (pages > 1 ? '<div class="pager"><button id="prev-page" type="button" ' + (state.page === 1 ? 'disabled' : '') + '>Trang trước</button><span>Trang ' + state.page + '/' + pages + '</span><button id="next-page" type="button" ' + (state.page === pages ? 'disabled' : '') + '>Trang sau</button></div>' : '') + commonContextRailHtml(context) + '<p class="disclaimer">STAGING · Frontend không phải security boundary. Công cụ không đưa ra khuyến nghị mua/bán.</p></main>';
  }
  function overviewHtml() {
    var plan = mockPlan();
    var watchlist = mockWatchlistRows();
    var inScope = watchlist.filter(function (row) { return row.signalCount >= 2; }).sort(priority).slice(0, 8);
    var summary2 = discoveryData("2plus");
    var density = [
      ["4of4", "Đạt 4/4", discoveryRows("4of4").length, "Hội tụ mạnh"],
      ["3plus", "Từ 3 tín hiệu", discoveryRows("3plus").length, "Đang hội tụ"],
      ["2plus", "Từ 2 tín hiệu", discoveryRows("2plus").length, "Đang hình thành"],
      ["rvol30", "RVOL30 nổi bật", discoveryRows("rvol30").length, "Dòng tiền tương đối"]
    ].map(function (metric) {
      var data = discoveryData(metric[0]);
      return '<div class="density-tile"><span>' + esc(metric[1]) + '</span><strong>' + metric[2] + '<small> mã</small></strong><div><em>' + esc(metric[3]) + '</em><b>' + data.visibleCount + ' trong phạm vi</b></div></div>';
    }).join('');
    var planOptions = Object.keys(MOCK_PLAN_CONFIG).map(function (code) { return '<option value="' + code + '" ' + (state.mockPlan === code ? 'selected' : '') + '>' + esc(MOCK_PLAN_CONFIG[code].label) + '</option>'; }).join('');
    var legendCard = railCardHtml("CCC Signal Rail", "4 phân đoạn", signalLegendHtml(), "signal-legend-card");
    return '<main class="wrap overview-main lovable-overview">' +
      '<section class="page-heading"><div><span class="eyebrow">MARKET INTELLIGENCE</span><h1>Tổng quan</h1><p>Nhịp thị trường, mật độ hội tụ tín hiệu và lực dòng tiền trong phạm vi của bạn.</p></div><div class="page-heading-meta"><span>Scanner · ' + state.rows.length + ' mã</span><label><span>Gói staging</span><select id="mock-plan-select" aria-label="Chọn gói giả lập staging">' + planOptions + '</select></label></div></section>' +
      secondarySourceWarningHtml(false) + marketPulseHtml() +
      '<section class="signal-density panel-anatomy"><header class="section-bar"><div><h2>Mật độ tín hiệu hôm nay</h2><span>Đếm trên toàn scanner universe</span></div><small>Ngoài phạm vi chỉ hiển thị số lượng</small></header><div class="density-grid">' + density + '</div></section>' +
      '<section class="in-scope-results panel-anatomy"><header class="section-bar"><div><h2>Tín hiệu trong phạm vi của bạn</h2><span>Danh tính chỉ hiển thị khi thuộc phạm vi gói ' + esc(plan.label) + '</span></div><small>' + inScope.length + ' mã hiển thị</small></header><div class="overview-row-head"><span>Công ty</span><span>Giá / thay đổi</span><span>Khối lượng</span><span>CCC</span></div><div class="overview-rows">' + (inScope.length ? inScope.map(overviewStockRowHtml).join('') : '<div class="empty-state"><strong>Chưa có mã đạt từ 2 tín hiệu</strong><span>Thử kiểm tra lại khi snapshot thị trường được cập nhật.</span></div>') + '</div></section>' +
      (summary2.lockedCount ? '<section class="locked-remainder"><div class="locked-remainder-icon">' + iconSvg('lock') + '</div><div><span>NGOÀI PHẠM VI</span><strong>' + summary2.lockedCount + ' mã đạt từ 2 tín hiệu đang được bảo vệ</strong><p>Danh tính và hình dạng tín hiệu không được liệt kê. Scanner universe vẫn giữ nguyên.</p></div><button type="button" class="secondary-action scanner-upgrade-trigger">Mở rộng phạm vi</button></section>' : '') +
      commonContextRailHtml(legendCard) +
      '<p class="disclaimer">STAGING · Dữ liệu thật, entitlement frontend chỉ phục vụ duyệt UX. Công cụ không đưa ra khuyến nghị mua/bán.</p></main>';
  }
  function membershipDialogHtml() {
    if (!state.discoveryGroup) return '<div id="membership-dialog" class="membership-backdrop" hidden></div>';
    var plan=mockPlan();
    var data=discoveryData(state.discoveryGroup);
    var remaining=plan.changeLimit===null?null:Math.max(0,plan.changeLimit-state.mockChangeUsed);
    if (state.upsellOpen) {
      return '<div id="membership-dialog" class="membership-backdrop"><section class="membership-dialog upsell-dialog" role="dialog" aria-modal="true" aria-labelledby="upsell-title"><div class="membership-dialog-head"><div><span class="staging-badge">STAGING PREVIEW</span><h2 id="upsell-title">Bạn đang dùng '+esc(plan.label)+'</h2></div><button id="membership-close" class="dialog-close" type="button" aria-label="Đóng xem trước nâng cấp">×</button></div><div class="membership-dialog-body"><div class="current-plan-summary"><div><small>Quyền xem hiện tại</small><strong>'+(plan.fullMarket?'Toàn scanner universe':plan.viewLimit+' mã')+'</strong></div><div><small>Lượt đổi còn lại</small><strong>'+(remaining===null?'Không giới hạn':remaining+'/'+plan.changeLimit)+'</strong></div><div><small>Email / Telegram</small><strong>'+(plan.email&&plan.telegram?'Có / Có':'Không / Không')+'</strong></div></div><article class="plus-preview"><div class="plus-preview-head"><div><span class="popular-badge">Phổ biến nhất</span><h3>Plus</h3></div><strong>300.000đ<span>/tháng</span></strong></div><ul><li>50 mã theo dõi chi tiết</li><li>50 lượt đổi mỗi chu kỳ</li><li>Cảnh báo Email</li><li>Cảnh báo Telegram</li></ul><p>Tăng phạm vi theo dõi; không thay đổi scanner universe.</p></article><div class="preview-actions"><button id="membership-back" type="button" class="secondary-action">Quay lại nhóm tín hiệu</button><button type="button" class="preview-disabled" disabled>Thanh toán chưa bật trong staging</button></div></div></section></div>';
    }
    var visiblePreview=data.visibleItems.slice(0,8);
    var hiddenVisible=Math.max(0,data.visibleCount-visiblePreview.length);
    var placeholderCount=data.lockedCount>8?4:data.lockedCount;
    var placeholders=Array.from({length:placeholderCount},function(){return '<span class="locked-placeholder">'+iconSvg('lock')+'<b>•••</b></span>';}).join('');
    return '<div id="membership-dialog" class="membership-backdrop"><section class="membership-dialog discovery-dialog" role="dialog" aria-modal="true" aria-labelledby="discovery-dialog-title"><div class="membership-dialog-head"><div><span class="staging-badge">STAGING · '+esc(plan.label)+'</span><h2 id="discovery-dialog-title">'+data.totalCount+' '+esc(discoveryLabel(state.discoveryGroup))+'</h2></div><button id="membership-close" class="dialog-close" type="button" aria-label="Đóng nhóm tín hiệu">×</button></div><div class="membership-dialog-body"><div class="coverage-summary"><div><small>Tổng nhóm</small><strong>'+data.totalCount+'</strong></div><div><small>Bạn xem được</small><strong>'+data.visibleCount+'/'+data.totalCount+'</strong></div><div><small>Ngoài quyền xem</small><strong>'+data.lockedCount+'</strong></div></div><section class="visible-entitlement"><h3>Trong quyền xem của bạn</h3>'+(visiblePreview.length?'<div class="dialog-visible-grid">'+visiblePreview.map(overviewStockCard).join('')+'</div>'+(hiddenVisible?'<p class="preview-note">+ '+hiddenVisible+' mã khác cũng nằm trong quyền xem.</p>':''):'<div class="empty compact-empty">Watchlist hiện chưa có mã nào trong nhóm này.</div>')+'</section>'+(data.lockedCount?'<button type="button" class="locked-area locked-trigger"><span class="locked-area-title">'+iconSvg('lock')+' Ngoài quyền xem</span><span class="locked-placeholder-grid">'+placeholders+'</span>'+(data.lockedCount>8?'<strong>+ '+(data.lockedCount-placeholderCount)+' mã khác ngoài quyền xem</strong>':'<strong>'+data.lockedCount+' mã ngoài quyền xem</strong>')+'<small>Chọn để xem preview gói Plus</small></button>':'<div class="all-unlocked">'+iconSvg('shield')+'<div><strong>Toàn bộ nhóm đang nằm trong quyền xem mock</strong><span>Full Market không khóa market detail trong trạng thái staging này.</span></div></div>')+'</div></section></div>';
  }
  function scannerActionDialogHtml() {
    if (!state.scannerDialog) return '<div id="scanner-action-dialog" class="membership-backdrop" hidden></div>';
    var plan = mockPlan();
    var watchlist = mockWatchlistRows();
    var remaining = plan.changeLimit === null ? null : Math.max(0, plan.changeLimit - state.mockChangeUsed);
    var target = state.scannerDialogSymbol ? ' ' + esc(state.scannerDialogSymbol) : '';
    var content = state.scannerDialog === "replace" ?
      '<div class="scanner-dialog-copy"><h3>Thay một mã trong Watchlist</h3><p>Watchlist đã đủ <strong>' + watchlist.length + '/' + plan.watchlistLimit + ' mã</strong>. Để mở quyền xem' + target + ', hãy chọn một mã hiện tại để thay.</p><div class="capacity-values"><div><small>Watchlist</small><strong>' + watchlist.length + '/' + plan.watchlistLimit + ' mã</strong></div><div><small>Lượt đổi còn lại</small><strong>' + remaining + '/' + plan.changeLimit + '</strong></div></div><p class="mock-notice">Xác nhận thay mã sẽ dùng 1 lượt đổi. Luồng này chỉ là preview UX; staging chưa ghi thay đổi.</p><div class="preview-actions"><button id="scanner-action-close-bottom" type="button" class="secondary-action">Để sau</button><button type="button" class="preview-disabled" disabled>Thay mã chưa bật trong staging</button></div></div>' :
      '<div class="scanner-dialog-copy"><h3>Tăng phạm vi theo dõi</h3><p>Bạn đang dùng <strong>' + esc(plan.label) + '</strong>. Nâng cấp tăng số mã được xem chi tiết; scanner universe không thay đổi.</p><article class="plus-preview"><div class="plus-preview-head"><div><span class="popular-badge">Phổ biến nhất</span><h3>Plus</h3></div><strong>300.000đ<span>/tháng</span></strong></div><ul><li>50 mã theo dõi chi tiết</li><li>50 lượt đổi mỗi chu kỳ</li><li>Cảnh báo Email</li><li>Cảnh báo Telegram</li></ul><p>Tín hiệu tìm đến bạn. Không phải cam kết lợi nhuận.</p></article><div class="preview-actions"><button id="scanner-action-close-bottom" type="button" class="secondary-action">Để sau</button><button type="button" class="preview-disabled" disabled>Thanh toán chưa bật trong staging</button></div></div>';
    return '<div id="scanner-action-dialog" class="membership-backdrop"><section class="membership-dialog scanner-action-dialog" role="dialog" aria-modal="true" aria-labelledby="scanner-action-title"><div class="membership-dialog-head"><div><span class="staging-badge">STAGING PREVIEW</span><h2 id="scanner-action-title">' + (state.scannerDialog === 'replace' ? 'Quản lý quyền xem' : 'Xem gói nâng cấp') + '</h2></div><button id="scanner-action-close" class="dialog-close" type="button" aria-label="Đóng">×</button></div><div class="membership-dialog-body">' + content + '</div></section></div>';
  }
  function legacyDialogHtml() {
    var r = state.selected;
    if (!r) return '<div id="dialog" class="dialog-backdrop" hidden></div>';
    var f=financialBySymbol(r.symbol), score=f?financialScore(f):null;
    var details = [["Sàn",r.exchange],["Giá hiện tại",formatPrice(r.currentPrice)],["% thay đổi",pct(r.changePct)],["KL lũy kế",shortVolume(r.cumVolume)],["KLTB10",shortVolume(r.avgVolume10)],["KL ngày / KLTB10",plainPct(r.dayVolumeRatioPct)],["MA10",formatPrice(r.ma10)],["Cách MA10",pct(r.ma10DistancePct)],["MA200",formatPrice(r.ma200)],["Cách MA200",pct(r.ma200DistancePct)],["RVOL30",plainPct(r.rvol30Pct)],["Số phiên RVOL30",r.rvol30Sessions + '/10']];
    var fund='';
    if(f){
      var parts=score.parts.map(function(p){return '<div class="score-part"><span><b>'+esc(p.name)+'</b><small>'+esc(p.detail||'')+'</small></span><strong>'+p.earned+'/'+p.max+'</strong></div>';}).join('');
      var badges=score.badges.map(function(x){return '<span class="analysis-badge">'+esc(x)+'</span>';}).join('');
      var qs=state.quarterlyBySymbol[r.symbol]||[];
      var qhtml=state.quarterlyLoading[r.symbol]?'<div class="quarter-loading">Đang tải lịch sử quý…</div>':state.quarterlyError[r.symbol]?'<div class="quarter-loading">'+esc(state.quarterlyError[r.symbol])+'</div>':qs.length?'<div class="quarter-table"><table><thead><tr><th>Kỳ</th><th class="num">Doanh thu / thu nhập</th><th class="num">Lợi nhuận sau thuế</th><th class="num">Tăng so cùng kỳ</th><th class="num">ROE</th></tr></thead><tbody>'+qs.slice(0,9).map(function(q){return '<tr><td>'+esc(q.period)+'</td><td class="num">'+moneyBil(q.income_bil_vnd)+'</td><td class="num">'+moneyBil(q.parent_net_profit_bil_vnd||q.net_profit_bil_vnd)+'</td><td class="num '+metricClass(num(q.profit_yoy_pct))+'">'+pct(num(q.profit_yoy_pct))+'</td><td class="num">'+pct(num(q.roea_pct))+'</td></tr>';}).join('')+'</tbody></table></div>':'<div class="quarter-loading">Chưa có lịch sử quý.</div>';
      fund='<section class="dialog-section"><div class="fund-summary"><div><span class="eyebrow">ĐIỂM CƠ BẢN</span><div class="big-score '+scoreClass(score)+'">'+esc(score.label)+'</div><p>Độ phủ chấm điểm: '+score.coverage+'% · '+esc(f.website_group||'—')+'</p></div><div class="fund-kpis"><div><small>Lợi nhuận sau thuế<br>so với cùng kỳ</small><b class="'+metricClass(num(f.profit_yoy_pct))+'">'+pct(num(f.profit_yoy_pct))+'</b></div><div><small>ROE<br>Lợi nhuận / vốn chủ</small><b>'+pct(num(f.roea_pct))+'</b></div><div><small>P/E<br>Giá / lợi nhuận</small><b>'+(num(f.pe)===null?'—':num(f.pe).toFixed(2)+'x')+'</b></div><div><small>P/B<br>Giá / giá trị sổ sách</small><b>'+(num(f.pb)===null?'—':num(f.pb).toFixed(2)+'x')+'</b></div></div></div><div class="analysis-badges">'+badges+'</div><div class="score-parts">'+parts+'</div></section><section class="dialog-section"><div class="section-title"><div><h3>Lịch sử tài chính theo quý</h3><p>Lịch sử tài chính theo quý đã lưu trong hệ thống.</p></div></div>'+qhtml+'</section>';
    } else fund='<section class="dialog-section"><div class="quarter-loading">Mã này chưa có dữ liệu cơ bản trong financial_latest.</div></section>';
    var m=state.metadataBySymbol[r.symbol]||{};
    var companyFull=m.company_name||"";
    var companyShort=m.display_name||companyFull||"";
    var groupName=(f&&f.website_group)||m.website_group||"";
    var companyHeader=(companyFull||companyShort)?'<div class="dialog-company"><span class="company-full">'+esc(companyFull||companyShort)+'</span><span class="company-short">'+esc(companyShort||companyFull)+'</span>'+(groupName?'<small>'+esc(groupName)+'</small>':'')+'</div>':(groupName?'<div class="dialog-company"><small>'+esc(groupName)+'</small></div>':'');
    var vietstockBctcUrl='https://finance.vietstock.vn/'+encodeURIComponent(String(r.symbol||'').toUpperCase())+'/tai-chinh.htm?tab=BCTT';
    var bctc='<section class="dialog-section bctc-access bctc-vietstock"><div class="bctc-copy"><span class="eyebrow">BÁO CÁO TÀI CHÍNH</span><h3>Tài liệu của '+esc(r.symbol)+'</h3><p>Xem Báo cáo tài chính và các tài liệu công bố doanh nghiệp trên VietstockFinance.</p><div class="bctc-source">Nguồn tài liệu: <strong>VietstockFinance</strong></div></div><a class="bctc-open" href="'+esc(vietstockBctcUrl)+'" target="_blank" rel="noopener noreferrer">Xem BCTC trên Vietstock ↗</a></section>';
    return '<div id="dialog" class="dialog-backdrop"><section class="dialog dialog-wide" role="dialog" aria-modal="true" aria-label="Chi tiết ' + esc(r.symbol) + '"><div class="dialog-head"><div class="dialog-symbol">' + logoHtml(r.symbol, 'dialog-logo') + '<div class="dialog-title-block"><div class="dialog-title-row"><h2>' + esc(r.symbol) + ' · <span class="signal-pill ' + signalClass(r.signalCount) + '">' + r.signalCount + '/4</span></h2>'+companyHeader+'</div></div></div><button id="dialog-close" class="dialog-close" type="button" aria-label="Đóng">×</button></div><div class="dialog-body"><section class="dialog-section"><div class="section-title"><div><h3>Tín hiệu kỹ thuật</h3><p>Snapshot gần nhất của hệ thống scanner.</p></div></div><div class="detail-grid">' + details.map(function(d){return '<div class="detail"><small>'+esc(d[0])+'</small><b>'+esc(d[1])+'</b></div>';}).join('') + '</div></section>'+fund+bctc+'</div></section></div>';
  }
  function detailMetricHtml(label, value, tone) {
    return '<div class="detail-metric"><small>' + esc(label) + '</small><strong class="' + esc(tone || '') + '">' + esc(value) + '</strong></div>';
  }
  function dialogHtml() {
    var r = state.selected;
    if (!r) return '<div id="dialog" class="dialog-backdrop" hidden></div>';
    var f = financialBySymbol(r.symbol);
    var score = f ? financialScore(f) : null;
    var meta = state.metadataBySymbol[r.symbol] || {};
    var company = meta.company_name || meta.display_name || "Tên công ty đang cập nhật";
    var groupName = (f && f.website_group) || meta.website_group || "";
    var entitled = isMockEntitled(r);
    var tabs = [["overview","Tổng quan"],["technical","Kỹ thuật"],["fundamental","Cơ bản"],["financials","BCTC"]].map(function (tab) { return '<button type="button" role="tab" data-detail-tab="' + tab[0] + '" aria-selected="' + (state.detailTab === tab[0]) + '" class="' + (state.detailTab === tab[0] ? 'active' : '') + '">' + tab[1] + (tab[0] === 'technical' && !entitled ? '<span class="tab-lock">' + iconSvg('lock') + '</span>' : '') + '</button>'; }).join('');
    var content = '';
    if (state.detailTab === "overview") {
      content = '<section class="detail-panel"><header><h3>Báo giá công khai</h3><span>Luôn hiển thị cho mọi mã</span></header><div class="detail-metric-grid">' + detailMetricHtml("Sàn", r.exchange) + detailMetricHtml("Giá hiện tại", formatPrice(r.currentPrice)) + detailMetricHtml("% thay đổi", pct(r.changePct), metricClass(r.changePct)) + detailMetricHtml("KL hiện tại", shortVolume(r.cumVolume)) + '</div></section>' +
        '<section class="detail-panel"><header><h3>Bối cảnh cơ bản</h3><span>Public Fundamental Research</span></header>' + (f ? '<div class="detail-metric-grid">' + detailMetricHtml("Điểm cơ bản", score.label) + detailMetricHtml("Ngành", f.website_group || "—") + detailMetricHtml("P/E", num(f.pe) === null ? "—" : num(f.pe).toFixed(2) + "x") + detailMetricHtml("ROE", pct(num(f.roea_pct))) + '</div>' : '<div class="empty-state compact"><strong>Chưa có dữ liệu cơ bản</strong><span>financial_latest chưa có bản ghi cho mã này.</span></div>') + '</section><div class="detail-notice">' + iconSvg('lock') + '<span>MA200, KLTB10, RVOL30 và CCC Signal Rail nằm trong tab <b>Kỹ thuật</b>.</span></div>';
    } else if (state.detailTab === "technical") {
      if (!entitled) {
        content = '<section class="technical-locked"><div>' + iconSvg('lock') + '</div><strong>CCC Technical Intelligence bị khóa</strong><p>Mã này nằm ngoài phạm vi gói ' + esc(mockPlan().label) + '. Khi được mở, cả bốn tín hiệu và số liệu kỹ thuật sẽ hiển thị đầy đủ.</p><button type="button" class="primary-action scanner-upgrade-trigger">Mở rộng phạm vi</button></section>';
      } else {
        var techMetrics = [
          ["Giá tăng ≥ 3%", pct(r.changePct), r.signalPrice3pct],
          ["KL ngày ≥ 200% KLTB10", plainPct(r.dayVolumeRatioPct), r.signalVolume200pct],
          ["Trên MA200", pct(r.ma200DistancePct), r.signalAboveMa200],
          ["RVOL30 ≥ 200%", plainPct(r.rvol30Pct), r.signalRvol30_200pct]
        ].map(function (item) { return '<div class="technical-signal ' + (item[2] ? 'is-on' : '') + '"><header><span>' + esc(item[0]) + '</span><b>' + (item[2] ? 'Đạt' : 'Chưa đạt') + '</b></header><strong>' + esc(item[1]) + '</strong></div>'; }).join('');
        content = '<section class="detail-panel"><header><h3>CCC Signal Rail</h3><span>Trạng thái snapshot hiện tại</span></header><div class="detail-rail-hero">' + signalRailHtml(r) + '</div><div class="technical-signal-grid">' + techMetrics + '</div></section><section class="detail-panel"><header><h3>Số liệu kỹ thuật</h3><span>MA10 chỉ là tham chiếu, không phải tín hiệu</span></header><div class="detail-metric-grid">' + detailMetricHtml("KLTB10", shortVolume(r.avgVolume10)) + detailMetricHtml("KL ngày / KLTB10", plainPct(r.dayVolumeRatioPct)) + detailMetricHtml("MA10 tham chiếu", formatPrice(r.ma10)) + detailMetricHtml("Cách MA10", pct(r.ma10DistancePct), metricClass(r.ma10DistancePct)) + detailMetricHtml("MA200", formatPrice(r.ma200)) + detailMetricHtml("Cách MA200", pct(r.ma200DistancePct), metricClass(r.ma200DistancePct)) + detailMetricHtml("RVOL30", plainPct(r.rvol30Pct)) + detailMetricHtml("Số phiên RVOL30", r.rvol30Sessions + "/10") + '</div></section>';
      }
    } else if (state.detailTab === "fundamental") {
      if (!f) content = '<div class="empty-state"><strong>Chưa có Fundamental Research</strong><span>Dữ liệu cơ bản cho mã này chưa có trong financial_latest.</span></div>';
      else {
        var parts = score.parts.map(function (part) { return '<div class="score-part"><span><b>' + esc(part.name) + '</b><small>' + esc(part.detail || '') + '</small></span><strong>' + part.earned + '/' + part.max + '</strong></div>'; }).join('');
        var badges = score.badges.map(function (badge) { return '<span class="analysis-badge">' + esc(badge) + '</span>'; }).join('');
        content = '<section class="detail-panel"><header><h3>Nghiên cứu cơ bản</h3><span>Công khai cho mọi mã, mọi gói</span></header><div class="fundamental-hero"><div><small>Điểm cơ bản</small><strong class="' + scoreClass(score) + '">' + esc(score.label) + '</strong><span>Độ phủ ' + score.coverage + '%</span></div><div class="detail-metric-grid">' + detailMetricHtml("LNST so cùng kỳ", pct(num(f.profit_yoy_pct)), metricClass(num(f.profit_yoy_pct))) + detailMetricHtml("ROE", pct(num(f.roea_pct))) + detailMetricHtml("P/E", num(f.pe) === null ? "—" : num(f.pe).toFixed(2) + "x") + detailMetricHtml("P/B", num(f.pb) === null ? "—" : num(f.pb).toFixed(2) + "x") + '</div></div><div class="analysis-badges">' + badges + '</div><div class="score-parts">' + parts + '</div></section>';
      }
    } else {
      var quarters = state.quarterlyBySymbol[r.symbol] || [];
      var qhtml = state.quarterlyLoading[r.symbol] ? '<div class="empty-state compact"><strong>Đang tải lịch sử quý…</strong></div>' : state.quarterlyError[r.symbol] ? '<div class="source-warning"><strong>Không tải được BCTC</strong><span>' + esc(state.quarterlyError[r.symbol]) + '</span></div>' : quarters.length ? '<div class="quarter-table"><table><thead><tr><th>Kỳ</th><th class="num">Doanh thu / thu nhập</th><th class="num">Lợi nhuận sau thuế</th><th class="num">Tăng so cùng kỳ</th><th class="num">ROE</th></tr></thead><tbody>' + quarters.slice(0,9).map(function (q) { return '<tr><td>' + esc(q.period) + '</td><td class="num">' + moneyBil(q.income_bil_vnd) + '</td><td class="num">' + moneyBil(q.parent_net_profit_bil_vnd || q.net_profit_bil_vnd) + '</td><td class="num ' + metricClass(num(q.profit_yoy_pct)) + '">' + pct(num(q.profit_yoy_pct)) + '</td><td class="num">' + pct(num(q.roea_pct)) + '</td></tr>'; }).join('') + '</tbody></table></div>' : '<div class="empty-state compact"><strong>Chưa có lịch sử quý</strong><span>financial_quarterly chưa trả về bản ghi.</span></div>';
      var bctcUrl = 'https://finance.vietstock.vn/' + encodeURIComponent(String(r.symbol || '').toUpperCase()) + '/tai-chinh.htm?tab=BCTT';
      content = '<section class="detail-panel"><header><h3>Báo cáo tài chính</h3><span>Dữ liệu quý đã lưu trong hệ thống</span></header>' + qhtml + '<div class="bctc-action"><div><strong>Tài liệu công bố doanh nghiệp</strong><span>Nguồn ngoài: VietstockFinance</span></div><a href="' + esc(bctcUrl) + '" target="_blank" rel="noopener noreferrer">Xem BCTC trên Vietstock ' + iconSvg('arrow') + '</a></div></section>';
    }
    return '<main class="wrap stock-detail-page">' +
      '<section class="stock-detail-navigation"><button id="detail-back" class="back-action" type="button">' + iconSvg('arrow') + '<span>Quay lại</span></button></section>' +
      '<section class="stock-detail-workspace" aria-labelledby="stock-detail-title"><header class="stock-detail-head"><div class="stock-public-identity">' + logoHtml(r.symbol, 'detail-logo') + '<div><div><h2 id="stock-detail-title">' + esc(r.symbol) + '</h2><span>' + esc(r.exchange) + '</span>' + (groupName ? '<span>' + esc(groupName) + '</span>' : '') + '</div><p>' + esc(company) + '</p><small>KL hiện tại · ' + shortVolume(r.cumVolume) + '</small></div></div><div class="stock-public-quote"><strong>' + formatPrice(r.currentPrice) + '</strong><span class="' + metricClass(r.changePct) + '">' + pct(r.changePct) + '</span></div></header><div class="detail-tabs" role="tablist" aria-label="Nội dung chi tiết cổ phiếu">' + tabs + '</div><div class="stock-detail-body" role="tabpanel">' + secondarySourceWarningHtml(true) + content + '</div></section></main>';
  }
  function accountDialogHtml() {
    if (!state.accountOpen) return '';
    var plan = mockPlan();
    var watchlist = mockWatchlistRows();
    var remaining = plan.changeLimit === null ? "Không giới hạn" : Math.max(0, plan.changeLimit - state.mockChangeUsed) + "/" + plan.changeLimit;
    var planCards = Object.keys(MOCK_PLAN_CONFIG).map(function (code) {
      var item = MOCK_PLAN_CONFIG[code];
      return '<button type="button" class="account-plan-card ' + (state.mockPlan === code ? 'active' : '') + '" data-account-plan="' + code + '" aria-pressed="' + (state.mockPlan === code) + '"><div><strong>' + esc(item.label) + '</strong>' + (item.recommended ? '<span>Phổ biến</span>' : '') + '</div><p>' + esc(item.price) + '</p><small>Phạm vi ' + (item.fullMarket ? 'toàn thị trường' : item.viewLimit + ' mã') + ' · Quota ' + (item.changeLimit === null ? 'không giới hạn' : item.changeLimit) + '</small></button>';
    }).join('');
    var benefits = [
      [true, 'Phạm vi kỹ thuật: ' + (plan.fullMarket ? 'toàn thị trường' : plan.viewLimit + ' mã')],
      [true, 'Watchlist capacity: ' + (plan.watchlistLimit === null ? 'ưu tiên cá nhân' : plan.watchlistLimit)],
      [true, 'Quota thay đổi còn lại: ' + remaining],
      [plan.email && plan.telegram, 'Cảnh báo Email / Telegram'],
      [plan.fullMarket, 'Full Market scope'],
      [true, 'Thông tin công khai toàn scanner universe']
    ].map(function (item) { return '<li class="' + (item[0] ? 'active' : '') + '"><span>' + (item[0] ? iconSvg('check') : '—') + '</span><p>' + esc(item[1]) + '</p></li>'; }).join('');
    return '<main class="wrap account-page"><section class="account-navigation"><button id="account-back" class="back-action" type="button">' + iconSvg('arrow') + '<span>Quay lại</span></button></section><section class="account-modal" aria-labelledby="account-title"><header><div><span class="eyebrow">STAGING MEMBERSHIP</span><h2 id="account-title">Tài khoản & gói thành viên</h2><p>Preview trải nghiệm gói; chưa có auth, billing hoặc hồ sơ production.</p></div></header><div class="account-layout"><div class="account-main"><section class="account-card profile-card"><header><h3>Hồ sơ staging</h3><span>Chưa kết nối xác thực</span></header><div class="profile-summary"><span class="account-avatar large">' + iconSvg('user') + '</span><div><strong>Người dùng staging</strong><p>Không sử dụng danh tính Lovable giả.</p></div></div><div class="account-metrics"><div><small>Gói hiện tại</small><strong>' + esc(plan.label) + '</strong></div><div><small>Watchlist</small><strong>' + watchlist.length + (plan.watchlistLimit === null ? '' : '/' + plan.watchlistLimit) + '</strong></div><div><small>Quota còn lại</small><strong>' + remaining + '</strong></div><div><small>Full Market</small><strong>' + (plan.fullMarket ? 'Có' : 'Không') + '</strong></div></div></section><section class="account-card"><header><h3>Demo state switcher</h3><span>Chỉ thay đổi state frontend</span></header><div class="account-plan-grid">' + planCards + '</div></section></div><aside class="account-side"><section class="account-card"><header><h3>Quyền lợi</h3><span>Không có gói phụ bên trong CCC</span></header><ul class="benefit-list">' + benefits + '</ul></section><section class="account-card security-card"><header><h3>Bảo mật</h3><span>Chưa kết nối auth</span></header><div><span>Xác thực 2 lớp</span><strong>Chưa bật</strong></div><div><span>Phiên đăng nhập</span><strong>Không khả dụng</strong></div><button type="button" disabled>Đăng xuất chưa khả dụng</button></section></aside></div></section></main>';
  }
  function applyPageShellLayout() {
    var main = app.querySelector("main.wrap");
    if (!main || !main.children.length) return;
    main.id = "main-content";
    main.classList.add("page-shell");

    var children = Array.prototype.slice.call(main.children);
    var pageHeader = children.shift();
    if (pageHeader) pageHeader.classList.add("page-header");

    var contentGrid = document.createElement("div");
    contentGrid.className = "content-grid";
    var contentMain = document.createElement("div");
    contentMain.className = "content-main";
    var contextRail = null;

    children.forEach(function (child) {
      if (!contextRail && child.classList && child.classList.contains("context-rail")) contextRail = child;
      else contentMain.appendChild(child);
    });
    contentGrid.appendChild(contentMain);
    if (contextRail) {
      main.classList.add("has-context-rail");
      contentGrid.classList.add("has-context-rail");
      contentGrid.appendChild(contextRail);
    }
    main.appendChild(contentGrid);
  }
  function render() {
    var body = state.route === "list" ? listHtml() : state.route === "industry" ? industryHtml() : state.route === "fundamental" ? fundamentalHtml() : overviewHtml();
    if (state.selected) body = dialogHtml();
    if (state.accountOpen) body = accountDialogHtml();
    app.innerHTML = headerHtml() + body + scannerActionDialogHtml();
    applyPageShellLayout();
    bind();
    updateClock();
  }
  function bind() {
    document.querySelectorAll(".company-logo-img").forEach(function (img) {
      img.addEventListener("load", function () { img.parentElement.classList.add("has-logo"); });
      img.addEventListener("error", function () { img.remove(); });
      if (img.complete && img.naturalWidth > 0) img.parentElement.classList.add("has-logo");
    });
    var themeToggle = document.getElementById("theme-toggle");
    if (themeToggle) themeToggle.addEventListener("click", function () {
      state.theme = state.theme === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", state.theme);
      var themeMeta = document.querySelector('meta[name="theme-color"]');
      if (themeMeta) themeMeta.setAttribute("content", state.theme === "light" ? "oklch(0.98 0.002 270)" : "oklch(0.13 0.02 270)");
      try { localStorage.setItem(THEME_KEY, state.theme); } catch (_) {}
      render();
    });
    var globalSearchForm = document.getElementById("global-search-form");
    var globalSearchInput = document.getElementById("global-stock-search");
    if (globalSearchInput) globalSearchInput.addEventListener("input", function () { state.globalQuery = globalSearchInput.value; });
    var submitGlobalSearch = function () {
      var query = String(state.globalQuery || "").trim().toUpperCase();
      location.assign("/danh-sach" + (query ? "?q=" + encodeURIComponent(query) : ""));
    };
    if (globalSearchInput) globalSearchInput.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") return;
      event.preventDefault();
      submitGlobalSearch();
    });
    if (globalSearchForm) globalSearchForm.addEventListener("submit", function (event) {
      event.preventDefault();
      submitGlobalSearch();
    });
    var mobileSearchForm = document.getElementById("mobile-global-search-form");
    var mobileSearchInput = document.getElementById("mobile-global-stock-search");
    if (mobileSearchInput) mobileSearchInput.addEventListener("input", function () { state.globalQuery = mobileSearchInput.value; });
    if (mobileSearchForm) mobileSearchForm.addEventListener("submit", function (event) { event.preventDefault(); submitGlobalSearch(); });
    var refresh = document.getElementById("refresh-btn");
    if (refresh) refresh.addEventListener("click", refreshAllSources);
    var mobileRefresh = document.getElementById("mobile-refresh");
    if (mobileRefresh) mobileRefresh.addEventListener("click", refreshAllSources);
    [document.getElementById("account-open"), document.getElementById("desktop-account-open")].forEach(function (button) {
      if (button) button.addEventListener("click", function () { state.accountReturnScroll = window.scrollY || 0; state.accountOpen = true; render(); var backButton = document.getElementById("account-back"); if (backButton) backButton.focus(); });
    });
    var accountBack = document.getElementById("account-back");
    if (accountBack) accountBack.addEventListener("click", function () { var y=state.accountReturnScroll; state.accountOpen = false; render(); requestAnimationFrame(function(){window.scrollTo(0,y);}); });
    document.querySelectorAll("[data-account-plan]").forEach(function (button) { button.addEventListener("click", function () { var code = button.getAttribute("data-account-plan"); if (MOCK_PLAN_CONFIG[code]) state.mockPlan = code; render(); }); });
    var mockPlanSelect = document.getElementById("mock-plan-select");
    if (mockPlanSelect) mockPlanSelect.addEventListener("change", function () {
      state.mockPlan = MOCK_PLAN_CONFIG[mockPlanSelect.value] ? mockPlanSelect.value : "FREE";
      state.scannerDialog = "";
      render();
    });
    document.querySelectorAll("[data-scanner-mode]").forEach(function (button) { button.addEventListener("click", function () { state.scannerMode = button.getAttribute("data-scanner-mode") === "watchlist" ? "watchlist" : "market"; state.page = 1; render(); }); });
    document.querySelectorAll("[data-select-filter]").forEach(function (select) { select.addEventListener("change", function () { state[select.getAttribute("data-select-filter")] = select.value; state.page = 1; render(); }); });
    var filterToggle = document.getElementById("scanner-filter-toggle");
    if (filterToggle) filterToggle.addEventListener("click", function () { state.scannerFiltersOpen = !state.scannerFiltersOpen; render(); });
    var resetFilters = document.getElementById("reset-filters");
    if (resetFilters) resetFilters.addEventListener("click", function () { state.exchange = "all"; state.signal = ""; state.sort = "signal"; state.page = 1; render(); });
    document.querySelectorAll(".scanner-replace-trigger").forEach(function (button) { button.addEventListener("click", function () { state.scannerDialog = "replace"; state.scannerDialogSymbol = button.getAttribute("data-target-symbol") || ""; render(); var closeButton = document.getElementById("scanner-action-close"); if (closeButton) closeButton.focus(); }); });
    document.querySelectorAll(".scanner-upgrade-trigger").forEach(function (button) { button.addEventListener("click", function () { state.scannerDialog = "upgrade"; state.scannerDialogSymbol = ""; render(); var closeButton = document.getElementById("scanner-action-close"); if (closeButton) closeButton.focus(); }); });
    var scannerActionClose = document.getElementById("scanner-action-close");
    if (scannerActionClose) scannerActionClose.addEventListener("click", closeScannerActionDialog);
    var scannerActionCloseBottom = document.getElementById("scanner-action-close-bottom");
    if (scannerActionCloseBottom) scannerActionCloseBottom.addEventListener("click", closeScannerActionDialog);
    var scannerActionBackdrop = document.getElementById("scanner-action-dialog");
    if (scannerActionBackdrop && !scannerActionBackdrop.hidden) scannerActionBackdrop.addEventListener("click", function (event) { if (event.target === scannerActionBackdrop) closeScannerActionDialog(); });
    document.querySelectorAll("[data-symbol]").forEach(function (el) {
      var symbol = el.getAttribute("data-symbol");
      el.setAttribute("tabindex", "0");
      el.setAttribute("aria-label", "Mở chi tiết " + symbol);
      if (el.tagName !== "TR") el.setAttribute("role", "button");
      el.addEventListener("click", function () { openSymbol(symbol); });
      el.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openSymbol(symbol);
        }
      });
    });
    document.querySelectorAll("[data-industry]").forEach(function(el){el.addEventListener("click",function(){state.industryGroup=el.getAttribute("data-industry")||"";render();window.scrollTo(0,0);});});
    document.querySelectorAll("[data-fund-filter]").forEach(function(el){el.addEventListener("click",function(){var t=el.getAttribute("data-fund-filter"),v=el.getAttribute("data-value");if(t==="score")state.fundamentalMinScore=Number(v)||0;if(t==="growth")state.fundamentalProfitGrowth=v;if(t==="roe")state.fundamentalRoe=v;render();});});
    document.querySelectorAll("[data-detail-tab]").forEach(function (button) { button.addEventListener("click", function () { state.detailTab = button.getAttribute("data-detail-tab") || "overview"; render(); var active = document.querySelector('[data-detail-tab="' + state.detailTab + '"]'); if (active) active.focus(); }); });
    var detailBack = document.getElementById("detail-back");
    if (detailBack) detailBack.addEventListener("click", function () { if (history.state && history.state.cccWorkspace === "stock") history.back(); else closeDialog(); });
    if (state.route !== "list") return;
    var input = document.getElementById("stock-search");
    if (!input) return;
    var submit = function () { state.query = input.value; state.page = 1; render(); };
    document.getElementById("search-btn").addEventListener("click", submit);
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); submit(); } });
    document.getElementById("clear-btn").addEventListener("click", function () { state.query = ""; state.page = 1; render(); });
    document.querySelectorAll("[data-filter]").forEach(function (button) { button.addEventListener("click", function () { state[button.getAttribute("data-filter")] = button.getAttribute("data-value"); state.page = 1; render(); }); });
    var prev = document.getElementById("prev-page"); if (prev) prev.addEventListener("click", function(){state.page--;render();window.scrollTo(0,0);});
    var next = document.getElementById("next-page"); if (next) next.addEventListener("click", function(){state.page++;render();window.scrollTo(0,0);});
  }
  function openSymbol(symbol) {
    var matched = state.rows.find(function(r){return r.symbol===symbol;});
    state.detailReturnScroll = window.scrollY || 0;
    state.detailTab = "overview";
    state.selected = matched || {symbol:String(symbol||"").toUpperCase(),exchange:"—",signalCount:0,currentPrice:null,changePct:null,cumVolume:null,avgVolume10:null,dayVolumeRatioPct:null,ma10:null,ma10DistancePct:null,ma200:null,ma200DistancePct:null,rvol30Pct:null,rvol30Sessions:0};
    try { history.pushState({cccWorkspace:"stock"}, "", location.href); } catch (_) {}
    render();
    var backButton = document.getElementById("detail-back"); if (backButton) backButton.focus();
    if (!state.quarterlyBySymbol[symbol] && !state.quarterlyLoading[symbol]) fetchQuarterly(symbol);
  }
  async function fetchQuarterly(symbol) {
    state.quarterlyLoading[symbol]=true; state.quarterlyError[symbol]=""; render();
    try {
      var url=SUPABASE_URL+"/rest/v1/financial_quarterly?select=*&symbol=eq."+encodeURIComponent(symbol)+"&order=year.desc,quarter.desc";
      var res=await fetch(url,{cache:"no-store",headers:{"apikey":SUPABASE_KEY,"Accept":"application/json"}});
      if(!res.ok)throw new Error("HTTP "+res.status);
      var data=await res.json(); state.quarterlyBySymbol[symbol]=Array.isArray(data)?data:[];
    } catch(e){state.quarterlyError[symbol]="Không tải được lịch sử quý: "+(e&&e.message?e.message:"Lỗi dữ liệu");}
    state.quarterlyLoading[symbol]=false; render();
  }
  function closeDialog() { var y=state.detailReturnScroll; state.selected = null; state.detailTab = "overview"; render(); requestAnimationFrame(function(){window.scrollTo(0,y);}); }
  function closeScannerActionDialog() { state.scannerDialog = ""; state.scannerDialogSymbol = ""; render(); }
  function extractCached() {
    try {
      var own = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
      if (own && Array.isArray(own.rows) && own.rows.length >= EXPECTED_UNIVERSE_COUNT) return own;
      var legacy = JSON.parse(localStorage.getItem(LEGACY_CACHE_KEY) || "null");
      if (legacy && legacy.data && Array.isArray(legacy.data.rows) && legacy.data.rows.length >= EXPECTED_UNIVERSE_COUNT) {
        return { rows: legacy.data.rows, meta: legacy.data.meta || {}, savedAt: legacy.savedAt };
      }
    } catch (_) {}
    return null;
  }
  function applyData(raw) {
    var rows = (raw.rows || []).map(normalize);
    state.rows = rows;
    state.meta = getMeta(raw, rows);
    state.error = "";
    var latest = rows.reduce(function (best, r) {
      var ms = Date.parse(r.updatedAt);
      return Number.isFinite(ms) && ms > best ? ms : best;
    }, 0);
    state.latestUpdateMs = latest || null;
    state.nextRefresh = state.latestUpdateMs ? state.latestUpdateMs + AUTO_REFRESH_INTERVAL_MS : null;
    state.waitingForNewData = false;
  }
  async function fetchFinancial() {
    try {
      var response=await fetch(FINANCIAL_API_URL,{method:"GET",cache:"no-store",headers:{"apikey":SUPABASE_KEY,"Accept":"application/json"}});
      if(!response.ok)throw new Error("HTTP "+response.status);
      var data=await response.json();
      state.financialRows=Array.isArray(data)?data:[];
      state.financialBySymbol={}; state.financialRows.forEach(function(r){state.financialBySymbol[String(r.symbol||"").toUpperCase()]=r;});
      state.financialLoaded=true; state.financialError="";
    } catch(e){state.financialError="Không tải được dữ liệu cơ bản.";}
  }
  async function fetchMetadata() {
    try {
      var response=await fetch(METADATA_API_URL,{method:"GET",cache:"no-store",headers:{"apikey":SUPABASE_KEY,"Accept":"application/json"}});
      if(!response.ok)throw new Error("HTTP "+response.status);
      var data=await response.json();
      state.metadataRows=Array.isArray(data)?data:[];
      state.metadataBySymbol={}; state.metadataRows.forEach(function(r){state.metadataBySymbol[String(r.symbol||"").toUpperCase()]=r;});
      state.metadataLoaded=true; state.metadataError="";
    } catch(e){state.metadataError="Không tải được tên công ty.";}
  }
  async function fetchData(manual) {
    if (state.fetching) return;
    state.fetching = true;
    render();
    var controller = new AbortController();
    var timeout = setTimeout(function(){ controller.abort(); }, 30000);
    try {
      var response = await fetch(API_URL, {
        method: "GET",
        cache: "no-store",
        signal: controller.signal,
        headers: {
          "apikey": SUPABASE_KEY,
          "Accept": "application/json"
        }
      });
      if (!response.ok) throw new Error("HTTP " + response.status);
      var rows = await response.json();
      if (!Array.isArray(rows)) throw new Error("Supabase trả về dữ liệu không hợp lệ");
      if (rows.length < EXPECTED_UNIVERSE_COUNT) throw new Error("Supabase chỉ trả " + rows.length + "/" + EXPECTED_UNIVERSE_COUNT + " mã; giữ dữ liệu đủ gần nhất");
      var raw = {
        ok: true,
        rows: rows,
        meta: {
          systemStatus: rows.some(function(r){ return ["MISSING_MARKET_DATA", "ERROR"].indexOf(r.data_status) >= 0; }) ? "DEGRADED" : "OK",
          totalSymbols: rows.length,
          dataSource: "Supabase"
        }
      };
      applyData(raw);
      try { localStorage.setItem(CACHE_KEY, JSON.stringify({ rows: raw.rows, meta: raw.meta || {}, savedAt: Date.now() })); } catch (_) {}
    } catch (error) {
      state.error = error && error.name === "AbortError" ? "Nguồn dữ liệu phản hồi quá 30 giây" : "Không thể tải dữ liệu: " + (error && error.message ? error.message : "Lỗi không xác định");
    } finally {
      clearTimeout(timeout);
      state.fetching = false;
      render();
    }
  }
  async function refreshAllSources() {
    await Promise.all([fetchData(true), fetchFinancial(), fetchMetadata()]);
    render();
  }
  function vietnamParts(ms) {
    var parts = new Intl.DateTimeFormat("en-GB", { timeZone:"Asia/Ho_Chi_Minh", year:"numeric", month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", second:"2-digit", hour12:false }).formatToParts(new Date(ms));
    var out = {}; parts.forEach(function(p){out[p.type]=Number(p.value);}); return out;
  }
  function inAutoRefreshWindow(ms) {
    var p=vietnamParts(ms);
    var day=new Date(Date.UTC(p.year,p.month-1,p.day)).getUTCDay();
    var n=p.hour*60+p.minute+p.second/60;
    if(day===0||day===6) return false;
    // Cho phep them it phut sau cuoi phien de nhan ket qua run 11:30 / 15:00.
    return (n>=540&&n<696)||(n>=780&&n<906);
  }
  function setCountdownText(text, mode) {
    [document.getElementById("countdown")].forEach(function(el){
      if(!el) return;
      el.textContent=text;
      el.classList.toggle("waiting", mode==="waiting");
      el.classList.toggle("outside", mode==="outside");
    });
  }
  function updateTrustBar() {
    var root = document.getElementById("data-trust");
    if (!root) return;
    var trust = trustModel(Date.now());
    root.className = "data-trust " + trust.tone;
    var values = {
      "trust-status": trust.label,
      "trust-time": trust.time,
      "trust-count": trust.count,
      "trust-detail": trust.detail
    };
    Object.keys(values).forEach(function (id) {
      var el = document.getElementById(id);
      if (el && el.textContent !== values[id]) el.textContent = values[id];
    });
  }
  async function pollLatestVersion() {
    if(state.versionPolling || state.fetching) return;
    state.versionPolling=true;
    state.lastVersionPollAt=Date.now();
    var controller=new AbortController();
    var timeout=setTimeout(function(){controller.abort();},10000);
    try{
      var response=await fetch(LATEST_API_URL,{method:"GET",cache:"no-store",signal:controller.signal,headers:{"apikey":SUPABASE_KEY,"Accept":"application/json"}});
      if(!response.ok) throw new Error("HTTP "+response.status);
      var rows=await response.json();
      var latest=rows&&rows[0] ? Date.parse(rows[0].updated_at) : NaN;
      if(Number.isFinite(latest) && (!state.latestUpdateMs || latest>state.latestUpdateMs+500)){
        await fetchData(false);
      }
    }catch(_){
      // Loi poll tam thoi khong lam mat du lieu dang hien thi.
    }finally{
      clearTimeout(timeout);
      state.versionPolling=false;
    }
  }
  function updateClock() {
    var now=Date.now();
    if(!inAutoRefreshWindow(now)){
      state.waitingForNewData=false;
      setCountdownText("Ngoài giờ hoạt động","outside");
      updateTrustBar();
      return;
    }
    if(!state.latestUpdateMs){
      state.waitingForNewData=true;
      setCountdownText("Đang chờ dữ liệu mới…","waiting");
    }else{
      state.nextRefresh=state.latestUpdateMs+AUTO_REFRESH_INTERVAL_MS;
      if(now<state.nextRefresh){
        state.waitingForNewData=false;
        var seconds=Math.max(0,Math.ceil((state.nextRefresh-now)/1000));
        setCountdownText(String(Math.floor(seconds/60)).padStart(2,"0")+":"+String(seconds%60).padStart(2,"0"),"countdown");
      }else{
        state.waitingForNewData=true;
        setCountdownText("Đang chờ dữ liệu mới…","waiting");
      }
    }
    updateTrustBar();
    if(state.waitingForNewData && now-state.lastVersionPollAt>=VERSION_POLL_INTERVAL_MS) pollLatestVersion();
  }
  setInterval(updateClock,1000);
  window.addEventListener("popstate",function(){if(!state.selected)return;closeDialog();});
  document.addEventListener("keydown", function(e){if(e.key!=="Escape")return;if(state.scannerDialog)closeScannerActionDialog();});
  var cached = extractCached();
  if (cached) applyData(cached);
  render();
  fetchFinancial().then(function(){ render(); });
  fetchMetadata().then(function(){ render(); });
  fetchData(false);
})();
