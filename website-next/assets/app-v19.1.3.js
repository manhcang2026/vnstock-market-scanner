(function () {
  "use strict";

  var ACCOUNT_PATH = "/tai-khoan";
  var THEME_KEY = "vnstock_dashboard_theme_v17";
  var app = document.getElementById("app");
  var lastFocused = null;
  var authSubscription = null;
  var searchTimer = null;
  var OVERVIEW_PAGE_SIZE = 50;
  var OVERVIEW_MOBILE_CHUNK = 20;

  var savedTheme = "";
  try { savedTheme = localStorage.getItem(THEME_KEY) || ""; } catch (_) {}

  var state = {
    route: routeFromLocation(),
    theme: savedTheme === "light" || savedTheme === "dark" ? savedTheme : "dark",
    authReady: false,
    authFatal: "",
    session: null,
    user: null,
    authDialogOpen: false,
    authBusy: false,
    authError: "",
    membership: { loading: false, error: "", profile: null, subscription: null, plan: null, catalog: [] },
    profile: { saving: false, error: "", notice: "" },
    watchlist: {
      loading: false, saving: false, loadedFor: "", data: null,
      original: [], selected: [], metadata: Object.create(null),
      query: "", searching: false, results: [], searchSeq: 0,
      error: "", notice: ""
    },
    research: { loading: false, loaded: false, error: "", financial: [], metadata: Object.create(null) },
    overview: { loading: false, error: "", loadedFor: "", data: null, group: "", page: 1, mobileShown: OVERVIEW_MOBILE_CHUNK },
    marketPulse: { loading: false, loaded: false, error: "", rows: [] },
    researchShown: 50,
    industry: "",
    filters: { score: 0, growth: "all", roe: "all" },
    planPreview: ""
  };

  document.documentElement.setAttribute("data-theme", state.theme);

  function routeFromLocation() {
    var path = window.location.pathname || "/";
    if (path === "/danh-sach") return "scanner";
    if (path === "/so-sanh-theo-nganh") return "industry";
    if (path === "/sang-loc-co-ban") return "fundamental";
    if (path === ACCOUNT_PATH) return "account";
    return "overview";
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function num(value) {
    if (value === null || value === undefined || value === "") return null;
    var parsed = Number(String(value).replace(/[,%\s]/g, ""));
    return Number.isFinite(parsed) ? parsed : null;
  }

  function pct(value, digits) {
    var parsed = num(value);
    if (parsed === null) return "—";
    return (parsed > 0 ? "+" : "") + parsed.toLocaleString("vi-VN", {
      minimumFractionDigits: digits == null ? 1 : digits,
      maximumFractionDigits: digits == null ? 1 : digits
    }) + "%";
  }

  function formatNumber(value, digits) {
    var parsed = num(value);
    if (parsed === null) return "—";
    return parsed.toLocaleString("vi-VN", {
      minimumFractionDigits: digits || 0,
      maximumFractionDigits: digits || 0
    });
  }

  function formatVolume(value) {
    var parsed = num(value);
    if (parsed === null) return "—";
    if (Math.abs(parsed) >= 1000000) return formatNumber(parsed / 1000000, 2) + " triệu";
    if (Math.abs(parsed) >= 1000) return formatNumber(parsed / 1000, 1) + " nghìn";
    return formatNumber(parsed, 0);
  }

  function isMobileViewport() {
    return !!(window.matchMedia && window.matchMedia("(max-width: 767px)").matches);
  }

  function logoHtml(symbol) {
    var safe = String(symbol || "?").toUpperCase().replace(/[^A-Z0-9]/g, "");
    var fallback = safe.slice(0, 3) || "?";
    return '<span class="stock-logo"><span class="stock-logo-fallback">' + esc(fallback) + '</span><img src="/assets/logos/' + esc(safe) + '.jpg?v=1741" alt="" decoding="async" onerror="this.style.display=\'none\'"></span>';
  }

  function overviewGroupConfig(key) {
    var map = {
      "4of4": { label: "Đạt 4/4", countKey: "four_of_four" },
      "3plus": { label: "Từ 3 tín hiệu", countKey: "three_plus" },
      "2plus": { label: "Từ 2 tín hiệu", countKey: "two_plus" },
      "rvol30": { label: "RVOL30 nổi bật", countKey: "rvol30" }
    };
    return map[key] || null;
  }

  function overviewMatches(row, key) {
    if (!key) return true;
    var count = Number(row && row.signal_count || 0);
    if (key === "4of4") return count === 4;
    if (key === "3plus") return count >= 3;
    if (key === "2plus") return count >= 2;
    if (key === "rvol30") return !!(row && row.signal_rvol30_200pct);
    return true;
  }

  function overviewIsFull() {
    return !!(state.overview.data && state.overview.data.effective_full_market_access);
  }

  function overviewSampleMode() {
    if (!state.overview.data) return false;
    if (!state.user) return true;
    return !overviewIsFull() && Number(state.overview.data.selected_watchlist_count || 0) === 0;
  }

  function overviewCount(key, mine) {
    var cfg = overviewGroupConfig(key), data = state.overview.data || {};
    if (!cfg) return 0;
    var source = mine ? data.watchlist_counts : data.market_counts;
    return Number(source && source[cfg.countKey] || 0);
  }

  function overviewSourceRows() {
    var data = state.overview.data || {};
    var source = overviewSampleMode() ? data.sample_rows : data.rows;
    return Array.isArray(source) ? source.slice() : [];
  }

  function overviewFilteredRows() {
    return overviewSourceRows().filter(function (row) { return overviewMatches(row, state.overview.group); });
  }

  function signalRailHtml(row) {
    var flags = [row.signal_price_3pct, row.signal_daily_volume_200pct, row.signal_above_ma200, row.signal_rvol30_200pct];
    var labels = ["Giá ≥3%", "KL ngày ≥200% KLTB10", "Trên MA200", "RVOL30 ≥200%"];
    var count = Number(row.signal_count || 0);
    var status = count === 4 ? 'Hội tụ mạnh' : count === 3 ? 'Đang hội tụ' : '';
    return '<div class="signal-rail signal-' + count + '" aria-label="' + count + ' trên 4 tín hiệu"><div class="signal-segments">' + flags.map(function (value, index) { return '<span class="signal-segment ' + (value ? 'on' : '') + '" title="' + esc(labels[index]) + '"></span>'; }).join("") + '</div><strong>' + count + '/4</strong>' + (status ? '<em>' + status + '</em>' : '') + '</div>';
  }

  function overviewRowHtml(row, sample) {
    var company = row.display_name || row.company_name || "Tên công ty đang cập nhật";
    var daily = num(row.daily_volume_pct);
    var rvol = num(row.rvol30_pct);
    return '<article class="overview-stock-row' + (sample ? ' is-sample' : '') + '">' +
      '<div class="overview-stock-identity">' + logoHtml(row.symbol) + '<div><strong>' + esc(row.symbol) + '</strong><span title="' + esc(company) + '">' + esc(company) + '</span><small>' + esc(row.exchange || '') + (sample ? ' · Mã mẫu' : '') + '</small></div></div>' +
      '<div class="overview-stock-price"><span>Giá / thay đổi</span><strong>' + formatNumber(row.current_price, 0) + '</strong><b class="' + tone(row.price_change_pct) + '">' + pct(row.price_change_pct, 2) + '</b></div>' +
      '<div class="overview-stock-volume"><span>Khối lượng</span><strong>' + formatVolume(row.volume_accumulated) + '</strong><b>' + (daily === null ? '—' : formatNumber(daily, 0) + '% KLTB10') + '</b></div>' +
      '<div class="overview-stock-evidence"><span class="evidence-rvol">RVOL30 <b>' + (rvol === null ? '—' : formatNumber(rvol, 0) + '%') + '</b></span><span class="evidence-ma10">MA10 <b class="' + tone(row.ma10_distance_pct) + '">' + pct(row.ma10_distance_pct, 1) + '</b></span><span class="evidence-ma200">MA200 <b class="' + tone(row.ma200_distance_pct) + '">' + pct(row.ma200_distance_pct, 1) + '</b></span></div>' +
      '<div class="overview-stock-ccc">' + signalRailHtml(row) + '</div>' +
    '</article>';
  }

  function overviewPager(total) {
    if (total <= 0 || overviewSampleMode()) return "";
    if (isMobileViewport()) {
      var shown = Math.min(total, state.overview.mobileShown);
      return '<div class="overview-load-more"><span>Đang hiển thị ' + shown + '/' + total + ' mã</span>' + (shown < total ? '<button class="button secondary" type="button" data-overview-more>Xem thêm ' + Math.min(OVERVIEW_MOBILE_CHUNK, total - shown) + ' mã</button>' : '') + '</div>';
    }
    var pages = Math.max(1, Math.ceil(total / OVERVIEW_PAGE_SIZE));
    state.overview.page = Math.min(state.overview.page, pages);
    if (pages <= 1) return "";
    return '<div class="overview-pagination"><button class="button secondary" type="button" data-overview-page="-1"' + (state.overview.page <= 1 ? ' disabled' : '') + '>← Trước</button><span>Trang <b>' + state.overview.page + '</b> / ' + pages + '</span><button class="button secondary" type="button" data-overview-page="1"' + (state.overview.page >= pages ? ' disabled' : '') + '>Sau →</button></div>';
  }

  function overviewVisibleRows(rows) {
    if (overviewSampleMode()) return rows;
    if (isMobileViewport()) return rows.slice(0, state.overview.mobileShown);
    var start = (state.overview.page - 1) * OVERVIEW_PAGE_SIZE;
    return rows.slice(start, start + OVERVIEW_PAGE_SIZE);
  }

  function overviewKpisHtml() {
    var keys = ["4of4", "3plus", "2plus", "rvol30"];
    return '<section class="panel overview-density"><header class="overview-section-head"><div><h2>Mật độ tín hiệu hôm nay</h2><p>Số lớn là toàn thị trường; mỗi thẻ cho biết số mã trong DS của bạn.</p></div><span>Không tiết lộ mã ngoài quyền xem</span></header><div class="overview-kpi-grid">' + keys.map(function (key) {
      var cfg = overviewGroupConfig(key), market = overviewCount(key, false), mine = overviewCount(key, true), active = state.overview.group === key;
      var mineText = state.user ? (overviewIsFull() ? 'DS của bạn: toàn bộ' : 'DS của bạn: ' + mine + ' mã') : 'DS của bạn: chưa tạo';
      return '<button type="button" class="overview-kpi-card kpi-' + key + (active ? ' active' : '') + '" data-overview-group="' + key + '" aria-pressed="' + (active ? 'true' : 'false') + '"><span>' + esc(cfg.label) + '</span><strong>' + market + '<small> mã</small></strong><footer><em>Toàn thị trường</em><b>' + esc(mineText) + '</b></footer><i class="kpi-activity" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></i></button>';
    }).join("") + '</div></section>';
  }

  function overviewUpsellHtml() {
    if (!state.overview.group || overviewIsFull() || !state.overview.data) return "";
    var cfg = overviewGroupConfig(state.overview.group), market = overviewCount(state.overview.group, false), mine = overviewCount(state.overview.group, true), hidden = Math.max(0, market - mine);
    if (!hidden) return "";
    var copy = !state.user || overviewSampleMode() ? 'Bạn chưa có DS mã theo dõi thật trong nhóm này.' : 'DS của bạn có ' + mine + ' mã trong nhóm này.';
    return '<section class="overview-upsell"><div><span>CÒN ' + hidden + ' MÃ KHÁC</span><strong>' + market + ' mã trên thị trường đang thuộc nhóm ' + esc(cfg.label) + '.</strong><p>' + esc(copy) + ' Danh tính các mã ngoài quyền không được tiết lộ.</p></div><div><a class="button primary" href="/tai-khoan#goi-thanh-vien">Mở FULL 24 giờ · 100.000đ</a><a class="button secondary" href="/tai-khoan#ds-ma-theo-doi">Mở rộng DS</a></div></section>';
  }

  function overviewResultsHtml() {
    var rows = overviewFilteredRows();
    var sample = overviewSampleMode();
    var visible = overviewVisibleRows(rows);
    var title, meta, intro = "";
    if (sample) {
      title = state.overview.group ? '6 mã mẫu theo điều kiện ' + overviewGroupConfig(state.overview.group).label : 'Khám phá CCC với 6 mã đại diện';
      meta = rows.length + ' mã mẫu';
      intro = '<div class="overview-sample-note"><div><span class="eyebrow">KHÁM PHÁ CCC</span><strong>Đây là 6 mã mẫu cố định để bạn xem cách CCC hoạt động.</strong><p>Không phải khuyến nghị đầu tư và không phải DS mã theo dõi của bạn.</p></div>' + (!state.user ? '<button class="button primary" type="button" data-open-login>Tạo DS mã theo dõi</button>' : '<a class="button primary" href="/tai-khoan#ds-ma-theo-doi">Tạo DS mã theo dõi</a>') + '</div>';
    } else {
      title = state.overview.group ? 'Tín hiệu trong DS mã theo dõi của bạn' : 'DS mã theo dõi của bạn';
      meta = rows.length + ' mã';
    }
    var reset = state.overview.group ? '<button class="overview-reset" type="button" data-overview-reset>← Xem tất cả DS mã theo dõi</button>' : '';
    var body = rows.length ? visible.map(function (row) { return overviewRowHtml(row, sample); }).join("") + overviewPager(rows.length) : '<div class="overview-empty"><strong>Chưa có mã phù hợp với điều kiện này.</strong><p>KPI phía trên vẫn phản ánh số lượng toàn thị trường.</p>' + reset + '</div>';
    return '<section class="panel overview-results"><header class="overview-results-head"><div><span class="eyebrow">' + (sample ? 'TRẢI NGHIỆM' : 'DS CỦA BẠN') + '</span><h2>' + esc(title) + '</h2><p>' + esc(meta) + '</p></div>' + reset + '</header>' + intro + '<div class="overview-row-head"><span>Công ty</span><span>Giá / thay đổi</span><span>Khối lượng</span><span>Điểm nổi bật</span><span>CCC</span></div><div class="overview-rows">' + body + '</div></section>' + overviewUpsellHtml();
  }

  function overviewLoadingHtml() {
    return '<section class="panel overview-loading"><span class="spinner"></span><div><strong>Đang tải Tổng quan…</strong><p>Khung giao diện được giữ ổn định trong khi dữ liệu được xác nhận.</p></div></section>';
  }

  function overviewErrorHtml() {
    return '<section class="panel error-state" role="alert"><strong>Không tải được Tổng quan.</strong><p>' + esc(state.overview.error || 'Nguồn dữ liệu tạm thời chưa phản hồi.') + '</p><button class="button secondary" type="button" data-overview-retry>Thử lại</button></section>';
  }

  function marketStatusLabel(row) {
    var status = String(row && row.market_status || "").toUpperCase();
    if (status === "OPEN") return "Đang giao dịch";
    if (status === "OPEN_24H") return "24/7";
    if (status === "LUNCH_BREAK") return "Nghỉ trưa";
    if (status === "PREOPEN") return "Chưa mở";
    if (status === "DELAYED") return "Dữ liệu trễ";
    if (status === "CLOSED") return "Đóng cửa";
    return status ? status : "Cập nhật";
  }

  function marketTimeLabel(row) {
    var value = row && (row.market_time || row.last_success_at || row.checked_at);
    if (!value) return "—";
    var date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "—";
    return date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  }

  function marketPulseRailHtml() {
    var rows = state.marketPulse.rows || [];
    if (state.marketPulse.loading && !rows.length) return railCard('Toàn cảnh thị trường', '<div class="rail-loading"><span class="spinner"></span><span>Đang cập nhật…</span></div>', 'LIVE');
    if (!rows.length) return railCard('Toàn cảnh thị trường', '<p>Chưa tải được dữ liệu bối cảnh thị trường.</p>', '—');

    var vn = rows.find(function (row) { return String(row.key || "").toLowerCase() === "vnindex"; }) || rows[0];
    var others = rows.filter(function (row) { return row !== vn; });
    var isLive = rows.some(function (row) { return row.market_status === 'OPEN' || row.market_status === 'OPEN_24H'; });

    return '<section class="rail-card market-pulse-card">' +
      '<header><span>TOÀN CẢNH THỊ TRƯỜNG</span><b>' + (isLive ? 'LIVE' : 'CẬP NHẬT') + '</b></header>' +
      '<div class="market-pulse-primary">' +
        '<div class="market-pulse-primary-head"><strong>' + esc(vn.display_name || vn.key || 'VN-INDEX') + '</strong><span>' + esc(marketStatusLabel(vn)) + '</span></div>' +
        '<div class="market-pulse-primary-value"><strong>' + formatNumber(vn.price, Number(vn.price) < 100 ? 2 : 2) + '</strong><b class="' + tone(vn.change_pct) + '">' + pct(vn.change_pct, 2) + '</b></div>' +
        '<small>Việt Nam · ' + esc(marketTimeLabel(vn)) + '</small>' +
      '</div>' +
      '<div class="market-pulse-list">' + others.map(function (row) {
        return '<div><span><strong>' + esc(row.display_name || row.key) + '</strong><small>' + esc(marketStatusLabel(row)) + ' · ' + esc(marketTimeLabel(row)) + '</small></span><strong>' + formatNumber(row.price, Number(row.price) < 100 ? 2 : 2) + '</strong><b class="' + tone(row.change_pct) + '">' + pct(row.change_pct, 2) + '</b></div>';
      }).join("") + '</div>' +
    '</section>';
  }

  function signalLegendRailHtml() {
    return '<section class="rail-card signal-legend-card"><header><span>CCC 4 TÍN HIỆU</span><b>GIẢI THÍCH</b></header>' +
      '<p class="legend-intro">Bốn ô luôn theo cùng một thứ tự. Ô sáng nghĩa là điều kiện hiện tại đã đạt.</p>' +
      '<div class="signal-legend-list">' +
        '<div><i class="legend-dot price"></i><span><strong>Giá</strong><small>Tăng ≥ 3%</small></span></div>' +
        '<div><i class="legend-dot volume"></i><span><strong>Khối lượng</strong><small>KL ngày ≥ 200% KLTB10</small></span></div>' +
        '<div><i class="legend-dot trend"></i><span><strong>Xu hướng</strong><small>Giá trên MA200</small></span></div>' +
        '<div><i class="legend-dot rvol"></i><span><strong>RVOL30</strong><small>RVOL30 ≥ 200%</small></span></div>' +
      '</div><p class="legend-foot"><b>3/4</b> = Đang hội tụ · <b>4/4</b> = Hội tụ mạnh.</p>' +
    '</section>';
  }

  function overviewTrustRailHtml() {
    var data = state.overview.data || {}, rows = state.marketPulse.rows || [];
    var latest = data.last_updated_at || (rows[0] && (rows[0].last_success_at || rows[0].checked_at)) || null;
    return railCard('Nguồn dữ liệu', '<dl class="rail-list"><div><dt>Cập nhật</dt><dd>' + esc(formatDateTime(latest)) + '</dd></div><div><dt>Tổng mã quét</dt><dd>' + esc(String(data.market_total || '—')) + '</dd></div><div><dt>Nguồn</dt><dd>Chuyện Chợ Chứng</dd></div></dl><p>Dữ liệu tín hiệu là công cụ tham khảo, không phải khuyến nghị mua/bán.</p>');
  }

  async function ensureMarketPulse(force) {
    if (state.marketPulse.loading || state.marketPulse.loaded && !force) return;
    state.marketPulse.loading = true;
    state.marketPulse.error = '';
    try {
      state.marketPulse.rows = await window.CCCData.loadMarketPulse();
      state.marketPulse.loaded = true;
    } catch (error) {
      state.marketPulse.error = 'Không tải được bối cảnh thị trường.';
      console.error('CCC market pulse load failed', error);
    } finally {
      state.marketPulse.loading = false;
      updateAccountTrigger();
      if (state.route === 'overview') renderRoute();
    }
  }

  async function ensureOverview(force) {
    if (!state.authReady || state.overview.loading) return;
    var owner = state.user ? state.user.id : 'guest';
    if (!force && state.overview.loadedFor === owner && state.overview.data) return;
    state.overview.loading = true;
    state.overview.error = '';
    if (state.route === 'overview') renderRoute();
    try {
      state.overview.data = state.user ? await window.CCCData.getMyOverviewState() : await window.CCCData.getPublicOverviewState();
      state.overview.loadedFor = owner;
      state.overview.page = 1;
      state.overview.mobileShown = OVERVIEW_MOBILE_CHUNK;
    } catch (error) {
      state.overview.error = 'Nguồn dữ liệu Tổng quan tạm thời chưa phản hồi. Vui lòng thử lại.';
      console.error('CCC overview load failed', error);
    } finally {
      state.overview.loading = false;
      if (state.route === 'overview') renderRoute();
    }
  }

  function tone(value) {
    var parsed = num(value);
    return parsed === null ? "" : parsed > 0 ? "positive" : parsed < 0 ? "negative" : "";
  }

  function formatDate(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "—";
    return date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
  }

  function formatDateTime(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "—";
    return date.toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function icon(name) {
    var paths = {
      home: '<path d="M3 11.5 12 4l9 7.5V21h-6v-6H9v6H3z"/>',
      list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
      chart: '<path d="M4 19V9m6 10V5m6 14v-7m5 7H2"/>',
      filter: '<path d="M4 5h16l-6 7v5l-4 2v-7z"/>',
      search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
      refresh: '<path d="M20 11a8 8 0 1 0-2.34 5.66M20 4v7h-7"/>',
      bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
      user: '<path d="M20 21a8 8 0 0 0-16 0m8-9a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/>',
      moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>',
      sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"/>',
      close: '<path d="m6 6 12 12M18 6 6 18"/>',
      shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>'
    };
    return '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + (paths[name] || paths.home) + '</svg>';
  }

  function navLink(href, key, label, iconName) {
    var active = Array.isArray(key) ? key.indexOf(state.route) >= 0 : state.route === key;
    return '<a class="nav-link' + (active ? ' active' : '') + '" href="' + href + '"' + (active ? ' aria-current="page"' : '') + '>' + icon(iconName) + '<span>' + esc(label) + '</span></a>';
  }

  function disabledNavItem(label, iconName) {
    return '<span class="nav-link disabled" aria-disabled="true" title="Chưa sẵn sàng">' + icon(iconName) + '<span>' + esc(label) + '</span><small>CHƯA SẴN SÀNG</small></span>';
  }

  function mountShell() {
    app.innerHTML = '' +
      '<header class="app-header">' +
        '<div class="app-header-inner">' +
          '<a class="brand" href="/" aria-label="Chuyện Chợ Chứng — Trang tổng quan"><span class="brand-mark">' + icon("chart") + '</span><span><strong>CHUYỆN CHỢ CHỨNG</strong><small>STOCK INTELLIGENCE</small></span></a>' +
          '<form class="global-search" role="search" aria-label="Tìm mã cổ phiếu an toàn"><label class="sr-only" for="global-stock-search">Tìm mã cổ phiếu</label><span class="global-search-icon">' + icon("search") + '</span><input id="global-stock-search" type="search" placeholder="Tìm mã chứng khoán" disabled aria-describedby="global-search-note"><button type="submit" disabled aria-label="Tìm kiếm chưa sẵn sàng">' + icon("search") + '</button><span id="global-search-note" class="sr-only">Tìm kiếm toàn thị trường sẽ được bật sau khi nguồn dữ liệu an toàn được nối hoàn chỉnh.</span></form>' +
          '<div class="header-right">' +
            '<section id="session-status" class="session-status" role="status" aria-live="polite" aria-atomic="true"><span class="session-primary"><i></i><strong id="session-status-label">Đang xác nhận phiên</strong></span><span id="session-status-context">Dữ liệu kỹ thuật đang khóa</span><span class="session-countdown">Kiểm tra tiếp: —</span></section>' +
            '<div class="top-actions">' +
              '<button class="icon-button" type="button" disabled aria-label="Làm mới dữ liệu chưa sẵn sàng" title="Làm mới: chưa tải dữ liệu kỹ thuật">' + icon("refresh") + '</button>' +
              '<button class="icon-button" type="button" disabled aria-label="Cảnh báo chưa sẵn sàng" title="Cảnh báo chưa sẵn sàng">' + icon("bell") + '</button>' +
              '<button id="theme-toggle" class="icon-button" type="button" aria-label="Đổi giao diện sáng tối">' + icon(state.theme === "dark" ? "sun" : "moon") + '</button>' +
              '<button id="account-open" class="account-trigger" type="button"><span id="account-avatar" class="account-avatar">C</span><span><strong id="account-label">Tài khoản</strong><small id="account-context">Đang xác nhận</small></span></button>' +
            '</div>' +
          '</div>' +
        '</div>' +
      '</header>' +
      '<aside class="desktop-sidebar" aria-label="Thanh điều hướng"><nav id="desktop-nav-links" aria-label="Điều hướng chính"></nav><div class="sidebar-footer"><div id="desktop-account-link"></div><span class="staging-badge"><strong>STAGING</strong><small>v19.1.3-baseline</small></span></div></aside>' +
      '<div class="workspace"><div id="route-host"></div></div>' +
      '<nav class="mobile-nav" aria-label="Điều hướng di động"><div id="mobile-nav-links"></div></nav>' +
      '<div id="dialog-host"></div>';
    updateNavigation();
    updateAccountTrigger();
  }

  function primaryNavigationHtml() {
    return navLink("/", "overview", "Tổng quan", "home") +
      navLink("/so-sanh-theo-nganh", ["industry", "fundamental"], "Nghiên cứu", "chart") +
      navLink("/danh-sach", "scanner", "DS mã theo dõi", "list") +
      disabledNavItem("Cảnh báo", "bell");
  }

  function updateNavigation() {
    var desktop = document.getElementById("desktop-nav-links");
    var desktopAccount = document.getElementById("desktop-account-link");
    var mobile = document.getElementById("mobile-nav-links");
    if (desktop) desktop.innerHTML = primaryNavigationHtml();
    if (desktopAccount) desktopAccount.innerHTML = navLink(ACCOUNT_PATH, "account", "Tài khoản", "user");
    if (mobile) mobile.innerHTML = primaryNavigationHtml() + navLink(ACCOUNT_PATH, "account", "Tài khoản", "user");
  }

  function userLabel() {
    if (!state.authReady) return "Tài khoản";
    if (!state.user) return "Đăng nhập";
    var profile = state.membership.profile;
    var meta = state.user.user_metadata || {};
    return profile && profile.display_name || meta.full_name || meta.name || state.user.email || "Tài khoản";
  }

  function marketHeaderState() {
    var rows = state.marketPulse && Array.isArray(state.marketPulse.rows) ? state.marketPulse.rows : [];
    var vn = rows.find(function (row) { return String(row.key || '').toLowerCase() === 'vnindex'; }) || rows[0] || null;
    if (!vn) return { label: 'Đang cập nhật thị trường', context: 'Cập nhật —', className: 'is-checking' };
    var status = String(vn.market_status || '').toUpperCase();
    var open = status === 'OPEN';
    var stamp = vn.market_time || vn.last_success_at || vn.checked_at || null;
    var timeText = '—';
    if (stamp) {
      var date = new Date(stamp);
      if (Number.isFinite(date.getTime())) timeText = date.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
    }
    return {
      label: open ? 'Trong giờ thị trường' : 'Ngoài giờ thị trường',
      context: 'Cập nhật ' + timeText,
      className: open ? 'is-ready' : 'is-ready'
    };
  }

  function updateAccountTrigger() {
    var label = document.getElementById("account-label");
    var avatar = document.getElementById("account-avatar");
    var context = document.getElementById("account-context");
    var trigger = document.getElementById("account-open");
    var statusLabel = document.getElementById("session-status-label");
    var statusContext = document.getElementById("session-status-context");
    var statusRoot = document.getElementById("session-status");
    var text = userLabel();
    if (label) label.textContent = text;
    if (avatar) avatar.textContent = text.trim().charAt(0).toUpperCase() || "C";
    if (trigger) trigger.setAttribute("aria-label", state.user ? "Mở trang tài khoản" : "Đăng nhập Chuyện Chợ Chứng");
    var subscriptionStatus = state.membership.subscription && String(state.membership.subscription.status || "").toUpperCase();
    var planCode = state.membership.plan && state.membership.plan.plan_code;
    if (context) context.textContent = !state.authReady ? "Đang xác nhận" : state.user ? (subscriptionStatus === "GRACE" ? "Chờ gia hạn" : subscriptionStatus === "SUSPENDED" ? "Tạm ngưng" : planCode || "Đã đăng nhập") : "Tài khoản CCC";
    var marketHeader = marketHeaderState();
    if (statusRoot) statusRoot.className = "session-status " + (state.authFatal ? "is-error" : marketHeader.className);
    if (statusLabel) statusLabel.textContent = state.authFatal ? "Kết nối dữ liệu lỗi" : marketHeader.label;
    if (statusContext) statusContext.textContent = state.authFatal ? "Dữ liệu đang được bảo vệ" : marketHeader.context;
  }

  function pageFrame(kicker, title, subtitle, mainHtml, railHtml, extraClass) {
    return '<main id="main-content" class="page-shell ' + esc(extraClass || "") + '" tabindex="-1">' +
      '<header class="page-header"><span class="eyebrow">' + esc(kicker) + '</span><h1>' + esc(title) + '</h1><p>' + esc(subtitle) + '</p></header>' +
      '<div class="content-grid"><div class="content-main">' + mainHtml + '</div><aside class="context-rail" aria-label="Thông tin liên quan">' + railHtml + '</aside></div>' +
    '</main>';
  }

  function railCard(title, body, badge) {
    return '<section class="rail-card"><header><span>' + esc(title) + '</span>' + (badge ? '<b>' + esc(badge) + '</b>' : '') + '</header>' + body + '</section>';
  }

  function safeAccessCard(area) {
    var loggedIn = !!state.user;
    var failed = !!state.authFatal;
    var copy = failed ? state.authFatal + ' Khu vực kỹ thuật tiếp tục được khóa.' : state.authReady ? (loggedIn ? 'Phiên đăng nhập đã được xác nhận. Dữ liệu kỹ thuật của ' + area + ' sẽ được chuyển sang bộ dựng hợp nhất ở giai đoạn kế tiếp.' : 'Đăng nhập để tạo DS mã theo dõi của bạn. Khu vực kỹ thuật không được dựng trước khi quyền truy cập được xác nhận.') : 'Đang xác nhận phiên đăng nhập. Không có dữ liệu kỹ thuật nào được dựng trong trạng thái này.';
    var title = failed ? 'Không xác nhận được phiên' : state.authReady ? (loggedIn ? 'Đã xác nhận tài khoản' : 'Chưa đăng nhập') : 'Đang xác nhận quyền truy cập';
    return '<section class="panel safe-state"><span class="safe-icon">' + icon("shield") + '</span><div><span class="eyebrow">TRẠNG THÁI AN TOÀN</span><h2>' + title + '</h2><p>' + esc(copy) + '</p>' + (!loggedIn && state.authReady && !failed ? '<button class="button primary" type="button" data-open-login>Đăng nhập</button>' : failed ? '<button class="button secondary" type="button" data-reload>Thử tải lại</button>' : '') + '</div></section>';
  }

  function overviewPage() {
    var main;
    if (!state.authReady) main = overviewLoadingHtml();
    else if (state.overview.loading && !state.overview.data) main = overviewLoadingHtml();
    else if (state.overview.error && !state.overview.data) main = overviewErrorHtml();
    else if (!state.overview.data) main = overviewLoadingHtml();
    else main = overviewKpisHtml() + overviewResultsHtml();
    var rail = marketPulseRailHtml() + signalLegendRailHtml() + overviewTrustRailHtml();
    return pageFrame("NHỊP THỊ TRƯỜNG", "Tổng quan", "Theo dõi sức nóng toàn thị trường và tín hiệu trong DS mã theo dõi của bạn.", main, rail, "overview-page");
  }

  function scannerPage() {
    var count = state.watchlist.data && Array.isArray(state.watchlist.data.symbols) ? state.watchlist.data.symbols.length : 0;
    var main = '<section class="panel tab-panel"><div class="tabs" role="tablist" aria-label="Loại danh sách"><button class="active" type="button" role="tab" aria-selected="true">DS mã theo dõi</button><button type="button" role="tab" aria-selected="false" disabled>Toàn bộ thị trường</button></div>' + safeAccessCard("DS mã theo dõi") + '</section>' +
      '<section class="panel action-panel"><div><span class="eyebrow">QUẢN LÝ DANH SÁCH</span><h2>' + (state.user ? count + ' mã đang theo dõi' : 'Tạo DS mã theo dõi') + '</h2><p>Thêm, xóa và lưu danh sách tại trang Tài khoản. Quota và giới hạn luôn do backend hiện tại quyết định.</p></div><a class="button secondary" href="/tai-khoan#ds-ma-theo-doi">Mở DS mã theo dõi</a></section>';
    var rail = railCard("Quyền xem kỹ thuật", '<p>Logic 4 tín hiệu hiện hành được giữ nguyên. Dữ liệu chi tiết chỉ hiển thị sau khi quyền truy cập được xác nhận.</p>') +
      railCard("Toàn bộ thị trường", '<p>Tab dữ liệu cơ bản toàn thị trường đang được nối vào runtime hợp nhất; không dùng dữ liệu kỹ thuật ngoài quyền làm phương án thay thế.</p>');
    return pageFrame("THEO DÕI THỊ TRƯỜNG", "DS mã theo dõi", "Theo dõi các mã của bạn hoặc xem dữ liệu cơ bản của toàn bộ thị trường.", main, rail, "scanner-page");
  }

  function researchTabs() {
    return '<nav class="research-tabs" aria-label="Điều hướng Nghiên cứu"><a href="/so-sanh-theo-nganh"' + (state.route === "industry" ? ' class="active" aria-current="page"' : '') + '>Theo ngành</a><a href="/sang-loc-co-ban"' + (state.route === "fundamental" ? ' class="active" aria-current="page"' : '') + '>Sàng lọc cơ bản</a></nav>';
  }

  function researchStatus() {
    if (state.research.loading) return '<section class="panel loading-state" role="status"><span class="spinner"></span><div><strong>Đang tải dữ liệu cơ bản…</strong><p>Nội dung hiện tại được giữ trong vùng có kích thước ổn định.</p></div></section>';
    if (state.research.error) return '<section class="panel error-state" role="alert"><strong>Không tải được dữ liệu nghiên cứu.</strong><p>' + esc(state.research.error) + '</p><button class="button secondary" type="button" data-retry-research>Thử lại</button></section>';
    return "";
  }

  function median(values) {
    var sorted = values.filter(function (value) { return value !== null && Number.isFinite(value); }).sort(function (a, b) { return a - b; });
    if (!sorted.length) return null;
    var middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function valuationScore(value, industryMedian, maxPoint) {
    if (value === null || industryMedian === null || value <= 0 || industryMedian <= 0) return null;
    var ratio = value / industryMedian;
    if (ratio <= .8) return maxPoint;
    if (ratio <= 1) return Math.round(maxPoint * .8);
    if (ratio <= 1.2) return Math.round(maxPoint * .6);
    if (ratio <= 1.5) return Math.round(maxPoint * .35);
    return Math.max(1, Math.round(maxPoint * .15));
  }

  function score(row) {
    if (!row || row.data_status === "NO_FINANCIAL_DATA") return { earned: 0, available: 0, ratio: null };
    var earned = 0;
    var available = 0;
    function add(max, value) { if (value === null) return; available += max; earned += Math.max(0, Math.min(max, value)); }
    var profit = num(row.profit_yoy_pct);
    add(20, profit === null ? null : profit >= 30 ? 20 : profit >= 20 ? 16 : profit >= 10 ? 12 : profit >= 0 ? 7 : 0);
    var revenue = num(row.income_yoy_pct);
    add(10, revenue === null ? null : revenue >= 20 ? 10 : revenue >= 10 ? 8 : revenue >= 5 ? 5 : revenue >= 0 ? 3 : 0);
    var qoq = num(row.profit_qoq_pct);
    add(5, qoq === null ? null : qoq >= 20 ? 5 : qoq >= 10 ? 4 : qoq >= 0 ? 3 : qoq > -10 ? 1 : 0);
    var roe = num(row.roea_pct);
    add(20, roe === null ? null : roe >= 20 ? 20 : roe >= 15 ? 16 : roe >= 10 ? 11 : roe >= 5 ? 6 : roe >= 0 ? 2 : 0);
    var roa = num(row.roaa_pct);
    add(10, roa === null ? null : roa >= 10 ? 10 : roa >= 7 ? 8 : roa >= 5 ? 6 : roa >= 2 ? 3 : roa >= 0 ? 1 : 0);
    var debtEquity = num(row.debt_equity_pct);
    var debtAssets = num(row.debt_assets_pct);
    if (row.financial_model === "NORMAL") {
      add(10, debtEquity === null ? null : debtEquity < 30 ? 10 : debtEquity < 60 ? 8 : debtEquity < 100 ? 5 : debtEquity < 150 ? 2 : 0);
      add(10, debtAssets === null ? null : debtAssets < 30 ? 10 : debtAssets < 45 ? 8 : debtAssets < 60 ? 5 : debtAssets < 75 ? 2 : 0);
    }
    var pe = num(row.pe);
    var pb = num(row.pb);
    var peers = state.research.financial.filter(function (item) { return item.website_group === row.website_group; });
    add(8, valuationScore(pe, median(peers.map(function (item) { return num(item.pe); })), 8));
    add(7, valuationScore(pb, median(peers.map(function (item) { return num(item.pb); })), 7));
    return { earned: earned, available: available, ratio: available ? earned / available * 100 : null };
  }

  function scoreBadge(row) {
    var result = score(row);
    if (!result.available) return '<span class="score-badge muted">Chưa đủ dữ liệu</span>';
    var label = result.earned + '/' + result.available;
    var cls = result.ratio >= 75 ? "good" : result.ratio >= 55 ? "mid" : "low";
    return '<span class="score-badge ' + cls + '" title="Điểm đạt ' + label + ' điểm có thể chấm">' + label + '</span>';
  }

  function financialRows() {
    return state.research.financial.slice().sort(function (a, b) {
      var sa = score(a).ratio;
      var sb = score(b).ratio;
      return (sb == null ? -1 : sb) - (sa == null ? -1 : sa) || String(a.symbol).localeCompare(String(b.symbol));
    });
  }

  function freshnessLabel(value) {
    var key = String(value || "").toUpperCase();
    if (key === "CURRENT") return "Mới nhất";
    if (key === "LAGGING") return "Chậm 1 kỳ";
    if (key === "STALE") return "Dữ liệu cũ";
    return "Chưa rõ";
  }

  function freshnessClass(value) {
    var key = String(value || "").toUpperCase();
    return key === "CURRENT" ? "fresh" : key === "LAGGING" ? "lagging" : key === "STALE" ? "stale" : "unknown";
  }

  function financialIdentity(row) {
    var meta = state.research.metadata[String(row.symbol || "").toUpperCase()] || {};
    var company = meta.display_name || meta.company_name || row.website_group || 'Tên công ty đang cập nhật';
    return '<div class="research-identity">' + logoHtml(row.symbol) + '<div><strong>' + esc(row.symbol) + '</strong><span title="' + esc(company) + '">' + esc(company) + '</span><small>' + esc(row.website_group || '') + '</small></div></div>';
  }

  function financialCard(row) {
    var result = score(row);
    return '<article class="financial-card">' +
      '<header>' + financialIdentity(row) + scoreBadge(row) + '</header>' +
      '<div class="metric-grid"><div><small>LNST so cùng kỳ</small><b class="' + tone(row.profit_yoy_pct) + '">' + pct(row.profit_yoy_pct) + '</b></div><div><small>ROE</small><b>' + pct(row.roea_pct) + '</b></div><div><small>P/E</small><b>' + (num(row.pe) === null ? '—' : num(row.pe).toFixed(2) + 'x') + '</b></div><div><small>P/B</small><b>' + (num(row.pb) === null ? '—' : num(row.pb).toFixed(2) + 'x') + '</b></div></div>' +
      '<footer><span>Điểm ' + result.earned + '/' + result.available + '</span><span class="freshness-tag ' + freshnessClass(row.freshness_status) + '">' + esc(freshnessLabel(row.freshness_status)) + '</span></footer>' +
    '</article>';
  }

  function financialTableHtml(rows) {
    return '<div class="financial-table-wrap"><table class="financial-table"><thead><tr>' +
      '<th>Doanh nghiệp</th><th>Điểm cơ bản</th><th>LNST YoY</th><th>ROE</th><th>ROA</th><th>P/E</th><th>P/B</th><th>Dữ liệu</th>' +
      '</tr></thead><tbody>' + rows.map(function (row) {
        return '<tr><td>' + financialIdentity(row) + '</td><td>' + scoreBadge(row) + '</td><td class="' + tone(row.profit_yoy_pct) + '">' + pct(row.profit_yoy_pct) + '</td><td>' + pct(row.roea_pct) + '</td><td>' + pct(row.roaa_pct) + '</td><td>' + (num(row.pe) === null ? '—' : num(row.pe).toFixed(2) + 'x') + '</td><td>' + (num(row.pb) === null ? '—' : num(row.pb).toFixed(2) + 'x') + '</td><td><span class="freshness-tag ' + freshnessClass(row.freshness_status) + '">' + esc(freshnessLabel(row.freshness_status)) + '</span></td></tr>';
      }).join("") + '</tbody></table></div><div class="financial-mobile-list">' + rows.map(financialCard).join("") + '</div>';
  }

  function industryPage() {
    var groups = Object.create(null);
    state.research.financial.forEach(function (row) {
      var group = row.website_group || "Khác";
      groups[group] = (groups[group] || 0) + 1;
    });
    var names = Object.keys(groups).sort(function (a, b) { return groups[b] - groups[a] || a.localeCompare(b, "vi"); });
    if (!state.industry && names.length) state.industry = names[0];
    var rows = financialRows().filter(function (row) { return (row.website_group || "Khác") === state.industry; });
    var chips = names.map(function (name) { return '<button class="chip' + (name === state.industry ? ' active' : '') + '" type="button" data-industry="' + esc(name) + '"><span>' + esc(name) + '</span><b>' + groups[name] + '</b></button>'; }).join("");
    var content = researchTabs() + researchStatus();
    if (state.research.loaded) content += '<section class="panel research-selector-panel"><div class="chip-list industry-chip-list">' + chips + '</div></section><section class="panel research-results-panel"><div class="section-heading"><div><span class="eyebrow">NHÓM ĐANG XEM</span><h2>' + esc(state.industry || 'Ngành') + '</h2></div><b>' + rows.length + ' mã</b></div>' + financialTableHtml(rows) + '</section>';
    var rail = railCard("Research công khai", '<p>Dữ liệu cơ bản không chứa CCC Technical Intelligence và không phụ thuộc gói thành viên.</p>', "PUBLIC") + railCard("Điểm có độ phủ", '<p>Điểm luôn hiển thị dạng điểm đạt / điểm có thể chấm. Không quy đổi dữ liệu thiếu thành 100.</p>');
    return pageFrame("NGHIÊN CỨU CƠ BẢN", "So sánh theo ngành", "Đặt các doanh nghiệp cùng ngành cạnh nhau theo dữ liệu tài chính hiện có.", content, rail, "research-page");
  }

  function passesFilters(row) {
    var result = score(row);
    if (state.filters.score && (result.ratio == null || result.ratio < state.filters.score)) return false;
    var growth = num(row.profit_yoy_pct);
    if (state.filters.growth === "positive" && !(growth !== null && growth > 0)) return false;
    if (state.filters.growth === "20plus" && !(growth !== null && growth >= 20)) return false;
    var roe = num(row.roea_pct);
    if (state.filters.roe === "15plus" && !(roe !== null && roe >= 15)) return false;
    if (state.filters.roe === "20plus" && !(roe !== null && roe >= 20)) return false;
    return true;
  }

  function filterButtons(kind, options, current) {
    return options.map(function (option) { return '<button class="chip' + (String(option[0]) === String(current) ? ' active' : '') + '" type="button" data-filter="' + kind + '" data-value="' + esc(option[0]) + '">' + esc(option[1]) + '</button>'; }).join("");
  }

  function fundamentalPage() {
    var rows = financialRows().filter(passesFilters);
    var shownRows = rows.slice(0, state.researchShown);
    var content = researchTabs() + researchStatus();
    if (state.research.loaded) content += '<section class="panel filter-panel"><div><label>Mức điểm trên phần có thể chấm</label><div class="chip-list">' + filterButtons("score", [[0,"Tất cả"],[55,"Từ 55%"],[70,"Từ 70%"],[80,"Từ 80%"]], state.filters.score) + '</div></div><div><label>Tăng trưởng lợi nhuận</label><div class="chip-list">' + filterButtons("growth", [["all","Tất cả"],["positive","Tăng dương"],["20plus","Từ 20%"]], state.filters.growth) + '</div></div><div><label>ROE</label><div class="chip-list">' + filterButtons("roe", [["all","Tất cả"],["15plus","Từ 15%"],["20plus","Từ 20%"]], state.filters.roe) + '</div></div></section><section class="panel research-results-panel"><div class="section-heading"><div><span class="eyebrow">KẾT QUẢ</span><h2>Doanh nghiệp phù hợp</h2></div><b>' + rows.length + '/' + state.research.financial.length + ' mã</b></div>' + financialTableHtml(shownRows) + (shownRows.length < rows.length ? '<div class="load-more"><span>Đang hiển thị ' + shownRows.length + '/' + rows.length + ' mã</span><button class="button secondary" type="button" data-research-more>Xem thêm</button></div>' : '') + '</section>';
    var rail = railCard("Phương pháp", '<p>Tăng trưởng tối đa 35đ · hiệu quả 30đ · sức khỏe tài chính 20đ · định giá 15đ.</p>') + railCard("Lưu ý", '<p>Điểm hỗ trợ học và sàng lọc ban đầu, không phải khuyến nghị mua hoặc bán.</p>');
    return pageFrame("NGHIÊN CỨU CƠ BẢN", "Sàng lọc cơ bản", "Tìm doanh nghiệp theo tăng trưởng, hiệu quả sinh lời và điểm trên phần dữ liệu hiện có.", content, rail, "research-page");
  }

  function scopeLabel(plan) {
    if (!plan) return "—";
    if (plan.full_market_access) return "Toàn thị trường";
    return plan.view_limit == null ? "—" : plan.view_limit + " mã";
  }

  function remainingLabel(plan, subscription) {
    if (!plan || !subscription) return "—";
    if (plan.change_limit == null) return "Không giới hạn";
    return Math.max(0, Number(plan.change_limit || 0) - Number(subscription.change_used || 0)) + "/" + Number(plan.change_limit || 0);
  }

  function providerLabel() {
    if (!state.user) return "—";
    return String((state.user.app_metadata || {}).provider || "email").toLowerCase() === "google" ? "Google" : "Email & mật khẩu";
  }

  function accountLoading() {
    return '<section class="panel loading-state account-loading" role="status"><span class="spinner"></span><div><strong>Đang tải tài khoản…</strong><p>Đang xác nhận hồ sơ, gói thành viên và DS mã theo dõi.</p></div></section>';
  }

  function profileCard() {
    var profile = state.membership.profile || {};
    var meta = state.user.user_metadata || {};
    var displayName = profile.display_name || meta.full_name || meta.name || "";
    var setup = !profile.profile_completed || new URLSearchParams(location.search).get("setup") === "1";
    var message = state.profile.error ? '<div class="form-message error" role="alert">' + esc(state.profile.error) + '</div>' : state.profile.notice ? '<div class="form-message success" role="status">' + esc(state.profile.notice) + '</div>' : '';
    return '<section class="panel account-card profile-card"><header class="card-header"><div><span class="eyebrow">' + (setup ? 'THIẾT LẬP LẦN ĐẦU' : 'HỒ SƠ CÁ NHÂN') + '</span><h2>' + (setup ? 'Hoàn tất hồ sơ hội viên' : 'Thông tin cá nhân') + '</h2><p>Cập nhật thông tin liên hệ của bạn.</p></div><span class="status ' + (profile.profile_completed ? 'ok' : 'pending') + '">' + (profile.profile_completed ? 'Đã hoàn tất' : 'Cần bổ sung') + '</span></header>' + message + '<form id="profile-form" class="form-grid" novalidate><label class="full">Email<input type="email" value="' + esc(state.user.email || '') + '" readonly><small>Email được quản lý bởi tài khoản đăng nhập.</small></label><label>Họ và tên <b>*</b><input name="display_name" type="text" minlength="2" maxlength="100" autocomplete="name" value="' + esc(displayName) + '" required></label><label>Số điện thoại <b>*</b><input name="phone" type="tel" inputmode="tel" autocomplete="tel" maxlength="30" value="' + esc(profile.phone || '') + '" required></label><label class="full">Địa chỉ <span>(không bắt buộc)</span><textarea name="address" rows="3" maxlength="500" autocomplete="street-address">' + esc(profile.address || '') + '</textarea></label><div class="full form-actions"><button class="button primary" type="submit"' + (state.profile.saving ? ' disabled' : '') + '>' + (state.profile.saving ? 'Đang lưu…' : 'Lưu hồ sơ') + '</button></div></form></section>';
  }

  function uniqueSorted(values) {
    var seen = Object.create(null);
    return (values || []).map(function (value) { return String(value || "").trim().toUpperCase(); }).filter(function (value) { if (!value || seen[value]) return false; seen[value] = true; return true; }).sort();
  }

  function arraysEqual(left, right) {
    var a = uniqueSorted(left), b = uniqueSorted(right);
    return a.length === b.length && a.every(function (value, index) { return value === b[index]; });
  }

  function watchlistFriendlyError(error) {
    var message = String(error && error.message || error || "");
    if (message.indexOf("WATCHLIST_LIMIT_EXCEEDED") >= 0) return "Số mã vượt giới hạn của gói hiện tại.";
    if (message.indexOf("CHANGE_QUOTA_EXCEEDED") >= 0) return "Không đủ lượt đổi mã để thực hiện thay đổi này.";
    if (message.indexOf("INVALID_SYMBOL") >= 0) return "Có mã không thuộc danh sách scanner hiện tại.";
    if (message.indexOf("SUBSCRIPTION_SUSPENDED") >= 0) return "Tài khoản đang tạm ngưng quyền thay đổi DS mã theo dõi.";
    if (message.indexOf("NO_CURRENT_SUBSCRIPTION") >= 0) return "Không tìm thấy gói thành viên đang hoạt động.";
    if (message.indexOf("AUTH_REQUIRED") >= 0) return "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.";
    return "Không cập nhật được DS mã theo dõi. Vui lòng thử lại.";
  }

  function watchlistCard() {
    var wl = state.watchlist;
    if (wl.loading && !wl.data) return '<section id="ds-ma-theo-doi" class="panel account-card"><header class="card-header"><div><span class="eyebrow">DS MÃ THEO DÕI & LƯỢT ĐỔI</span><h2>Danh sách mã theo dõi</h2></div><span class="status pending">Đang tải</span></header><div class="loading-state compact"><span class="spinner"></span><strong>Đang tải…</strong></div></section>';
    if (!wl.data) return '<section id="ds-ma-theo-doi" class="panel account-card"><header class="card-header"><div><span class="eyebrow">DS MÃ THEO DÕI & LƯỢT ĐỔI</span><h2>Danh sách mã theo dõi</h2><p>Quản lý các mã theo gói hiện tại.</p></div><span class="status pending">Chưa sẵn sàng</span></header>' + (wl.error ? '<div class="form-message error" role="alert">' + esc(wl.error) + '</div>' : '') + '<button class="button secondary" type="button" data-watchlist-retry>Thử lại</button></section>';
    var data = wl.data;
    var limit = data.watchlist_limit == null ? null : Number(data.watchlist_limit);
    var remaining = data.change_remaining == null ? null : Number(data.change_remaining);
    var dirty = !arraysEqual(wl.original, wl.selected);
    var originalMap = Object.create(null);
    wl.original.forEach(function (symbol) { originalMap[symbol] = true; });
    var added = wl.selected.filter(function (symbol) { return !originalMap[symbol]; }).length;
    var selectedRows = wl.selected.length ? wl.selected.map(function (symbol) {
      var meta = wl.metadata[symbol] || {};
      return '<article class="watchlist-row"><div class="symbol-logo">' + esc(symbol.slice(0, 3)) + '</div><div><strong>' + esc(symbol) + '</strong><span>' + esc(meta.display_name || meta.company_name || 'Tên công ty đang cập nhật') + '</span><small>' + esc(meta.exchange || '') + '</small></div><button type="button" data-watchlist-remove="' + esc(symbol) + '" aria-label="Xóa ' + esc(symbol) + '">' + icon("close") + '</button></article>';
    }).join("") : '<div class="empty-state">Chưa có mã nào trong DS mã theo dõi.</div>';
    var selectedMap = Object.create(null);
    wl.selected.forEach(function (symbol) { selectedMap[symbol] = true; });
    var canAdd = limit == null || wl.selected.length < limit;
    var results = wl.searching ? '<div class="search-status">Đang tìm mã…</div>' : wl.query && !wl.results.length ? '<div class="search-status">Không tìm thấy mã hoặc tên công ty phù hợp.</div>' : wl.results.filter(function (item) { return !selectedMap[item.symbol]; }).map(function (item) { return '<button class="search-result" type="button" data-watchlist-add="' + esc(item.symbol) + '"' + (canAdd ? '' : ' disabled') + '><span><strong>' + esc(item.symbol) + '</strong><small>' + esc(item.display_name || item.company_name || '') + '</small></span><b>+ Thêm</b></button>'; }).join("");
    var banner = data.status === "GRACE" ? '<div class="watchlist-banner danger"><strong>Gói đang chờ gia hạn.</strong><span>DS được giữ đến ' + esc(formatDateTime(data.grace_end_at)) + '.</span></div>' : data.setup_active ? '<div class="watchlist-banner info"><strong>7 ngày khởi tạo miễn phí.</strong><span>Có thể thêm mã đến giới hạn gói mà chưa trừ lượt đổi đến ' + esc(formatDateTime(data.setup_window_end)) + '.</span></div>' : '';
    var feedback = wl.error ? '<div class="form-message error" role="alert">' + esc(wl.error) + '</div>' : wl.notice ? '<div class="form-message success" role="status">' + esc(wl.notice) + '</div>' : '';
    var quotaWarning = !data.setup_active && !data.full_market_access && remaining != null && added > remaining ? '<div class="form-message error">Bạn đang thêm ' + added + ' mã nhưng chỉ còn ' + remaining + ' lượt đổi. Hệ thống sẽ không lưu một phần.</div>' : '';
    return '<section id="ds-ma-theo-doi" class="panel account-card watchlist-card"><header class="card-header"><div><span class="eyebrow">DS MÃ THEO DÕI & LƯỢT ĐỔI</span><h2>Danh sách mã theo dõi</h2><p>Backend hiện tại quyết định quota, capacity và kết quả lưu.</p></div><span class="status ' + (data.status === 'GRACE' ? 'pending' : 'ok') + '">' + (data.status === 'GRACE' ? 'Chờ gia hạn' : data.setup_active ? 'Đang khởi tạo' : 'Đang hoạt động') + '</span></header><div class="watchlist-metrics"><div><span>Đang theo dõi</span><strong>' + wl.selected.length + (limit == null ? '' : '/' + limit) + '</strong></div><div><span>Lượt đổi còn lại</span><strong>' + (data.change_limit == null ? 'Không giới hạn' : Number(data.change_remaining || 0) + '/' + Number(data.change_limit || 0)) + '</strong></div><div><span>Reset tiếp theo</span><strong>' + esc(formatDate(data.cycle_end)) + '</strong></div></div>' + banner + feedback + quotaWarning + '<div class="watchlist-editor"><label for="watchlist-search">Thêm mã vào DS theo dõi</label><div class="search-wrap"><input id="watchlist-search" type="search" inputmode="search" autocomplete="off" placeholder="Gõ mã hoặc tên công ty, ví dụ VIC…" value="' + esc(wl.query) + '"' + (canAdd ? '' : ' disabled') + '><div class="search-results">' + results + '</div></div><div class="watchlist-list-head"><span>Mã đang theo dõi</span><small>' + (dirty ? 'Có thay đổi chưa lưu' : 'Chưa có thay đổi') + '</small></div><div class="watchlist-list">' + selectedRows + '</div></div><div class="watchlist-actions"><button class="button secondary" type="button" data-watchlist-reset' + (!dirty || wl.saving ? ' disabled' : '') + '>Hoàn tác</button><button class="button primary" type="button" data-watchlist-save' + (!dirty || wl.saving ? ' disabled' : '') + '>' + (wl.saving ? 'Đang lưu…' : 'Lưu DS mã theo dõi') + '</button></div><p class="rule-note">Xóa mã không trừ lượt. Sau thời gian miễn phí, mỗi mã mới thêm dùng 1 lượt đổi; xóa rồi thêm lại cùng mã vẫn tính 1.</p></section>';
  }

  function membershipCard() {
    var membership = state.membership;
    if (membership.error) return railCard("Gói thành viên", '<div class="form-message error" role="alert">' + esc(membership.error) + '</div>');
    var plan = membership.plan, sub = membership.subscription;
    if (!plan || !sub) return railCard("Gói thành viên", '<p>Chưa có dữ liệu gói hoạt động.</p>', "—");
    var alternatives = membership.catalog.filter(function (item) { return String(item.plan_code) !== String(plan.plan_code); });
    var selected = alternatives.find(function (item) { return String(item.plan_code) === state.planPreview; });
    var choices = alternatives.map(function (item) { return '<button type="button" class="plan-choice' + (selected === item ? ' active' : '') + '" data-plan-preview="' + esc(item.plan_code) + '"><span>' + esc(item.display_name || item.plan_code) + '</span><strong>' + (Number(item.price_vnd || 0) ? Number(item.price_vnd).toLocaleString('vi-VN') + 'đ' : 'Miễn phí') + '</strong></button>'; }).join("");
    var subscriptionStatus = String(sub.status || "").toUpperCase();
    var statusText = subscriptionStatus === "GRACE" ? "Chờ gia hạn" : subscriptionStatus === "SUSPENDED" ? "Tạm ngưng" : "Đang hoạt động";
    var statusClass = subscriptionStatus === "ACTIVE" ? "ok" : "pending";
    var graceRow = subscriptionStatus === "GRACE" ? '<div><dt>Gia hạn đến</dt><dd>' + esc(formatDateTime(sub.grace_end_at)) + '</dd></div>' : '';
    return '<section id="goi-thanh-vien" class="rail-card membership-card"><header><span>GÓI HIỆN TẠI · ' + esc(plan.plan_code) + '</span><b class="status ' + statusClass + '">' + statusText + '</b></header><h2>' + esc(plan.display_name || plan.plan_code) + '</h2><dl class="rail-list"><div><dt>Quyền CCC</dt><dd>' + esc(scopeLabel(plan)) + '</dd></div><div><dt>Lượt đổi còn lại</dt><dd>' + esc(remainingLabel(plan, sub)) + '</dd></div><div><dt>Chu kỳ</dt><dd>' + esc(formatDate(sub.cycle_end)) + '</dd></div>' + graceRow + '</dl>' + (choices ? '<details class="plan-explorer"><summary>Xem các gói khác</summary><div>' + choices + '</div>' + (selected ? '<p><strong>' + esc(selected.display_name || selected.plan_code) + '</strong><br>Quyền: ' + esc(scopeLabel(selected)) + ' · Thanh toán chưa mở trong bước này.</p>' : '') + '</details>' : '') + '</section>';
  }

  function securityCard() {
    return railCard("Đăng nhập & phiên", '<dl class="rail-list"><div><dt>Phương thức</dt><dd>' + esc(providerLabel()) + '</dd></div><div><dt>Trạng thái</dt><dd>Đang hoạt động</dd></div></dl><button class="button danger full" type="button" data-logout>Đăng xuất</button>');
  }

  function accountPage() {
    var main, rail;
    if (!state.authReady) {
      main = accountLoading();
      rail = railCard("Quyền riêng tư", '<p>Không dựng hồ sơ, gói hoặc DS mã theo dõi trước khi phiên được xác nhận.</p>');
    } else if (state.authFatal) {
      main = '<section class="panel error-state" role="alert"><strong>Không xác nhận được phiên đăng nhập.</strong><p>' + esc(state.authFatal) + '</p><button class="button secondary" type="button" data-reload>Thử tải lại</button></section>';
      rail = railCard("Trạng thái an toàn", '<p>Hồ sơ, gói và DS mã theo dõi không được dựng khi thư viện xác thực gặp lỗi.</p>');
    } else if (!state.user) {
      main = '<section class="panel account-empty"><span class="safe-icon">' + icon("user") + '</span><h2>Bạn chưa đăng nhập</h2><p>Đăng nhập bằng Google hoặc Email để quản lý hồ sơ và DS mã theo dõi.</p><button class="button primary" type="button" data-open-login>Đăng nhập</button></section>';
      rail = railCard("Tài khoản CCC", '<p>Một tài khoản dùng cho hồ sơ, gói thành viên và DS mã theo dõi.</p>');
    } else if (state.membership.loading && !state.membership.profile) {
      main = accountLoading();
      rail = railCard("Phiên đăng nhập", '<p>' + esc(state.user.email || '') + '</p>', "OK");
    } else {
      main = profileCard() + '<div id="watchlist-region">' + watchlistCard() + '</div>';
      rail = membershipCard() + securityCard();
    }
    return pageFrame("CCC ACCOUNT", "Tài khoản", "Quản lý hồ sơ, gói thành viên và thiết lập cá nhân.", main, rail, "account-page");
  }

  function renderRoute(options) {
    state.route = routeFromLocation();
    updateNavigation();
    var host = document.getElementById("route-host");
    if (!host) return;
    if (state.route === "scanner") host.innerHTML = scannerPage();
    else if (state.route === "industry") host.innerHTML = industryPage();
    else if (state.route === "fundamental") host.innerHTML = fundamentalPage();
    else if (state.route === "account") host.innerHTML = accountPage();
    else host.innerHTML = overviewPage();
    updateAccountTrigger();
    if (state.route === "industry" || state.route === "fundamental") ensureResearch(false);
    if (state.route === "overview") { ensureOverview(false); ensureMarketPulse(false); }
    if ((state.route === "account" || state.route === "scanner") && state.user) ensureWatchlist(false);
    if (state.route === "account" && location.hash) {
      requestAnimationFrame(function () {
        var target = document.querySelector(location.hash);
        if (target) target.scrollIntoView({ block: "start", behavior: "auto" });
      });
    }
    if (options && options.focus) {
      requestAnimationFrame(function () { var main = document.getElementById("main-content"); if (main) main.focus({ preventScroll: true }); });
    }
  }

  function renderWatchlistRegion(refocus) {
    var region = document.getElementById("watchlist-region");
    if (!region) return;
    region.innerHTML = watchlistCard();
    if (refocus) requestAnimationFrame(function () {
      var input = document.getElementById("watchlist-search");
      if (input) { input.focus(); try { input.setSelectionRange(input.value.length, input.value.length); } catch (_) {} }
    });
  }

  function renderAuthDialog() {
    var host = document.getElementById("dialog-host");
    if (!host) return;
    if (!state.authDialogOpen) {
      host.innerHTML = "";
      document.body.classList.remove("modal-open");
      return;
    }
    document.body.classList.add("modal-open");
    var feedback = state.authFatal ? '<div class="form-message error" role="alert">' + esc(state.authFatal) + '</div>' : state.authError ? '<div class="form-message error" role="alert">' + esc(state.authError) + '</div>' : '';
    var content = state.user ? '<div class="current-user"><span class="account-avatar large">' + esc(userLabel().charAt(0).toUpperCase()) + '</span><div><strong>' + esc(userLabel()) + '</strong><p>' + esc(state.user.email || '') + '</p></div></div><a class="button primary full" href="/tai-khoan">Mở trang Tài khoản</a><button class="button danger full" type="button" data-logout>Đăng xuất</button>' : '<button class="google-button" type="button" data-google-login' + (state.authBusy || state.authFatal ? ' disabled' : '') + '><span aria-hidden="true">G</span>Tiếp tục với Google</button><div class="dialog-divider"><span>hoặc đăng nhập bằng email</span></div><form id="email-login-form" class="login-form" novalidate><label>Email<input name="email" type="email" autocomplete="email" inputmode="email" required' + (state.authBusy || state.authFatal ? ' disabled' : '') + '></label><label>Mật khẩu<input name="password" type="password" autocomplete="current-password" minlength="8" required' + (state.authBusy || state.authFatal ? ' disabled' : '') + '></label><button class="button primary full" type="submit"' + (state.authBusy || state.authFatal ? ' disabled' : '') + '>' + (state.authBusy ? 'Đang xử lý…' : 'Đăng nhập') + '</button></form>';
    host.innerHTML = '<div class="dialog-overlay" data-dialog-overlay><section class="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title"><header><div><span class="eyebrow">CCC ACCOUNT</span><h2 id="auth-title">' + (state.user ? 'Tài khoản của bạn' : 'Đăng nhập') + '</h2><p>' + (state.user ? 'Bạn đã đăng nhập vào Chuyện Chợ Chứng.' : 'Đăng nhập để sử dụng DS mã theo dõi và gói thành viên của bạn.') + '</p></div><button class="icon-button" type="button" data-close-dialog aria-label="Đóng cửa sổ">' + icon("close") + '</button></header>' + feedback + '<div class="dialog-body">' + content + '</div></section></div>';
  }

  function openLogin() {
    lastFocused = document.activeElement;
    state.authDialogOpen = true;
    state.authError = "";
    renderAuthDialog();
    requestAnimationFrame(function () { var target = document.querySelector('[data-google-login], .auth-dialog button'); if (target) target.focus(); });
  }

  function closeDialog() {
    state.authDialogOpen = false;
    state.authError = "";
    renderAuthDialog();
    if (lastFocused && typeof lastFocused.focus === "function") requestAnimationFrame(function () { lastFocused.focus(); });
  }

  function friendlyAuthError(error) {
    var message = String(error && error.message || "Không thể đăng nhập lúc này.");
    var lower = message.toLowerCase();
    if (lower.indexOf("invalid login credentials") >= 0) return "Email hoặc mật khẩu chưa đúng.";
    if (lower.indexOf("email not confirmed") >= 0) return "Email chưa được xác nhận. Vui lòng kiểm tra hộp thư.";
    if (lower.indexOf("rate limit") >= 0) return "Bạn thao tác quá nhanh. Vui lòng thử lại sau ít phút.";
    return message;
  }

  async function hydrateMembership(user) {
    if (!user) return;
    var userId = user.id;
    state.membership.loading = true;
    state.membership.error = "";
    if (state.route === "account") renderRoute();
    try {
      var data = await window.CCCData.loadMembership(userId);
      if (!state.user || state.user.id !== userId) return;
      state.membership.profile = data.profile;
      state.membership.subscription = data.subscription;
      state.membership.plan = data.plan;
      state.membership.catalog = data.catalog;
      if (!data.subscription || !data.plan) state.membership.error = "Không tìm thấy gói thành viên đang hoạt động. Vui lòng liên hệ quản trị viên.";
      if (data.profile && !data.profile.profile_completed && state.route !== "account") {
        navigate(ACCOUNT_PATH + "?setup=1", false);
      }
    } catch (error) {
      if (state.user && state.user.id === userId) state.membership.error = "Không tải được hồ sơ hoặc gói thành viên. Vui lòng thử lại.";
      console.error("CCC membership load failed", error);
    } finally {
      if (state.user && state.user.id === userId) {
        state.membership.loading = false;
        updateAccountTrigger();
        if (state.route === "account" || state.route === "overview") renderRoute();
      }
    }
  }

  function resetMemberState() {
    state.membership = { loading: false, error: "", profile: null, subscription: null, plan: null, catalog: [] };
    state.profile = { saving: false, error: "", notice: "" };
    state.watchlist = { loading: false, saving: false, loadedFor: "", data: null, original: [], selected: [], metadata: Object.create(null), query: "", searching: false, results: [], searchSeq: 0, error: "", notice: "" };
    state.planPreview = "";
  }

  async function applySession(session, source) {
    var oldId = state.user ? state.user.id : "";
    var nextUser = session && session.user ? session.user : null;
    var nextId = nextUser ? nextUser.id : "";
    state.session = session || null;
    state.user = nextUser;
    state.authReady = true;
    if (oldId !== nextId) {
      resetMemberState();
      state.overview = { loading: false, error: "", loadedFor: "", data: null, group: "", page: 1, mobileShown: OVERVIEW_MOBILE_CHUNK };
    }
    updateAccountTrigger();
    renderRoute();
    if (nextUser && (!state.membership.profile || oldId !== nextId || source === "bootstrap")) await hydrateMembership(nextUser);
  }

  async function ensureWatchlist(force) {
    if (!state.user || state.watchlist.loading) return;
    var wl = state.watchlist;
    if (!force && wl.loadedFor === state.user.id) return;
    wl.loading = true;
    wl.error = "";
    if (state.route === "account") renderWatchlistRegion(false);
    try {
      var data = await window.CCCData.getWatchlistState();
      if (!state.user) return;
      wl.data = data || null;
      wl.loadedFor = state.user.id;
      wl.original = uniqueSorted(data && data.symbols || []);
      wl.selected = wl.original.slice();
      wl.metadata = Object.create(null);
      (data && data.items || []).forEach(function (item) { if (item && item.symbol) wl.metadata[String(item.symbol).toUpperCase()] = item; });
      wl.query = "";
      wl.results = [];
    } catch (error) {
      wl.error = watchlistFriendlyError(error);
      wl.data = null;
      console.error("CCC watchlist load failed", error);
    } finally {
      if (state.user) wl.loadedFor = state.user.id;
      wl.loading = false;
      if (state.route === "account") renderWatchlistRegion(false);
      if (state.route === "scanner") renderRoute();
    }
  }

  async function saveWatchlist() {
    var wl = state.watchlist;
    if (wl.saving || !wl.data) return;
    wl.saving = true;
    wl.error = "";
    wl.notice = "";
    renderWatchlistRegion(false);
    try {
      var data = await window.CCCData.replaceWatchlist(uniqueSorted(wl.selected));
      wl.data = data || wl.data;
      wl.original = uniqueSorted(wl.data.symbols || wl.selected);
      wl.selected = wl.original.slice();
      (wl.data.items || []).forEach(function (item) { if (item && item.symbol) wl.metadata[String(item.symbol).toUpperCase()] = item; });
      wl.query = "";
      wl.results = [];
      wl.notice = "Đã lưu DS mã theo dõi thành công.";
      state.overview.loadedFor = "";
      state.overview.data = null;
    } catch (error) {
      wl.error = watchlistFriendlyError(error);
      console.error("CCC watchlist save failed", error);
    } finally {
      wl.saving = false;
      renderWatchlistRegion(false);
    }
  }

  async function runMetadataSearch(query, seq) {
    try {
      var results = await window.CCCData.searchMetadata(query);
      if (seq !== state.watchlist.searchSeq) return;
      state.watchlist.results = results;
      results.forEach(function (item) { state.watchlist.metadata[item.symbol] = item; });
    } catch (error) {
      if (seq === state.watchlist.searchSeq) {
        state.watchlist.results = [];
        state.watchlist.error = "Không tìm được mã lúc này. Vui lòng thử lại.";
      }
    } finally {
      if (seq === state.watchlist.searchSeq) {
        state.watchlist.searching = false;
        renderWatchlistRegion(true);
      }
    }
  }

  function scheduleMetadataSearch(value) {
    var wl = state.watchlist;
    wl.query = value || "";
    wl.error = "";
    wl.notice = "";
    if (searchTimer) clearTimeout(searchTimer);
    if (!wl.query.trim()) {
      wl.results = [];
      wl.searching = false;
      renderWatchlistRegion(true);
      return;
    }
    wl.searching = true;
    var seq = ++wl.searchSeq;
    searchTimer = setTimeout(function () { runMetadataSearch(wl.query, seq); }, 220);
  }

  async function ensureResearch(force) {
    if (state.research.loading || state.research.loaded && !force) return;
    state.research.loading = true;
    state.research.error = "";
    renderRoute();
    try {
      var data = await window.CCCData.loadResearch(force);
      state.research.financial = data.financial;
      state.research.metadata = Object.create(null);
      data.metadata.forEach(function (item) { state.research.metadata[String(item.symbol || "").toUpperCase()] = item; });
      state.research.loaded = true;
    } catch (error) {
      state.research.error = "Nguồn dữ liệu cơ bản phản hồi lỗi. Dữ liệu kỹ thuật không được dùng làm phương án thay thế.";
      console.error("CCC research load failed", error);
    } finally {
      state.research.loading = false;
      if (state.route === "industry" || state.route === "fundamental") renderRoute();
    }
  }

  function navigate(url, replace) {
    var next = new URL(url, location.origin);
    if (next.origin !== location.origin) return;
    if (replace) history.replaceState({ ccc: true }, "", next.pathname + next.search + next.hash);
    else history.pushState({ ccc: true }, "", next.pathname + next.search + next.hash);
    renderRoute({ focus: true });
    if (!next.hash) window.scrollTo({ top: 0, behavior: "auto" });
  }

  async function submitEmail(form) {
    if (state.authBusy) return;
    var data = new FormData(form);
    var email = String(data.get("email") || "").trim();
    var password = String(data.get("password") || "");
    if (!email || !password) { state.authError = "Vui lòng nhập đầy đủ email và mật khẩu."; renderAuthDialog(); return; }
    state.authBusy = true;
    state.authError = "";
    renderAuthDialog();
    try {
      var result = await window.CCCData.signInWithPassword(email, password);
      await applySession(result.session || null, "email");
      state.authDialogOpen = false;
    } catch (error) {
      state.authError = friendlyAuthError(error);
    } finally {
      state.authBusy = false;
      renderAuthDialog();
    }
  }

  async function googleLogin() {
    if (state.authBusy) return;
    state.authBusy = true;
    state.authError = "";
    renderAuthDialog();
    try {
      await window.CCCData.signInWithGoogle(location.origin + location.pathname + location.search + location.hash);
    } catch (error) {
      state.authBusy = false;
      state.authError = friendlyAuthError(error);
      renderAuthDialog();
    }
  }

  async function logout() {
    if (state.authBusy) return;
    state.authBusy = true;
    try {
      await window.CCCData.signOut();
      await applySession(null, "logout");
      state.authDialogOpen = false;
      if (state.route === "account") renderRoute();
    } catch (error) {
      state.authError = friendlyAuthError(error);
      if (!state.authDialogOpen) openLogin();
    } finally {
      state.authBusy = false;
      renderAuthDialog();
    }
  }

  async function saveProfile(form) {
    if (!state.user || state.profile.saving) return;
    var data = new FormData(form);
    var displayName = String(data.get("display_name") || "").trim();
    var phone = String(data.get("phone") || "").trim();
    var address = String(data.get("address") || "").trim();
    var digits = phone.replace(/[^0-9]/g, "");
    state.profile.error = "";
    state.profile.notice = "";
    if (displayName.length < 2 || displayName.length > 100) state.profile.error = "Họ và tên cần từ 2 đến 100 ký tự.";
    else if (digits.length < 8 || digits.length > 15) state.profile.error = "Số điện thoại chưa hợp lệ.";
    else if (address.length > 500) state.profile.error = "Địa chỉ tối đa 500 ký tự.";
    if (state.profile.error) { renderRoute(); return; }
    state.profile.saving = true;
    renderRoute();
    try {
      await window.CCCData.saveProfile(displayName, phone, address);
      await hydrateMembership(state.user);
      state.profile.notice = "Đã lưu hồ sơ thành công.";
      if (new URLSearchParams(location.search).get("setup") === "1") history.replaceState({}, "", ACCOUNT_PATH + location.hash);
    } catch (error) {
      var message = String(error && error.message || "");
      state.profile.error = message.indexOf("INVALID_DISPLAY_NAME") >= 0 ? "Họ và tên chưa hợp lệ." : message.indexOf("INVALID_PHONE") >= 0 ? "Số điện thoại chưa hợp lệ." : message.indexOf("ADDRESS_TOO_LONG") >= 0 ? "Địa chỉ quá dài." : "Không lưu được hồ sơ. Vui lòng thử lại.";
    } finally {
      state.profile.saving = false;
      renderRoute();
    }
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("a[href]");
    if (link && !link.hasAttribute("download") && link.target !== "_blank") {
      var url = new URL(link.href, location.origin);
      if (url.origin === location.origin) { event.preventDefault(); navigate(url.href, false); closeDialog(); return; }
    }
    var button = event.target.closest && event.target.closest("button");
    if (!button) return;
    if (button.id === "theme-toggle") {
      state.theme = state.theme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", state.theme);
      try { localStorage.setItem(THEME_KEY, state.theme); } catch (_) {}
      button.innerHTML = icon(state.theme === "dark" ? "sun" : "moon");
      return;
    }
    if (button.id === "account-open") { state.user ? navigate(ACCOUNT_PATH, false) : openLogin(); return; }
    if (button.matches("[data-open-login]")) { openLogin(); return; }
    if (button.matches("[data-reload]")) { location.reload(); return; }
    if (button.matches("[data-overview-retry]")) { ensureOverview(true); ensureMarketPulse(true); return; }
    if (button.dataset.overviewGroup != null) { state.overview.group = state.overview.group === button.dataset.overviewGroup ? "" : button.dataset.overviewGroup; state.overview.page = 1; state.overview.mobileShown = OVERVIEW_MOBILE_CHUNK; renderRoute(); return; }
    if (button.matches("[data-overview-reset]")) { state.overview.group = ""; state.overview.page = 1; state.overview.mobileShown = OVERVIEW_MOBILE_CHUNK; renderRoute(); return; }
    if (button.dataset.overviewPage != null) { state.overview.page = Math.max(1, state.overview.page + Number(button.dataset.overviewPage || 0)); renderRoute(); return; }
    if (button.matches("[data-overview-more]")) { state.overview.mobileShown += OVERVIEW_MOBILE_CHUNK; renderRoute(); return; }
    if (button.matches("[data-close-dialog]")) { closeDialog(); return; }
    if (button.matches("[data-google-login]")) { googleLogin(); return; }
    if (button.matches("[data-logout]")) { logout(); return; }
    if (button.matches("[data-retry-research]")) { ensureResearch(true); return; }
    if (button.dataset.industry != null) { state.industry = button.dataset.industry; renderRoute(); return; }
    if (button.dataset.filter) { var kind = button.dataset.filter; state.filters[kind] = kind === "score" ? Number(button.dataset.value) : button.dataset.value; state.researchShown = 50; renderRoute(); return; }
    if (button.matches("[data-research-more]")) { state.researchShown += 50; renderRoute(); return; }
    if (button.dataset.planPreview != null) { state.planPreview = button.dataset.planPreview; renderRoute(); return; }
    if (button.matches("[data-watchlist-retry]")) { ensureWatchlist(true); return; }
    if (button.dataset.watchlistAdd != null) {
      var symbol = String(button.dataset.watchlistAdd).toUpperCase();
      var limit = state.watchlist.data.watchlist_limit == null ? null : Number(state.watchlist.data.watchlist_limit);
      if (limit != null && state.watchlist.selected.length >= limit) state.watchlist.error = "DS mã theo dõi đã đạt giới hạn của gói hiện tại.";
      else if (state.watchlist.selected.indexOf(symbol) < 0) { state.watchlist.selected.push(symbol); state.watchlist.selected.sort(); state.watchlist.query = ""; state.watchlist.results = []; }
      renderWatchlistRegion(false); return;
    }
    if (button.dataset.watchlistRemove != null) { state.watchlist.selected = state.watchlist.selected.filter(function (item) { return item !== button.dataset.watchlistRemove; }); state.watchlist.error = ""; state.watchlist.notice = ""; renderWatchlistRegion(false); return; }
    if (button.matches("[data-watchlist-reset]")) { state.watchlist.selected = state.watchlist.original.slice(); state.watchlist.query = ""; state.watchlist.results = []; state.watchlist.error = ""; state.watchlist.notice = ""; renderWatchlistRegion(false); return; }
    if (button.matches("[data-watchlist-save]")) { saveWatchlist(); }
  });

  document.addEventListener("submit", function (event) {
    if (event.target.id === "email-login-form") { event.preventDefault(); submitEmail(event.target); }
    else if (event.target.id === "profile-form") { event.preventDefault(); saveProfile(event.target); }
  });

  document.addEventListener("input", function (event) {
    if (event.target.id === "watchlist-search") scheduleMetadataSearch(event.target.value);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && state.authDialogOpen) closeDialog();
  });

  document.addEventListener("mousedown", function (event) {
    if (event.target.matches && event.target.matches("[data-dialog-overlay]")) closeDialog();
  });

  window.addEventListener("popstate", function () { renderRoute({ focus: true }); });
  window.addEventListener("resize", function () { if (state.route === "overview" && state.overview.data) renderRoute(); });

  async function bootstrap() {
    mountShell();
    renderRoute();
    try {
      window.CCCData.init();
      var sessionData = await window.CCCData.getSession();
      await applySession(sessionData.session || null, "bootstrap");
      var authResult = window.CCCData.onAuthStateChange(function (event, session) {
        if (event === "INITIAL_SESSION") return;
        window.setTimeout(function () { applySession(session || null, event); }, 0);
      });
      authSubscription = authResult && authResult.data ? authResult.data.subscription : null;
      var warmResearch = function () {
        if (state.research.loaded || state.research.loading) return;
        window.CCCData.loadResearch(false).then(function (data) {
          if (state.research.loaded || state.research.loading) return;
          state.research.financial = data.financial || [];
          state.research.metadata = Object.create(null);
          (data.metadata || []).forEach(function (item) { state.research.metadata[String(item.symbol || "").toUpperCase()] = item; });
          state.research.loaded = true;
        }).catch(function () {});
      };
      if ("requestIdleCallback" in window) window.requestIdleCallback(warmResearch, { timeout: 1800 });
      else window.setTimeout(warmResearch, 900);
    } catch (error) {
      state.authFatal = error && error.message === "SUPABASE_LIBRARY_UNAVAILABLE" ? "Không tải được thư viện xác thực Supabase. Vui lòng tải lại trang." : "Không xác nhận được phiên đăng nhập. Vui lòng thử lại.";
      state.authReady = true;
      renderRoute();
      console.error("CCC bootstrap failed", error);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bootstrap, { once: true });
  else bootstrap();

  window.addEventListener("pagehide", function () {
    if (authSubscription && typeof authSubscription.unsubscribe === "function") authSubscription.unsubscribe();
  }, { once: true });
})();
