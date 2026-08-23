(function () {
  "use strict";

  var ACCOUNT_PATH = "/tai-khoan";
  var THEME_KEY = "vnstock_dashboard_theme_v17";
  var PAGE_SIZE = 50;
  var MOBILE_CHUNK = 20;
  var REFRESH_SECONDS = 300;

  var app = document.getElementById("app");
  var authSubscription = null;
  var countdownTimer = null;

  var savedTheme = "";
  try { savedTheme = localStorage.getItem(THEME_KEY) || ""; } catch (_) {}

  var state = {
    route: routeFromLocation(),
    theme: savedTheme === "light" || savedTheme === "dark" ? savedTheme : "dark",
    authReady: false,
    session: null,
    user: null,
    membership: { profile: null, subscription: null, plan: null, catalog: [] },
    overview: {
      loading: false,
      error: "",
      loadedFor: "",
      data: null,
      group: "2plus",
      page: 1,
      mobileShown: MOBILE_CHUNK
    },
    marketPulse: {
      loading: false,
      error: "",
      rows: []
    },
    nextRefreshAt: Date.now() + REFRESH_SECONDS * 1000
  };

  document.documentElement.setAttribute("data-theme", state.theme);

  function routeFromLocation() {
    var path = location.pathname || "/";
    if (path === "/danh-sach") return "scanner";
    if (path === "/so-sanh-theo-nganh" || path === "/sang-loc-co-ban") return "research";
    if (path === ACCOUNT_PATH) return "account";
    return "overview";
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function num(value) {
    if (value === null || value === undefined || value === "") return null;
    var parsed = Number(String(value).replace(/[,%\s]/g, ""));
    return Number.isFinite(parsed) ? parsed : null;
  }

  function fmt(value, digits) {
    var parsed = num(value);
    if (parsed === null) return "—";
    return parsed.toLocaleString("vi-VN", {
      minimumFractionDigits: digits || 0,
      maximumFractionDigits: digits || 0
    });
  }

  function pct(value, digits) {
    var parsed = num(value);
    if (parsed === null) return "—";
    return (parsed > 0 ? "+" : "") + parsed.toLocaleString("vi-VN", {
      minimumFractionDigits: digits == null ? 2 : digits,
      maximumFractionDigits: digits == null ? 2 : digits
    }) + "%";
  }

  function shortVolume(value) {
    var parsed = num(value);
    if (parsed === null) return "—";
    if (Math.abs(parsed) >= 1000000) return fmt(parsed / 1000000, 2) + " triệu";
    if (Math.abs(parsed) >= 1000) return fmt(parsed / 1000, 1) + " nghìn";
    return fmt(parsed, 0);
  }

  function metricClass(value) {
    var parsed = num(value);
    return parsed === null ? "" : parsed > 0 ? "positive" : parsed < 0 ? "negative" : "";
  }

  function isMobile() {
    return !!(window.matchMedia && window.matchMedia("(max-width:767px)").matches);
  }

  function iconSvg(name) {
    var paths = {
      home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10"/><path d="M9.5 20v-6h5v6"/>',
      list: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 9h8M8 13h8M8 17h5"/>',
      industry: '<path d="M4 20V9l5-3v14M9 11l6-3v12M15 5l5 3v12M2 20h20"/>',
      watchlist: '<path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z"/>',
      bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/>',
      sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"/>',
      moon: '<path d="M20 15.5A8 8 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z"/>',
      refresh: '<path d="M20 11a8 8 0 1 0-2.34 5.66"/><path d="M20 4v7h-7"/>',
      search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
      user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 21a7.5 7.5 0 0 1 15 0"/>',
      lock: '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
      shield: '<path d="M12 3 5 6v5c0 4.6 2.8 8 7 10 4.2-2 7-5.4 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-4"/>',
      chart: '<path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/>'
    };
    return '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (paths[name] || "") + '</svg>';
  }

  function navLink(href, route, icon, label, compactLabel) {
    var active = Array.isArray(route) ? route.indexOf(state.route) >= 0 : state.route === route;
    return '<a href="' + href + '" class="shell-nav-link ' + (active ? 'active' : '') + '"' + (active ? ' aria-current="page"' : '') + '><span class="nav-ico">' + iconSvg(icon) + '</span><span class="nav-label">' + esc(label) + '</span><small>' + esc(compactLabel || label) + '</small></a>';
  }

  function navPlaceholder(icon, label, compactLabel) {
    return '<span class="shell-nav-link shell-nav-placeholder" aria-disabled="true"><span class="nav-ico">' + iconSvg(icon) + '</span><span class="nav-label">' + esc(label) + '</span><small>' + esc(compactLabel || label) + '</small></span>';
  }

  function primaryNavHtml(includeAccount) {
    var html =
      navLink("/", "overview", "home", "Tổng quan") +
      navLink("/so-sanh-theo-nganh", "research", "industry", "Nghiên cứu", "Nghiên cứu") +
      navLink("/danh-sach", "scanner", "list", "DS mã theo dõi", "DS theo dõi") +
      navPlaceholder("bell", "Cảnh báo");
    if (includeAccount) html += navLink(ACCOUNT_PATH, "account", "user", "Tài khoản");
    return html;
  }

  function routeLabel() {
    if (state.route === "scanner") return "DS mã theo dõi";
    if (state.route === "research") return "Nghiên cứu";
    if (state.route === "account") return "Tài khoản";
    return "Tổng quan";
  }

  function displayUserName() {
    if (!state.authReady) return "Tài khoản";
    if (!state.user) return "Đăng nhập";
    var profile = state.membership.profile || {};
    var meta = state.user.user_metadata || {};
    return profile.display_name || meta.full_name || meta.name || state.user.email || "Tài khoản";
  }

  function planModel() {
    var plan = state.membership.plan || {};
    var subscription = state.membership.subscription || {};
    var data = state.overview.data || {};
    var code = String(plan.plan_code || "FREE").toUpperCase();
    var localizedPlans = {
      FREE: "Miễn phí",
      BASIC: "Cơ bản",
      PLUS: "Nâng cao",
      PRO: "Chuyên nghiệp",
      FULL_MARKET: "Toàn thị trường",
      FULLMARKET: "Toàn thị trường"
    };
    var display = localizedPlans[code] || plan.display_name || code;
    var price = num(plan.price_vnd);
    var watchlistLimit = num(plan.watchlist_limit);
    var viewLimit = num(plan.view_limit);
    var changeLimit = num(plan.change_limit);
    var changeUsed = num(subscription.change_used) || 0;
    var selected = num(data.selected_watchlist_count) || 0;
    var remaining = changeLimit === null ? "Không giới hạn" : Math.max(0, changeLimit - changeUsed) + "/" + changeLimit;
    return {
      code: code,
      display: display,
      price: price === null ? (code === "FREE" ? "0đ" : "—") : fmt(price, 0) + "đ",
      full: !!plan.full_market_access || !!data.effective_full_market_access,
      viewLimit: viewLimit,
      watchlistLimit: watchlistLimit,
      selected: selected,
      remaining: remaining,
      email: !!plan.email_alerts,
      telegram: !!plan.telegram_alerts
    };
  }

  function marketByKey() {
    var map = Object.create(null);
    (state.marketPulse.rows || []).forEach(function (row) {
      map[String(row.key || "").toLowerCase()] = row;
    });
    return map;
  }

  function marketTime(value) {
    if (!value) return "—";
    var d = new Date(value);
    if (!Number.isFinite(d.getTime())) return "—";
    return d.toLocaleString("vi-VN", {
      timeZone: "Asia/Ho_Chi_Minh",
      day: "2-digit", month: "2-digit",
      hour: "2-digit", minute: "2-digit"
    }).replace(",", " ·");
  }

  function marketStatus(row) {
    var status = String(row && row.market_status || "").toUpperCase();
    var dataStatus = String(row && row.data_status || "").toUpperCase();
    if (!row || dataStatus === "ERROR" || dataStatus === "NO_DATA") return { label: "Không có dữ liệu", cls: "is-error" };
    if (dataStatus === "STALE") return { label: "Chậm cập nhật", cls: "is-stale" };
    if (status === "OPEN_24H") return { label: "24/7", cls: "is-open" };
    if (status === "OPEN" || status === "REGULAR") return { label: "Đang giao dịch", cls: "is-open" };
    return { label: "Đóng cửa", cls: "is-closed" };
  }

  function marketFreshness() {
    var map = marketByKey();
    var vn = map.vnindex || (state.marketPulse.rows && state.marketPulse.rows[0]) || null;
    var checked = vn && (vn.checked_at || vn.last_success_at || vn.market_time);
    var checkedMs = checked ? Date.parse(checked) : NaN;
    var age = Number.isFinite(checkedMs) ? Date.now() - checkedMs : Infinity;
    return {
      row: vn,
      fresh: age >= -60000 && age <= 20 * 60 * 1000,
      status: marketStatus(vn)
    };
  }

  function marketSessionLabel() {
    var meta = marketFreshness();
    if (!meta.row) return "Đang kiểm tra dữ liệu";
    if (meta.fresh && meta.status.cls === "is-open") return "Đang giao dịch";
    return "Ngoài giờ thị trường";
  }

  function countdownText() {
    var seconds = Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000));
    var minutes = Math.floor(seconds / 60);
    var rest = seconds % 60;
    return String(minutes).padStart(2, "0") + ":" + String(rest).padStart(2, "0");
  }

  function headerHtml() {
    var user = displayUserName();
    var plan = planModel();
    var sessionLabel = marketSessionLabel();
    var nav = primaryNavHtml(false);

    return '<header class="app-header"><div class="app-header-inner">' +
      '<a class="app-brand" href="/" aria-label="Chuyện Chợ Chứng — Trang tổng quan"><span class="brand-mark">' + iconSvg("chart") + '</span><span class="brand-copy"><strong>CHUYỆN CHỢ CHỨNG</strong><small>Stock Intelligence</small></span></a>' +
      '<form id="global-search-form" class="global-search" role="search" action="/danh-sach" method="get"><label class="sr-only" for="global-stock-search">Tìm mã cổ phiếu</label><span class="global-search-icon">' + iconSvg("search") + '</span><input id="global-stock-search" name="q" type="search" inputmode="search" autocomplete="off" placeholder="Tìm mã chứng khoán"><button class="global-search-submit" type="submit" aria-label="Tìm mã chứng khoán">' + iconSvg("search") + '</button></form>' +
      '<div class="header-right"><section id="data-trust" class="data-trust trust-outside" role="status" aria-live="polite"><div class="trust-primary"><i class="trust-dot"></i><strong id="trust-status">' + esc(sessionLabel) + '</strong></div><span class="trust-separator" aria-hidden="true">·</span><span class="trust-countdown">Làm mới <b id="countdown">' + countdownText() + '</b></span></section>' +
      '<div class="top-actions"><button id="refresh-btn" class="icon-action refresh-btn" type="button" aria-label="Làm mới dữ liệu" title="Làm mới dữ liệu">' + iconSvg("refresh") + '</button><button class="icon-action alert-action" type="button" aria-label="Cảnh báo chưa khả dụng" disabled>' + iconSvg("bell") + '</button><button id="theme-toggle" class="icon-action theme-toggle" type="button" aria-label="Đổi giao diện sáng tối">' + iconSvg(state.theme === "light" ? "moon" : "sun") + '</button><button id="account-open" class="account-action" type="button"><span class="account-avatar">' + iconSvg("user") + '</span><span><strong>' + esc(user) + '</strong><small>' + esc(plan.display) + '</small></span></button></div></div></div>' +
      '<div id="mobile-status-row" class="mobile-status-row trust-outside"><div class="mobile-status-primary"><span class="mobile-market"><i class="trust-dot"></i><b id="mobile-market-status">' + esc(sessionLabel) + '</b></span><span class="mobile-now">Làm mới <b id="mobile-countdown">' + countdownText() + '</b></span></div></div>' +
      '<div class="mobile-search-row"><span class="mobile-route">' + esc(routeLabel()) + '</span><form id="mobile-global-search-form" class="mobile-global-search" role="search" action="/danh-sach" method="get"><label class="sr-only" for="mobile-global-stock-search">Tìm mã cổ phiếu</label><span>' + iconSvg("search") + '</span><input id="mobile-global-stock-search" name="q" type="search" inputmode="search" autocomplete="off" placeholder="Tìm mã chứng khoán"></form></div></header>' +
      '<aside class="desktop-nav"><nav aria-label="Điều hướng chính">' + nav + '</nav><a href="' + ACCOUNT_PATH + '" class="shell-nav-link account-nav ' + (state.route === "account" ? "active" : "") + '"><span class="nav-ico">' + iconSvg("user") + '</span><span class="nav-label">Tài khoản</span><small>Tài khoản</small></a><div class="nav-stage"><span>STAGING</span><small>Alpha.19 donor</small></div></aside>' +
      '<nav class="mobile-bottom" aria-label="Điều hướng chính trên thiết bị di động">' + primaryNavHtml(true) + '</nav>';
  }

  function groupConfig(key) {
    var map = {
      "4of4": { title: "Đạt 4/4", countKey: "four_of_four", description: "Đạt chuẩn" },
      "3plus": { title: "Từ 3 tín hiệu", countKey: "three_plus", description: "Hội tụ" },
      "2plus": { title: "Từ 2 tín hiệu", countKey: "two_plus", description: "Hình thành" },
      "rvol30": { title: "Dòng tiền", countKey: "rvol30", description: "RVOL30 ≥ 200%" }
    };
    return map[key] || map["2plus"];
  }

  function groupMatches(row, key) {
    var count = Number(row && row.signal_count || 0);
    if (key === "4of4") return count === 4;
    if (key === "3plus") return count >= 3;
    if (key === "2plus") return count >= 2;
    if (key === "rvol30") return !!(row && row.signal_rvol30_200pct);
    return true;
  }

  function groupCounts(key) {
    var data = state.overview.data || {};
    var cfg = groupConfig(key);
    return {
      market: Number(data.market_counts && data.market_counts[cfg.countKey] || 0),
      mine: Number(data.watchlist_counts && data.watchlist_counts[cfg.countKey] || 0)
    };
  }

  function sampleMode() {
    if (!state.overview.data) return false;
    if (!state.user) return true;
    return !state.overview.data.effective_full_market_access && Number(state.overview.data.selected_watchlist_count || 0) === 0;
  }

  function sourceRows() {
    var data = state.overview.data || {};
    var rows = sampleMode() ? data.sample_rows : data.rows;
    return Array.isArray(rows) ? rows.slice() : [];
  }

  function filteredRows() {
    return sourceRows().filter(function (row) { return groupMatches(row, state.overview.group); });
  }

  function visibleRows(rows) {
    if (sampleMode()) return rows;
    if (isMobile()) return rows.slice(0, state.overview.mobileShown);
    var start = (state.overview.page - 1) * PAGE_SIZE;
    return rows.slice(start, start + PAGE_SIZE);
  }

  function companyLogo(symbol) {
    var safe = String(symbol || "?").toUpperCase().replace(/[^A-Z0-9]/g, "");
    var label = safe.slice(0, 3) || "?";
    return '<span class="company-logo row-logo"><img class="company-logo-img" decoding="async" src="/assets/logos/' + esc(safe) + '.jpg?v=1741" alt=""><span class="company-logo-fallback">' + esc(label) + '</span></span>';
  }

  function signalRailHtml(row) {
    var values = [
      !!row.signal_price_3pct,
      !!row.signal_daily_volume_200pct,
      !!row.signal_above_ma200,
      !!row.signal_rvol30_200pct
    ];
    var tones = ["price", "volume", "trend", "rvol"];
    var count = Number(row.signal_count || 0);
    var segments = values.map(function (value, index) {
      return '<span class="ccc-segment ccc-' + tones[index] + ' ' + (value ? "is-on" : "is-off") + '"></span>';
    }).join("");
    var stateLabel = count === 4 ? '<em>Đạt chuẩn</em>' : count === 3 ? '<em>Hội tụ</em>' : count === 2 ? '<em>Hình thành</em>' : "";
    var statusClass = count === 4 ? "is-confluent" : count === 3 ? "is-converging" : count === 2 ? "is-forming" : "";
    return '<span class="ccc-rail ' + statusClass + '"><span class="ccc-segments">' + segments + '</span><b>' + count + '/4</b>' + stateLabel + '</span>';
  }

  function stockRowHtml(row) {
    var company = row.display_name || row.company_name || "Tên công ty đang cập nhật";
    var identityMeta = String(row.exchange || "");
    var daily = num(row.daily_volume_pct);
    var volumeRatio = daily === null ? "—" : fmt(daily, 0) + "% KLTB10";
    var rvol = num(row.rvol30_pct);
    var rvolText = rvol === null ? "—" : fmt(rvol, 0) + "%";
    var ma200Text = pct(row.ma200_distance_pct, 1);
    var ma10Text = pct(row.ma10_distance_pct, 1);
    var volumeClass = daily !== null && daily >= 200 ? " is-strong" : "";

    return '<article class="lovable-stock-row universal-stock-card" data-symbol="' + esc(row.symbol) + '">' +
      '<div class="stock-row-identity">' + companyLogo(row.symbol) + '<div><strong>' + esc(row.symbol) + '</strong><span title="' + esc(company) + '">' + esc(company) + '</span><small>' + esc(identityMeta) + '</small></div></div>' +
      '<div class="stock-row-price"><strong>' + fmt(row.current_price, 0) + '</strong><span class="' + metricClass(row.price_change_pct) + '">' + pct(row.price_change_pct, 2) + '</span></div>' +
      '<div class="stock-row-volume"><small>KL hiện tại</small><strong>' + shortVolume(row.volume_accumulated) + '</strong><span class="volume-ratio' + volumeClass + '">' + esc(volumeRatio) + '</span></div>' +
      '<div class="stock-row-highlights"><div class="stock-row-highlight-line highlight-rvol"><span>RVOL30</span><strong>' + esc(rvolText) + '</strong></div><div class="stock-row-highlight-line highlight-trend"><span>MA200</span><strong class="' + metricClass(row.ma200_distance_pct) + '">' + esc(ma200Text) + '</strong></div></div>' +
      '<div class="stock-row-ccc"><span class="stock-row-ccc-main">' + signalRailHtml(row) + '</span><span class="stock-row-ma10"><i></i><span>MA10</span><strong class="' + metricClass(row.ma10_distance_pct) + '">' + esc(ma10Text) + '</strong></span></div>' +
    '</article>';
  }

  function densityHtml() {
    var keys = ["4of4", "3plus", "2plus", "rvol30"];
    return keys.map(function (key) {
      var cfg = groupConfig(key);
      var counts = groupCounts(key);
      var active = state.overview.group === key;
      return '<button type="button" class="density-tile overview-density-trigger ' + (active ? "active" : "") + '" data-overview-group="' + key + '" aria-pressed="' + (active ? "true" : "false") + '"><span>' + esc(cfg.title) + '</span><strong>' + counts.market + '<small> mã</small></strong><div><em>' + esc(cfg.description) + '</em><b>' + counts.mine + ' trong phạm vi</b></div></button>';
    }).join("");
  }

  function pagerHtml(total) {
    if (sampleMode() || total <= 0) return "";
    if (isMobile()) {
      var shown = Math.min(total, state.overview.mobileShown);
      return '<div class="ccc-a19-more"><span>' + shown + '/' + total + ' mã</span>' + (shown < total ? '<button type="button" data-overview-more>Xem thêm ' + Math.min(MOBILE_CHUNK, total - shown) + ' mã</button>' : "") + '</div>';
    }
    var pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    state.overview.page = Math.min(state.overview.page, pages);
    if (pages <= 1) return "";
    return '<div class="ccc-a19-pager"><button type="button" data-overview-page="-1"' + (state.overview.page <= 1 ? " disabled" : "") + '>← Trước</button><span>Trang <b>' + state.overview.page + '</b> / ' + pages + '</span><button type="button" data-overview-page="1"' + (state.overview.page >= pages ? " disabled" : "") + '>Sau →</button></div>';
  }

  function sampleIntroHtml() {
    return '<section class="ccc-a19-sample"><span>KHÁM PHÁ CCC</span><h3>6 mã mẫu đại diện</h3><p>Xem cách CCC theo dõi tín hiệu trước khi tạo DS riêng. Đây là mã mẫu cố định, không phải khuyến nghị đầu tư.</p></section>';
  }

  function signalLegendHtml() {
    var rows = [
      ["price", "Giá", "Tăng ≥ 3%"],
      ["volume", "Khối lượng", "KL ngày ≥ 200% KLTB10"],
      ["trend", "Xu hướng", "Trên MA200"],
      ["rvol", "Dòng tiền", "RVOL30 ≥ 200%"]
    ];
    return '<dl class="signal-legend">' + rows.map(function (item) {
      return '<div><span class="ccc-segment ccc-' + item[0] + ' is-on"></span><dt>' + esc(item[1]) + '</dt><dd>' + esc(item[2]) + '</dd></div>';
    }).join("") + '</dl><div class="signal-state-list"><div><b>2/4 tín hiệu</b><span>Hình thành</span></div><div><b>3/4 tín hiệu</b><span>Hội tụ</span></div><div><b>4/4 tín hiệu</b><span>Đạt chuẩn</span></div></div>';
  }

  function railCardHtml(title, meta, body, extraClass) {
    return '<section class="rail-card ' + esc(extraClass || "") + '"><header><h3>' + esc(title) + '</h3>' + (meta ? '<span>' + esc(meta) + '</span>' : "") + '</header><div class="rail-card-body">' + body + '</div></section>';
  }

  function planScopeCardHtml() {
    var plan = planModel();
    var scope = plan.full ? "Toàn bộ thị trường" : (plan.viewLimit === null ? "—" : plan.viewLimit + " mã");
    var capacity = plan.watchlistLimit === null ? "Ưu tiên cá nhân" : plan.selected + "/" + plan.watchlistLimit;
    var rows = '<dl class="rail-kv"><div><dt>Giá gói</dt><dd>' + esc(plan.price) + '</dd></div><div><dt>Phạm vi kỹ thuật</dt><dd>' + esc(scope) + '</dd></div><div><dt>Số mã theo dõi</dt><dd>' + esc(capacity) + '</dd></div><div><dt>Lượt đổi còn lại</dt><dd>' + esc(plan.remaining) + '</dd></div><div><dt>Cảnh báo Email / Telegram</dt><dd>' + (plan.email && plan.telegram ? "Có" : "Không") + '</dd></div></dl>';
    return railCardHtml("Gói & phạm vi", plan.display, rows + '<p class="rail-note">' + iconSvg("lock") + '<span>Mã ngoài phạm vi chỉ hiển thị số lượng, không tiết lộ danh tính.</span></p><a class="rail-action transplant-rail-link" href="/tai-khoan">Mở rộng phạm vi</a>', "plan-scope-card");
  }

  function marketPulseRailHtml() {
    var map = marketByKey();
    var instruments = [
      ["vnindex", "VN-INDEX", true, "Việt Nam"],
      ["sp500", "S&P 500", false, "Hoa Kỳ"],
      ["hangseng", "HANG SENG", false, "Hong Kong"],
      ["dxy", "DXY", false, "USD Index"],
      ["gold", "GOLD", false, "Gold Futures"],
      ["wti", "WTI", false, "WTI Futures"],
      ["btc", "BTC", false, "Bitcoin"]
    ];

    var latest = null;
    (state.marketPulse.rows || []).forEach(function (row) {
      var ms = Date.parse(row.checked_at || row.last_success_at || row.market_time || "");
      if (Number.isFinite(ms) && (latest === null || ms > latest)) latest = ms;
    });
    var updated = latest === null ? "—" : new Date(latest).toLocaleTimeString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", minute: "2-digit" });

    var cards = instruments.map(function (item) {
      var row = map[item[0]] || null;
      var status = marketStatus(row);
      var hasData = !!row && num(row.price) !== null;
      var digits = item[0] === "btc" ? 0 : item[0] === "dxy" ? 3 : 2;
      var body = hasData ?
        '<div class="market-live-data"><div class="market-live-quote"><b class="market-live-price">' + fmt(row.price, digits) + '</b><span class="market-live-change ' + metricClass(row.change_pct) + '">' + (num(row.change_value) === null ? "" : (num(row.change_value) > 0 ? "+" : "") + fmt(row.change_value, digits) + '<br>') + pct(row.change_pct, 2) + '</span></div><div class="market-live-meta"><span>' + esc(item[3]) + ' · ' + esc(marketTime(row.market_time || row.last_success_at)) + '</span></div></div>' :
        '<div class="market-unavailable"><b>—</b><span>Đang chờ dữ liệu backend</span></div>';

      return '<article class="market-tile ' + (item[2] ? "is-primary " : "") + (hasData ? "has-live-data" : "") + '"><header><strong>' + esc(item[1]) + '</strong>' + (item[2] ? '<span>CHỦ ĐẠO</span>' : "") + '<em class="market-status ' + status.cls + '">' + esc(status.label) + '</em></header>' + body + '</article>';
    }).join("");

    return '<section class="market-pulse panel-anatomy market-pulse-rail"><header class="section-bar"><div><i class="status-dot"></i><h2>Toàn cảnh thị trường</h2><span>Cập nhật ' + esc(updated) + '</span></div><small>Cập nhật<br>' + esc(updated) + '</small></header><div class="market-pulse-grid">' + cards + '</div></section>';
  }

  function overviewBodyHtml() {
    var rows = filteredRows();
    var shown = visibleRows(rows);
    var cfg = groupConfig(state.overview.group);
    var counts = groupCounts(state.overview.group);
    var title = "Tín hiệu trong phạm vi của bạn";
    var summary = 'Đang xem: <b class="overview-chip">' + esc(cfg.title) + '</b> · ' + counts.mine + '/' + counts.market + ' mã trong phạm vi';
    var countText = shown.length + " mã hiển thị";

    if (sampleMode()) {
      title = "Khám phá CCC";
      summary = 'Bạn chưa tạo DS mã theo dõi · xem trước bằng 6 mã mẫu';
      countText = shown.length + " mã mẫu";
    }

    var rowsHtml = shown.length ? shown.map(stockRowHtml).join("") + pagerHtml(rows.length) :
      '<div class="empty-state"><strong>Chưa có mã thuộc phạm vi của bạn trong nhóm này</strong><span>KPI phía trên vẫn phản ánh toàn thị trường.</span></div>';

    return '<section class="signal-density panel-anatomy"><header class="section-bar"><div><h2>Mật độ tín hiệu hôm nay</h2><span>Chọn một nhóm để xem các mã thuộc phạm vi của bạn ngay bên dưới</span></div><small>Ngoài phạm vi chỉ hiển thị số lượng</small></header><div class="density-grid">' + densityHtml() + '</div></section>' +
      '<section id="overview-results" class="in-scope-results panel-anatomy overview-group-' + esc(state.overview.group) + '"><header class="section-bar"><div><h2>' + esc(title) + '</h2><span id="overview-selection-summary">' + summary + '</span></div><small id="overview-selection-count">' + esc(countText) + '</small></header>' +
      (sampleMode() ? sampleIntroHtml() : "") +
      '<div class="overview-row-head"><span>Công ty</span><span>Giá / thay đổi</span><span>Khối lượng</span><span>Điểm nổi bật</span><span>CCC</span></div><div id="overview-rows" class="overview-rows">' + rowsHtml + '</div></section>';
  }

  function loadingHtml() {
    return '<section class="panel-anatomy transplant-state"><span class="transplant-spinner"></span><div><strong>Đang tải Tổng quan…</strong><p>Đang xác nhận phạm vi và dữ liệu mới nhất.</p></div></section>';
  }

  function errorHtml() {
    return '<section class="panel-anatomy transplant-state is-error"><div><strong>Không tải được Tổng quan.</strong><p>' + esc(state.overview.error || "Nguồn dữ liệu tạm thời chưa phản hồi.") + '</p><button type="button" class="secondary-action" data-overview-retry>Thử lại</button></div></section>';
  }

  function overviewPageHtml() {
    var content;
    if (!state.authReady || (state.overview.loading && !state.overview.data)) content = loadingHtml();
    else if (state.overview.error && !state.overview.data) content = errorHtml();
    else if (!state.overview.data) content = loadingHtml();
    else content = overviewBodyHtml();

    var legend = railCardHtml("Tín hiệu CCC", "4 phân đoạn", signalLegendHtml(), "signal-legend-card signal-legend-compact");
    var rail = '<aside class="context-rail overview-context-rail">' + marketPulseRailHtml() + legend + planScopeCardHtml() + '</aside>';

    return '<main id="main-content" class="wrap overview-main lovable-overview page-shell has-context-rail">' +
      '<section class="page-heading page-header"><div><h1>Tổng quan</h1><p>Theo dõi thị trường, tín hiệu nổi bật và dòng tiền trong phạm vi của bạn.</p></div></section>' +
      '<div class="content-grid has-context-rail"><div class="content-main">' + content + '</div>' + rail + '</div>' +
      '<p class="disclaimer">STAGING · Dữ liệu thật. Công cụ không đưa ra khuyến nghị mua/bán.</p></main>';
  }

  function placeholderPageHtml(title, copy) {
    return '<main id="main-content" class="wrap page-shell"><section class="page-heading page-header"><div><h1>' + esc(title) + '</h1><p>' + esc(copy) + '</p></div></section><div class="content-grid"><div class="content-main"><section class="panel-anatomy transplant-placeholder"><strong>Đang giữ checkpoint kiến trúc sạch.</strong><p>Màn hình này sẽ được port ở phase tiếp theo bằng cùng Alpha.19 donor.</p></section></div></div></main>';
  }

  function routeHtml() {
    if (state.route === "overview") return overviewPageHtml();
    if (state.route === "scanner") return placeholderPageHtml("DS mã theo dõi", "Phase 3 sẽ transplant Watchlist + Toàn bộ thị trường.");
    if (state.route === "research") return placeholderPageHtml("Nghiên cứu", "Nghiên cứu sẽ tiếp tục dùng Golden UI Reference sau khi Overview được khóa.");
    return placeholderPageHtml("Tài khoản", "Phase 4 sẽ transplant Account theo cùng visual baseline.");
  }

  function render() {
    app.innerHTML = headerHtml() + routeHtml();
    bind();
    refreshLogoStates();
    updateCountdown();
  }

  function refreshLogoStates() {
    document.querySelectorAll(".company-logo-img").forEach(function (img) {
      function loaded() {
        if (img.parentElement) img.parentElement.classList.add("has-logo");
      }
      img.addEventListener("load", loaded, { once: true });
      img.addEventListener("error", function () { img.remove(); }, { once: true });
      if (img.complete && img.naturalWidth > 0) loaded();
    });
  }

  async function ensureMarketPulse(force) {
    if (state.marketPulse.loading || (!force && state.marketPulse.rows.length)) return;
    state.marketPulse.loading = true;
    state.marketPulse.error = "";
    try {
      state.marketPulse.rows = await window.CCCData.loadMarketPulse();
    } catch (error) {
      state.marketPulse.error = "Không tải được Toàn cảnh thị trường.";
      console.error("CCC market pulse load failed", error);
    } finally {
      state.marketPulse.loading = false;
      state.nextRefreshAt = Date.now() + REFRESH_SECONDS * 1000;
      if (state.route === "overview") render();
    }
  }

  async function ensureOverview(force) {
    if (!state.authReady || state.overview.loading) return;
    var owner = state.user ? state.user.id : "guest";
    if (!force && state.overview.loadedFor === owner && state.overview.data) return;

    state.overview.loading = true;
    state.overview.error = "";
    if (state.route === "overview") render();

    try {
      state.overview.data = state.user ?
        await window.CCCData.getMyOverviewState() :
        await window.CCCData.getPublicOverviewState();
      state.overview.loadedFor = owner;
      state.overview.page = 1;
      state.overview.mobileShown = MOBILE_CHUNK;
    } catch (error) {
      state.overview.error = "Nguồn dữ liệu Tổng quan tạm thời chưa phản hồi. Vui lòng thử lại.";
      console.error("CCC overview load failed", error);
    } finally {
      state.overview.loading = false;
      state.nextRefreshAt = Date.now() + REFRESH_SECONDS * 1000;
      if (state.route === "overview") render();
    }
  }

  async function loadMembership() {
    if (!state.user) {
      state.membership = { profile: null, subscription: null, plan: null, catalog: [] };
      return;
    }
    try {
      state.membership = await window.CCCData.loadMembership(state.user.id);
    } catch (error) {
      console.error("CCC membership load failed", error);
      state.membership = { profile: null, subscription: null, plan: null, catalog: [] };
    }
  }

  async function initAuth() {
    try {
      window.CCCData.init();
      var sessionResult = await window.CCCData.getSession();
      state.session = sessionResult && sessionResult.session || null;
      state.user = state.session && state.session.user || null;
      await loadMembership();
      state.authReady = true;

      var result = window.CCCData.onAuthStateChange(async function (_event, session) {
        state.session = session || null;
        state.user = session && session.user || null;
        state.overview.data = null;
        state.overview.loadedFor = "";
        await loadMembership();
        render();
        ensureOverview(true);
      });
      authSubscription = result && result.data && result.data.subscription || result && result.subscription || null;
    } catch (error) {
      state.authReady = true;
      state.user = null;
      console.error("CCC auth init failed", error);
    } finally {
      render();
      ensureOverview(false);
      ensureMarketPulse(false);
    }
  }

  function updateCountdown() {
    var text = countdownText();
    var desktop = document.getElementById("countdown");
    var mobile = document.getElementById("mobile-countdown");
    if (desktop) desktop.textContent = text;
    if (mobile) mobile.textContent = text;

    var sessionLabel = marketSessionLabel();
    var trust = document.getElementById("trust-status");
    var mobileTrust = document.getElementById("mobile-market-status");
    if (trust) trust.textContent = sessionLabel;
    if (mobileTrust) mobileTrust.textContent = sessionLabel;
  }

  function startCountdown() {
    if (countdownTimer) clearInterval(countdownTimer);
    countdownTimer = setInterval(function () {
      if (Date.now() >= state.nextRefreshAt) state.nextRefreshAt = Date.now() + REFRESH_SECONDS * 1000;
      updateCountdown();
    }, 1000);
  }

  function submitSearch(form) {
    var input = form && form.querySelector("input[name=q]");
    var query = String(input && input.value || "").trim().toUpperCase();
    location.assign("/danh-sach" + (query ? "?q=" + encodeURIComponent(query) : ""));
  }

  function bind() {
    var theme = document.getElementById("theme-toggle");
    if (theme) theme.addEventListener("click", function () {
      state.theme = state.theme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", state.theme);
      try { localStorage.setItem(THEME_KEY, state.theme); } catch (_) {}
      render();
    });

    document.querySelectorAll("#global-search-form,#mobile-global-search-form").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        submitSearch(form);
      });
    });

    var refresh = document.getElementById("refresh-btn");
    if (refresh) refresh.addEventListener("click", function () {
      state.nextRefreshAt = Date.now() + REFRESH_SECONDS * 1000;
      ensureOverview(true);
      ensureMarketPulse(true);
    });

    var account = document.getElementById("account-open");
    if (account) account.addEventListener("click", function () {
      location.assign(ACCOUNT_PATH);
    });

    document.querySelectorAll("[data-overview-group]").forEach(function (button) {
      button.addEventListener("click", function () {
        var key = button.getAttribute("data-overview-group");
        if (!groupConfig(key)) return;
        state.overview.group = key;
        state.overview.page = 1;
        state.overview.mobileShown = MOBILE_CHUNK;
        render();
      });
    });

    document.querySelectorAll("[data-overview-page]").forEach(function (button) {
      button.addEventListener("click", function () {
        state.overview.page = Math.max(1, state.overview.page + Number(button.getAttribute("data-overview-page") || 0));
        render();
        var results = document.getElementById("overview-results");
        if (results) results.scrollIntoView({ block: "start" });
      });
    });

    document.querySelectorAll("[data-overview-more]").forEach(function (button) {
      button.addEventListener("click", function () {
        state.overview.mobileShown += MOBILE_CHUNK;
        render();
      });
    });

    document.querySelectorAll("[data-overview-retry]").forEach(function (button) {
      button.addEventListener("click", function () {
        ensureOverview(true);
      });
    });
  }

  window.addEventListener("popstate", function () {
    state.route = routeFromLocation();
    render();
  });

  window.addEventListener("resize", function () {
    if (state.route === "overview") render();
  });

  window.addEventListener("beforeunload", function () {
    if (authSubscription && typeof authSubscription.unsubscribe === "function") authSubscription.unsubscribe();
    if (countdownTimer) clearInterval(countdownTimer);
  });

  render();
  startCountdown();
  initAuth();
})();
