(function () {
  "use strict";

  var ACCOUNT_PATH = "/tai-khoan";
  var THEME_KEY = "vnstock_dashboard_theme_v17";
  var OVERVIEW_PAGE_SIZE = 10;
  var PAGE_SIZE = 50;
  var RESEARCH_PAGE_SIZE = 25;
  var MOBILE_CHUNK = 20;
  var REFRESH_SECONDS = 300;

  var app = document.getElementById("app");
  var authSubscription = null;
  var countdownTimer = null;
  var vipExpiryTimer = null;
  var accessNoticeTimer = null;

  var savedTheme = "";
  try { savedTheme = localStorage.getItem(THEME_KEY) || ""; } catch (_) {}

  var state = {
    route: routeFromLocation(),
    theme: savedTheme === "light" || savedTheme === "dark" ? savedTheme : "dark",
    authReady: false,
    session: null,
    user: null,
    membership: { profile: null, subscription: null, plan: null, catalog: [] },
    access: {
      loading: false,
      loadedFor: "",
      error: "",
      raw: null,
      context: null,
      lastCheckedAt: 0,
      refreshingEntitlement: false,
      notice: ""
    },
    overview: {
      loading: false,
      error: "",
      loadedFor: "",
      data: null,
      group: "all",
      page: 1,
      mobileShown: MOBILE_CHUNK
    },
    marketPulse: {
      loading: false,
      error: "",
      rows: []
    },
    research: {
      loading: false,
      loaded: false,
      error: "",
      financialRows: [],
      metadataBySymbol: Object.create(null),
      groupRows: Object.create(null),
      scoreBySymbol: Object.create(null),
      industryGroup: new URLSearchParams(location.search).get("group") || "",
      industryPage: 1,
      fundamentalIndustry: "all",
      fundamentalMinScore: 0,
      fundamentalProfitGrowth: "all",
      fundamentalRoe: "all",
      fundamentalPage: 1
    },
    searchUniverse: {
      loading: false,
      loaded: false,
      error: "",
      rows: []
    },
    account: {
      loading: false,
      loadedFor: "",
      watchlist: null,
      originalSymbols: [],
      selectedSymbols: [],
      profileSaving: false,
      profileError: "",
      profileNotice: "",
      watchlistSaving: false,
      watchlistError: "",
      watchlistNotice: "",
      query: "",
      authOpen: false,
      authBusy: false,
      authError: "",
      passwordOpen: false,
      passwordBusy: false,
      passwordError: "",
      passwordNotice: "",
      vipInfoOpen: false,
      guestPlansOpen: false,
      purchaseIntent: ""
    },
    scanner: {
      mode: new URLSearchParams(location.search).get("mode") === "watchlist" ? "watchlist" : "market",
      loading: false,
      error: "",
      marketLoaded: false,
      marketRows: [],
      watchlistLoadedFor: "",
      watchlistRows: [],
      personalWatchlistSymbols: [],
      personalWatchlistLoadedFor: "",
      technicalRows: [],
      technicalMeta: null,
      technicalLoadedKey: "",
      technicalRowsReceived: 0,
      technicalScopeAtLoad: "",
      query: new URLSearchParams(location.search).get("q") || "",
      exchange: "all",
      sort: new URLSearchParams(location.search).get("sort") || (new URLSearchParams(location.search).get("mode") === "watchlist" ? "signal_desc" : "symbol"),
      signal: ["4of4","3plus","2plus","rvol30"].indexOf(new URLSearchParams(location.search).get("signal") || "") >= 0 ? new URLSearchParams(location.search).get("signal") : "",
      page: 1,
      mobileShown: MOBILE_CHUNK,
      filtersOpen: false,
      mobileDropdown: ""
    },
    detail: {
      open: false,
      symbol: "",
      loading: false,
      error: "",
      basic: null,
      metadata: null,
      financial: null,
      quarterly: [],
      valuationPeers: [],
      technical: null,
      technicalAllowed: false,
      technicalReason: "",
      watchlist: null,
      watchlistBusy: false,
      watchlistError: "",
      tab: "overview",
      returnScroll: 0
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

  function normalizeStockSearch(value) {
    var text = String(value == null ? "" : value).trim().toLowerCase();
    try {
      text = text.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    } catch (_) {}
    return text.replace(/đ/g, "d").replace(/\s+/g, " ");
  }

  function stockSearchName(row) {
    return String(row && (row.display_name || row.company_name) || "");
  }

  function stockMatchesSearch(row, query) {
    var q = normalizeStockSearch(query);
    if (!q) return true;
    var symbol = normalizeStockSearch(row && row.symbol);
    var display = normalizeStockSearch(row && row.display_name);
    var company = normalizeStockSearch(row && row.company_name);
    return symbol.indexOf(q) >= 0 || display.indexOf(q) >= 0 || company.indexOf(q) >= 0;
  }

  function rankStockSearch(rows, query, limit) {
    var q = normalizeStockSearch(query);
    if (!q) return [];

    var seen = Object.create(null);
    var ranked = [];

    (rows || []).forEach(function (row) {
      var symbolRaw = String(row && row.symbol || "").toUpperCase();
      if (!symbolRaw || seen[symbolRaw]) return;

      var symbol = normalizeStockSearch(symbolRaw);
      var display = normalizeStockSearch(row && row.display_name);
      var company = normalizeStockSearch(row && row.company_name);
      var rank = 999;

      if (symbol === q) rank = 0;
      else if (symbol.indexOf(q) === 0) rank = 10;
      else if (symbol.indexOf(q) >= 0) rank = 20;
      else if (display === q || company === q) rank = 30;
      else if (display.indexOf(q) === 0) rank = 40;
      else if (company.indexOf(q) === 0) rank = 45;
      else if (display.indexOf(q) >= 0) rank = 50;
      else if (company.indexOf(q) >= 0) rank = 60;

      if (rank >= 999) return;
      seen[symbolRaw] = true;
      ranked.push({ row: row, rank: rank });
    });

    ranked.sort(function (a, b) {
      return a.rank - b.rank || String(a.row.symbol || "").localeCompare(String(b.row.symbol || ""));
    });

    return ranked.slice(0, limit || 8).map(function (item) { return item.row; });
  }

  function searchSuggestionItemsHtml(rows, context) {
    if (!rows.length) {
      return '<div class="stock-suggestion-empty">Không tìm thấy mã phù hợp</div>';
    }
    return rows.map(function (row) {
      var symbol = String(row.symbol || "").toUpperCase();
      var name = stockSearchName(row) || "Tên công ty đang cập nhật";
      var exchange = String(row.exchange || "");
      return '<button type="button" class="stock-suggestion-item" data-search-context="' + esc(context) + '" data-search-symbol="' + esc(symbol) + '">' +
        '<span class="stock-suggestion-symbol">' + esc(symbol) + '</span>' +
        '<span class="stock-suggestion-copy"><strong>' + esc(name) + '</strong><small>' + esc(exchange) + '</small></span>' +
      '</button>';
    }).join("");
  }

  function filterTechnicalRowsToPersonalWatchlist(rows, symbols) {
    var allowed = Object.create(null);
    (symbols || []).forEach(function (symbol) {
      allowed[String(symbol || "").toUpperCase()] = true;
    });

    return (Array.isArray(rows) ? rows : []).filter(function (row) {
      return !!allowed[String(row && row.symbol || "").toUpperCase()];
    });
  }

  function scannerPersonalWatchlistCount() {
    return Array.isArray(state.scanner.personalWatchlistSymbols)
      ? state.scanner.personalWatchlistSymbols.length
      : 0;
  }

  function scannerSearchSourceRows() {
    return state.scanner.mode === "watchlist" ? state.scanner.watchlistRows : state.scanner.marketRows;
  }

  function formatDate(value) {
    if (!value) return "—";
    var d = new Date(value);
    if (!Number.isFinite(d.getTime())) return "—";
    return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
  }

  function formatDateTime(value) {
    if (!value) return "—";
    var d = new Date(value);
    if (!Number.isFinite(d.getTime())) return "—";

    var parts = new Intl.DateTimeFormat("vi-VN", {
      timeZone: "Asia/Ho_Chi_Minh",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false
    }).formatToParts(d);

    var map = {};
    parts.forEach(function (part) {
      if (part.type !== "literal") map[part.type] = part.value;
    });

    return (map.hour || "--") + ":" + (map.minute || "--") +
      " · " + (map.day || "--") + "/" + (map.month || "--") + "/" + (map.year || "----");
  }

  function uniqueSorted(values) {
    var seen = Object.create(null);
    return (values || []).map(function (value) {
      return String(value || "").trim().toUpperCase();
    }).filter(function (value) {
      if (!value || seen[value]) return false;
      seen[value] = true;
      return true;
    }).sort();
  }

  function arraysEqual(a, b) {
    var left = uniqueSorted(a);
    var right = uniqueSorted(b);
    if (left.length !== right.length) return false;
    for (var i = 0; i < left.length; i += 1) {
      if (left[i] !== right[i]) return false;
    }
    return true;
  }

  function userInitial() {
    var label = displayUserName().trim();
    return label ? label.charAt(0).toUpperCase() : "U";
  }

  function providerLabel() {
    if (!state.user) return "—";
    var provider = String((state.user.app_metadata || {}).provider || "email").toLowerCase();
    return provider === "google" ? "Google" : "Email & mật khẩu";
  }

  function friendlyAuthError(error) {
    var message = String(error && error.message ? error.message : "Không thể đăng nhập lúc này.");
    var lower = message.toLowerCase();
    if (lower.indexOf("invalid login credentials") >= 0) return "Email hoặc mật khẩu chưa đúng.";
    if (lower.indexOf("email not confirmed") >= 0) return "Email chưa được xác nhận.";
    if (lower.indexOf("rate limit") >= 0) return "Bạn thao tác quá nhanh. Vui lòng thử lại sau ít phút.";
    return message;
  }

  function watchlistFriendlyError(error) {
    var message = String(error && error.message ? error.message : error || "");
    if (message.indexOf("WATCHLIST_LIMIT_EXCEEDED") >= 0) return "Số mã vượt giới hạn của gói hiện tại.";
    if (message.indexOf("CHANGE_QUOTA_EXCEEDED") >= 0) return "Không đủ lượt đổi mã để thực hiện thay đổi này.";
    if (message.indexOf("INVALID_SYMBOL") >= 0) return "Có mã không thuộc danh sách scanner hiện tại.";
    if (message.indexOf("SUBSCRIPTION_SUSPENDED") >= 0) return "Tài khoản đang tạm ngưng quyền thay đổi DS mã theo dõi.";
    if (message.indexOf("NO_CURRENT_SUBSCRIPTION") >= 0) return "Không tìm thấy gói thành viên đang hoạt động.";
    if (message.indexOf("AUTH_REQUIRED") >= 0) return "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.";
    return "Không cập nhật được DS mã theo dõi. Vui lòng thử lại.";
  }

  function normalizeAccessContext(raw) {
    raw = raw && typeof raw === "object" ? raw : {};

    var changeLimit = num(raw.change_limit);
    var changeUsed = num(raw.change_used);
    var changeRemaining = changeLimit === null
      ? null
      : Math.max(0, changeLimit - (changeUsed || 0));

    var baseFull = raw.base_full_market_access === true;
    var vipActive = raw.vip_day_active === true;
    var effectiveFull = raw.effective_full_market_access === true;

    return {
      subscriptionId: raw.subscription_id || null,
      subscriptionStatus: String(raw.subscription_status || ""),
      basePlanId: raw.base_plan_id || null,
      basePlanCode: String(raw.base_plan_code || ""),
      basePlanName: String(raw.base_plan_name || ""),
      baseFullMarketAccess: baseFull,

      /* Base-plan state remains untouched by VIP Day. */
      watchlistLimit: num(raw.watchlist_limit),
      watchlistCount: num(raw.watchlist_count) || 0,
      changeLimit: changeLimit,
      changeUsed: changeUsed || 0,
      changeRemaining: changeRemaining,
      cycleStart: raw.cycle_start || null,
      cycleEnd: raw.cycle_end || null,

      /* Temporary overlay only. */
      vipDayActive: vipActive,
      vipDayEndsAt: raw.vip_day_ends_at || null,
      vipDayPriceVnd: num(raw.vip_day_price_vnd) || 100000,

      effectiveFullMarketAccess: effectiveFull,
      effectiveTechnicalScope: effectiveFull ? "MARKET" : "PERSONAL_WATCHLIST"
    };
  }

  function accessContext() {
    return state.access.context || null;
  }

  function basePlanCode() {
    var access = accessContext();
    return access ? access.basePlanCode : String((state.membership.plan || {}).plan_code || "");
  }

  function vipDayActive() {
    var access = accessContext();
    return !!(access && access.vipDayActive);
  }

  function vipDayEndsAt() {
    var access = accessContext();
    return access ? access.vipDayEndsAt : null;
  }

  function effectiveFullMarketAccess() {
    var access = accessContext();
    if (access) return !!access.effectiveFullMarketAccess;
    return !!((state.membership.plan || {}).full_market_access);
  }

  function effectiveTechnicalScope() {
    return effectiveFullMarketAccess() ? "MARKET" : "PERSONAL_WATCHLIST";
  }


  function clearVipExpiryTimer() {
    if (vipExpiryTimer) {
      clearTimeout(vipExpiryTimer);
      vipExpiryTimer = null;
    }
  }

  function setAccessNotice(message) {
    state.access.notice = String(message || "");
    if (accessNoticeTimer) clearTimeout(accessNoticeTimer);
    if (!state.access.notice) return;

    accessNoticeTimer = setTimeout(function () {
      state.access.notice = "";
      accessNoticeTimer = null;
      render();
    }, 12000);
  }

  function accessNoticeHtml() {
    if (!state.access.notice) return "";
    return '<div class="access-state-notice" role="status" aria-live="polite">' +
      '<span>' + iconSvg("shield") + '</span><strong>' + esc(state.access.notice) + '</strong></div>';
  }

  function invalidateEntitlementViews() {
    state.overview.loadedFor = "";
    state.overview.data = null;
    state.overview.page = 1;

    state.scanner.technicalLoadedKey = "";
    state.scanner.technicalRows = [];
    state.scanner.technicalMeta = null;
    state.scanner.technicalRowsReceived = 0;
    state.scanner.technicalScopeAtLoad = "";
    state.scanner.page = 1;
    state.scanner.mobileShown = MOBILE_CHUNK;

    if (state.detail.open) {
      state.detail.technical = null;
      state.detail.technicalAllowed = false;
      state.detail.technicalReason = "ENTITLEMENT_REFRESH";
    }

    /* MARKET basic must be re-read after a VIP/FULL downgrade. */
    if (state.scanner.mode === "market" && !effectiveFullMarketAccess()) {
      state.scanner.marketLoaded = false;
      state.scanner.marketRows = [];
    }
  }

  function scheduleVipExpiryCheck() {
    clearVipExpiryTimer();
    if (!state.user || !vipDayActive() || !vipDayEndsAt()) return;

    var endMs = Date.parse(vipDayEndsAt());
    if (!Number.isFinite(endMs)) return;

    var delay = Math.max(100, endMs - Date.now() + 250);
    vipExpiryTimer = setTimeout(function () {
      vipExpiryTimer = null;
      refreshAccessEntitlement("vip_expiry", true);
    }, delay);
  }

  async function refreshAccessEntitlement(reason, force) {
    if (!state.user || state.access.refreshingEntitlement) return accessContext();

    var now = Date.now();
    var current = accessContext();
    var vipEndMs = current && current.vipDayEndsAt ? Date.parse(current.vipDayEndsAt) : NaN;
    var expiryDue = !!(current && current.vipDayActive && Number.isFinite(vipEndMs) && now >= vipEndMs);
    var stale = !state.access.lastCheckedAt || now - state.access.lastCheckedAt >= 60000;

    if (!force && !expiryDue && !stale) return current;

    state.access.refreshingEntitlement = true;
    var beforeVip = vipDayActive();
    var beforeFull = effectiveFullMarketAccess();

    try {
      var ctx = await loadAccessContext(true);
      var afterVip = !!(ctx && ctx.vipDayActive);
      var afterFull = !!(ctx && ctx.effectiveFullMarketAccess);
      var changed = beforeVip !== afterVip || beforeFull !== afterFull;

      if (changed) {
        invalidateEntitlementViews();

        if (beforeVip && !afterVip) {
          setAccessNotice("VIP DAY đã hết hạn. Bạn đã trở về quyền của gói " + planProductName(basePlanCode()) + ".");
        }

        render();

        if (state.route === "overview") await ensureOverview(true);
        if (state.route === "scanner") await ensureScanner(true);
        if (state.route === "account") await ensureAccount(true);
        if (state.detail.open) await ensureDetail(true);
      } else {
        scheduleVipExpiryCheck();
      }

      return ctx;
    } catch (error) {
      console.error("CCC entitlement refresh failed", reason || "", error);
      return accessContext();
    } finally {
      state.access.refreshingEntitlement = false;
    }
  }

  function accountSelectedCount() {
    return state.route === "account" && state.account.loadedFor && Array.isArray(state.account.selectedSymbols)
      ? state.account.selectedSymbols.length
      : null;
  }

  function accountWatchlistLimit() {
    var w = state.account.watchlist || {};
    var raw = num(w.watchlist_limit);
    if (raw !== null) return raw;
    return num((state.membership.plan || {}).watchlist_limit);
  }

  function accountChangeRemaining() {
    var w = state.account.watchlist || {};
    if (w.change_remaining !== null && w.change_remaining !== undefined) return num(w.change_remaining);
    var plan = state.membership.plan || {};
    var sub = state.membership.subscription || {};
    var limit = num(plan.change_limit);
    if (limit === null) return null;
    return Math.max(0, limit - (num(sub.change_used) || 0));
  }

  function accountChangeLimit() {
    var w = state.account.watchlist || {};
    if (w.change_limit !== null && w.change_limit !== undefined) return num(w.change_limit);
    return num((state.membership.plan || {}).change_limit);
  }

  function accountQuotaLabel() {
    var limit = accountChangeLimit();
    var remaining = accountChangeRemaining();
    if (limit === null) return "Không giới hạn";
    return Math.max(0, remaining || 0) + "/" + limit;
  }

  function planProductName(planOrCode) {
    var raw = typeof planOrCode === "string"
      ? planOrCode
      : String(planOrCode && planOrCode.plan_code || "");
    var code = String(raw || "").trim().toUpperCase().replace(/\s+/g, "_");
    if (code === "FULL_MARKET" || code === "FULLMARKET") return "FULL";
    if (code === "VIP_DAY" || code === "VIPDAY") return "VIP DAY";
    if (["FREE", "BASIC", "PLUS", "PRO", "FULL"].indexOf(code) >= 0) return code;
    return code || "FREE";
  }

  function planScopeLabel(plan) {
    if (!plan) return "—";
    if (plan.full_market_access) return "Toàn thị trường";
    var view = num(plan.view_limit);
    return view === null ? "—" : view + " mã";
  }

  function alertLabel(plan) {
    if (!plan) return "—";
    if (plan.email_alerts && plan.telegram_alerts) return "Email + Telegram";
    if (plan.email_alerts) return "Email";
    if (plan.telegram_alerts) return "Telegram";
    return "Chưa bao gồm";
  }

  function planPriceLabel(plan) {
    if (!plan) return "—";
    var price = num(plan.price_vnd);
    if (price === null || price <= 0) return "0đ";
    return fmt(price, 0) + "đ/tháng";
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
      navLink("/danh-sach", "scanner", "list", "DS mã theo dõi", "DS theo dõi") +
      navLink("/so-sanh-theo-nganh", "research", "industry", "Nghiên cứu", "Nghiên cứu") +
      navPlaceholder("bell", "Cảnh báo");
    if (includeAccount) html += navLink(ACCOUNT_PATH, "account", "user", "Tài khoản");
    return html;
  }

  function routeLabel() {
    if (state.detail.open) return "Chi tiết cổ phiếu";
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
    var display = planProductName(code);
    var price = num(plan.price_vnd);
    var watchlistLimit = num(plan.watchlist_limit);
    var viewLimit = num(plan.view_limit);
    var changeLimit = num(plan.change_limit);
    var changeUsed = num(subscription.change_used) || 0;
    var overviewSelected = num(data.selected_watchlist_count);
    var accountSelected = accountSelectedCount();
    var scannerSelected = state.route === "scanner" && state.scanner && state.scanner.watchlistLoadedFor
      ? state.scanner.watchlistRows.length
      : null;
    var selected = accountSelected !== null ? accountSelected :
      (scannerSelected !== null ? scannerSelected : (overviewSelected || 0));
    var remaining = changeLimit === null ? "Không giới hạn" : Math.max(0, changeLimit - changeUsed) + "/" + changeLimit;
    return {
      code: code,
      display: display,
      price: price === null ? (code === "FREE" ? "0đ" : "—") : fmt(price, 0) + "đ",
      full: effectiveFullMarketAccess(),
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
    var accountMeta = state.authReady && state.user
      ? '<small>' + esc(plan.display + (vipDayActive() ? " · VIP DAY" : "")) + '</small>'
      : '';
    var sessionLabel = marketSessionLabel();
    var nav = primaryNavHtml(false);
    var mobileRouteHtml = '<span class="mobile-route">' + esc(routeLabel()) + '</span>';
    var mobileSearchHtml = state.route === "scanner" ? "" :
      '<div class="mobile-search-row">' + mobileRouteHtml +
      '<form id="mobile-global-search-form" class="mobile-global-search stock-search-host" role="search" action="/danh-sach" method="get"><label class="sr-only" for="mobile-global-stock-search">Tìm mã cổ phiếu</label><span>' + iconSvg("search") + '</span><input id="mobile-global-stock-search" name="q" type="search" inputmode="search" autocomplete="off" placeholder="Tìm mã chứng khoán"><div id="mobile-global-search-suggestions" class="stock-suggestions" hidden></div></form></div>';

    return '<header class="app-header"><div class="app-header-inner">' +
      '<a class="app-brand" href="/" aria-label="Chuyện Chợ Chứng — Trang tổng quan"><span class="brand-mark">' + iconSvg("chart") + '</span><span class="brand-copy"><strong>CHUYỆN CHỢ CHỨNG</strong><small>Stock Intelligence</small></span></a>' +
      '<form id="global-search-form" class="global-search stock-search-host" role="search" action="/danh-sach" method="get"><label class="sr-only" for="global-stock-search">Tìm mã cổ phiếu</label><span class="global-search-icon">' + iconSvg("search") + '</span><input id="global-stock-search" name="q" type="search" inputmode="search" autocomplete="off" placeholder="Tìm mã chứng khoán"><button class="global-search-submit" type="submit" aria-label="Tìm mã chứng khoán">' + iconSvg("search") + '</button><div id="global-search-suggestions" class="stock-suggestions" hidden></div></form>' +
      '<div class="header-right"><section id="data-trust" class="data-trust trust-outside" role="status" aria-live="polite"><div class="trust-primary"><i class="trust-dot"></i><strong id="trust-status">' + esc(sessionLabel) + '</strong></div><span class="trust-separator" aria-hidden="true">·</span><span class="trust-countdown">Làm mới <b id="countdown">' + countdownText() + '</b></span></section>' +
      '<div class="top-actions"><button id="refresh-btn" class="icon-action refresh-btn" type="button" aria-label="Làm mới dữ liệu" title="Làm mới dữ liệu">' + iconSvg("refresh") + '</button><button class="icon-action alert-action" type="button" aria-label="Cảnh báo chưa khả dụng" disabled>' + iconSvg("bell") + '</button><button id="theme-toggle" class="icon-action theme-toggle" type="button" aria-label="Đổi giao diện sáng tối">' + iconSvg(state.theme === "light" ? "moon" : "sun") + '</button><button id="account-open" class="account-action" type="button"><span class="account-avatar">' + iconSvg("user") + '</span><span><strong>' + esc(user) + '</strong>' + accountMeta + '</span></button></div></div></div>' +
      '<div id="mobile-status-row" class="mobile-status-row trust-outside"><div class="mobile-status-primary"><span class="mobile-market"><i class="trust-dot"></i><b id="mobile-market-status">' + esc(sessionLabel) + '</b></span><span class="mobile-now">Làm mới <b id="mobile-countdown">' + countdownText() + '</b></span></div></div>' +
      mobileSearchHtml + '</header>' +
      '<aside class="desktop-nav"><nav aria-label="Điều hướng chính">' + nav + '</nav><a href="' + ACCOUNT_PATH + '" class="shell-nav-link account-nav ' + (state.route === "account" ? "active" : "") + '"><span class="nav-ico">' + iconSvg("user") + '</span><span class="nav-label">Tài khoản</span><small>Tài khoản</small></a><div class="nav-stage"><span>STAGING</span><small>Alpha.19 donor</small></div></aside>' +
      '<nav class="mobile-bottom" aria-label="Điều hướng chính trên thiết bị di động">' + primaryNavHtml(true) + '</nav>';
  }

  function groupConfig(key) {
    var map = {
      "all": { title: "Tất cả", countKey: "", description: "Toàn bộ phạm vi" },
      "4of4": { title: "Đạt 4/4", countKey: "four_of_four", description: "Đạt chuẩn" },
      "3plus": { title: "Từ 3 tín hiệu", countKey: "three_plus", description: "Hội tụ" },
      "2plus": { title: "Từ 2 tín hiệu", countKey: "two_plus", description: "Hình thành" },
      "rvol30": { title: "Dòng tiền", countKey: "rvol30", description: "RVOL30 ≥ 200%" }
    };
    return map[key] || map["all"];
  }

  function groupMatches(row, key) {
    var count = Number(row && row.signal_count || 0);
    if (key === "4of4") return count === 4;
    if (key === "3plus") return count >= 3;
    if (key === "2plus") return count >= 2;
    if (key === "rvol30") return !!(row && row.signal_rvol30_200pct);
    return true;
  }

  function sampleGroupCount(key) {
    var data = state.overview.data || {};
    var rows = Array.isArray(data.sample_rows) ? data.sample_rows : [];
    return rows.filter(function (row) { return groupMatches(row, key); }).length;
  }

  function groupCounts(key) {
    var data = state.overview.data || {};
    var cfg = groupConfig(key);
    var market = key === "all"
      ? Number(data.market_total || 0)
      : Number(data.market_counts && data.market_counts[cfg.countKey] || 0);
    var mine;

    if (sampleMode()) {
      mine = sampleGroupCount(key);
    } else {
      mine = key === "all"
        ? Number(data.watchlist_count || 0)
        : Number(data.watchlist_counts && data.watchlist_counts[cfg.countKey] || 0);
    }

    return { market: market, mine: mine };
  }

  function sampleMode() {
    return !!state.overview.data && !state.user;
  }

  function memberEmptyWatchlistMode() {
    if (!state.overview.data || !state.user) return false;
    return !state.overview.data.effective_full_market_access &&
      Number(state.overview.data.selected_watchlist_count || 0) === 0;
  }

  function sourceRows() {
    var data = state.overview.data || {};
    var rows = sampleMode() ? data.sample_rows : data.rows;
    return Array.isArray(rows) ? rows.slice() : [];
  }

  function filteredRows() {
    var rows = sourceRows();
    if (sampleMode()) {
      return rows.slice(0, 10).filter(function (row) {
        return groupMatches(row, state.overview.group);
      });
    }
    return rows;
  }

  function visibleRows(rows) {
    return rows;
  }

  function companyLogo(symbol) {
    var safe = String(symbol || "?").toUpperCase().replace(/[^A-Z0-9]/g, "");
    var label = safe.slice(0, 3) || "?";
    return '<span class="company-logo row-logo"><img class="company-logo-img" loading="lazy" decoding="async" fetchpriority="low" src="/assets/logos/' + esc(safe) + '.jpg?v=1741" alt=""><span class="company-logo-fallback">' + esc(label) + '</span></span>';
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
      var scopeLabel = sampleMode()
        ? counts.mine + "/10 mã mẫu"
        : (memberEmptyWatchlistMode() ? "Chưa có DS của bạn" : counts.mine + " trong phạm vi");
      return '<button type="button" class="density-tile overview-density-trigger ' + (active ? "active" : "") + '" data-overview-group="' + key + '" aria-pressed="' + (active ? "true" : "false") + '"><span>' + esc(cfg.title) + '</span><strong>' + counts.market + '<small> mã</small></strong><div><em>' + esc(cfg.description) + '</em><b>' + esc(scopeLabel) + '</b></div></button>';
    }).join("");
  }

  function overviewTotalMatching() {
    if (sampleMode()) return filteredRows().length;
    return Number(state.overview.data && state.overview.data.total_matching || 0);
  }

  function overviewRangeLabel(shownCount) {
    if (sampleMode()) return shownCount + " mã mẫu";
    var total = Number(state.overview.data && state.overview.data.total_matching || 0);
    if (!total) return "0 mã";
    if (total <= shownCount) return total + " mã";
    return "Hiển thị " + shownCount + " / " + total + " mã";
  }

  function pagerHtml() {
    return "";
  }

  function sampleIntroHtml() {
    return '<section class="ccc-a19-sample"><span>KHÁM PHÁ CCC</span><h3>10 mã mẫu cố định</h3><p>Xem cách CCC theo dõi tín hiệu trước khi tạo DS riêng. Đây là bộ mã trải nghiệm do CCC chọn sẵn, không phải khuyến nghị đầu tư.</p></section>';
  }

  function setPurchaseIntent(value) {
    state.account.purchaseIntent = String(value || "");
    try {
      if (state.account.purchaseIntent) sessionStorage.setItem("ccc_purchase_intent", state.account.purchaseIntent);
      else sessionStorage.removeItem("ccc_purchase_intent");
    } catch (_) {}
  }

  function storedPurchaseIntent() {
    if (state.account.purchaseIntent) return state.account.purchaseIntent;
    try { return sessionStorage.getItem("ccc_purchase_intent") || ""; } catch (_) { return ""; }
  }

  function consumePurchaseIntentAfterAuth() {
    if (!state.user) return false;
    var intent = storedPurchaseIntent();
    if (!intent) return false;
    setPurchaseIntent("");
    if (intent === "VIP_DAY") {
      location.assign("/tai-khoan?intent=vip_day");
      return true;
    }
    return false;
  }

  function upsellAllowed() {
    return !effectiveFullMarketAccess() && !vipDayActive();
  }

  function upsellButtonsHtml(compact) {
    if (!upsellAllowed()) return "";
    var cls = compact ? " is-compact" : "";
    var secondary = sampleMode() ? "Xem các gói" : "Tăng số mã theo dõi";
    return '<div class="overview-upsell-actions' + cls + '">' +
      '<button type="button" class="overview-vip-primary" data-upsell-vip>Mở VIP DAY · 100.000đ</button>' +
      '<button type="button" class="overview-upgrade-secondary" data-upsell-upgrade>' + esc(secondary) + '</button>' +
    '</div>';
  }

  function contextualUpsellHtml() {
    if (state.overview.group === "all" || !upsellAllowed()) return "";
    var counts = groupCounts(state.overview.group);
    var outside = Math.max(0, counts.market - counts.mine);
    if (outside <= 0) return "";

    var cfg = groupConfig(state.overview.group);

    if (sampleMode()) {
      return '<section class="overview-context-upsell guest-free-first"><div>' +
        '<strong>' + counts.market + ' mã trên thị trường đang ' + esc(cfg.title.toLowerCase()) + '</strong>' +
        '<span>Trong 10 mã trải nghiệm có <b>' + counts.mine + ' mã</b>. Bạn có thể tạo miễn phí DS 10 mã của riêng mình để theo dõi các mã bạn thực sự quan tâm.</span>' +
        '</div><div class="guest-context-actions">' +
        '<button type="button" class="overview-free-primary" data-guest-auth>Tạo DS 10 mã miễn phí</button>' +
        '<button type="button" class="overview-paid-text" data-upsell-vip>Muốn xem ngay ' + outside + ' mã còn lại? Xem VIP DAY</button>' +
        '</div></section>';
    }

    return '<section class="overview-context-upsell"><div>' +
      '<strong>' + counts.market + ' mã trên thị trường đang ' + esc(cfg.title.toLowerCase()) + '</strong>' +
      '<span>DS hiện tại của bạn có <b>' + counts.mine + ' mã</b>. Còn <b>' + outside + ' mã</b> khác đang thỏa điều kiện. <b>Bạn muốn xem thêm không?</b></span>' +
      '</div>' + upsellButtonsHtml(true) + '</section>';
  }


  function overviewScannerTarget() {
    var mode = effectiveFullMarketAccess() ? "market" : "watchlist";
    var params = new URLSearchParams();
    params.set("mode", mode);
    if (state.overview.group !== "all") params.set("signal", state.overview.group);
    if (mode === "market") params.set("sort", "signal_desc");
    return "/danh-sach?" + params.toString();
  }

  function overviewSeeAllHtml(shownCount) {
    if (!state.user || memberEmptyWatchlistMode()) return "";
    var total = Number(state.overview.data && state.overview.data.total_matching || 0);
    if (!total || total <= shownCount) return "";

    var cfg = groupConfig(state.overview.group);
    var full = effectiveFullMarketAccess();
    var label;

    if (state.overview.group === "all") {
      label = full
        ? "Mở Scanner toàn thị trường · " + total + " mã"
        : "Xem toàn bộ " + total + " mã trong DS của tôi";
    } else {
      label = "Xem toàn bộ " + total + " mã " + cfg.title;
    }

    return '<div class="overview-see-all"><a href="' + esc(overviewScannerTarget()) + '">' +
      esc(label) + ' <span aria-hidden="true">→</span></a></div>';
  }

  function memberOverviewCtaHtml() {
    if (!state.user) return "";

    var plan = planModel();
    var limit = plan.watchlistLimit;
    var selected = plan.selected;

    if (vipDayActive()) {
      return '<section class="overview-member-status vip-active"><div><span>VIP DAY ĐANG HOẠT ĐỘNG</span><strong>FULL toàn thị trường đang mở đến ' + esc(formatDateTime(vipDayEndsAt())) + '</strong><small>Gói nền ' + esc(planProductName(basePlanCode())) + ' và DS cá nhân vẫn giữ nguyên.</small></div><a href="/tai-khoan" class="overview-manage-link">Quản lý tài khoản</a></section>';
    }

    if (effectiveFullMarketAccess()) {
      return '<section class="overview-member-status"><div><span>QUYỀN FULL</span><strong>Bạn đang có quyền kỹ thuật toàn thị trường.</strong><small>DS cá nhân vẫn dùng để lưu các mã ưu tiên của bạn.</small></div><a href="/tai-khoan" class="overview-manage-link">Quản lý DS mã theo dõi</a></section>';
    }

    if (state.overview.group !== "all") {
      return '<div class="overview-filter-footer"><a href="/tai-khoan" class="overview-manage-link">Quản lý DS mã theo dõi</a></div>';
    }

    var capacity = limit === null ? selected + " mã" : selected + "/" + limit + " mã";
    var remaining = limit === null ? "" : Math.max(0, limit - selected);
    var detail = limit === null
      ? 'Bạn có thể quản lý DS cá nhân trong Tài khoản.'
      : (remaining > 0
        ? 'Bạn còn ' + remaining + ' vị trí trong DS hiện tại. Mở VIP DAY để xem toàn thị trường trong 24 giờ, hoặc tăng số mã theo dõi cho nhu cầu dài hạn.'
        : 'DS hiện tại đã đủ ' + limit + ' mã. Mở VIP DAY để xem toàn thị trường ngay, hoặc tăng số mã theo dõi cho nhu cầu dài hạn.');

    return '<section class="overview-member-cta"><div><span>GÓI HIỆN TẠI · ' + esc(plan.display) + '</span><strong>DS của bạn: ' + esc(capacity) + '</strong><small>' + esc(detail) + '</small></div>' +
      upsellButtonsHtml(false) +
      '<a href="/tai-khoan" class="overview-manage-link">Quản lý DS mã theo dõi</a></section>';
  }

  function guestPlansHtml() {
    if (!state.account.guestPlansOpen) return "";
    return '<div class="guest-plan-preview" aria-label="Các gói CCC">' +
      '<div><b>FREE</b><span>10 mã · 10 lượt thêm mã/chu kỳ</span><small>7 ngày đầu hoàn thiện DS không tính lượt</small></div>' +
      '<div><b>BASIC</b><span>20 mã · 20 lượt/chu kỳ</span><small>100.000đ/tháng</small></div>' +
      '<div><b>PLUS</b><span>50 mã · 50 lượt + cảnh báo</span><small>300.000đ/tháng</small></div>' +
      '<div><b>PRO</b><span>100 mã · 100 lượt + cảnh báo</span><small>500.000đ/tháng</small></div>' +
      '<div><b>FULL</b><span>Toàn thị trường</span><small>1.000.000đ/tháng</small></div>' +
      '<div class="vip"><b>VIP DAY</b><span>FULL trong 24 giờ</span><small>100.000đ</small></div>' +
    '</div>';
  }

  function guestOnboardingCtaHtml() {
    if (!sampleMode()) return "";
    return '<section class="guest-onboarding-cta guest-free-onboarding">' +
      '<div><span class="guest-onboarding-kicker">BẮT ĐẦU MIỄN PHÍ</span><h3>Tạo danh sách 10 mã của riêng bạn</h3>' +
      '<p>Chọn 10 mã bạn quan tâm và theo dõi tín hiệu CCC theo DS riêng. 7 ngày đầu bạn có thể hoàn thiện DS thoải mái mà không tính lượt thêm mã.</p></div>' +
      '<button type="button" class="overview-free-primary guest-free-main" data-guest-auth>Tạo tài khoản / Đăng nhập miễn phí</button>' +
      '<div class="guest-paid-options"><span>Cần xem rộng hơn?</span>' +
      '<button type="button" data-upsell-vip>Xem VIP DAY · 100.000đ / 24h</button>' +
      '<span>·</span><button type="button" data-upsell-upgrade>Xem các gói</button></div>' +
      guestPlansHtml() +
    '</section>';
  }

  function memberEmptyOnboardingHtml() {
    if (!memberEmptyWatchlistMode()) return "";
    return '<section class="member-empty-onboarding"><div><span>BẮT ĐẦU DS CỦA BẠN</span><h3>Chọn tối đa 10 mã để theo dõi</h3>' +
      '<p>Gói ' + esc(planProductName(basePlanCode())) + ' đã sẵn sàng. Hãy tạo DS mã theo dõi của riêng bạn để xem dữ liệu kỹ thuật CCC theo đúng các mã bạn quan tâm.</p></div>' +
      '<a class="primary-action" href="/tai-khoan">Tạo DS mã theo dõi</a></section>';
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

  function guestAccessCardHtml() {
    var body = '<dl class="rail-kv guest-access-kv">' +
      '<div><dt>Trạng thái</dt><dd>Khách</dd></div>' +
      '<div><dt>Dữ liệu công khai</dt><dd>Có</dd></div>' +
      '<div><dt>Tín hiệu CCC</dt><dd>10 mã mẫu</dd></div>' +
      '<div><dt>DS của riêng bạn</dt><dd>Chưa có</dd></div>' +
      '<div><dt>Cảnh báo</dt><dd>Chưa có</dd></div>' +
      '</dl>' +
      '<p class="rail-note">' + iconSvg("lock") + '<span>Bạn đang xem bản trải nghiệm, chưa có gói thành viên.</span></p>' +
      '<button type="button" class="rail-action transplant-rail-link guest-rail-auth" data-guest-auth>Đăng nhập / tạo tài khoản</button>';
    return railCardHtml("Trải nghiệm CCC", "10 mã mẫu", body, "guest-access-card");
  }

  function planScopeCardHtml() {
    var plan = planModel();
    var access = accessContext();
    var vip = vipDayActive();
    var technical = effectiveFullMarketAccess() ? "Toàn thị trường" : "Theo DS của bạn";
    var capacity = plan.watchlistLimit === null ? "Ưu tiên cá nhân" : plan.selected + "/" + plan.watchlistLimit;

    var rows = '<dl class="rail-kv">' +
      '<div><dt>Gói nền</dt><dd>' + esc(plan.display) + '</dd></div>' +
      '<div><dt>Giá gói</dt><dd>' + esc(plan.price) + '</dd></div>' +
      (vip
        ? '<div class="rail-vip-row"><dt>Quyền tạm thời</dt><dd>VIP DAY</dd></div>' +
          '<div class="rail-vip-row"><dt>VIP hết hạn</dt><dd>' + esc(formatDateTime(vipDayEndsAt())) + '</dd></div>'
        : '') +
      '<div><dt>Tín hiệu CCC</dt><dd>' + esc(technical) + '</dd></div>' +
      '<div><dt>DS theo dõi</dt><dd>' + esc(capacity) + '</dd></div>' +
      '<div><dt>Lượt đổi còn lại</dt><dd>' + esc(plan.remaining) + '</dd></div>' +
      '<div><dt>Cảnh báo Email / Telegram</dt><dd>' + (plan.email && plan.telegram ? "Có" : "Không") + '</dd></div>' +
    '</dl>';

    var note = vip
      ? '<p class="rail-note vip-note">' + iconSvg("shield") + '<span>VIP DAY đang mở tín hiệu CCC toàn thị trường. Gói nền, DS cá nhân và quota không thay đổi.</span></p>'
      : (effectiveFullMarketAccess()
        ? '<p class="rail-note">' + iconSvg("lock") + '<span>Bạn đang có quyền xem tín hiệu CCC toàn thị trường.</span></p>'
        : '<p class="rail-note">' + iconSvg("lock") + '<span>Mã ngoài DS của bạn chỉ hiển thị số lượng, không tiết lộ danh tính.</span></p>');

    var action = effectiveFullMarketAccess()
      ? '<a class="rail-action transplant-rail-link" href="/tai-khoan">Quản lý tài khoản</a>'
      : '<a class="rail-action transplant-rail-link" href="/tai-khoan?intent=upgrade">Tăng số mã theo dõi</a>';

    return railCardHtml(
      "Gói & quyền xem",
      plan.display + (vip ? " · VIP DAY" : ""),
      rows + note + action,
      "plan-scope-card" + (vip ? " is-vip-active" : "")
    );
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
    var rows = filteredRows().slice(0, 10);
    var shown = rows;
    var cfg = groupConfig(state.overview.group);
    var counts = groupCounts(state.overview.group);
    var isAll = state.overview.group === "all";
    var title = "Tín hiệu trong phạm vi của bạn";
    var summary = 'Đang xem: <button type="button" class="overview-chip overview-all-reset' + (isAll ? " is-all" : "") + '" data-overview-all>Tất cả</button>' +
      (isAll ? "" : ' <span>›</span> <b class="overview-chip">' + esc(cfg.title) + '</b>') +
      ' · ' + counts.mine + '/' + counts.market + ' mã trong phạm vi';
    var countText = overviewRangeLabel(shown.length);

    if (sampleMode()) {
      title = "Khám phá CCC";
      summary = 'Đang xem: <button type="button" class="overview-chip overview-all-reset' + (isAll ? " is-all" : "") + '" data-overview-all>Tất cả</button>' +
        (isAll ? "" : ' <span>›</span> <b class="overview-chip">' + esc(cfg.title) + '</b>') +
        ' · ' + counts.mine + '/10 mã mẫu · ' + counts.market + ' mã toàn thị trường';
      countText = overviewRangeLabel(shown.length);
    } else if (memberEmptyWatchlistMode()) {
      title = "DS mã theo dõi của bạn";
      summary = 'Bạn đã đăng nhập nhưng chưa tạo DS mã theo dõi';
      countText = "0 mã";
    }

    var rowsHtml = shown.length
      ? shown.map(stockRowHtml).join("")
      : (sampleMode()
        ? '<div class="empty-state"><strong>Không có mã mẫu thỏa bộ lọc này</strong><span>KPI phía trên vẫn phản ánh toàn thị trường. Chọn Tất cả để xem lại 10 mã mẫu.</span></div>'
        : (memberEmptyWatchlistMode()
          ? memberEmptyOnboardingHtml()
          : '<div class="empty-state"><strong>Không có mã thuộc phạm vi của bạn thỏa bộ lọc này</strong><span>KPI phía trên vẫn phản ánh toàn thị trường.</span></div>'));

    var densityCopy = sampleMode()
      ? '<span>KPI phản ánh toàn thị trường; bấm KPI để lọc trong 10 mã mẫu.</span>'
      : (memberEmptyWatchlistMode()
        ? '<span>KPI vẫn phản ánh toàn thị trường. Tạo DS riêng để bắt đầu theo dõi.</span>'
        : '<span>Tổng quan chỉ hiển thị tối đa 10 mã nổi bật; vào Scanner để xem và lọc toàn bộ.</span>');
    var densityMeta = sampleMode() ? "Bản trải nghiệm" : (memberEmptyWatchlistMode() ? "Chưa có DS" : "Top 10 theo bộ lọc");

    return '<section class="signal-density panel-anatomy"><header class="section-bar"><div><h2>Mật độ tín hiệu hôm nay</h2>' + densityCopy + '</div><small>' + esc(densityMeta) + '</small></header><div class="density-grid">' + densityHtml() + '</div></section>' +
      contextualUpsellHtml() +
      '<section id="overview-results" class="in-scope-results panel-anatomy overview-group-' + esc(state.overview.group) + '"><header class="section-bar"><div><h2>' + esc(title) + '</h2><span id="overview-selection-summary">' + summary + '</span></div><small id="overview-selection-count">' + esc(countText) + '</small></header>' +
      (sampleMode() ? sampleIntroHtml() : "") +
      '<div class="overview-row-head"><span>Công ty</span><span>Giá / thay đổi</span><span>Khối lượng</span><span>Điểm nổi bật</span><span>CCC</span></div>' +
      '<div id="overview-rows" class="overview-rows">' + rowsHtml + '</div>' +
      overviewSeeAllHtml(shown.length) +
      (sampleMode() ? guestOnboardingCtaHtml() : memberOverviewCtaHtml()) +
      '</section>';
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
    var accessRail = state.user ? planScopeCardHtml() : guestAccessCardHtml();
    var rail = '<aside class="context-rail overview-context-rail">' + marketPulseRailHtml() + legend + accessRail + '</aside>';

    return '<main id="main-content" class="wrap overview-main lovable-overview page-shell has-context-rail">' +
      '<section class="page-heading page-header"><div><h1>Tổng quan</h1><p>Theo dõi thị trường, tín hiệu nổi bật và dòng tiền trong phạm vi của bạn.</p></div></section>' +
      '<div class="content-grid has-context-rail"><div class="content-main">' + content + '</div>' + rail + '</div>' +
      '<p class="disclaimer">STAGING · Dữ liệu thật. Công cụ không đưa ra khuyến nghị mua/bán.</p></main>';
  }



  function scannerTechnicalMode() {
    if (!state.user) return false;
    if (state.scanner.mode === "watchlist") return true;
    return state.scanner.mode === "market" && effectiveFullMarketAccess();
  }

  function scannerTechnicalScope() {
    return state.scanner.mode === "market" ? "MARKET" : "PERSONAL";
  }

  function scannerTechnicalMeta() {
    return state.scanner.technicalMeta || {};
  }

  function scannerPageSize() {
    return isMobile() ? 20 : 50;
  }

  function scannerCompany(row) {
    return row.display_name || row.company_name || "Tên công ty đang cập nhật";
  }

  function scannerCompareNumber(aValue, bValue, direction) {
    var aNum = num(aValue);
    var bNum = num(bValue);
    if (aNum === null && bNum === null) return 0;
    if (aNum === null) return 1;
    if (bNum === null) return -1;
    return direction === "asc" ? aNum - bNum : bNum - aNum;
  }

  function scannerCompareNearZero(aValue, bValue) {
    var aNum = num(aValue);
    var bNum = num(bValue);
    if (aNum === null && bNum === null) return 0;
    if (aNum === null) return 1;
    if (bNum === null) return -1;
    return Math.abs(aNum) - Math.abs(bNum);
  }

  function scannerMarketFilteredRows() {
    var rows = state.scanner.marketRows.slice();
    var query = String(state.scanner.query || "").trim().toUpperCase();
    var exchange = state.scanner.exchange;

    rows = rows.filter(function (row) {
      if (exchange !== "all" && String(row.exchange || "").toUpperCase() !== exchange) return false;
      if (!query) return true;
      return stockMatchesSearch(row, query);
    });

    rows.sort(function (a, b) {
      var sort = state.scanner.sort;
      if (sort === "change_desc") return scannerCompareNumber(a.price_change_pct, b.price_change_pct, "desc");
      if (sort === "change_asc") return scannerCompareNumber(a.price_change_pct, b.price_change_pct, "asc");
      if (sort === "volume_desc") return scannerCompareNumber(a.volume_accumulated, b.volume_accumulated, "desc");
      if (sort === "volume_asc") return scannerCompareNumber(a.volume_accumulated, b.volume_accumulated, "asc");
      if (sort === "ma200_near") return scannerCompareNearZero(a.ma200_distance_pct, b.ma200_distance_pct);
      if (sort === "ma10_near") return scannerCompareNearZero(a.ma10_distance_pct, b.ma10_distance_pct);
      return String(a.symbol || "").localeCompare(String(b.symbol || ""));
    });
    return rows;
  }

  function scannerWatchlistFilteredRows() {
    var rows = state.scanner.watchlistRows.slice();
    var query = String(state.scanner.query || "").trim().toUpperCase();
    var exchange = state.scanner.exchange;
    var signal = state.scanner.signal;

    rows = rows.filter(function (row) {
      if (exchange !== "all" && String(row.exchange || "").toUpperCase() !== exchange) return false;
      if (query && !stockMatchesSearch(row, query)) return false;
      var count = Number(row.signal_count || 0);
      if (signal === "4of4" && count !== 4) return false;
      if (signal === "3plus" && count < 3) return false;
      if (signal === "2plus" && count < 2) return false;
      if (signal === "rvol30" && !row.signal_rvol30_200pct) return false;
      return true;
    });

    rows.sort(function (a, b) {
      var sort = state.scanner.sort;
      if (sort === "signal_desc") return Number(b.signal_count || 0) - Number(a.signal_count || 0) || String(a.symbol || "").localeCompare(String(b.symbol || ""));
      if (sort === "change_desc") return scannerCompareNumber(a.price_change_pct, b.price_change_pct, "desc");
      if (sort === "change_asc") return scannerCompareNumber(a.price_change_pct, b.price_change_pct, "asc");
      if (sort === "volume_desc") return scannerCompareNumber(a.volume_accumulated, b.volume_accumulated, "desc");
      if (sort === "volume_asc") return scannerCompareNumber(a.volume_accumulated, b.volume_accumulated, "asc");
      if (sort === "ma200_near") return scannerCompareNearZero(a.ma200_distance_pct, b.ma200_distance_pct);
      if (sort === "ma10_near") return scannerCompareNearZero(a.ma10_distance_pct, b.ma10_distance_pct);
      if (sort === "rvol_desc") return scannerCompareNumber(a.rvol30_pct, b.rvol30_pct, "desc");
      return String(a.symbol || "").localeCompare(String(b.symbol || ""));
    });
    return rows;
  }

  function scannerVisibleRows(rows) {
    if (scannerTechnicalMode()) return rows;
    if (isMobile()) return rows.slice(0, state.scanner.mobileShown);
    var pageSize = scannerPageSize();
    var start = (state.scanner.page - 1) * pageSize;
    return rows.slice(start, start + pageSize);
  }

  function marketBasicRowHtml(row) {
    var company = scannerCompany(row);
    var daily = num(row.daily_volume_pct);
    return '<tr data-symbol="' + esc(row.symbol) + '"><td><div class="scanner-company">' + companyLogo(row.symbol) + '<div><strong>' + esc(row.symbol) + '</strong><span title="' + esc(company) + '">' + esc(company) + '</span><small>' + esc(row.exchange || "") + '</small></div></div></td>' +
      '<td class="num"><strong>' + fmt(row.current_price, 0) + '</strong></td>' +
      '<td class="num ' + metricClass(row.price_change_pct) + '"><strong>' + pct(row.price_change_pct, 2) + '</strong></td>' +
      '<td class="num"><strong>' + shortVolume(row.volume_accumulated) + '</strong><small>' + (daily === null ? "—" : fmt(daily, 0) + "% KLTB10") + '</small></td>' +
      '<td class="num ' + metricClass(row.ma200_distance_pct) + '"><strong>' + pct(row.ma200_distance_pct, 1) + '</strong></td>' +
      '<td class="num ' + metricClass(row.ma10_distance_pct) + '"><strong>' + pct(row.ma10_distance_pct, 1) + '</strong></td></tr>';
  }

  function marketBasicCardHtml(row) {
    var company = scannerCompany(row);
    var daily = num(row.daily_volume_pct);
    return '<article class="market-basic-card" data-symbol="' + esc(row.symbol) + '">' +
      '<div class="market-basic-head">' + companyLogo(row.symbol) + '<div class="market-basic-id"><strong>' + esc(row.symbol) + '</strong><span>' + esc(company) + '</span><small>' + esc(row.exchange || "") + '</small></div><div class="market-basic-quote"><strong>' + fmt(row.current_price, 0) + '</strong><span class="' + metricClass(row.price_change_pct) + '">' + pct(row.price_change_pct, 2) + '</span></div></div>' +
      '<div class="market-basic-volume"><span>KL hiện tại</span><div><strong>' + shortVolume(row.volume_accumulated) + '</strong><small>' + (daily === null ? "—" : fmt(daily, 0) + "% KLTB10") + '</small></div></div>' +
      '<div class="market-basic-ma"><span><i></i>MA200 <strong class="' + metricClass(row.ma200_distance_pct) + '">' + pct(row.ma200_distance_pct, 1) + '</strong></span><span><i></i>MA10 <strong class="' + metricClass(row.ma10_distance_pct) + '">' + pct(row.ma10_distance_pct, 1) + '</strong></span></div>' +
    '</article>';
  }

  function watchlistTableRowHtml(row) {
    var company = row.display_name || row.company_name || "Tên công ty đang cập nhật";
    return '<tr data-symbol="' + esc(row.symbol) + '"><td><div class="scanner-company">' + companyLogo(row.symbol) + '<div><strong>' + esc(row.symbol) + '</strong><span title="' + esc(company) + '">' + esc(company) + '</span><small>' + esc(row.exchange || "") + '</small></div></div></td>' +
      '<td class="num"><strong>' + fmt(row.current_price, 0) + '</strong></td>' +
      '<td class="num ' + metricClass(row.price_change_pct) + '"><strong>' + pct(row.price_change_pct, 2) + '</strong></td>' +
      '<td class="num"><strong>' + shortVolume(row.volume_accumulated) + '</strong></td>' +
      '<td>' + signalRailHtml(row) + '</td></tr>';
  }

  function scannerPagerHtml(total) {
    if (scannerTechnicalMode()) {
      var meta = scannerTechnicalMeta();
      var pages = Number(meta.total_pages || 1);
      var page = Number(meta.page || state.scanner.page || 1);
      var matching = Number(meta.total_matching || 0);
      if (matching <= 0 || pages <= 1) return "";
      return '<div class="pager scanner-server-pager">' +
        '<button type="button" data-scanner-page="-1"' + (page <= 1 ? " disabled" : "") + '>← Trang trước</button>' +
        '<span>Trang <b>' + page + '</b> / ' + pages + ' · ' + matching + ' mã</span>' +
        '<button type="button" data-scanner-page="1"' + (page >= pages ? " disabled" : "") + '>Trang sau →</button>' +
      '</div>';
    }

    if (total <= 0) return "";
    if (isMobile()) {
      var shown = Math.min(total, state.scanner.mobileShown);
      if (shown >= total) return "";
      return '<div class="ccc-a19-more"><span>' + shown + '/' + total + ' mã</span><button type="button" data-scanner-more>Xem thêm ' + Math.min(MOBILE_CHUNK, total - shown) + ' mã</button></div>';
    }
    var pagesLocal = Math.max(1, Math.ceil(total / scannerPageSize()));
    state.scanner.page = Math.min(state.scanner.page, pagesLocal);
    if (pagesLocal <= 1) return "";
    return '<div class="pager"><button type="button" data-scanner-page="-1"' + (state.scanner.page <= 1 ? " disabled" : "") + '>Trang trước</button><span>Trang ' + state.scanner.page + '/' + pagesLocal + '</span><button type="button" data-scanner-page="1"' + (state.scanner.page >= pagesLocal ? " disabled" : "") + '>Trang sau</button></div>';
  }

  function scannerMobileOptions(key, mode) {
    if (key === "exchange") {
      return [
        ["all", "Tất cả sàn"],
        ["HOSE", "HOSE"],
        ["HNX", "HNX"],
        ["UPCOM", "UPCoM"]
      ];
    }

    if (mode === "watchlist") {
      return [
        ["signal_desc", "Ưu tiên tín hiệu"],
        ["change_desc", "Giá tăng mạnh"],
        ["change_asc", "Giá giảm mạnh"],
        ["volume_desc", "KL cao nhất"],
        ["volume_asc", "KL thấp nhất"],
        ["ma200_near", "Gần MA200"],
        ["ma10_near", "Gần MA10"],
        ["rvol_desc", "Dòng tiền (RVOL30)"]
      ];
    }

    return [
      ["symbol", "Theo mã"],
      ["change_desc", "Giá tăng mạnh"],
      ["change_asc", "Giá giảm mạnh"],
      ["volume_desc", "KL cao nhất"],
      ["volume_asc", "KL thấp nhất"],
      ["ma200_near", "Gần MA200"],
      ["ma10_near", "Gần MA10"]
    ];
  }

  function scannerMobileInlineDropdownHtml(key, label, mode) {
    var options = scannerMobileOptions(key, mode);
    var current = state.scanner[key];
    var selectedLabel = options.length ? options[0][1] : "";
    options.forEach(function (item) {
      if (item[0] === current) selectedLabel = item[1];
    });

    var open = state.scanner.mobileDropdown === key;
    var list = options.map(function (item) {
      var selected = item[0] === current;
      return '<button type="button" class="scanner-inline-option ' + (selected ? "selected" : "") + '" data-mobile-dropdown-key="' + esc(key) + '" data-mobile-dropdown-value="' + esc(item[0]) + '" role="option" aria-selected="' + (selected ? "true" : "false") + '"><span>' + esc(item[1]) + '</span>' + (selected ? '<b aria-hidden="true">✓</b>' : '') + '</button>';
    }).join("");

    return '<div class="scanner-mobile-inline-field">' +
      '<span class="scanner-field-label">' + esc(label) + '</span>' +
      '<button type="button" class="scanner-inline-trigger ' + (open ? "is-open" : "") + '" data-mobile-dropdown-toggle="' + esc(key) + '" aria-expanded="' + (open ? "true" : "false") + '"><span>' + esc(selectedLabel) + '</span><i aria-hidden="true"></i></button>' +
      '<div class="scanner-inline-options ' + (open ? "is-open" : "") + '" role="listbox">' + list + '</div>' +
    '</div>';
  }

  function scannerDesktopNativeControlsHtml(mode) {
    var sortHtml = mode === "watchlist"
      ? '<option value="signal_desc">Ưu tiên tín hiệu</option><option value="change_desc">Giá tăng nhiều nhất</option><option value="change_asc">Giá giảm nhiều nhất</option><option value="volume_desc">Khối lượng cao nhất</option><option value="volume_asc">Khối lượng thấp nhất</option><option value="ma200_near">Gần MA200 nhất</option><option value="ma10_near">Gần MA10 nhất</option><option value="rvol_desc">Dòng tiền cao nhất (RVOL30)</option>'
      : '<option value="symbol">Theo mã</option><option value="change_desc">Giá tăng nhiều nhất</option><option value="change_asc">Giá giảm nhiều nhất</option><option value="volume_desc">Khối lượng cao nhất</option><option value="volume_asc">Khối lượng thấp nhất</option><option value="ma200_near">Gần MA200 nhất</option><option value="ma10_near">Gần MA10 nhất</option>';

    return '<div class="scanner-filter-controls scanner-desktop-filter-controls ' + (mode === "market" ? "scanner-market-filters " : "") + 'is-open">' +
      '<label><span>Sàn giao dịch</span><select data-scanner-filter="exchange" aria-label="Sàn giao dịch"><option value="all">Tất cả sàn</option><option value="HOSE">HOSE</option><option value="HNX">HNX</option><option value="UPCOM">UPCoM</option></select></label>' +
      '<label><span>Sắp xếp</span><select data-scanner-filter="sort" aria-label="Sắp xếp">' + sortHtml + '</select></label>' +
      '<button type="button" class="secondary-action clear-filters" data-scanner-reset>Đặt lại</button></div>';
  }

  function scannerMobileInlineControlsHtml(mode) {
    return '<div class="scanner-mobile-filter-controls">' +
      scannerMobileInlineDropdownHtml("exchange", "Sàn giao dịch", mode) +
      scannerMobileInlineDropdownHtml("sort", "Sắp xếp", mode) +
      '<button type="button" class="secondary-action clear-filters scanner-mobile-reset" data-scanner-reset>Đặt lại</button>' +
    '</div>';
  }

  function scannerMarketControlsHtml() {
    return isMobile() ? scannerMobileInlineControlsHtml("market") : scannerDesktopNativeControlsHtml("market");
  }

  function scannerWatchlistControlsHtml(scopeLabel) {
    var buttons = [
      ["", "Tất cả", "all"],
      ["4of4", "4/4", "pass"],
      ["3plus", "≥3", "converge"],
      ["2plus", "≥2", "forming"],
      ["rvol30", "Dòng tiền", "money"]
    ].map(function (item) {
      return '<button type="button" data-scanner-signal="' + item[0] + '" data-signal-tone="' + item[2] + '" class="scanner-signal-chip ' + (state.scanner.signal === item[0] ? "active" : "") + '">' + item[1] + '</button>';
    }).join("");

    var label = scopeLabel || "DS của tôi";
    return '<div class="quick-filters scanner-signal-filters" aria-label="Bộ lọc tín hiệu ' + esc(label) + '">' + buttons + '</div>' +
      (isMobile() ? scannerMobileInlineControlsHtml("watchlist") : scannerDesktopNativeControlsHtml("watchlist"));
  }

  function scannerContextRailHtml(mode, filteredCount, shownCount) {
    if (scannerTechnicalMode()) {
      var meta = scannerTechnicalMeta();
      var scopeTotal = Number(meta.scope_total || 0);
      var matching = Number(meta.total_matching || filteredCount || 0);
      var personalCount = Number(meta.personal_watchlist_count || scannerPersonalWatchlistCount() || 0);
      var isMarket = mode === "market";
      var accessLabel = isMarket
        ? (vipDayActive() ? "VIP DAY · MARKET" : "FULL · MARKET")
        : "DS của tôi";

      var body = '<dl class="rail-kv">' +
        '<div><dt>' + (isMarket ? "Tổng mã thị trường" : "DS của tôi") + '</dt><dd>' + scopeTotal + '</dd></div>' +
        '<div><dt>Khớp bộ lọc</dt><dd>' + matching + '</dd></div>' +
        '<div><dt>Trang hiện tại</dt><dd>' + shownCount + ' mã</dd></div>' +
        (isMarket ? '<div><dt>DS cá nhân</dt><dd>' + personalCount + ' mã</dd></div>' : '') +
        '</dl>' +
        '<p class="rail-note">' + iconSvg("shield") + '<span>' +
          (isMarket
            ? 'Bạn đang dùng bộ lọc kỹ thuật CCC trên toàn thị trường. DS cá nhân không bị thay đổi.'
            : 'Đây là đúng các mã bạn đã lưu trong DS cá nhân; bộ lọc chỉ sàng lọc bên trong DS này.') +
        '</span></p>';

      return railCardHtml("Ngữ cảnh kết quả", accessLabel, body, "scanner-context-card") + planScopeCardHtml();
    }

    if (mode === "market") {
      var total = state.scanner.marketRows.length;
      var bodyBasic = '<dl class="rail-kv"><div><dt>Tổng mã thị trường</dt><dd>' + total + '</dd></div><div><dt>Khớp bộ lọc</dt><dd>' + filteredCount + '</dd></div><div><dt>Đang hiển thị</dt><dd>' + shownCount + '</dd></div></dl>' +
        '<p class="rail-note">' + iconSvg("shield") + '<span>Toàn bộ thị trường đang ở chế độ dữ liệu cơ bản. FULL hoặc VIP DAY sẽ mở bộ lọc kỹ thuật CCC toàn thị trường.</span></p>';
      return railCardHtml("Ngữ cảnh kết quả", "Toàn thị trường", bodyBasic, "scanner-context-card") +
        railCardHtml("Nguồn dữ liệu", "", '<dl class="rail-kv"><div><dt>Tổng mã quét</dt><dd>' + total + '</dd></div><div><dt>Nguồn</dt><dd>Chuyện Chợ Chứng</dd></div></dl>', "scanner-source-card");
    }

    return "";
  }

  function scannerLoadingHtml() {
    return '<section class="panel-anatomy transplant-state"><span class="transplant-spinner"></span><div><strong>Đang tải danh sách…</strong><p>Đang lấy dữ liệu đúng theo chế độ bạn chọn.</p></div></section>';
  }

  function scannerErrorHtml() {
    return '<section class="panel-anatomy transplant-state is-error"><div><strong>Không tải được danh sách.</strong><p>' + esc(state.scanner.error || "Nguồn dữ liệu tạm thời chưa phản hồi.") + '</p><button type="button" class="secondary-action" data-scanner-retry>Thử lại</button></div></section>';
  }

  function scannerGuestWatchlistHtml() {
    return '<section class="panel-anatomy scanner-auth-required"><div class="scanner-auth-icon">' + iconSvg("lock") + '</div><div><strong>Đăng nhập để xem DS của tôi</strong><p>Toàn bộ thị trường vẫn xem được dữ liệu cơ bản. Tín hiệu CCC chỉ hiển thị trong phạm vi tài khoản.</p></div><a class="primary-action scanner-account-link" href="/tai-khoan">Đi tới tài khoản</a></section>';
  }

  function scannerPageHtml() {
    var mode = state.scanner.mode;
    var loading = state.scanner.loading;
    var technical = scannerTechnicalMode();
    var rows;
    var visible;
    var title;
    var resultBody = "";

    if (technical) {
      rows = state.scanner.technicalRows || [];
      visible = rows;
      title = mode === "market" ? "Scanner toàn thị trường" : "Kết quả DS của tôi";
    } else {
      rows = mode === "market" ? scannerMarketFilteredRows() : [];
      visible = scannerVisibleRows(rows);
      title = mode === "market" ? "Kết quả toàn thị trường" : "Kết quả DS của tôi";
    }

    var hasLoaded = technical
      ? !!state.scanner.technicalLoadedKey
      : (mode === "market" ? state.scanner.marketLoaded : state.scanner.watchlistLoadedFor);

    if (loading && !hasLoaded) {
      resultBody = scannerLoadingHtml();
    } else if (state.scanner.error) {
      resultBody = scannerErrorHtml();
    } else if (mode === "watchlist" && !state.user) {
      resultBody = scannerGuestWatchlistHtml();
    } else if (!rows.length) {
      resultBody = '<div class="empty-state"><strong>Không có mã phù hợp</strong><span>Thử đổi tìm kiếm hoặc bộ lọc.</span></div>';
    } else if (technical) {
      resultBody =
        '<div class="overview-row-head scanner-universal-head"><span>Công ty</span><span>Giá / thay đổi</span><span>Khối lượng</span><span>Điểm nổi bật</span><span>CCC</span></div>' +
        '<div class="overview-rows scanner-universal-rows">' + visible.map(stockRowHtml).join("") + '</div>' +
        scannerPagerHtml(Number(scannerTechnicalMeta().total_matching || rows.length));
    } else if (mode === "market") {
      if (isMobile()) {
        resultBody = '<div class="scanner-mobile-list scanner-market-mobile-list">' +
          visible.map(marketBasicCardHtml).join("") +
          '</div>' +
          scannerPagerHtml(rows.length);
      } else {
        resultBody = '<div class="scanner-table-wrap scanner-market-table-wrap"><table class="lovable-scanner-table scanner-market-table"><colgroup><col class="col-company"><col class="col-price"><col class="col-change"><col class="col-volume"><col class="col-ma200"><col class="col-ma10"></colgroup><thead><tr><th>Công ty</th><th class="num">Giá</th><th class="num">% thay đổi</th><th class="num">Khối lượng</th><th class="num">MA200</th><th class="num">MA10</th></tr></thead><tbody>' +
          visible.map(marketBasicRowHtml).join("") +
          '</tbody></table></div>' +
          scannerPagerHtml(rows.length);
      }
    }

    var controls = technical
      ? scannerWatchlistControlsHtml(mode === "market" ? "Toàn bộ thị trường" : "DS của tôi")
      : scannerMarketControlsHtml();

    var rail = scannerContextRailHtml(mode, technical ? Number(scannerTechnicalMeta().total_matching || 0) : rows.length, visible.length);
    var resultTotal = technical ? Number(scannerTechnicalMeta().total_matching || 0) : rows.length;
    var modeNote;

    if (mode === "market" && technical) {
      modeNote = '<strong>' + (vipDayActive() ? "VIP DAY" : "FULL") + ' · Toàn bộ thị trường:</strong> đầy đủ tín hiệu CCC, cùng bộ lọc kỹ thuật như DS của tôi.';
    } else if (mode === "market") {
      modeNote = '<strong>Toàn bộ thị trường:</strong> dữ liệu cơ bản của khoảng 800 mã. FULL hoặc VIP DAY mở Scanner kỹ thuật toàn thị trường.';
    } else {
      modeNote = '<strong>DS của tôi:</strong> đúng danh sách cá nhân của bạn, với đầy đủ bộ lọc kỹ thuật CCC.';
    }

    return '<main id="main-content" class="wrap scanner-main lovable-scanner page-shell">' +
      '<section class="scanner-controls panel-anatomy"><div class="scanner-mode" role="group" aria-label="Phạm vi dữ liệu">' +
      '<button type="button" data-scanner-mode="market" class="' + (mode === "market" ? "active" : "") + '">Toàn bộ thị trường' + (mode === "market" && technical ? '<small class="scanner-mode-badge">' + (vipDayActive() ? "VIP DAY" : "FULL") + '</small>' : '') + '</button>' +
      '<button type="button" data-scanner-mode="watchlist" class="' + (mode === "watchlist" ? "active" : "") + '">DS của tôi' + (state.user ? '<small class="scanner-mode-count">' + scannerPersonalWatchlistCount() + '</small>' : '') + '</button></div>' +
      '<div class="scanner-search-stack"><div class="scanner-search-row"><div class="search-box"><span class="search-icon">' + iconSvg("search") + '</span><input id="stock-search" type="search" autocomplete="off" placeholder="Nhập mã hoặc tên công ty" value="' + esc(state.scanner.query) + '"></div><button id="scanner-search-btn" class="primary-action" type="button">Tìm mã</button><button id="scanner-clear-btn" class="secondary-action" type="button">Xóa</button></div><div id="scanner-search-suggestions" class="stock-suggestions scanner-stock-suggestions" hidden></div></div>' +
      '<div class="scanner-mode-note">' + modeNote + '</div>' +
      controls + '</section>' +
      '<div class="scanner-layout"><div class="scanner-layout-main"><section class="scanner-results panel-anatomy"><header class="section-bar"><div><h2>' + title + '</h2><span>Tổng ' + resultTotal + ' mã phù hợp</span></div><small>' + visible.length + ' mã trên trang này</small></header>' + resultBody + '</section></div><aside class="context-rail scanner-context-rail">' + rail + '</aside></div>' +
      '<p class="disclaimer">STAGING · Scanner universe do backend quản lý; bộ lọc không làm thay đổi danh sách quét hay DS cá nhân.</p></main>';
  }


  function plainPct(value, digits) {
    var parsed = num(value);
    if (parsed === null) return "—";
    return parsed.toLocaleString("vi-VN", {
      minimumFractionDigits: digits == null ? 0 : digits,
      maximumFractionDigits: digits == null ? 0 : digits
    }) + "%";
  }

  function moneyBil(value) {
    var parsed = num(value);
    return parsed === null ? "—" : fmt(parsed, parsed >= 1000 ? 0 : 1) + " tỷ";
  }

  function detailMedian(values) {
    var rows = (values || []).map(num).filter(function (value) {
      return value !== null && value > 0;
    }).sort(function (a, b) { return a - b; });
    if (!rows.length) return null;
    var mid = Math.floor(rows.length / 2);
    return rows.length % 2 ? rows[mid] : (rows[mid - 1] + rows[mid]) / 2;
  }

  function detailScoreBand(value, bands) {
    if (value === null || !Number.isFinite(value)) return null;
    for (var i = 0; i < bands.length; i += 1) {
      if (bands[i][0](value)) return bands[i][1];
    }
    return bands.length ? bands[bands.length - 1][1] : 0;
  }

  function detailValuationScore(value, median, maxPoint) {
    if (value === null || median === null || value <= 0 || median <= 0) return null;
    var ratio = value / median;
    if (ratio <= 0.8) return maxPoint;
    if (ratio <= 1) return Math.round(maxPoint * 0.8);
    if (ratio <= 1.2) return Math.round(maxPoint * 0.6);
    if (ratio <= 1.5) return Math.round(maxPoint * 0.35);
    return Math.max(1, Math.round(maxPoint * 0.15));
  }

  function detailFinancialScore(row, peers) {
    if (!row || row.data_status === "NO_FINANCIAL_DATA") {
      return { earned: 0, available: 0, coverage: 0, label: "Chưa có dữ liệu", parts: [], badges: ["Chưa có BCTC"] };
    }

    var parts = [], earned = 0, available = 0;
    function add(name, max, value, detail) {
      if (value === null || value === undefined || !Number.isFinite(value)) return;
      available += max;
      earned += value;
      parts.push({ name: name, earned: value, max: max, detail: detail });
    }

    var py = num(row.profit_yoy_pct), iy = num(row.income_yoy_pct), pq = num(row.profit_qoq_pct);
    var roe = num(row.roea_pct), roa = num(row.roaa_pct), de = num(row.debt_equity_pct), da = num(row.debt_assets_pct);
    var pe = num(row.pe), pb = num(row.pb);

    add("Lợi nhuận sau thuế so với cùng kỳ", 20, detailScoreBand(py, [
      [function (v) { return v >= 30; }, 20],
      [function (v) { return v >= 20; }, 16],
      [function (v) { return v >= 10; }, 12],
      [function (v) { return v >= 0; }, 7],
      [function () { return true; }, 0]
    ]), py === null ? "—" : pct(py));

    add("Doanh thu / thu nhập so với cùng kỳ", 10, detailScoreBand(iy, [
      [function (v) { return v >= 20; }, 10],
      [function (v) { return v >= 10; }, 8],
      [function (v) { return v >= 5; }, 5],
      [function (v) { return v >= 0; }, 3],
      [function () { return true; }, 0]
    ]), iy === null ? "—" : pct(iy));

    add("Lợi nhuận sau thuế so với quý trước", 5, detailScoreBand(pq, [
      [function (v) { return v >= 20; }, 5],
      [function (v) { return v >= 10; }, 4],
      [function (v) { return v >= 0; }, 3],
      [function (v) { return v >= -10; }, 1],
      [function () { return true; }, 0]
    ]), pq === null ? "—" : pct(pq));

    add("ROE – Lợi nhuận trên vốn chủ sở hữu", 20, detailScoreBand(roe, [
      [function (v) { return v >= 20; }, 20],
      [function (v) { return v >= 15; }, 16],
      [function (v) { return v >= 10; }, 11],
      [function (v) { return v >= 5; }, 6],
      [function (v) { return v >= 0; }, 2],
      [function () { return true; }, 0]
    ]), roe === null ? "—" : pct(roe));

    add("ROA – Lợi nhuận trên tổng tài sản", 10, detailScoreBand(roa, [
      [function (v) { return v >= 10; }, 10],
      [function (v) { return v >= 7; }, 8],
      [function (v) { return v >= 5; }, 6],
      [function (v) { return v >= 2; }, 3],
      [function (v) { return v >= 0; }, 1],
      [function () { return true; }, 0]
    ]), roa === null ? "—" : pct(roa));

    if (row.financial_model === "NORMAL") {
      add("Nợ vay trên vốn chủ sở hữu", 10, detailScoreBand(de, [
        [function (v) { return v < 30; }, 10],
        [function (v) { return v < 60; }, 8],
        [function (v) { return v < 100; }, 5],
        [function (v) { return v < 150; }, 2],
        [function () { return true; }, 0]
      ]), de === null ? "—" : plainPct(de));

      add("Nợ trên tổng tài sản", 10, detailScoreBand(da, [
        [function (v) { return v < 30; }, 10],
        [function (v) { return v < 45; }, 8],
        [function (v) { return v < 60; }, 5],
        [function (v) { return v < 75; }, 2],
        [function () { return true; }, 0]
      ]), da === null ? "—" : plainPct(da));
    }

    var medPe = detailMedian((peers || []).map(function (item) { return item && item.pe; }));
    var medPb = detailMedian((peers || []).map(function (item) { return item && item.pb; }));
    var peScore = detailValuationScore(pe, medPe, 8);
    var pbScore = detailValuationScore(pb, medPb, 7);

    add("P/E – Giá so với lợi nhuận, so cùng ngành", 8, peScore,
      pe === null ? "—" : pe.toFixed(2) + "x" + (medPe ? " · trung vị " + medPe.toFixed(2) + "x" : ""));
    add("P/B – Giá so với giá trị sổ sách, so cùng ngành", 7, pbScore,
      pb === null ? "—" : pb.toFixed(2) + "x" + (medPb ? " · trung vị " + medPb.toFixed(2) + "x" : ""));

    var badges = [];
    if (py !== null) {
      if (py >= 30) badges.push("Tăng trưởng mạnh");
      else if (py >= 10) badges.push("Tăng trưởng tốt");
      else if (py < 0) badges.push("LNST suy giảm");
    }
    if (roe !== null) {
      if (roe >= 20) badges.push("Hiệu quả vốn chủ sở hữu cao");
      else if (roe >= 15) badges.push("Hiệu quả vốn chủ sở hữu khá");
    }
    if (peScore !== null && peScore >= 6) badges.push("Định giá P/E hấp dẫn so với ngành");
    if (pbScore !== null && pbScore >= 5) badges.push("Định giá P/B hấp dẫn so với ngành");
    if (row.financial_model !== "NORMAL") badges.push("Chưa đủ chỉ tiêu chuyên biệt để chấm sức khỏe tài chính ngành");
    if (available < 100) badges.push("Chưa đủ dữ liệu để chấm trọn 100 điểm");

    return {
      earned: earned,
      available: available,
      coverage: available,
      label: available ? earned + "/" + available : "Chưa đủ dữ liệu",
      parts: parts,
      badges: badges
    };
  }

  function detailScoreClass(score) {
    if (!score || !score.available) return "score-na";
    var ratio = score.earned / score.available * 100;
    return ratio >= 75 ? "score-good" : ratio >= 55 ? "score-mid" : "score-low";
  }

  function detailMetricHtml(label, value, tone) {
    return '<div class="detail-metric"><small>' + esc(label) + '</small><strong class="' + esc(tone || "") + '">' + esc(value) + '</strong></div>';
  }

  function detailReset(keepScroll) {
    var previousScroll = state.detail.returnScroll || 0;
    state.detail.open = false;
    state.detail.symbol = "";
    state.detail.loading = false;
    state.detail.error = "";
    state.detail.basic = null;
    state.detail.metadata = null;
    state.detail.financial = null;
    state.detail.quarterly = [];
    state.detail.valuationPeers = [];
    state.detail.technical = null;
    state.detail.technicalAllowed = false;
    state.detail.technicalReason = "";
    state.detail.watchlist = null;
    state.detail.watchlistBusy = false;
    state.detail.watchlistError = "";
    state.detail.tab = "overview";
    if (keepScroll) {
      requestAnimationFrame(function () { window.scrollTo(0, previousScroll); });
    }
  }

  function openStockDetail(symbol) {
    symbol = String(symbol || "").trim().toUpperCase();
    if (!symbol) return;
    state.detail.returnScroll = window.scrollY || 0;
    state.detail.open = true;
    state.detail.symbol = symbol;
    state.detail.tab = "overview";
    state.detail.loading = false;
    state.detail.error = "";
    state.detail.basic = null;
    state.detail.metadata = null;
    state.detail.financial = null;
    state.detail.quarterly = [];
    state.detail.valuationPeers = [];
    state.detail.technical = null;
    state.detail.technicalAllowed = false;
    state.detail.technicalReason = "";
    state.detail.watchlist = null;
    state.detail.watchlistBusy = false;
    state.detail.watchlistError = "";
    ensureDetail(false);
  }

  function closeStockDetail() {
    detailReset(true);
    render();
  }

  async function ensureDetail(force) {
    if (!state.detail.open || state.detail.loading && !force) return;
    if (!force && state.detail.basic && state.detail.symbol) return;

    var symbol = state.detail.symbol;
    state.detail.loading = true;
    state.detail.error = "";
    render();

    try {
      var technicalPromise = state.user
        ? window.CCCData.getMemberStockTechnical(symbol, effectiveFullMarketAccess() ? "MARKET" : "PERSONAL")
        : window.CCCData.getGuestDemoTechnical(symbol);

      /* Watchlist state only supports the locked-member CTA.
         A temporary Watchlist read failure must not block public Stock Detail. */
      var watchlistPromise = state.user && !effectiveFullMarketAccess()
        ? window.CCCData.getWatchlistState().catch(function (error) {
            console.warn("CCC detail watchlist context unavailable", error);
            return null;
          })
        : Promise.resolve(null);

      var results = await Promise.all([
        window.CCCData.loadStockDetailBasic(symbol),
        window.CCCData.loadStockDetailMetadata(symbol),
        window.CCCData.loadStockDetailFinancial(symbol),
        window.CCCData.loadStockDetailQuarterly(symbol),
        technicalPromise,
        watchlistPromise
      ]);

      state.detail.basic = results[0] || null;
      state.detail.metadata = results[1] || null;
      state.detail.financial = results[2] || null;
      state.detail.quarterly = Array.isArray(results[3]) ? results[3] : [];
      state.detail.technical = results[4] || null;
      state.detail.technicalAllowed = !!state.detail.technical;
      state.detail.watchlist = results[5] || state.detail.watchlist || null;

      if (state.detail.financial && state.detail.financial.website_group) {
        state.detail.valuationPeers = await window.CCCData.loadStockDetailValuationPeers(state.detail.financial.website_group);
      } else {
        state.detail.valuationPeers = [];
      }

      if (state.detail.technicalAllowed) {
        if (!state.user) state.detail.technicalReason = "GUEST_DEMO";
        else if (vipDayActive()) state.detail.technicalReason = "VIP_DAY";
        else if (effectiveFullMarketAccess()) state.detail.technicalReason = "FULL_MARKET";
        else state.detail.technicalReason = "PERSONAL_WATCHLIST";
      } else {
        state.detail.technicalReason = !state.user ? "GUEST_LOCKED" : "OUTSIDE_PERSONAL_SCOPE";
      }

      if (!state.detail.basic && !state.detail.metadata) {
        state.detail.error = "Không tìm thấy mã " + symbol + " trong dữ liệu hiện tại.";
      }
    } catch (error) {
      state.detail.error = "Không tải được chi tiết " + symbol + ". Vui lòng thử lại.";
      console.error("CCC stock detail load failed", error);
    } finally {
      state.detail.loading = false;
      if (state.detail.open && state.detail.symbol === symbol) render();
    }
  }

  function detailAccessLabel() {
    if (state.detail.technicalAllowed) {
      if (state.detail.technicalReason === "GUEST_DEMO") return "Mã demo · Được mở";
      if (state.detail.technicalReason === "VIP_DAY") return "VIP DAY · Toàn thị trường";
      if (state.detail.technicalReason === "FULL_MARKET") return "FULL · Toàn thị trường";
      return "Trong DS của tôi";
    }
    return state.user ? "Ngoài DS của tôi" : "Ngoài 10 mã demo";
  }

  function detailHeaderHtml() {
    var basic = state.detail.basic || {};
    var meta = state.detail.metadata || {};
    var financial = state.detail.financial || {};
    var company = meta.company_name || meta.display_name || basic.company_name || basic.display_name || "Tên công ty đang cập nhật";
    var group = financial.website_group || meta.website_group || "";
    var exchange = basic.exchange || meta.exchange || "";

    return '<header class="stock-detail-head"><div class="stock-public-identity">' +
      companyLogo(state.detail.symbol) +
      '<div><div><h2 id="stock-detail-title">' + esc(state.detail.symbol) + '</h2>' +
      (exchange ? '<span>' + esc(exchange) + '</span>' : '') +
      (group ? '<span>' + esc(group) + '</span>' : '') +
      '</div><p>' + esc(company) + '</p><small>KL hiện tại · ' + esc(shortVolume(basic.volume_accumulated)) + '</small></div></div>' +
      '<div class="stock-public-quote"><strong>' + esc(fmt(basic.current_price, 0)) + '</strong><span class="' + metricClass(basic.price_change_pct) + '">' + esc(pct(basic.price_change_pct, 2)) + '</span></div></header>';
  }

  function detailTabsHtml() {
    var items = [
      ["overview", "Tổng quan"],
      ["technical", "Kỹ thuật"],
      ["fundamental", "Cơ bản"],
      ["financials", "BCTC"]
    ];
    return '<div class="detail-tabs" role="tablist" aria-label="Nội dung chi tiết cổ phiếu">' +
      items.map(function (item) {
        var active = state.detail.tab === item[0];
        var lock = item[0] === "technical" && !state.detail.technicalAllowed
          ? '<span class="tab-lock">' + iconSvg("lock") + '</span>'
          : "";
        return '<button type="button" role="tab" data-detail-tab="' + item[0] + '" aria-selected="' + (active ? "true" : "false") + '" class="' + (active ? "active" : "") + '">' + item[1] + lock + '</button>';
      }).join("") + '</div>';
  }

  function detailOverviewHtml() {
    var basic = state.detail.basic || {};
    var f = state.detail.financial;
    var score = f ? detailFinancialScore(f, state.detail.valuationPeers) : null;

    return '<section class="detail-panel"><header><h3>Báo giá công khai</h3><span>Luôn hiển thị cho mọi mã</span></header><div class="detail-metric-grid">' +
      detailMetricHtml("Sàn", basic.exchange || "—") +
      detailMetricHtml("Giá hiện tại", fmt(basic.current_price, 0)) +
      detailMetricHtml("% thay đổi", pct(basic.price_change_pct, 2), metricClass(basic.price_change_pct)) +
      detailMetricHtml("KL hiện tại", shortVolume(basic.volume_accumulated)) +
      '</div></section>' +
      '<section class="detail-panel"><header><h3>Bối cảnh cơ bản</h3><span>Public Fundamental Research</span></header>' +
      (f ? '<div class="detail-metric-grid">' +
        detailMetricHtml("Điểm cơ bản", score.label) +
        detailMetricHtml("Ngành", f.website_group || "—") +
        detailMetricHtml("P/E", num(f.pe) === null ? "—" : num(f.pe).toFixed(2) + "x") +
        detailMetricHtml("ROE", pct(f.roea_pct, 2), metricClass(f.roea_pct)) +
        '</div>' : '<div class="empty-state compact"><strong>Chưa có dữ liệu cơ bản</strong><span>Hệ thống chưa có bản ghi tài chính cho mã này.</span></div>') +
      '</section><div class="detail-notice">' + iconSvg("lock") + '<span>MA200, KLTB10, RVOL30 và CCC Signal Rail nằm trong tab <b>Kỹ thuật</b>.</span></div>';
  }

  function detailWatchlistCtaModel() {
    var w = state.detail.watchlist || {};
    var access = accessContext() || {};
    var symbols = uniqueSorted(w.symbols || []);
    var count = symbols.length;

    if (!count && num(w.watchlist_count) !== null) count = num(w.watchlist_count) || 0;
    if (!count && num(access.watchlistCount) !== null) count = num(access.watchlistCount) || 0;

    var limit = num(w.watchlist_limit);
    if (limit === null) limit = num(access.watchlistLimit);
    if (limit === null) limit = num((state.membership.plan || {}).watchlist_limit);

    var remainingSlots = limit === null ? null : Math.max(0, limit - count);
    var setupActive = w.setup_active === true;
    var upgradeFree = Math.max(0, num(w.upgrade_free_additions_remaining) || 0);

    var changeRemaining = w.change_remaining !== null && w.change_remaining !== undefined
      ? num(w.change_remaining)
      : num(access.changeRemaining);
    if (changeRemaining !== null) changeRemaining = Math.max(0, changeRemaining);

    var full = limit !== null && count >= limit;
    var canUseAdd = setupActive || upgradeFree > 0 || changeRemaining === null || changeRemaining > 0;

    return {
      loaded: !!state.detail.watchlist,
      count: count,
      limit: limit,
      remainingSlots: remainingSlots,
      setupActive: setupActive,
      upgradeFree: upgradeFree,
      changeRemaining: changeRemaining,
      full: full,
      canAdd: !full && canUseAdd
    };
  }

  function detailMemberLockedCtaHtml() {
    var model = detailWatchlistCtaModel();
    var symbol = state.detail.symbol;
    var capacity = model.limit === null
      ? model.count + " mã"
      : model.count + "/" + model.limit + " mã";
    var helper = "";
    var primary = "";

    if (!model.loaded) {
      helper = "Chưa đọc được trạng thái DS hiện tại. Bạn vẫn có thể quản lý DS hoặc mở VIP DAY.";
      primary = '<a class="primary-action detail-lock-primary" href="/tai-khoan#ds-ma-theo-doi">Quản lý DS mã theo dõi</a>';
    } else if (model.full) {
      helper = "DS hiện tại đã đủ " + capacity + ". Nâng gói để tăng giới hạn theo dõi lâu dài.";
      primary = '<button type="button" class="primary-action detail-lock-primary" data-upsell-upgrade>Nâng gói để thêm nhiều mã hơn</button>';
    } else if (!model.canAdd) {
      helper = "DS hiện tại " + capacity + " · còn " + model.remainingSlots + " vị trí nhưng đã hết lượt thêm mã trong chu kỳ này.";
      primary = '<button type="button" class="primary-action detail-lock-primary" data-upsell-upgrade>Xem gói nâng cấp</button>';
    } else {
      if (model.setupActive) {
        helper = "DS hiện tại " + capacity + " · còn " + model.remainingSlots + " vị trí · đang trong 7 ngày khởi tạo, thêm mã chưa trừ lượt.";
      } else if (model.upgradeFree > 0) {
        helper = "DS hiện tại " + capacity + " · còn " + model.remainingSlots + " vị trí · còn " + model.upgradeFree + " lượt bổ sung miễn phí sau nâng cấp.";
      } else if (model.changeRemaining === null) {
        helper = "DS hiện tại " + capacity + " · còn chỗ để thêm mã này.";
      } else {
        helper = "DS hiện tại " + capacity + " · còn " + model.remainingSlots + " vị trí · còn " + model.changeRemaining + " lượt thêm trong chu kỳ.";
      }

      primary = '<button type="button" class="primary-action detail-lock-primary" data-detail-add-watchlist="' + esc(symbol) + '"' +
        (state.detail.watchlistBusy ? " disabled" : "") + '>' +
        (state.detail.watchlistBusy ? "Đang thêm " + esc(symbol) + "…" : "Thêm " + esc(symbol) + " vào DS mã theo dõi") +
        '</button>';
    }

    var error = state.detail.watchlistError
      ? '<div class="detail-lock-feedback" role="alert">' + esc(state.detail.watchlistError) + '</div>'
      : "";

    return '<div class="detail-lock-cta"><div class="detail-lock-context"><strong>' + esc(helper) + '</strong></div>' +
      error +
      '<div class="detail-locked-actions">' +
        primary +
        '<button type="button" class="secondary-action detail-vip-secondary" data-upsell-vip>Mở VIP DAY · 24h</button>' +
      '</div>' +
      '<a class="detail-manage-link" href="/tai-khoan#ds-ma-theo-doi">Quản lý DS hiện tại</a>' +
    '</div>';
  }

  async function addDetailSymbolToWatchlist() {
    if (!state.user || !state.detail.open || state.detail.watchlistBusy) return;

    var symbol = String(state.detail.symbol || "").toUpperCase();
    if (!symbol) return;

    state.detail.watchlistBusy = true;
    state.detail.watchlistError = "";
    render();

    try {
      /* Re-read immediately before mutation: backend remains authoritative. */
      var current = await window.CCCData.getWatchlistState();
      var symbols = uniqueSorted(current && current.symbols || []);

      if (symbols.indexOf(symbol) < 0) {
        var limit = num(current && current.watchlist_limit);
        if (limit !== null && symbols.length >= limit) throw new Error("WATCHLIST_LIMIT_EXCEEDED");

        var result = await window.CCCData.replaceWatchlist(uniqueSorted(symbols.concat([symbol])));
        state.detail.watchlist = result || current || null;
      } else {
        state.detail.watchlist = current || null;
      }

      state.overview.loadedFor = "";
      state.overview.data = null;
      state.overview.page = 1;

      state.scanner.watchlistLoadedFor = "";
      state.scanner.personalWatchlistLoadedFor = "";
      state.scanner.personalWatchlistSymbols = [];
      state.scanner.watchlistRows = [];
      state.scanner.technicalLoadedKey = "";
      state.scanner.technicalRows = [];
      state.scanner.technicalMeta = null;

      state.account.loadedFor = "";
      state.account.watchlist = null;
      state.account.originalSymbols = [];
      state.account.selectedSymbols = [];

      await Promise.all([loadMembership(), loadAccessContext(true)]);
      setAccessNotice("Đã thêm " + symbol + " vào DS mã theo dõi.");

      state.detail.basic = null;
      state.detail.technical = null;
      state.detail.technicalAllowed = false;
      await ensureDetail(true);
    } catch (error) {
      state.detail.watchlistError = watchlistFriendlyError(error);
      console.error("CCC detail add watchlist failed", error);
    } finally {
      state.detail.watchlistBusy = false;
      if (state.detail.open) render();
    }
  }

  function detailTechnicalHtml() {
    if (!state.detail.technicalAllowed) {
      var lockedTitle = "Tín hiệu CCC chưa mở cho " + state.detail.symbol;
      var copy = state.user
        ? state.detail.symbol + " chưa nằm trong DS mã theo dõi của bạn. Thêm mã vào DS để xem tín hiệu CCC. Cơ bản và BCTC vẫn được xem bình thường."
        : state.detail.symbol + " không thuộc 10 mã demo của bản trải nghiệm. Cơ bản và BCTC vẫn được xem bình thường; đăng nhập để tạo DS riêng.";
      var action = state.user
        ? detailMemberLockedCtaHtml()
        : '<button type="button" class="primary-action detail-guest-auth" data-guest-auth>Tạo tài khoản / Đăng nhập miễn phí</button>';
      return '<section class="technical-locked"><div class="technical-lock-icon">' + iconSvg("lock") + '</div><strong>' + esc(lockedTitle) + '</strong><p>' + esc(copy) + '</p>' + action + '</section>';
    }

    var basic = state.detail.basic || {};
    var tech = state.detail.technical || {};
    var merged = Object.assign({}, basic, tech);
    var signals = [
      ["Giá tăng ≥ 3%", pct(basic.price_change_pct, 2), !!tech.signal_price_3pct],
      ["KL ngày ≥ 200% KLTB10", plainPct(basic.daily_volume_pct, 0), !!tech.signal_daily_volume_200pct],
      ["Giá trên MA200", pct(basic.ma200_distance_pct, 1), !!tech.signal_above_ma200],
      ["RVOL30 ≥ 200%", plainPct(tech.rvol30_pct, 0), !!tech.signal_rvol30_200pct]
    ];

    return '<section class="detail-panel"><header><h3>CCC Signal Rail</h3><span>Trạng thái snapshot hiện tại</span></header><div class="detail-rail-hero">' +
      signalRailHtml(merged) + '</div><div class="technical-signal-grid">' +
      signals.map(function (item) {
        return '<div class="technical-signal ' + (item[2] ? "is-on" : "") + '"><header><span>' + esc(item[0]) + '</span><b>' + (item[2] ? "Đạt" : "Chưa đạt") + '</b></header><strong>' + esc(item[1]) + '</strong></div>';
      }).join("") + '</div></section>' +
      '<section class="detail-panel"><header><h3>Số liệu kỹ thuật</h3><span>MA10 chỉ là tham chiếu, không phải tín hiệu</span></header><div class="detail-metric-grid">' +
      detailMetricHtml("KLTB10", shortVolume(basic.avg_volume_10)) +
      detailMetricHtml("KL ngày / KLTB10", plainPct(basic.daily_volume_pct, 0)) +
      detailMetricHtml("MA10 tham chiếu", fmt(basic.ma10, 0)) +
      detailMetricHtml("Cách MA10", pct(basic.ma10_distance_pct, 1), metricClass(basic.ma10_distance_pct)) +
      detailMetricHtml("MA200", fmt(basic.ma200, 0)) +
      detailMetricHtml("Cách MA200", pct(basic.ma200_distance_pct, 1), metricClass(basic.ma200_distance_pct)) +
      detailMetricHtml("RVOL30", plainPct(tech.rvol30_pct, 0)) +
      detailMetricHtml("Số phiên RVOL30", (num(tech.rvol30_sessions) || 0) + "/10") +
      '</div></section>';
  }

  function detailFundamentalHtml() {
    var f = state.detail.financial;
    if (!f) {
      return '<div class="empty-state"><strong>Chưa có Fundamental Research</strong><span>Dữ liệu cơ bản cho mã này chưa có trong hệ thống.</span></div>';
    }

    var score = detailFinancialScore(f, state.detail.valuationPeers);
    var parts = score.parts.map(function (part) {
      return '<div class="score-part"><span><b>' + esc(part.name) + '</b><small>' + esc(part.detail || "") + '</small></span><strong>' + part.earned + '/' + part.max + '</strong></div>';
    }).join("");
    var badges = score.badges.map(function (badge) {
      return '<span class="analysis-badge">' + esc(badge) + '</span>';
    }).join("");

    return '<section class="detail-panel"><header><h3>Nghiên cứu cơ bản</h3><span>Công khai cho mọi mã, mọi gói</span></header><div class="fundamental-hero"><div><small>Điểm cơ bản</small><strong class="' +
      detailScoreClass(score) + '">' + esc(score.label) + '</strong><span>Độ phủ ' + score.coverage + '%</span></div><div class="detail-metric-grid">' +
      detailMetricHtml("LNST so cùng kỳ", pct(f.profit_yoy_pct, 2), metricClass(f.profit_yoy_pct)) +
      detailMetricHtml("ROE", pct(f.roea_pct, 2), metricClass(f.roea_pct)) +
      detailMetricHtml("P/E", num(f.pe) === null ? "—" : num(f.pe).toFixed(2) + "x") +
      detailMetricHtml("P/B", num(f.pb) === null ? "—" : num(f.pb).toFixed(2) + "x") +
      '</div></div><div class="analysis-badges">' + badges + '</div><div class="score-parts">' + parts + '</div></section>';
  }

  function detailFinancialsHtml() {
    var rows = Array.isArray(state.detail.quarterly) ? state.detail.quarterly : [];
    var table = rows.length
      ? '<div class="quarter-table"><table><thead><tr><th>Kỳ</th><th class="num">Doanh thu / thu nhập</th><th class="num">Lợi nhuận sau thuế</th><th class="num">Tăng so cùng kỳ</th><th class="num">ROE</th></tr></thead><tbody>' +
        rows.map(function (q) {
          var profit = q.parent_net_profit_bil_vnd != null ? q.parent_net_profit_bil_vnd : q.net_profit_bil_vnd;
          return '<tr><td>' + esc(q.period || ((q.quarter || "") + "/" + (q.year || ""))) + '</td><td class="num">' + esc(moneyBil(q.income_bil_vnd)) + '</td><td class="num">' + esc(moneyBil(profit)) + '</td><td class="num ' +
            metricClass(q.profit_yoy_pct) + '">' + esc(pct(q.profit_yoy_pct, 2)) + '</td><td class="num">' + esc(pct(q.roea_pct, 2)) + '</td></tr>';
        }).join("") + '</tbody></table></div>'
      : '<div class="empty-state compact"><strong>Chưa có lịch sử quý</strong><span>Hệ thống chưa lưu dữ liệu BCTC theo quý cho mã này.</span></div>';

    var url = 'https://finance.vietstock.vn/' + encodeURIComponent(state.detail.symbol) + '/tai-chinh.htm?tab=BCTT';
    return '<section class="detail-panel"><header><h3>Báo cáo tài chính</h3><span>Dữ liệu quý đã lưu trong hệ thống</span></header>' +
      table + '<div class="bctc-action"><div><strong>Tài liệu công bố doanh nghiệp</strong><span>Nguồn ngoài: VietstockFinance</span></div><a href="' +
      esc(url) + '" target="_blank" rel="noopener noreferrer">Xem BCTC trên Vietstock <span aria-hidden="true">↗</span></a></div></section>';
  }

  function detailBodyHtml() {
    if (state.detail.tab === "technical") return detailTechnicalHtml();
    if (state.detail.tab === "fundamental") return detailFundamentalHtml();
    if (state.detail.tab === "financials") return detailFinancialsHtml();
    return detailOverviewHtml();
  }

  function detailContextRailHtml() {
    var basic = state.detail.basic || {};
    var meta = state.detail.metadata || {};
    var f = state.detail.financial || {};
    var group = f.website_group || meta.website_group || "—";
    var sourceBody = '<dl class="rail-kv"><div><dt>Cập nhật</dt><dd>' + esc(formatDateTime(basic.updated_at)) + '</dd></div><div><dt>Trạng thái</dt><dd>' +
      esc(basic.data_status || "—") + '</dd></div><div><dt>Nguồn</dt><dd>Chuyện Chợ Chứng</dd></div></dl>';
    var accessBody = '<dl class="rail-kv"><div><dt>Trạng thái</dt><dd>' + esc(detailAccessLabel()) + '</dd></div><div><dt>Dữ liệu công khai</dt><dd>Có</dd></div><div><dt>Kỹ thuật CCC</dt><dd>' +
      (state.detail.technicalAllowed ? "Được mở" : "Bị khóa") + '</dd></div></dl>' +
      (!state.detail.technicalAllowed ? '<p class="rail-note">' + iconSvg("lock") + '<span>Kỹ thuật phụ thuộc phạm vi gói; Cơ bản và BCTC không bị khóa.</span></p>' : '');
    var contextBody = '<dl class="rail-kv"><div><dt>Mã</dt><dd>' + esc(state.detail.symbol) + '</dd></div><div><dt>Sàn</dt><dd>' +
      esc(basic.exchange || meta.exchange || "—") + '</dd></div><div><dt>Ngành</dt><dd>' + esc(group) + '</dd></div></dl><a class="rail-action transplant-rail-link" href="/tai-khoan#ds-ma-theo-doi">Quản lý DS mã theo dõi</a>';

    var signalGuide = railCardHtml("Tín hiệu CCC", "4 phân đoạn", signalLegendHtml(), "signal-legend-card signal-legend-compact detail-signal-card");

    return railCardHtml("Ngữ cảnh mã", state.detail.symbol, contextBody, "detail-symbol-card") +
      signalGuide +
      railCardHtml("Quyền xem", state.user ? planProductName(basePlanCode()) + (vipDayActive() ? " · VIP DAY" : "") : "Khách", accessBody, "detail-access-card") +
      railCardHtml("Nguồn dữ liệu", "", sourceBody, "detail-source-card");
  }

  function stockDetailPageHtml() {
    var navigation = '<section class="stock-detail-navigation"><button id="detail-back" class="back-action" type="button"><span aria-hidden="true">←</span><span>Quay lại</span></button></section>';

    if (state.detail.loading && !state.detail.basic) {
      return '<main id="main-content" class="wrap stock-detail-page phase5a-stock-detail page-shell">' + navigation +
        '<section class="panel-anatomy transplant-state"><span class="transplant-spinner"></span><div><strong>Đang tải ' + esc(state.detail.symbol) + '…</strong><p>Đang lấy dữ liệu đúng của mã này.</p></div></section></main>';
    }

    if (state.detail.error && !state.detail.basic) {
      return '<main id="main-content" class="wrap stock-detail-page phase5a-stock-detail page-shell">' + navigation +
        '<section class="panel-anatomy transplant-state is-error"><div><strong>Không tải được chi tiết.</strong><p>' + esc(state.detail.error) + '</p><button type="button" class="secondary-action" data-detail-retry>Thử lại</button></div></section></main>';
    }

    return '<main id="main-content" class="wrap stock-detail-page phase5a-stock-detail page-shell">' + navigation +
      '<div class="phase5a-detail-layout"><section class="stock-detail-workspace" aria-labelledby="stock-detail-title">' +
      detailHeaderHtml() + detailTabsHtml() + '<div class="stock-detail-body" role="tabpanel">' + detailBodyHtml() + '</div></section>' +
      '<aside class="context-rail phase5a-detail-context-rail">' + detailContextRailHtml() + '</aside></div>' +
      '<p class="disclaimer">STAGING · Stock Detail phục hồi từ Alpha.19 Golden UI trên runtime Phase 4.</p></main>';
  }


  function accountLoadingHtml() {
    return '<main id="main-content" class="wrap ccc-account-page phase4-account-page"><section class="ccc-account-loading"><span class="transplant-spinner" aria-hidden="true"></span><div><strong>Đang tải tài khoản…</strong><p>Đang đọc hồ sơ, gói thành viên và DS mã theo dõi.</p></div></section></main>';
  }

  function accountLoggedOutHtml() {
    return '<main id="main-content" class="wrap ccc-account-page phase4-account-page">' +
      '<header class="ccc-account-heading"><div><h1>Tài khoản</h1><p>Đăng nhập để quản lý hồ sơ, gói thành viên và thiết lập cá nhân.</p></div></header>' +
      '<section class="ccc-account-empty"><div class="ccc-account-empty-icon">C</div><h2>Bạn chưa đăng nhập</h2><p>Đăng nhập bằng Google hoặc Email để mở trang tài khoản của bạn.</p><button id="account-login-open" class="ccc-account-primary" type="button">Đăng nhập</button></section>' +
    '</main>';
  }

  function accountProfileHtml() {
    var profile = state.membership.profile || {};
    var meta = state.user && state.user.user_metadata || {};
    var displayName = profile.display_name || meta.full_name || meta.name || "";
    var completed = !!profile.profile_completed;
    var message = state.account.profileError
      ? '<div class="ccc-account-form-message error" role="alert">' + esc(state.account.profileError) + '</div>'
      : state.account.profileNotice
        ? '<div class="ccc-account-form-message success" role="status">' + esc(state.account.profileNotice) + '</div>'
        : "";

    return '<section class="ccc-account-card profile phase4-profile-card">' +
      '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">HỒ SƠ CÁ NHÂN</span><h2>Thông tin cá nhân</h2><p>Cập nhật thông tin liên hệ của bạn.</p></div><span class="ccc-account-status ' + (completed ? "ok" : "pending") + '">' + (completed ? "Đã hoàn tất" : "Cần bổ sung") + '</span></header>' +
      message +
      '<form id="account-profile-form" class="ccc-account-form" novalidate>' +
        '<div class="ccc-account-field full"><label>Email</label><input type="email" value="' + esc(state.user.email || "") + '" readonly><small>Email được quản lý bởi tài khoản đăng nhập.</small></div>' +
        '<div class="ccc-account-field"><label for="account-profile-name">Họ và tên <b>*</b></label><input id="account-profile-name" name="display_name" type="text" minlength="2" maxlength="100" autocomplete="name" value="' + esc(displayName) + '" required></div>' +
        '<div class="ccc-account-field"><label for="account-profile-phone">Số điện thoại <b>*</b></label><input id="account-profile-phone" name="phone" type="tel" inputmode="tel" maxlength="30" autocomplete="tel" value="' + esc(profile.phone || "") + '" required></div>' +
        '<div class="ccc-account-field full"><label for="account-profile-address">Địa chỉ <span>(không bắt buộc)</span></label><textarea id="account-profile-address" name="address" rows="3" maxlength="500" autocomplete="street-address">' + esc(profile.address || "") + '</textarea></div>' +
        '<div class="ccc-account-form-actions"><button class="ccc-account-primary" type="submit"' + (state.account.profileSaving ? ' disabled' : '') + '>' + (state.account.profileSaving ? "Đang lưu…" : "Lưu thay đổi") + '</button></div>' +
      '</form>' +
    '</section>';
  }

  function accountMetadataBySymbol() {
    var map = Object.create(null);
    var w = state.account.watchlist || {};
    (w.items || []).forEach(function (row) {
      var symbol = String(row && row.symbol || "").toUpperCase();
      if (symbol) map[symbol] = row;
    });
    (state.searchUniverse.rows || []).forEach(function (row) {
      var symbol = String(row && row.symbol || "").toUpperCase();
      if (symbol && !map[symbol]) map[symbol] = row;
    });
    return map;
  }

  function accountWatchlistSelectedHtml() {
    var map = accountMetadataBySymbol();
    if (!state.account.selectedSymbols.length) {
      return '<div class="ccc-wl-empty">Chưa có mã nào trong DS mã theo dõi.</div>';
    }
    return '<div class="ccc-wl-selected-list">' + state.account.selectedSymbols.map(function (symbol) {
      var meta = map[symbol] || {};
      var name = meta.display_name || meta.company_name || "Tên công ty đang cập nhật";
      return '<article class="ccc-wl-selected-row">' +
        companyLogo(symbol) +
        '<div><strong>' + esc(symbol) + '</strong><span>' + esc(name) + '</span><small>' + esc(meta.exchange || "") + '</small></div>' +
        '<button type="button" data-account-remove="' + esc(symbol) + '" aria-label="Xóa ' + esc(symbol) + '">×</button>' +
      '</article>';
    }).join("") + '</div>';
  }

  function accountWatchlistSetupNoticeHtml() {
    var w = state.account.watchlist || {};
    if (String(w.status || "").toUpperCase() === "GRACE") {
      return '<div class="ccc-wl-banner danger"><strong>Gói đang chờ gia hạn.</strong><span>DS mã theo dõi vẫn được giữ đến ' + esc(formatDateTime(w.grace_end_at)) + '.</span></div>';
    }
    if (w.setup_active) {
      return '<div class="ccc-wl-banner info"><strong>7 ngày khởi tạo miễn phí.</strong><span>Bạn có thể thêm mã đến giới hạn gói mà chưa trừ lượt đổi đến ' + esc(formatDateTime(w.setup_window_end)) + '.</span></div>';
    }
    if (num(w.upgrade_free_additions_remaining) > 0 && w.upgrade_free_additions_end_at) {
      return '<div class="ccc-wl-banner info"><strong>7 ngày bổ sung sau nâng cấp.</strong><span>Còn ' + esc(w.upgrade_free_additions_remaining) + ' mã được bổ sung miễn phí đến ' + esc(formatDateTime(w.upgrade_free_additions_end_at)) + '.</span></div>';
    }
    return "";
  }

  function accountWatchlistHtml() {
    var w = state.account.watchlist || {};
    var limit = accountWatchlistLimit();
    var dirty = !arraysEqual(state.account.originalSymbols, state.account.selectedSymbols);
    var message = state.account.watchlistError
      ? '<div class="ccc-wl-feedback error" role="alert">' + esc(state.account.watchlistError) + '</div>'
      : state.account.watchlistNotice
        ? '<div class="ccc-wl-feedback success" role="status">' + esc(state.account.watchlistNotice) + '</div>'
        : "";

    if (state.account.loading && !state.account.watchlist) {
      return '<section class="ccc-account-card ccc-watchlist-main-card phase4-watchlist-card"><header class="ccc-account-card-head"><div><span class="ccc-account-kicker">DS MÃ THEO DÕI & LƯỢT ĐỔI</span><h2>Danh sách mã theo dõi</h2><p>Đang đọc danh sách và quota thật từ hệ thống.</p></div><span class="ccc-account-status pending">Đang tải</span></header><div class="ccc-wl-loading"><span class="transplant-spinner"></span><span>Đang tải…</span></div></section>';
    }

    return '<section class="ccc-account-card ccc-watchlist-main-card phase4-watchlist-card">' +
      '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">DS MÃ THEO DÕI & LƯỢT ĐỔI</span><h2>Danh sách mã theo dõi</h2><p>Danh sách được giữ xuyên suốt gói; hàng tháng chỉ reset lượt đổi mã.</p></div><span class="ccc-account-status ' + (w.setup_active ? "ok" : "ok") + '">' + (w.setup_active ? "Đang khởi tạo" : "Đang hoạt động") + '</span></header>' +
      '<div class="ccc-wl-metrics"><div><span>Đang theo dõi</span><strong>' + state.account.selectedSymbols.length + (limit === null ? "" : "/" + limit) + '</strong></div><div><span>Lượt đổi còn lại</span><strong>' + esc(accountQuotaLabel()) + '</strong></div><div><span>Reset tiếp theo</span><strong>' + esc(formatDate(w.cycle_end || (state.membership.subscription || {}).cycle_end)) + '</strong></div></div>' +
      accountWatchlistSetupNoticeHtml() + message +
      '<div class="ccc-wl-editor"><div class="ccc-wl-search-wrap"><label for="account-wl-search">Thêm mã vào DS theo dõi</label><input id="account-wl-search" type="search" inputmode="search" autocomplete="off" placeholder="Gõ mã hoặc tên công ty, ví dụ VIC…" value="' + esc(state.account.query) + '"><div id="account-wl-suggestions" class="ccc-wl-search-results phase4-wl-suggestions" hidden></div></div>' +
      '<div class="ccc-wl-list-head"><span>Mã đang theo dõi</span><small>' + (dirty ? "Có thay đổi chưa lưu" : "Chưa có thay đổi") + '</small></div>' + accountWatchlistSelectedHtml() + '</div>' +
      '<div class="ccc-wl-actions"><button type="button" class="ccc-account-secondary" id="account-wl-undo"' + (!dirty || state.account.watchlistSaving ? " disabled" : "") + '>Hoàn tác</button><button type="button" class="ccc-account-primary" id="account-wl-save"' + (!dirty || state.account.watchlistSaving ? " disabled" : "") + '>' + (state.account.watchlistSaving ? "Đang lưu…" : "Lưu DS mã theo dõi") + '</button></div>' +
      '<p class="ccc-wl-rule-note">7 ngày đầu của gói mới được hoàn thiện DS không tính lượt. Sau đó mỗi mã mới thêm dùng 1 lượt; xóa mã không tốn lượt; xóa rồi thêm lại cùng mã vẫn tính 1 lượt.</p>' +
    '</section>';
  }

  function accountUpgradeHtml() {
    var currentCode = String((state.membership.plan || {}).plan_code || "").toUpperCase();
    var items = (state.membership.catalog || []).filter(function (plan) {
      return String(plan.plan_code || "").toUpperCase() !== currentCode;
    });
    if (!items.length) return "";

    return '<div id="upgrade-plans" class="phase4-upgrade' + (new URLSearchParams(location.search).get("intent") === "upgrade" ? " is-intent" : "") + '"><div class="phase4-upgrade-head"><span class="ccc-account-kicker">XEM & NÂNG CẤP</span><h3>Mở rộng gói</h3><p>Chỉ xem, chưa thay đổi gói.</p></div><div class="phase4-upgrade-grid">' +
      items.map(function (plan) {
        var code = String(plan.plan_code || "");
        return '<article class="phase4-plan-choice"><strong>' + esc(planProductName(code)) + '</strong><b>' + esc(planPriceLabel(plan)) + '</b><span>' + (plan.is_recommended ? "Phổ biến" : "Xem gói") + '</span></article>';
      }).join("") +
    '</div><div class="phase4-upgrade-note">Chọn gói và thanh toán sẽ được nối ở bước billing sau.</div></div>';
  }

  function accountVipDayHtml() {
    var access = accessContext();
    var active = vipDayActive();
    var endsAt = vipDayEndsAt();
    var price = access && access.vipDayPriceVnd ? access.vipDayPriceVnd : 100000;

    if (active) {
      return '<section id="vip-day" class="ccc-vip-day-offer phase4-vip active' + (new URLSearchParams(location.search).get("intent") === "vip_day" ? " is-intent" : "") + '">' +
        '<div><span>VIP DAY · ĐANG HOẠT ĐỘNG</span><strong>FULL toàn thị trường đang mở</strong>' +
        '<small>Hết hạn ' + esc(formatDateTime(endsAt)) + '. Gói nền ' + esc(planProductName(basePlanCode())) + ' và DS mã theo dõi vẫn giữ nguyên.</small></div>' +
        '<button type="button" disabled>Đang sử dụng VIP DAY</button>' +
      '</section>';
    }

    return '<section id="vip-day" class="ccc-vip-day-offer phase4-vip' + (new URLSearchParams(location.search).get("intent") === "vip_day" ? " is-intent" : "") + '">' +
      '<div><span>VIP DAY</span><strong>Mở FULL trong 24 giờ</strong>' +
      '<small>' + esc(fmt(price, 0)) + 'đ · Mở quyền kỹ thuật toàn thị trường trong 24 giờ, không cần đổi gói hiện tại.</small></div>' +
      '<button id="vip-day-info" type="button">Xem VIP DAY · ' + esc(fmt(price, 0)) + 'đ</button>' +
      (state.account.vipInfoOpen
        ? '<p class="phase4-vip-note">Thanh toán thật chưa được mở ở phase này. Backend VIP DAY đã sẵn sàng; khi nối billing, CTA này sẽ là điểm kích hoạt sau thanh toán thành công.</p>'
        : '') +
    '</section>';
  }

  function accountPlanHtml() {
    var plan = state.membership.plan || {};
    var sub = state.membership.subscription || {};
    var selected = accountSelectedCount();
    var watchLimit = accountWatchlistLimit();

    if (!state.membership.plan || !state.membership.subscription) {
      return '<section class="ccc-account-card phase4-plan-card"><div class="ccc-account-form-message error">Chưa đọc được gói thành viên hiện tại.</div></section>';
    }

    return '<section class="ccc-account-card membership compact-membership ccc-plan-rail-card phase4-plan-card">' +
      '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">GÓI HIỆN TẠI</span><h2>' + esc(planProductName(plan)) + '</h2></div><span class="ccc-account-plan-badge">' + esc(planProductName(plan) + (vipDayActive() ? " · VIP DAY" : "")) + '</span></header>' +
      '<div class="phase4-plan-metrics">' +
        '<div><span>Giá gói</span><strong>' + esc(planPriceLabel(plan)) + '</strong></div>' +
        '<div><span>Quyền CCC</span><strong>' + esc(effectiveFullMarketAccess() ? "Toàn thị trường" : planScopeLabel(plan)) + '</strong></div>' +
        '<div><span>Số mã theo dõi</span><strong>' + (selected === null ? "—" : selected) + (watchLimit === null ? "" : "/" + watchLimit) + '</strong></div>' +
        '<div><span>Lượt đổi còn lại</span><strong>' + esc(accountQuotaLabel()) + '</strong></div>' +
        '<div><span>Cảnh báo</span><strong>' + esc(alertLabel(plan)) + '</strong></div>' +
      '</div>' +
      '<div class="ccc-account-cycle compact"><span>Chu kỳ hiện tại</span><strong>' + esc(formatDate(sub.cycle_start)) + ' → ' + esc(formatDate(sub.cycle_end)) + '</strong></div>' +
      accountVipDayHtml() +
      accountUpgradeHtml() +
    '</section>';
  }

  function accountAlertChannelsHtml() {
    var plan = state.membership.plan || {};
    var entitlement = alertLabel(plan);
    return '<section class="ccc-account-card compact phase4-alert-card">' +
      '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">KÊNH NHẬN CẢNH BÁO</span><h2>Email, Telegram & Zalo</h2><p>Kết nối kênh nhận thông báo; quyền gửi vẫn phụ thuộc gói.</p></div></header>' +
      '<div class="phase4-channel-list">' +
        '<div><span>Email</span><strong>' + esc(state.user && state.user.email || "—") + '</strong><small>' + (plan.email_alerts ? "Có trong gói" : "Chưa bao gồm trong gói") + '</small></div>' +
        '<div><span>Telegram</span><strong>Chưa kết nối</strong><small>Sau này kết nối qua bot, không nhập ID thủ công.</small></div>' +
        '<div><span>Zalo</span><strong>Chưa kết nối</strong><small>Sau này kết nối qua Zalo OA, không nhập ID thủ công.</small></div>' +
      '</div>' +
      '<p class="phase4-channel-note">Quyền cảnh báo hiện tại: <strong>' + esc(entitlement) + '</strong>.</p>' +
    '</section>';
  }

  function accountSecurityHtml() {
    var provider = String((state.user && state.user.app_metadata || {}).provider || "email").toLowerCase();
    var isEmail = provider !== "google";
    var passwordAction = isEmail
      ? '<button id="account-password-open" class="ccc-account-secondary phase4-password-open" type="button">Đổi mật khẩu</button>'
      : '<p class="phase4-security-note">Mật khẩu được quản lý bởi tài khoản Google.</p>';

    return '<section class="ccc-account-card compact phase4-security-card">' +
      '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">BẢO MẬT</span><h2>Đăng nhập & phiên</h2><p>Quản lý phiên đăng nhập hiện tại.</p></div></header>' +
      (state.account.passwordNotice ? '<div class="ccc-account-form-message success" role="status">' + esc(state.account.passwordNotice) + '</div>' : '') +
      '<div class="ccc-account-security-row"><span>Phương thức</span><strong>' + esc(providerLabel()) + '</strong></div>' +
      '<div class="ccc-account-security-row"><span>Trạng thái</span><strong>Đang hoạt động</strong></div>' +
      '<div class="phase4-security-actions">' + passwordAction +
        '<button id="account-logout" class="ccc-account-secondary danger" type="button">Đăng xuất</button></div>' +
    '</section>';
  }

  function passwordDialogHtml() {
    if (!state.account.passwordOpen) return "";
    var feedback = state.account.passwordError
      ? '<div class="ccc-auth-feedback error" role="alert">' + esc(state.account.passwordError) + '</div>'
      : "";

    return '<div class="ccc-auth-overlay phase4-auth-overlay phase4-password-overlay"><section class="ccc-auth-dialog phase4-password-dialog" role="dialog" aria-modal="true" aria-labelledby="phase4-password-title">' +
      '<header class="ccc-auth-head"><div><span class="eyebrow">BẢO MẬT</span><h2 id="phase4-password-title">Đổi mật khẩu</h2><p>Xác nhận mật khẩu hiện tại trước khi đặt mật khẩu mới.</p></div><button id="account-password-close" class="ccc-auth-close" type="button" aria-label="Đóng">×</button></header>' +
      feedback +
      '<form id="account-password-form" class="ccc-auth-form phase4-password-form" novalidate>' +
        '<label>Mật khẩu hiện tại</label><input name="current_password" type="password" autocomplete="current-password" minlength="8" required>' +
        '<label>Mật khẩu mới</label><input name="new_password" type="password" autocomplete="new-password" minlength="8" required>' +
        '<label>Nhập lại mật khẩu mới</label><input name="confirm_password" type="password" autocomplete="new-password" minlength="8" required>' +
        '<button class="ccc-auth-button primary" type="submit"' + (state.account.passwordBusy ? " disabled" : "") + '>' + (state.account.passwordBusy ? "Đang đổi…" : "Đổi mật khẩu") + '</button>' +
      '</form>' +
    '</section></div>';
  }

  function accountSourceHtml() {
    return '<section class="ccc-account-card compact phase4-source-card"><header class="ccc-account-card-head"><div><h2>Nguồn Dữ liệu</h2></div></header><div class="ccc-account-security-row"><span>Tổng mã quét</span><strong>800</strong></div><div class="ccc-account-security-row"><span>Nguồn dữ liệu</span><strong>Chuyện Chợ Chứng</strong></div><p class="phase4-source-note">Tín hiệu CCC được tính trên dữ liệu thực tế của thị trường, không dự đoán giá.</p></section>';
  }

  function accountPageHtml() {
    if (!state.authReady) return accountLoadingHtml();
    if (!state.user) return accountLoggedOutHtml();

    return '<main id="main-content" class="wrap ccc-account-page phase4-account-page">' +
      '<header class="ccc-account-heading"><div><h1>Tài khoản</h1><p>Quản lý hồ sơ, gói thành viên và thiết lập cá nhân.</p></div><div class="ccc-account-identity"><span class="ccc-account-avatar">' + esc(userInitial()) + '</span><div><strong>' + esc(displayUserName()) + '</strong><span>' + esc(state.user.email || "") + '</span></div></div></header>' +
      '<div class="phase4-account-layout"><div class="phase4-account-main">' + accountProfileHtml() + accountWatchlistHtml() + '</div><aside class="phase4-account-rail">' + accountPlanHtml() + accountAlertChannelsHtml() + accountSecurityHtml() + accountSourceHtml() + '</aside></div>' +
    '</main>';
  }

  function authDialogHtml() {
    if (!state.account.authOpen) return "";
    var feedback = state.account.authError ? '<div class="ccc-auth-feedback error" role="alert">' + esc(state.account.authError) + '</div>' : "";
    return '<div class="ccc-auth-overlay phase4-auth-overlay"><section class="ccc-auth-dialog" role="dialog" aria-modal="true" aria-labelledby="phase4-auth-title">' +
      '<header class="ccc-auth-head"><div><span class="eyebrow">CCC ACCOUNT</span><h2 id="phase4-auth-title">Đăng nhập</h2><p>Đăng nhập để sử dụng phạm vi cá nhân của Chuyện Chợ Chứng.</p></div><button id="auth-dialog-close" class="ccc-auth-close" type="button" aria-label="Đóng">×</button></header>' +
      feedback +
      '<div class="ccc-auth-body"><button id="auth-google" class="ccc-auth-google" type="button"' + (state.account.authBusy ? " disabled" : "") + '><span class="ccc-auth-google-mark">G</span><span>Tiếp tục với Google</span></button><div class="ccc-auth-divider"><span>hoặc đăng nhập bằng email</span></div><form id="auth-email-form" class="ccc-auth-form" novalidate><label>Email</label><input name="email" type="email" autocomplete="email" placeholder="tenban@example.com" required><label>Mật khẩu</label><input name="password" type="password" autocomplete="current-password" minlength="8" placeholder="Tối thiểu 8 ký tự" required><button class="ccc-auth-button primary" type="submit"' + (state.account.authBusy ? " disabled" : "") + '>' + (state.account.authBusy ? "Đang xử lý…" : "Đăng nhập") + '</button></form><p class="ccc-auth-stage-note">Đăng nhập Google hoặc dùng tài khoản Email đã được tạo trên hệ thống.</p></div>' +
    '</section></div>';
  }



  /* ==========================================================
     Phase 5B — Public Fundamental Research
     Alpha.19 is the visual donor; Phase 4/5A remains the clean runtime.
     No CCC Technical Intelligence is mixed into these surfaces.
     ========================================================== */

  function researchMode() {
    return location.pathname === "/sang-loc-co-ban" ? "fundamental" : "industry";
  }

  function researchMetadata(symbol) {
    return state.research.metadataBySymbol[String(symbol || "").toUpperCase()] || {};
  }

  function researchCompany(row) {
    var meta = researchMetadata(row && row.symbol);
    return meta.display_name || meta.company_name || "Tên công ty đang cập nhật";
  }

  function researchScore(row) {
    var key = String(row && row.symbol || "").toUpperCase();
    return state.research.scoreBySymbol[key] || detailFinancialScore(row, state.research.groupRows[String(row && row.website_group || "")] || []);
  }

  function researchScoreRatio(row) {
    var score = researchScore(row);
    return score && score.available ? score.earned / score.available * 100 : null;
  }

  function researchScoreTone(row) {
    var ratio = researchScoreRatio(row);
    return ratio === null ? "score-na" : ratio >= 75 ? "score-good" : ratio >= 55 ? "score-mid" : "score-low";
  }

  function researchGroupList() {
    var counts = Object.create(null);
    state.research.financialRows.forEach(function (row) {
      var group = String(row && row.website_group || "").trim();
      if (!group) return;
      counts[group] = (counts[group] || 0) + 1;
    });
    return Object.keys(counts).sort(function (a, b) {
      return a.localeCompare(b, "vi");
    }).map(function (group) { return [group, counts[group]]; });
  }

  function researchFreshnessLabel(value) {
    var raw = String(value || "").trim().toUpperCase();
    if (!raw) return "Chưa rõ";
    if (["FRESH", "CURRENT", "OK"].indexOf(raw) >= 0) return "Mới";
    if (["STALE", "OLD"].indexOf(raw) >= 0) return "Cần cập nhật";
    if (["NO_DATA", "NO_FINANCIAL_DATA", "MISSING"].indexOf(raw) >= 0) return "Thiếu dữ liệu";
    return raw.replace(/_/g, " ");
  }

  function researchMetricHead(title, helper) {
    return '<span class="th-main">' + esc(title) + '</span>' + (helper ? '<span class="th-sub">' + esc(helper) + '</span>' : '');
  }

  function researchScoreHtml(row) {
    var score = researchScore(row);
    if (!score || !score.available) return '<strong class="research-score score-na">—</strong>';
    return '<strong class="research-score ' + researchScoreTone(row) + '">' + score.earned + '/' + score.available + '</strong>';
  }

  function researchTabsHtml() {
    var mode = researchMode();
    return '<nav class="research-tabs phase5b-research-tabs" aria-label="Điều hướng Nghiên cứu">' +
      '<a href="/so-sanh-theo-nganh" class="' + (mode === "industry" ? "active" : "") + '"' + (mode === "industry" ? ' aria-current="page"' : '') + '>Theo ngành</a>' +
      '<a href="/sang-loc-co-ban" class="' + (mode === "fundamental" ? "active" : "") + '"' + (mode === "fundamental" ? ' aria-current="page"' : '') + '>Sàng lọc cơ bản</a>' +
    '</nav>';
  }

  function researchHeroHtml(title, copy) {
    return '<section class="page-intro research-hero page-header"><span class="eyebrow">NGHIÊN CỨU CƠ BẢN CÔNG KHAI</span><h1>' + esc(title) + '</h1><p>' + esc(copy) + '</p></section>';
  }

  function researchFinancialCard(row, mode) {
    mode = mode || researchMode();
    var score = researchScore(row);
    var company = researchCompany(row);
    var meta = researchMetadata(row.symbol);
    var metaBits = [String(meta.exchange || "").trim()];
    if (mode === "fundamental" && row.website_group) metaBits.push(String(row.website_group));
    var metaLine = metaBits.filter(Boolean).join(" · ");

    return '<article class="fund-card panel phase5b-fund-card" data-symbol="' + esc(row.symbol) + '">' +
      '<div class="fund-card-top"><div class="phase5b-card-id">' + companyLogo(row.symbol) +
        '<div><strong class="fund-symbol">' + esc(row.symbol) + '</strong><span title="' + esc(company) + '">' + esc(company) + '</span><small title="' + esc(metaLine) + '">' + esc(metaLine) + '</small></div></div>' +
        '<div class="phase5b-card-score"><strong class="' + researchScoreTone(row) + '">' + (score.available ? score.earned + '/' + score.available : '—') + '</strong><span>Điểm cơ bản</span></div>' +
      '</div>' +
      '<div class="fund-card-grid">' +
        '<div><small>LNST so cùng kỳ</small><b class="' + metricClass(row.profit_yoy_pct) + '">' + pct(row.profit_yoy_pct, 2) + '</b></div>' +
        '<div><small>ROE · LN / vốn chủ</small><b class="' + metricClass(row.roea_pct) + '">' + pct(row.roea_pct, 2) + '</b></div>' +
        '<div><small>P/E · Giá / lợi nhuận</small><b>' + (num(row.pe) === null ? '—' : fmt(row.pe, 2) + 'x') + '</b></div>' +
        '<div><small>P/B · Giá / sổ sách</small><b>' + (num(row.pb) === null ? '—' : fmt(row.pb, 2) + 'x') + '</b></div>' +
      '</div>' +
      '<div class="fund-card-foot phase5b-card-freshness"><span>Dữ liệu: <strong>' + esc(researchFreshnessLabel(row.freshness_status)) + '</strong></span></div>' +
    '</article>';
  }

  function researchIndustryTableRow(row) {
    var company = researchCompany(row);
    var meta = researchMetadata(row.symbol);
    return '<tr data-symbol="' + esc(row.symbol) + '">' +
      '<td><div class="research-company-cell">' + companyLogo(row.symbol) + '<div><strong>' + esc(row.symbol) + '</strong><span title="' + esc(company) + '">' + esc(company) + '</span><small>' + esc(meta.exchange || "") + '</small></div></div></td>' +
      '<td class="center">' + researchScoreHtml(row) + '</td>' +
      '<td class="num ' + metricClass(row.profit_yoy_pct) + '"><strong>' + pct(row.profit_yoy_pct, 2) + '</strong></td>' +
      '<td class="num ' + metricClass(row.roea_pct) + '"><strong>' + pct(row.roea_pct, 2) + '</strong></td>' +
      '<td class="num">' + (num(row.pe) === null ? '—' : fmt(row.pe, 2) + 'x') + '</td>' +
      '<td class="num">' + (num(row.pb) === null ? '—' : fmt(row.pb, 2) + 'x') + '</td>' +
      '<td class="center"><span class="freshness-tag freshness-' + esc(String(row.freshness_status || '').toLowerCase()) + '">' + esc(researchFreshnessLabel(row.freshness_status)) + '</span></td>' +
    '</tr>';
  }

  function researchScreenerTableRow(row) {
    var company = researchCompany(row);
    var meta = researchMetadata(row.symbol);
    return '<tr data-symbol="' + esc(row.symbol) + '">' +
      '<td><div class="research-company-cell">' + companyLogo(row.symbol) + '<div><strong>' + esc(row.symbol) + '</strong><span title="' + esc(company) + '">' + esc(company) + '</span><small>' + esc(meta.exchange || "") + '</small></div></div></td>' +
      '<td><span class="industry-name-cell" title="' + esc(row.website_group || '') + '">' + esc(row.website_group || '—') + '</span></td>' +
      '<td class="center">' + researchScoreHtml(row) + '</td>' +
      '<td class="num ' + metricClass(row.profit_yoy_pct) + '"><strong>' + pct(row.profit_yoy_pct, 2) + '</strong></td>' +
      '<td class="num ' + metricClass(row.roea_pct) + '"><strong>' + pct(row.roea_pct, 2) + '</strong></td>' +
      '<td class="num">' + (num(row.pe) === null ? '—' : fmt(row.pe, 2) + 'x') + '</td>' +
      '<td class="num">' + (num(row.pb) === null ? '—' : fmt(row.pb, 2) + 'x') + '</td>' +
      '<td class="center"><span class="freshness-tag freshness-' + esc(String(row.freshness_status || '').toLowerCase()) + '">' + esc(researchFreshnessLabel(row.freshness_status)) + '</span></td>' +
    '</tr>';
  }

  function researchLatestUpdatedAt() {
    var latest = 0;
    var latestValue = null;
    state.research.financialRows.forEach(function (row) {
      var ms = Date.parse(row && row.updated_at || "");
      if (Number.isFinite(ms) && ms > latest) {
        latest = ms;
        latestValue = row.updated_at;
      }
    });
    return latestValue;
  }

  function researchSourceRailHtml() {
    var rows = state.research.financialRows;
    var withScore = rows.filter(function (row) { return !!researchScore(row).available; }).length;
    var body = '<dl class="rail-kv">' +
      '<div><dt>Nguồn</dt><dd>Chuyện Chợ Chứng</dd></div>' +
      '<div><dt>Bộ dữ liệu</dt><dd>Dữ liệu cơ bản doanh nghiệp</dd></div>' +
      '<div><dt>Cập nhật</dt><dd>' + esc(formatDateTime(researchLatestUpdatedAt())) + '</dd></div>' +
      '<div><dt>Có thể chấm điểm</dt><dd>' + withScore + '/' + rows.length + ' mã</dd></div>' +
    '</dl><p class="rail-note"><span>Thiếu dữ liệu được ghi rõ, không tự biến thành điểm 0.</span></p>';
    return railCardHtml("Nguồn dữ liệu", "Cơ bản công khai", body, "research-source-card");
  }

  function researchPages(total) {
    return Math.max(1, Math.ceil(Math.max(0, total) / RESEARCH_PAGE_SIZE));
  }

  function researchClampPage(page, total) {
    return Math.max(1, Math.min(researchPages(total), Number(page || 1)));
  }

  function researchPageSlice(rows, page) {
    var current = researchClampPage(page, rows.length);
    var start = (current - 1) * RESEARCH_PAGE_SIZE;
    return {
      page: current,
      pages: researchPages(rows.length),
      start: start,
      end: Math.min(rows.length, start + RESEARCH_PAGE_SIZE),
      total: rows.length,
      rows: rows.slice(start, start + RESEARCH_PAGE_SIZE)
    };
  }

  function researchPaginationHtml(mode, pageData) {
    if (!pageData || pageData.pages <= 1) return "";
    var total = pageData.total != null ? pageData.total : pageData.end;
    return '<nav class="phase5b-pagination" aria-label="Phân trang kết quả">' +
      '<button type="button" class="secondary-action phase5b-page-prev" data-research-page="' + esc(mode) + '" data-delta="-1"' + (pageData.page <= 1 ? ' disabled' : '') + '>← Trước</button>' +
      '<span class="phase5b-page-status"><strong>Trang ' + pageData.page + ' / ' + pageData.pages + '</strong><small>' + (pageData.start + 1) + '–' + pageData.end + ' / ' + total + ' mã</small></span>' +
      '<button type="button" class="secondary-action phase5b-page-next" data-research-page="' + esc(mode) + '" data-delta="1"' + (pageData.page >= pageData.pages ? ' disabled' : '') + '>Sau →</button>' +
    '</nav>';
  }

  function researchIndustryGuideRailHtml() {
    var body = '<div class="phase5b-rail-guide">' +
      '<p><strong>Điểm cơ bản</strong><span>Là điểm đạt trên phần dữ liệu hiện có, ví dụ 52/80.</span></p>' +
      '<p><strong>Thiếu dữ liệu</strong><span>Không bị tự tính thành điểm 0.</span></p>' +
      '<p><strong>P/E · P/B</strong><span>Được chấm tương đối so với doanh nghiệp cùng ngành.</span></p>' +
    '</div>';
    return railCardHtml("Cách đọc kết quả", "Điểm & dữ liệu", body, "research-guide-card");
  }

  function researchFundamentalFilterRailHtml(rows) {
    var score = state.research.fundamentalMinScore ? 'Từ ' + state.research.fundamentalMinScore + '%' : 'Tất cả';
    var growth = state.research.fundamentalProfitGrowth === 'positive' ? 'LNST tăng' :
      state.research.fundamentalProfitGrowth === '20plus' ? 'LNST ≥ 20%' : 'Tất cả';
    var roe = state.research.fundamentalRoe === '15plus' ? 'ROE ≥ 15%' :
      state.research.fundamentalRoe === '20plus' ? 'ROE ≥ 20%' : 'Tất cả';
    var body = '<dl class="rail-kv">' +
      '<div><dt>Ngành</dt><dd>' + esc(state.research.fundamentalIndustry === 'all' ? 'Tất cả' : state.research.fundamentalIndustry) + '</dd></div>' +
      '<div><dt>Điểm cơ bản</dt><dd>' + esc(score) + '</dd></div>' +
      '<div><dt>LNST</dt><dd>' + esc(growth) + '</dd></div>' +
      '<div><dt>ROE</dt><dd>' + esc(roe) + '</dd></div>' +
    '</dl><p class="rail-note"><span>' + rows.length + ' mã phù hợp với bộ lọc hiện tại.</span></p>';
    return railCardHtml("Bộ lọc đang áp dụng", "Sàng lọc", body, "research-filter-rail-card");
  }

  function researchContextRailHtml(mode, rows, group, pageData) {
    var body;
    if (mode === "industry") {
      body = '<dl class="rail-kv">' +
        '<div><dt>Ngành đang xem</dt><dd>' + esc(group || '—') + '</dd></div>' +
        '<div><dt>Số doanh nghiệp</dt><dd>' + rows.length + ' mã</dd></div>' +
        '<div><dt>Sắp xếp</dt><dd>Điểm cơ bản</dd></div>' +
        '<div><dt>Trang</dt><dd>' + (pageData ? pageData.page + '/' + pageData.pages : '1/1') + '</dd></div>' +
      '</dl><p class="rail-note"><span>So sánh chỉ dùng dữ liệu cơ bản; không trộn tín hiệu kỹ thuật CCC.</span></p>';
      return railCardHtml("Ngữ cảnh nghiên cứu", "Theo ngành", body, "research-context-card");
    }

    body = '<dl class="rail-kv">' +
      '<div><dt>Kết quả</dt><dd>' + rows.length + ' mã</dd></div>' +
      '<div><dt>Tổng dữ liệu</dt><dd>' + state.research.financialRows.length + ' mã</dd></div>' +
      '<div><dt>Trang</dt><dd>' + (pageData ? pageData.page + '/' + pageData.pages : '1/1') + '</dd></div>' +
    '</dl><p class="rail-note"><span>Mã thiếu dữ liệu vẫn hiện khi không bị loại bởi tiêu chí bạn chọn.</span></p>';
    return railCardHtml("Ngữ cảnh nghiên cứu", "Sàng lọc", body, "research-context-card");
  }


  function researchScoreMethodHtml() {
    return '<details class="score-method panel phase5b-score-method phase5b-method-disclosure">' +
      '<summary><span><strong>Cách tính Điểm cơ bản</strong><small>4 nhóm chỉ tiêu · tối đa 100 điểm · mở để xem chi tiết</small></span><span class="method-total">Tối đa 100 điểm</span></summary>' +
      '<div class="phase5b-method-body">' +
        '<p class="phase5b-method-intro">Mỗi điểm xuất phát từ chỉ tiêu tài chính thực tế. Mã thiếu dữ liệu chỉ được chấm trên phần có dữ liệu và <b>không tự quy đổi thành 100 điểm</b>.</p>' +
        '<div class="method-grid">' +
          '<div class="method-card"><b>1. Tăng trưởng · tối đa 35 điểm</b><p><strong>20đ</strong> LNST so với cùng kỳ.<br><strong>10đ</strong> Doanh thu / thu nhập so cùng kỳ.<br><strong>5đ</strong> LNST so với quý trước.</p></div>' +
          '<div class="method-card"><b>2. Hiệu quả sinh lời · tối đa 30 điểm</b><p><strong>20đ</strong> ROE – lợi nhuận trên vốn chủ sở hữu.<br><strong>10đ</strong> ROA – lợi nhuận trên tổng tài sản.</p></div>' +
          '<div class="method-card"><b>3. Sức khỏe tài chính · tối đa 20 điểm</b><p>Doanh nghiệp thông thường: <strong>10đ</strong> Nợ vay / vốn chủ và <strong>10đ</strong> Nợ / tổng tài sản. Một số ngành đặc thù có thể chưa đủ chỉ tiêu để chấm phần này.</p></div>' +
          '<div class="method-card"><b>4. Định giá · tối đa 15 điểm</b><p><strong>8đ</strong> P/E và <strong>7đ</strong> P/B, so tương đối với trung vị các doanh nghiệp cùng ngành.</p></div>' +
        '</div>' +
        '<div class="term-glossary"><div><b>ROE là gì?</b><span>100 đồng vốn chủ sở hữu tạo ra bao nhiêu đồng lợi nhuận.</span></div><div><b>ROA là gì?</b><span>Doanh nghiệp sử dụng toàn bộ tài sản hiệu quả đến mức nào.</span></div><div><b>P/E là gì?</b><span>So sánh giá cổ phiếu với lợi nhuận doanh nghiệp tạo ra.</span></div><div><b>P/B là gì?</b><span>So sánh giá cổ phiếu với giá trị sổ sách trên mỗi cổ phần.</span></div></div>' +
        '<details class="score-rules"><summary>Xem chi tiết ngưỡng chấm điểm</summary><div class="rule-grid">' +
          '<p><b>LNST so cùng kỳ · 20đ:</b><br>≥30%: 20đ · ≥20%: 16đ · ≥10%: 12đ · ≥0%: 7đ · âm: 0đ.</p>' +
          '<p><b>Doanh thu / thu nhập · 10đ:</b><br>≥20%: 10đ · ≥10%: 8đ · ≥5%: 5đ · ≥0%: 3đ · âm: 0đ.</p>' +
          '<p><b>ROE · 20đ:</b><br>≥20%: 20đ · ≥15%: 16đ · ≥10%: 11đ · ≥5%: 6đ · ≥0%: 2đ.</p>' +
          '<p><b>ROA · 10đ:</b><br>≥10%: 10đ · ≥7%: 8đ · ≥5%: 6đ · ≥2%: 3đ · ≥0%: 1đ.</p>' +
          '<p><b>Nợ vay / vốn chủ · 10đ:</b><br>&lt;30%: 10đ · &lt;60%: 8đ · &lt;100%: 5đ · &lt;150%: 2đ.</p>' +
          '<p><b>P/E và P/B · 15đ:</b><br>Điểm cao hơn khi định giá thấp hơn trung vị ngành; giảm dần khi vượt trung vị.</p>' +
        '</div></details>' +
        '<p class="score-note"><b>Lưu ý:</b> Điểm số hỗ trợ sàng lọc và học phân tích, không phải khuyến nghị mua/bán.</p>' +
      '</div>' +
    '</details>';
  }

  function researchHasActiveFilters() {
    return state.research.fundamentalIndustry !== "all" ||
      Number(state.research.fundamentalMinScore || 0) > 0 ||
      state.research.fundamentalProfitGrowth !== "all" ||
      state.research.fundamentalRoe !== "all";
  }

  function researchIndustryHtml() {
    var groups = researchGroupList();
    if (!state.research.industryGroup && groups.length) state.research.industryGroup = groups[0][0];

    var selected = (state.research.groupRows[state.research.industryGroup] || []).slice().sort(function (a, b) {
      var ar = researchScoreRatio(a), br = researchScoreRatio(b);
      if (ar === null && br === null) return String(a.symbol || '').localeCompare(String(b.symbol || ''));
      if (ar === null) return 1;
      if (br === null) return -1;
      return br - ar || String(a.symbol || '').localeCompare(String(b.symbol || ''));
    });

    state.research.industryPage = researchClampPage(state.research.industryPage, selected.length);
    var pageData = researchPageSlice(selected, state.research.industryPage);

    var options = groups.map(function (group) {
      return '<option value="' + esc(group[0]) + '"' + (state.research.industryGroup === group[0] ? ' selected' : '') + '>' + esc(group[0]) + ' · ' + group[1] + ' mã</option>';
    }).join('');

    var groupButtons = groups.map(function (group) {
      var active = state.research.industryGroup === group[0];
      return '<button type="button" class="industry-chip ' + (active ? 'active' : '') + '" data-research-industry="' + esc(group[0]) + '" aria-pressed="' + (active ? 'true' : 'false') + '"><span>' + esc(group[0]) + '</span><b>' + group[1] + ' mã</b></button>';
    }).join('');

    var selector =
      '<div class="phase5b-industry-desktop-select"><label><span>Ngành đang xem</span><select data-research-industry-select aria-label="Chọn ngành">' + options + '</select></label><small>' + groups.length + ' nhóm ngành</small></div>' +
      '<section class="industry-picker research-industry-grid" aria-label="Chọn ngành">' + groupButtons + '</section>';

    var tableRows = pageData.rows.map(researchIndustryTableRow).join('');
    var cards = pageData.rows.map(function (row) { return researchFinancialCard(row, "industry"); }).join('');

    var main = selector +
      '<section class="panel industry-panel phase5b-industry-panel" data-research-results>' +
        '<div class="section-title"><div><h2>' + esc(state.research.industryGroup || 'Ngành') + '</h2><p>' + selected.length + ' mã · sắp xếp theo Điểm cơ bản trên phần dữ liệu có thể chấm.</p></div></div>' +
        '<div class="desktop-table"><div class="table-shell fund-table-shell"><table class="fundamental-table industry-table">' +
          '<colgroup><col class="col-company"><col class="col-score"><col class="col-growth"><col class="col-roe"><col class="col-pe"><col class="col-pb"><col class="col-fresh"></colgroup>' +
          '<thead><tr>' +
            '<th>' + researchMetricHead('Mã cổ phiếu', 'Công ty / sàn') + '</th>' +
            '<th>' + researchMetricHead('Điểm cơ bản', 'Điểm đạt / phần có thể chấm') + '</th>' +
            '<th class="num">' + researchMetricHead('Tăng trưởng lợi nhuận', 'So với cùng kỳ') + '</th>' +
            '<th class="num">' + researchMetricHead('ROE', 'LN / vốn chủ sở hữu') + '</th>' +
            '<th class="num">' + researchMetricHead('P/E', 'Giá / lợi nhuận') + '</th>' +
            '<th class="num">' + researchMetricHead('P/B', 'Giá / giá trị sổ sách') + '</th>' +
            '<th>' + researchMetricHead('Dữ liệu', 'Mức độ cập nhật') + '</th>' +
          '</tr></thead><tbody>' + tableRows + '</tbody></table></div></div>' +
        '<div class="mobile-list fund-mobile-list">' + cards + '</div>' +
        researchPaginationHtml("industry", pageData) +
      '</section>';

    var rail = researchContextRailHtml('industry', selected, state.research.industryGroup, pageData) +
      researchIndustryGuideRailHtml() +
      researchSourceRailHtml();

    return '<main id="main-content" class="wrap fund-main research-main page-shell has-context-rail">' +
      researchHeroHtml('So sánh theo ngành', 'Chọn một ngành để đặt các doanh nghiệp cạnh nhau theo tăng trưởng lợi nhuận, khả năng sinh lời và định giá.') +
      researchTabsHtml() +
      '<div class="content-grid phase5b-research-grid"><div class="content-main">' + main + '</div><aside class="context-rail research-context-rail">' + rail + '</aside></div>' +
      '<p class="disclaimer">Điểm số hỗ trợ sàng lọc và học phân tích, không phải khuyến nghị mua/bán.</p></main>';
  }

  function researchFundamentalRows() {
    return state.research.financialRows.slice().filter(function (row) {
      if (state.research.fundamentalIndustry !== "all" && String(row.website_group || "") !== state.research.fundamentalIndustry) return false;
      var ratio = researchScoreRatio(row);
      if (state.research.fundamentalMinScore && (ratio === null || ratio < state.research.fundamentalMinScore)) return false;
      var py = num(row.profit_yoy_pct), roe = num(row.roea_pct);
      if (state.research.fundamentalProfitGrowth === 'positive' && !(py !== null && py > 0)) return false;
      if (state.research.fundamentalProfitGrowth === '20plus' && !(py !== null && py >= 20)) return false;
      if (state.research.fundamentalRoe === '15plus' && !(roe !== null && roe >= 15)) return false;
      if (state.research.fundamentalRoe === '20plus' && !(roe !== null && roe >= 20)) return false;
      return true;
    }).sort(function (a, b) {
      var ar = researchScoreRatio(a), br = researchScoreRatio(b);
      if (ar === null && br === null) return String(a.symbol || '').localeCompare(String(b.symbol || ''));
      if (ar === null) return 1;
      if (br === null) return -1;
      return br - ar || String(a.symbol || '').localeCompare(String(b.symbol || ''));
    });
  }

  function researchFilterChips(items, current, key) {
    return items.map(function (item) {
      var active = String(current) === String(item[0]);
      return '<button type="button" class="chip ' + (active ? 'active' : '') + '" data-research-filter="' + esc(key) + '" data-value="' + esc(item[0]) + '" aria-pressed="' + (active ? 'true' : 'false') + '">' + esc(item[1]) + '</button>';
    }).join('');
  }

  function researchFundamentalHtml() {
    var rows = researchFundamentalRows();
    state.research.fundamentalPage = researchClampPage(state.research.fundamentalPage, rows.length);
    var pageData = researchPageSlice(rows, state.research.fundamentalPage);
    var groups = researchGroupList();

    var scoreBtns = researchFilterChips([[0,'Tất cả'],[55,'Từ 55% mức điểm có thể chấm'],[70,'Từ 70% mức điểm có thể chấm'],[80,'Từ 80% mức điểm có thể chấm']], state.research.fundamentalMinScore, 'score');
    var growthBtns = researchFilterChips([['all','Tất cả'],['positive','Lợi nhuận tăng so cùng kỳ'],['20plus','Lợi nhuận tăng từ 20% so cùng kỳ']], state.research.fundamentalProfitGrowth, 'growth');
    var roeBtns = researchFilterChips([['all','Tất cả'],['15plus','ROE từ 15%'],['20plus','ROE từ 20%']], state.research.fundamentalRoe, 'roe');

    var industryOptions = '<option value="all"' + (state.research.fundamentalIndustry === 'all' ? ' selected' : '') + '>Tất cả ngành</option>' +
      groups.map(function (group) {
        return '<option value="' + esc(group[0]) + '"' + (state.research.fundamentalIndustry === group[0] ? ' selected' : '') + '>' + esc(group[0]) + ' · ' + group[1] + ' mã</option>';
      }).join('');

    var filters = '<section class="panel fund-filters phase5b-fund-filters">' +
      '<div class="phase5b-filter-head"><div><h2>Bộ lọc cơ bản</h2><p>Thu hẹp danh sách theo ngành, mức điểm, tăng trưởng lợi nhuận và ROE.</p></div>' +
      (researchHasActiveFilters() ? '<button type="button" class="secondary-action phase5b-reset-filters" data-research-reset>Xóa bộ lọc</button>' : '') + '</div>' +
      '<div class="filter-block phase5b-industry-filter"><p class="filter-label">Ngành</p><div class="filter-help">Giới hạn kết quả trong một nhóm ngành nếu bạn muốn so sánh tập trung hơn.</div><select data-research-fund-industry aria-label="Lọc theo ngành">' + industryOptions + '</select></div>' +
      '<div class="filter-block"><p class="filter-label">Mức Điểm cơ bản</p><div class="filter-help">Ví dụ 70% nghĩa là doanh nghiệp đạt ít nhất 70% số điểm trên những chỉ tiêu hiện có.</div><div class="chips">' + scoreBtns + '</div></div>' +
      '<div class="filter-block"><p class="filter-label">Tăng trưởng lợi nhuận sau thuế</p><div class="chips">' + growthBtns + '</div></div>' +
      '<div class="filter-block"><p class="filter-label">ROE – lợi nhuận trên vốn chủ sở hữu</p><div class="chips">' + roeBtns + '</div></div>' +
    '</section>';

    var result = '<p class="result-info phase5b-result-info">Tìm thấy <strong>' + rows.length + '</strong> / ' + state.research.financialRows.length + ' mã có dữ liệu cơ bản. Mỗi trang hiển thị tối đa ' + RESEARCH_PAGE_SIZE + ' mã.</p>' +
      '<section class="panel screener-table-panel phase5b-screener-panel" data-research-results>' +
        '<div class="desktop-table"><div class="table-shell screener-table-shell"><table class="fundamental-table screener-table">' +
          '<colgroup><col class="col-company"><col class="col-industry"><col class="col-score"><col class="col-growth"><col class="col-roe"><col class="col-pe"><col class="col-pb"><col class="col-fresh"></colgroup>' +
          '<thead><tr>' +
            '<th>' + researchMetricHead('Mã cổ phiếu', 'Công ty / sàn') + '</th>' +
            '<th>' + researchMetricHead('Ngành', 'Nhóm hoạt động chính') + '</th>' +
            '<th>' + researchMetricHead('Điểm cơ bản', 'Điểm đạt / phần có thể chấm') + '</th>' +
            '<th class="num">' + researchMetricHead('Tăng trưởng lợi nhuận', 'So với cùng kỳ') + '</th>' +
            '<th class="num">' + researchMetricHead('ROE', 'LN / vốn chủ sở hữu') + '</th>' +
            '<th class="num">' + researchMetricHead('P/E', 'Giá / lợi nhuận') + '</th>' +
            '<th class="num">' + researchMetricHead('P/B', 'Giá / giá trị sổ sách') + '</th>' +
            '<th>' + researchMetricHead('Dữ liệu', 'Mức độ cập nhật') + '</th>' +
          '</tr></thead><tbody>' + pageData.rows.map(researchScreenerTableRow).join('') + '</tbody></table></div></div>' +
        '<div class="mobile-list fund-mobile-list">' + pageData.rows.map(function (row) { return researchFinancialCard(row, "fundamental"); }).join('') + '</div>' +
        researchPaginationHtml("fundamental", pageData) +
      '</section>';

    var rail = researchContextRailHtml('fundamental', rows, '', pageData) +
      researchFundamentalFilterRailHtml(rows) +
      researchSourceRailHtml();

    return '<main id="main-content" class="wrap fund-main research-main page-shell has-context-rail">' +
      researchHeroHtml('Sàng lọc cơ bản', 'Dùng các chỉ tiêu tài chính để tìm doanh nghiệp phù hợp với tiêu chí của bạn. Phần dữ liệu thiếu luôn được ghi rõ thay vì biến thành điểm 0 giả.') +
      researchTabsHtml() +
      '<div class="content-grid phase5b-research-grid"><div class="content-main">' + filters + researchScoreMethodHtml() + result + '</div><aside class="context-rail research-context-rail">' + rail + '</aside></div>' +
      '<p class="disclaimer">Điểm số hỗ trợ sàng lọc và học phân tích, không phải khuyến nghị mua/bán.</p></main>';
  }

  function researchLoadingHtml() {
    return '<main id="main-content" class="wrap fund-main research-main page-shell">' + researchHeroHtml(researchMode() === 'industry' ? 'So sánh theo ngành' : 'Sàng lọc cơ bản', 'Đang tải dữ liệu cơ bản công khai…') + researchTabsHtml() + '<section class="panel-anatomy transplant-state"><span class="transplant-spinner"></span><div><strong>Đang tải Nghiên cứu…</strong><p>Đang lấy dữ liệu tài chính và tên doanh nghiệp.</p></div></section></main>';
  }

  function researchErrorHtml() {
    var industry = researchMode() === 'industry';
    var title = industry ? 'So sánh theo ngành' : 'Sàng lọc cơ bản';
    var copy = industry
      ? 'Chọn một ngành để đặt các doanh nghiệp cạnh nhau theo tăng trưởng lợi nhuận, khả năng sinh lời và định giá.'
      : 'Dùng các chỉ tiêu tài chính để tìm doanh nghiệp phù hợp với tiêu chí của bạn.';
    return '<main id="main-content" class="wrap fund-main research-main page-shell">' + researchHeroHtml(title, copy) + researchTabsHtml() + '<section class="panel-anatomy transplant-state is-error"><div><strong>Không tải được dữ liệu Nghiên cứu.</strong><p>' + esc(state.research.error || 'Nguồn dữ liệu tạm thời chưa phản hồi.') + '</p><button type="button" class="secondary-action" data-research-retry>Thử lại</button></div></section></main>';
  }

  function researchPageHtml() {
    if (state.research.loading && !state.research.loaded) return researchLoadingHtml();
    if (state.research.error && !state.research.loaded) return researchErrorHtml();
    if (!state.research.loaded) return researchLoadingHtml();
    return researchMode() === 'fundamental' ? researchFundamentalHtml() : researchIndustryHtml();
  }


  function placeholderPageHtml(title, copy) {
    return '<main id="main-content" class="wrap page-shell"><section class="page-heading page-header"><div><h1>' + esc(title) + '</h1><p>' + esc(copy) + '</p></div></section><div class="content-grid"><div class="content-main"><section class="panel-anatomy transplant-placeholder"><strong>Đang giữ checkpoint kiến trúc sạch.</strong><p>Màn hình này sẽ được port ở phase tiếp theo bằng cùng Alpha.19 donor.</p></section></div></div></main>';
  }

  function routeHtml() {
    if (state.detail.open) return stockDetailPageHtml();
    if (state.route === "overview") return overviewPageHtml();
    if (state.route === "scanner") return scannerPageHtml();
    if (state.route === "research") return researchPageHtml();
    return accountPageHtml();
  }

  function render() {
    app.innerHTML = headerHtml() + accessNoticeHtml() + routeHtml() + authDialogHtml() + passwordDialogHtml();
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
    var selectionKey = owner + ":" + state.overview.group;
    if (!force && state.overview.loadedFor === selectionKey && state.overview.data) return;

    state.overview.loading = true;
    state.overview.error = "";
    if (state.route === "overview") render();

    try {
      state.overview.data = state.user
        ? await window.CCCData.getMyOverviewPage(state.overview.group, 1, OVERVIEW_PAGE_SIZE)
        : await window.CCCData.getPublicOverviewState();

      if (state.user) reconcileOverviewAccessSnapshot(state.overview.data);
      state.overview.page = 1;
      state.overview.loadedFor = selectionKey;
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

  async function ensureScanner(force) {
    if (!state.authReady || state.scanner.loading) return;

    var technical = scannerTechnicalMode();

    if (state.scanner.mode === "watchlist" && !state.user) {
      state.scanner.technicalRows = [];
      state.scanner.technicalMeta = null;
      state.scanner.technicalLoadedKey = "";
      state.scanner.watchlistRows = [];
      state.scanner.personalWatchlistSymbols = [];
      state.scanner.personalWatchlistLoadedFor = "";
      state.scanner.watchlistLoadedFor = "";
      if (state.route === "scanner") render();
      return;
    }

    state.scanner.loading = true;
    state.scanner.error = "";
    if (state.route === "scanner") render();

    try {
      if (!technical && state.scanner.mode === "market") {
        if (force || !state.scanner.marketLoaded) {
          state.scanner.marketRows = await window.CCCData.loadScannerMarketBasics();
          state.scanner.marketLoaded = true;
        }
        return;
      }

      if (state.scanner.mode === "watchlist" && state.user &&
          (force || state.scanner.personalWatchlistLoadedFor !== state.user.id)) {
        var personalState = await window.CCCData.getWatchlistState();
        state.scanner.personalWatchlistSymbols = uniqueSorted(personalState && personalState.symbols || []);
        state.scanner.personalWatchlistLoadedFor = state.user.id;
        state.scanner.watchlistLoadedFor = state.user.id;
      }

      var scope = scannerTechnicalScope();
      var key = [
        state.user && state.user.id || "",
        scope,
        state.scanner.signal,
        state.scanner.exchange,
        String(state.scanner.query || "").trim(),
        state.scanner.sort,
        state.scanner.page
      ].join("|");

      if (!force && state.scanner.technicalLoadedKey === key && state.scanner.technicalMeta) return;

      var result = await window.CCCData.getMyScannerPage({
        scope: scope,
        signal: state.scanner.signal,
        exchange: state.scanner.exchange,
        query: state.scanner.query,
        sort: state.scanner.sort,
        page: state.scanner.page,
        pageSize: 50
      });

      state.scanner.technicalMeta = result || {};
      state.scanner.technicalRows = Array.isArray(result && result.rows) ? result.rows : [];
      state.scanner.technicalRowsReceived = state.scanner.technicalRows.length;
      state.scanner.technicalScopeAtLoad = scope === "MARKET" ? "MARKET" : "PERSONAL_WATCHLIST";
      state.scanner.page = Number(result && result.page || state.scanner.page || 1);

      if (scope === "PERSONAL") {
        state.scanner.watchlistRows = state.scanner.technicalRows.slice();
        state.scanner.watchlistLoadedFor = state.user.id;
      }

      state.scanner.technicalLoadedKey = [
        state.user && state.user.id || "",
        scope,
        state.scanner.signal,
        state.scanner.exchange,
        String(state.scanner.query || "").trim(),
        state.scanner.sort,
        state.scanner.page
      ].join("|");
    } catch (error) {
      state.scanner.error = "Nguồn dữ liệu danh sách tạm thời chưa phản hồi. Vui lòng thử lại.";
      console.error("CCC scanner load failed", error);
    } finally {
      state.scanner.loading = false;
      if (state.route === "scanner") render();
    }
  }


  async function ensureResearch(force) {
    if (state.research.loading) return;
    if (!force && state.research.loaded) return;

    state.research.loading = true;
    state.research.error = "";
    if (state.route === "research") render();

    try {
      var result = await window.CCCData.loadResearch(!!force);
      var financial = Array.isArray(result && result.financial) ? result.financial : [];
      var metadata = Array.isArray(result && result.metadata) ? result.metadata : [];
      var metaBySymbol = Object.create(null);
      var groupRows = Object.create(null);
      var scoreBySymbol = Object.create(null);

      metadata.forEach(function (row) {
        var symbol = String(row && row.symbol || "").toUpperCase();
        if (symbol) metaBySymbol[symbol] = row;
      });

      financial.forEach(function (row) {
        var group = String(row && row.website_group || "").trim();
        if (!group) return;
        if (!groupRows[group]) groupRows[group] = [];
        groupRows[group].push(row);
      });

      financial.forEach(function (row) {
        var symbol = String(row && row.symbol || "").toUpperCase();
        if (!symbol) return;
        scoreBySymbol[symbol] = detailFinancialScore(row, groupRows[String(row.website_group || "")] || []);
      });

      state.research.financialRows = financial;
      state.research.metadataBySymbol = metaBySymbol;
      state.research.groupRows = groupRows;
      state.research.scoreBySymbol = scoreBySymbol;
      state.research.loaded = true;

      var groups = researchGroupList();
      if (!state.research.industryGroup || !groupRows[state.research.industryGroup]) {
        state.research.industryGroup = groups.length ? groups[0][0] : "";
      }
    } catch (error) {
      state.research.error = "Nguồn dữ liệu Nghiên cứu tạm thời chưa phản hồi. Vui lòng thử lại.";
      console.error("CCC research load failed", error);
    } finally {
      state.research.loading = false;
      state.nextRefreshAt = Date.now() + REFRESH_SECONDS * 1000;
      if (state.route === "research") render();
    }
  }

  async function loadAccessContext(force) {
    if (!state.user) return null;

    if (!force && state.access.loadedFor === state.user.id && state.access.context) {
      scheduleVipExpiryCheck();
      return state.access.context;
    }

    if (state.access.loading) return state.access.context;

    state.access.loading = true;
    state.access.error = "";

    try {
      var raw = await window.CCCData.getAccessContext();
      var normalized = normalizeAccessContext(raw);
      state.access.raw = raw;
      state.access.context = normalized;
      state.access.loadedFor = state.user.id;
      state.access.lastCheckedAt = Date.now();
      scheduleVipExpiryCheck();
      return normalized;
    } catch (error) {
      state.access.error = String(
        error && error.message ? error.message : error || "Không đọc được quyền truy cập."
      );
      console.error("CCC access context load failed", error);
      return null;
    } finally {
      state.access.loading = false;
    }
  }

  function resetAccessContext() {
    clearVipExpiryTimer();
    state.access.loading = false;
    state.access.loadedFor = "";
    state.access.error = "";
    state.access.raw = null;
    state.access.context = null;
    state.access.lastCheckedAt = 0;
    state.access.refreshingEntitlement = false;
    state.access.notice = "";
  }

  function reconcileOverviewAccessSnapshot(data) {
    if (!data || !state.access.context) return false;

    var overviewFull = data.effective_full_market_access === true;
    var overviewVip = data.vip_day_active === true;
    var overviewVipEnd = data.vip_day_ends_at || null;
    var ctx = state.access.context;

    var beforeVip = !!ctx.vipDayActive;
    var beforeFull = !!ctx.effectiveFullMarketAccess;
    var changed =
      overviewFull !== beforeFull ||
      overviewVip !== beforeVip ||
      String(overviewVipEnd || "") !== String(ctx.vipDayEndsAt || "");

    if (!changed) {
      scheduleVipExpiryCheck();
      return false;
    }

    ctx.vipDayActive = overviewVip;
    ctx.vipDayEndsAt = overviewVipEnd;
    ctx.effectiveFullMarketAccess = overviewFull;
    ctx.effectiveTechnicalScope = overviewFull ? "MARKET" : "PERSONAL_WATCHLIST";
    state.access.lastCheckedAt = Date.now();

    if (state.access.raw) {
      state.access.raw.vip_day_active = overviewVip;
      state.access.raw.vip_day_ends_at = overviewVipEnd;
      state.access.raw.effective_full_market_access = overviewFull;
    }

    state.scanner.technicalLoadedKey = "";
    state.scanner.technicalRows = [];
    state.scanner.technicalMeta = null;
    state.scanner.page = 1;

    if (beforeVip && !overviewVip) {
      setAccessNotice("VIP DAY đã hết hạn. Bạn đã trở về quyền của gói " + planProductName(basePlanCode()) + ".");
    }

    scheduleVipExpiryCheck();
    return true;
  }

  async function ensureAccount(force) {
    if (!state.authReady || !state.user || state.account.loading) return;
    if (!force && state.account.loadedFor === state.user.id && state.account.watchlist) return;

    state.account.loading = true;
    state.account.watchlistError = "";
    if (state.route === "account") render();

    try {
      var w = await window.CCCData.getWatchlistState();
      state.account.watchlist = w || {};
      state.account.originalSymbols = uniqueSorted(w && w.symbols || []);
      state.account.selectedSymbols = state.account.originalSymbols.slice();
      state.account.loadedFor = state.user.id;
      state.account.query = "";
    } catch (error) {
      state.account.watchlist = null;
      state.account.watchlistError = watchlistFriendlyError(error);
      console.error("CCC account watchlist load failed", error);
    } finally {
      state.account.loading = false;
      if (state.route === "account") render();
    }
  }

  function resetAccountState() {
    state.account.loading = false;
    state.account.loadedFor = "";
    state.account.watchlist = null;
    state.account.originalSymbols = [];
    state.account.selectedSymbols = [];
    state.account.profileSaving = false;
    state.account.profileError = "";
    state.account.profileNotice = "";
    state.account.watchlistSaving = false;
    state.account.watchlistError = "";
    state.account.watchlistNotice = "";
    state.account.query = "";
  }

  async function saveAccountProfile(event) {
    event.preventDefault();
    if (!state.user || state.account.profileSaving) return;

    var fd = new FormData(event.currentTarget);
    var displayName = String(fd.get("display_name") || "").trim();
    var phone = String(fd.get("phone") || "").trim();
    var address = String(fd.get("address") || "").trim();
    var phoneDigits = phone.replace(/[^0-9]/g, "");

    state.account.profileError = "";
    state.account.profileNotice = "";

    if (displayName.length < 2 || displayName.length > 100) {
      state.account.profileError = "Họ và tên cần từ 2 đến 100 ký tự.";
      render();
      return;
    }
    if (phoneDigits.length < 8 || phoneDigits.length > 15) {
      state.account.profileError = "Số điện thoại chưa hợp lệ.";
      render();
      return;
    }
    if (address.length > 500) {
      state.account.profileError = "Địa chỉ tối đa 500 ký tự.";
      render();
      return;
    }

    state.account.profileSaving = true;
    render();

    try {
      await window.CCCData.saveProfile(displayName, phone, address);
      await loadMembership();
      state.account.profileNotice = "Đã lưu hồ sơ thành công.";
    } catch (error) {
      state.account.profileError = "Không lưu được hồ sơ. Vui lòng thử lại.";
      console.error("CCC profile save failed", error);
    } finally {
      state.account.profileSaving = false;
      render();
    }
  }

  async function saveAccountWatchlist() {
    if (!state.user || state.account.watchlistSaving || !state.account.watchlist) return;
    state.account.watchlistSaving = true;
    state.account.watchlistError = "";
    state.account.watchlistNotice = "";
    render();

    try {
      var result = await window.CCCData.replaceWatchlist(uniqueSorted(state.account.selectedSymbols));
      state.account.watchlist = result || state.account.watchlist;
      state.account.originalSymbols = uniqueSorted((result && result.symbols) || state.account.selectedSymbols);
      state.account.selectedSymbols = state.account.originalSymbols.slice();
      state.scanner.watchlistLoadedFor = "";
      state.scanner.personalWatchlistLoadedFor = "";
      state.scanner.technicalLoadedKey = "";
      state.scanner.technicalRows = [];
      state.scanner.technicalMeta = null;
      await Promise.all([loadMembership(), loadAccessContext(true)]);
      state.scanner.watchlistLoadedFor = "";
      state.scanner.personalWatchlistLoadedFor = "";
      state.scanner.personalWatchlistSymbols = [];
      state.scanner.watchlistRows = [];
      state.account.watchlistNotice = "Đã lưu DS mã theo dõi thành công.";
    } catch (error) {
      state.account.watchlistError = watchlistFriendlyError(error);
      console.error("CCC watchlist save failed", error);
    } finally {
      state.account.watchlistSaving = false;
      render();
    }
  }

  async function signInAccountEmail(event) {
    event.preventDefault();
    if (state.account.authBusy) return;

    var fd = new FormData(event.currentTarget);
    var email = String(fd.get("email") || "").trim();
    var password = String(fd.get("password") || "");

    if (!email || !password) {
      state.account.authError = "Vui lòng nhập đầy đủ email và mật khẩu.";
      render();
      return;
    }

    state.account.authBusy = true;
    state.account.authError = "";
    render();

    try {
      await window.CCCData.signInWithPassword(email, password);
      state.account.authOpen = false;
    } catch (error) {
      state.account.authError = friendlyAuthError(error);
    } finally {
      state.account.authBusy = false;
      render();
    }
  }

  async function signInAccountGoogle() {
    if (state.account.authBusy) return;
    state.account.authBusy = true;
    state.account.authError = "";
    render();
    try {
      var intent = storedPurchaseIntent();
      var redirectPath = intent === "VIP_DAY" ? "/tai-khoan?intent=vip_day" : window.location.pathname;
      await window.CCCData.signInWithGoogle(window.location.origin + redirectPath);
    } catch (error) {
      state.account.authBusy = false;
      state.account.authError = friendlyAuthError(error);
      render();
    }
  }

  async function changeAccountPassword(event) {
    event.preventDefault();
    if (state.account.passwordBusy) return;

    var fd = new FormData(event.currentTarget);
    var currentPassword = String(fd.get("current_password") || "");
    var newPassword = String(fd.get("new_password") || "");
    var confirmPassword = String(fd.get("confirm_password") || "");

    if (!currentPassword || !newPassword || !confirmPassword) {
      state.account.passwordError = "Vui lòng nhập đầy đủ ba ô mật khẩu.";
      render();
      return;
    }
    if (newPassword.length < 8) {
      state.account.passwordError = "Mật khẩu mới cần tối thiểu 8 ký tự.";
      render();
      return;
    }
    if (newPassword !== confirmPassword) {
      state.account.passwordError = "Hai lần nhập mật khẩu mới chưa khớp.";
      render();
      return;
    }
    if (newPassword === currentPassword) {
      state.account.passwordError = "Mật khẩu mới cần khác mật khẩu hiện tại.";
      render();
      return;
    }

    state.account.passwordBusy = true;
    state.account.passwordError = "";
    render();

    try {
      await window.CCCData.changePassword(currentPassword, newPassword);
      state.account.passwordOpen = false;
      state.account.passwordNotice = "Đổi mật khẩu thành công.";
    } catch (error) {
      var message = String(error && error.message ? error.message : "");
      if (message.toLowerCase().indexOf("invalid login credentials") >= 0) {
        state.account.passwordError = "Mật khẩu hiện tại chưa đúng.";
      } else if (message.toLowerCase().indexOf("password") >= 0) {
        state.account.passwordError = message;
      } else {
        state.account.passwordError = "Chưa đổi được mật khẩu. Vui lòng thử lại.";
      }
      console.error("CCC password change failed", error);
    } finally {
      state.account.passwordBusy = false;
      render();
    }
  }

  async function signOutAccount() {
    try {
      await window.CCCData.signOut();
    } catch (error) {
      console.error("CCC sign out failed", error);
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
      await Promise.all([loadMembership(), loadAccessContext(true)]);
      state.authReady = true;

      var result = window.CCCData.onAuthStateChange(async function (_event, session) {
        state.session = session || null;
        state.user = session && session.user || null;
        state.overview.data = null;
        state.overview.loadedFor = "";
        state.overview.group = "all";
        state.overview.page = 1;
        state.scanner.watchlistRows = [];
        state.scanner.watchlistLoadedFor = "";
        state.scanner.personalWatchlistLoadedFor = "";
        state.scanner.personalWatchlistSymbols = [];
        state.scanner.technicalRows = [];
        state.scanner.technicalMeta = null;
        state.scanner.technicalLoadedKey = "";
        if (state.detail.open) {
          state.detail.technical = null;
          state.detail.technicalAllowed = false;
          state.detail.technicalReason = "AUTH_REFRESH";
        }
        resetAccountState();
        resetAccessContext();
        await Promise.all([loadMembership(), loadAccessContext(true)]);
        state.account.authOpen = false;
        if (consumePurchaseIntentAfterAuth()) return;
        render();
        if (state.route === "overview") ensureOverview(true);
        if (state.route === "scanner") ensureScanner(true);
        if (state.route === "account" && state.user) ensureAccount(true);
        if (state.detail.open) ensureDetail(true);
      });
      authSubscription = result && result.data && result.data.subscription || result && result.subscription || null;
    } catch (error) {
      state.authReady = true;
      state.user = null;
      console.error("CCC auth init failed", error);
    } finally {
      render();
      if (state.route === "overview") ensureOverview(false);
      if (state.route === "scanner") ensureScanner(false);
      if (state.route === "research") ensureResearch(false);
      if (state.route === "account" && state.user) ensureAccount(false);
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

  function ensureSearchUniverse() {
    if (state.searchUniverse.loaded) return Promise.resolve(state.searchUniverse.rows);
    if (state.searchUniverse.loading) {
      return new Promise(function (resolve) {
        var wait = setInterval(function () {
          if (!state.searchUniverse.loading) {
            clearInterval(wait);
            resolve(state.searchUniverse.rows);
          }
        }, 30);
      });
    }

    state.searchUniverse.loading = true;
    state.searchUniverse.error = "";
    return window.CCCData.loadSearchUniverse(false).then(function (rows) {
      state.searchUniverse.rows = Array.isArray(rows) ? rows : [];
      state.searchUniverse.loaded = true;
      state.searchUniverse.loading = false;
      return state.searchUniverse.rows;
    }).catch(function () {
      state.searchUniverse.rows = [];
      state.searchUniverse.error = "Không tải được dữ liệu tìm kiếm.";
      state.searchUniverse.loading = false;
      return [];
    });
  }

  function hideSearchSuggestions(container) {
    if (!container) return;
    container.hidden = true;
    container.innerHTML = "";
  }

  function paintSearchSuggestions(input, container, context) {
    if (!input || !container) return;
    var query = String(input.value || "").trim();
    if (!query) {
      hideSearchSuggestions(container);
      return;
    }

    if (context === "scanner") {
      var localRows = rankStockSearch(scannerSearchSourceRows(), query, 6);
      container.innerHTML = searchSuggestionItemsHtml(localRows, "scanner");
      container.hidden = false;
      return;
    }

    if (!state.searchUniverse.loaded) {
      container.innerHTML = '<div class="stock-suggestion-empty">Đang tải dữ liệu tìm kiếm…</div>';
      container.hidden = false;
      ensureSearchUniverse().then(function () {
        if (!document.body.contains(input) || !document.body.contains(container)) return;
        if (!String(input.value || "").trim()) return hideSearchSuggestions(container);
        var rows = rankStockSearch(state.searchUniverse.rows, input.value, 6);
        container.innerHTML = searchSuggestionItemsHtml(rows, "global");
        container.hidden = false;
      });
      return;
    }

    var rows = rankStockSearch(state.searchUniverse.rows, query, 6);
    container.innerHTML = searchSuggestionItemsHtml(rows, "global");
    container.hidden = false;
  }

  function selectSearchSuggestion(context, symbol) {
    if (!symbol) return;
    if (context === "scanner") {
      state.scanner.query = symbol;
      state.scanner.page = 1;
      state.scanner.mobileShown = MOBILE_CHUNK;
      render();
      return;
    }

    /* Current clean writer has no Stock Detail route yet.
       Keep the existing stable global-search destination; this function is
       intentionally isolated so Phase 4/5 can point it to Stock Detail later. */
    location.assign("/danh-sach?q=" + encodeURIComponent(symbol));
  }

  function bindSearchAutocomplete(input, container, context) {
    if (!input || !container) return;

    input.addEventListener("input", function () {
      paintSearchSuggestions(input, container, context);
    });

    input.addEventListener("focus", function () {
      if (String(input.value || "").trim()) paintSearchSuggestions(input, container, context);
    });

    input.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        hideSearchSuggestions(container);
      }
    });

    container.addEventListener("mousedown", function (event) {
      event.preventDefault();
    });

    container.addEventListener("click", function (event) {
      var button = event.target && event.target.closest ? event.target.closest("[data-search-symbol]") : null;
      if (!button) return;
      var symbol = button.getAttribute("data-search-symbol") || "";
      var selectedContext = button.getAttribute("data-search-context") || context;
      selectSearchSuggestion(selectedContext, symbol);
    });

    input.addEventListener("blur", function () {
      setTimeout(function () {
        hideSearchSuggestions(container);
      }, 120);
    });
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

    bindSearchAutocomplete(
      document.getElementById("global-stock-search"),
      document.getElementById("global-search-suggestions"),
      "global"
    );
    bindSearchAutocomplete(
      document.getElementById("mobile-global-stock-search"),
      document.getElementById("mobile-global-search-suggestions"),
      "global"
    );

    var refresh = document.getElementById("refresh-btn");
    if (refresh) refresh.addEventListener("click", function () {
      state.nextRefreshAt = Date.now() + REFRESH_SECONDS * 1000;
      if (state.detail.open) ensureDetail(true);
      else {
        if (state.route === "overview") ensureOverview(true);
        if (state.route === "scanner") ensureScanner(true);
        if (state.route === "research") ensureResearch(true);
      }
      ensureMarketPulse(true);
    });

    var account = document.getElementById("account-open");
    if (account) account.addEventListener("click", function () {
      if (state.user) location.assign(ACCOUNT_PATH);
      else {
        state.account.authOpen = true;
        state.account.authError = "";
        render();
      }
    });

    document.querySelectorAll("[data-upsell-vip]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (!state.user) {
          setPurchaseIntent("VIP_DAY");
          state.account.authOpen = true;
          state.account.authError = "";
          render();
          return;
        }
        location.assign("/tai-khoan?intent=vip_day");
      });
    });

    document.querySelectorAll("[data-upsell-upgrade]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (!state.user) {
          state.account.guestPlansOpen = true;
          render();
          var cta = document.querySelector(".guest-onboarding-cta");
          if (cta) cta.scrollIntoView({ block: "nearest" });
          return;
        }
        location.assign("/tai-khoan?intent=upgrade");
      });
    });

    document.querySelectorAll("[data-guest-auth]").forEach(function (button) {
      button.addEventListener("click", function () {
        state.account.authOpen = true;
        state.account.authError = "";
        render();
      });
    });

    document.querySelectorAll("[data-guest-plans]").forEach(function (button) {
      button.addEventListener("click", function () {
        state.account.guestPlansOpen = !state.account.guestPlansOpen;
        render();
      });
    });

    var accountLoginOpen = document.getElementById("account-login-open");
    if (accountLoginOpen) accountLoginOpen.addEventListener("click", function () {
      state.account.authOpen = true;
      state.account.authError = "";
      render();
    });

    var authClose = document.getElementById("auth-dialog-close");
    if (authClose) authClose.addEventListener("click", function () {
      state.account.authOpen = false;
      state.account.authError = "";
      setPurchaseIntent("");
      render();
    });

    var authOverlay = document.querySelector(".phase4-auth-overlay");
    if (authOverlay) authOverlay.addEventListener("click", function (event) {
      if (event.target === authOverlay) {
        state.account.authOpen = false;
        state.account.authError = "";
        render();
      }
    });

    var authEmail = document.getElementById("auth-email-form");
    if (authEmail) authEmail.addEventListener("submit", signInAccountEmail);

    var authGoogle = document.getElementById("auth-google");
    if (authGoogle) authGoogle.addEventListener("click", signInAccountGoogle);

    var profileForm = document.getElementById("account-profile-form");
    if (profileForm) profileForm.addEventListener("submit", saveAccountProfile);

    var passwordOpen = document.getElementById("account-password-open");
    if (passwordOpen) passwordOpen.addEventListener("click", function () {
      state.account.passwordOpen = true;
      state.account.passwordError = "";
      state.account.passwordNotice = "";
      render();
    });

    var passwordClose = document.getElementById("account-password-close");
    if (passwordClose) passwordClose.addEventListener("click", function () {
      state.account.passwordOpen = false;
      state.account.passwordError = "";
      render();
    });

    var passwordOverlay = document.querySelector(".phase4-password-overlay");
    if (passwordOverlay) passwordOverlay.addEventListener("click", function (event) {
      if (event.target === passwordOverlay) {
        state.account.passwordOpen = false;
        state.account.passwordError = "";
        render();
      }
    });

    var passwordForm = document.getElementById("account-password-form");
    if (passwordForm) passwordForm.addEventListener("submit", changeAccountPassword);

    var vipInfo = document.getElementById("vip-day-info");
    if (vipInfo) vipInfo.addEventListener("click", function () {
      state.account.vipInfoOpen = !state.account.vipInfoOpen;
      render();
    });

    var accountLogout = document.getElementById("account-logout");
    if (accountLogout) accountLogout.addEventListener("click", signOutAccount);

    var wlInput = document.getElementById("account-wl-search");
    var wlSuggestions = document.getElementById("account-wl-suggestions");

    function paintAccountWatchlistSuggestions() {
      if (!wlInput || !wlSuggestions) return;
      var query = String(wlInput.value || "").trim();
      state.account.query = query;
      if (!query) {
        wlSuggestions.hidden = true;
        wlSuggestions.innerHTML = "";
        return;
      }

      if (!state.searchUniverse.loaded) {
        wlSuggestions.hidden = false;
        wlSuggestions.innerHTML = '<div class="ccc-wl-search-status">Đang tải dữ liệu tìm kiếm…</div>';
        ensureSearchUniverse().then(function () {
          if (document.body.contains(wlInput)) paintAccountWatchlistSuggestions();
        });
        return;
      }

      var selectedMap = Object.create(null);
      state.account.selectedSymbols.forEach(function (symbol) { selectedMap[symbol] = true; });
      var rows = rankStockSearch(state.searchUniverse.rows, query, 7).filter(function (row) {
        return !selectedMap[String(row.symbol || "").toUpperCase()];
      });

      if (!rows.length) {
        wlSuggestions.hidden = false;
        wlSuggestions.innerHTML = '<div class="ccc-wl-search-status">Không có mã mới phù hợp.</div>';
        return;
      }

      wlSuggestions.hidden = false;
      wlSuggestions.innerHTML = rows.map(function (row) {
        var symbol = String(row.symbol || "").toUpperCase();
        return '<button type="button" class="ccc-wl-result" data-account-add="' + esc(symbol) + '">' +
          companyLogo(symbol) +
          '<span class="ccc-wl-result-copy"><b>' + esc(symbol) + '</b><small>' + esc(stockSearchName(row)) + '</small><em>' + esc(row.exchange || "") + '</em></span><strong>+ Thêm</strong>' +
        '</button>';
      }).join("");
    }

    if (wlInput) wlInput.addEventListener("input", paintAccountWatchlistSuggestions);

    if (wlSuggestions) wlSuggestions.addEventListener("click", function (event) {
      var button = event.target && event.target.closest ? event.target.closest("[data-account-add]") : null;
      if (!button) return;
      var symbol = String(button.getAttribute("data-account-add") || "").toUpperCase();
      var limit = accountWatchlistLimit();
      if (limit !== null && state.account.selectedSymbols.length >= limit) {
        state.account.watchlistError = "DS mã theo dõi đã đạt giới hạn của gói hiện tại.";
        render();
        return;
      }
      if (state.account.selectedSymbols.indexOf(symbol) < 0) state.account.selectedSymbols.push(symbol);
      state.account.selectedSymbols = uniqueSorted(state.account.selectedSymbols);
      state.account.query = "";
      state.account.watchlistError = "";
      state.account.watchlistNotice = "";
      render();
    });

    document.querySelectorAll("[data-account-remove]").forEach(function (button) {
      button.addEventListener("click", function () {
        var symbol = String(button.getAttribute("data-account-remove") || "").toUpperCase();
        state.account.selectedSymbols = state.account.selectedSymbols.filter(function (item) { return item !== symbol; });
        state.account.watchlistError = "";
        state.account.watchlistNotice = "";
        render();
      });
    });

    var wlUndo = document.getElementById("account-wl-undo");
    if (wlUndo) wlUndo.addEventListener("click", function () {
      state.account.selectedSymbols = state.account.originalSymbols.slice();
      state.account.query = "";
      state.account.watchlistError = "";
      state.account.watchlistNotice = "";
      render();
    });

    var wlSave = document.getElementById("account-wl-save");
    if (wlSave) wlSave.addEventListener("click", saveAccountWatchlist);

    document.querySelectorAll("[data-overview-group]").forEach(function (button) {
      button.addEventListener("click", function () {
        var key = button.getAttribute("data-overview-group") || "all";
        state.overview.group = groupConfig(key) ? key : "all";
        state.overview.page = 1;
        state.overview.mobileShown = MOBILE_CHUNK;
        if (state.user) ensureOverview(true);
        else render();
      });
    });

    document.querySelectorAll("[data-overview-all]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (state.overview.group === "all") return;
        state.overview.group = "all";
        state.overview.page = 1;
        state.overview.mobileShown = MOBILE_CHUNK;
        if (state.user) ensureOverview(true);
        else render();
      });
    });


    document.querySelectorAll("[data-overview-retry]").forEach(function (button) {
      button.addEventListener("click", function () {
        ensureOverview(true);
      });
    });

    function scannerRefreshAfterControl() {
      state.scanner.page = 1;
      state.scanner.mobileShown = MOBILE_CHUNK;
      state.scanner.mobileDropdown = "";
      if (scannerTechnicalMode()) ensureScanner(true);
      else render();
    }

    document.querySelectorAll("[data-scanner-mode]").forEach(function (button) {
      button.addEventListener("click", function () {
        state.scanner.mode = button.getAttribute("data-scanner-mode") === "watchlist" ? "watchlist" : "market";
        state.scanner.signal = "";
        state.scanner.sort = state.scanner.mode === "watchlist" || (state.scanner.mode === "market" && effectiveFullMarketAccess())
          ? "signal_desc"
          : "symbol";
        state.scanner.page = 1;
        state.scanner.mobileShown = MOBILE_CHUNK;
        state.scanner.mobileDropdown = "";
        state.scanner.technicalLoadedKey = "";
        render();
        ensureScanner(true);
      });
    });

    document.querySelectorAll("[data-scanner-filter]").forEach(function (select) {
      var key = select.getAttribute("data-scanner-filter");
      if (key === "exchange") select.value = state.scanner.exchange;
      if (key === "sort") select.value = state.scanner.sort;
      select.addEventListener("change", function () {
        state.scanner[key] = select.value;
        scannerRefreshAfterControl();
      });
    });

    document.querySelectorAll("[data-mobile-dropdown-toggle]").forEach(function (button) {
      button.addEventListener("click", function () {
        var key = button.getAttribute("data-mobile-dropdown-toggle") || "";
        state.scanner.mobileDropdown = state.scanner.mobileDropdown === key ? "" : key;
        render();
      });
    });

    document.querySelectorAll("[data-mobile-dropdown-value]").forEach(function (button) {
      button.addEventListener("click", function () {
        var key = button.getAttribute("data-mobile-dropdown-key") || "";
        var value = button.getAttribute("data-mobile-dropdown-value") || "";
        if (key !== "exchange" && key !== "sort") return;
        state.scanner[key] = value;
        scannerRefreshAfterControl();
      });
    });

    document.querySelectorAll("[data-scanner-signal]").forEach(function (button) {
      button.addEventListener("click", function () {
        state.scanner.signal = button.getAttribute("data-scanner-signal") || "";
        scannerRefreshAfterControl();
      });
    });

    var scannerInput = document.getElementById("stock-search");
    var scannerSearch = document.getElementById("scanner-search-btn");
    var scannerClear = document.getElementById("scanner-clear-btn");

    bindSearchAutocomplete(
      scannerInput,
      document.getElementById("scanner-search-suggestions"),
      "scanner"
    );

    function applyScannerSearch() {
      state.scanner.query = String(scannerInput && scannerInput.value || "").trim();
      scannerRefreshAfterControl();
    }

    if (scannerSearch) scannerSearch.addEventListener("click", applyScannerSearch);
    if (scannerInput) scannerInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        applyScannerSearch();
      }
    });

    if (scannerClear) scannerClear.addEventListener("click", function () {
      state.scanner.query = "";
      scannerRefreshAfterControl();
    });

    document.querySelectorAll("[data-scanner-reset]").forEach(function (button) {
      button.addEventListener("click", function () {
        state.scanner.exchange = "all";
        state.scanner.signal = "";
        state.scanner.sort = scannerTechnicalMode() ? "signal_desc" : "symbol";
        scannerRefreshAfterControl();
      });
    });

    document.querySelectorAll("[data-scanner-page]").forEach(function (button) {
      button.addEventListener("click", function () {
        var delta = Number(button.getAttribute("data-scanner-page") || 0);
        if (scannerTechnicalMode()) {
          var meta = scannerTechnicalMeta();
          var pages = Number(meta.total_pages || 1);
          var next = Math.max(1, Math.min(pages, state.scanner.page + delta));
          if (next === state.scanner.page) return;
          state.scanner.page = next;
          ensureScanner(true);
        } else {
          state.scanner.page = Math.max(1, state.scanner.page + delta);
          render();
        }
      });
    });

    document.querySelectorAll("[data-scanner-more]").forEach(function (button) {
      button.addEventListener("click", function () {
        state.scanner.mobileShown += MOBILE_CHUNK;
        render();
      });
    });

    document.querySelectorAll("[data-scanner-retry]").forEach(function (button) {
      button.addEventListener("click", function () {
        ensureScanner(true);
      });
    });



    function setResearchIndustry(value) {
      state.research.industryGroup = value || "";
      state.research.industryPage = 1;
      var url = new URL(location.href);
      if (state.research.industryGroup) url.searchParams.set("group", state.research.industryGroup);
      else url.searchParams.delete("group");
      history.replaceState(null, "", url.pathname + url.search);
      render();
    }

    document.querySelectorAll("[data-research-industry]").forEach(function (button) {
      button.addEventListener("click", function () {
        setResearchIndustry(button.getAttribute("data-research-industry") || "");
      });
    });

    var researchIndustrySelect = document.querySelector("[data-research-industry-select]");
    if (researchIndustrySelect) {
      researchIndustrySelect.addEventListener("change", function () {
        setResearchIndustry(researchIndustrySelect.value || "");
      });
    }

    var researchFundIndustry = document.querySelector("[data-research-fund-industry]");
    if (researchFundIndustry) {
      researchFundIndustry.addEventListener("change", function () {
        state.research.fundamentalIndustry = researchFundIndustry.value || "all";
        state.research.fundamentalPage = 1;
        render();
      });
    }

    var researchReset = document.querySelector("[data-research-reset]");
    if (researchReset) {
      researchReset.addEventListener("click", function () {
        state.research.fundamentalIndustry = "all";
        state.research.fundamentalMinScore = 0;
        state.research.fundamentalProfitGrowth = "all";
        state.research.fundamentalRoe = "all";
        state.research.fundamentalPage = 1;
        render();
      });
    }

    document.querySelectorAll("[data-research-filter]").forEach(function (button) {
      button.addEventListener("click", function () {
        var key = button.getAttribute("data-research-filter") || "";
        var value = button.getAttribute("data-value") || "";
        if (key === "score") state.research.fundamentalMinScore = Number(value || 0);
        if (key === "growth") state.research.fundamentalProfitGrowth = value || "all";
        if (key === "roe") state.research.fundamentalRoe = value || "all";
        state.research.fundamentalPage = 1;
        render();
      });
    });

    document.querySelectorAll("[data-research-page]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (button.disabled) return;
        var mode = button.getAttribute("data-research-page") || "";
        var delta = Number(button.getAttribute("data-delta") || 0);
        if (mode === "industry") state.research.industryPage = Math.max(1, state.research.industryPage + delta);
        if (mode === "fundamental") state.research.fundamentalPage = Math.max(1, state.research.fundamentalPage + delta);
        render();
        requestAnimationFrame(function () {
          var results = document.querySelector("[data-research-results]");
          if (results) results.scrollIntoView({ block: "start" });
        });
      });
    });

    document.querySelectorAll("[data-research-retry]").forEach(function (button) {
      button.addEventListener("click", function () { ensureResearch(true); });
    });

    document.querySelectorAll("[data-symbol]").forEach(function (element) {
      var symbol = String(element.getAttribute("data-symbol") || "").toUpperCase();
      if (!symbol) return;
      element.setAttribute("role", "button");
      if (!element.hasAttribute("tabindex")) element.setAttribute("tabindex", "0");
      function activateDetail(event) {
        if (event && event.type === "keydown" && event.key !== "Enter" && event.key !== " ") return;
        if (event && event.type === "keydown") event.preventDefault();
        openStockDetail(symbol);
      }
      element.addEventListener("click", activateDetail);
      element.addEventListener("keydown", activateDetail);
    });

    document.querySelectorAll("[data-detail-tab]").forEach(function (button) {
      button.addEventListener("click", function () {
        state.detail.tab = button.getAttribute("data-detail-tab") || "overview";
        render();
        var active = document.querySelector('[data-detail-tab="' + state.detail.tab + '"]');
        if (active) active.focus();
      });
    });

    var detailBack = document.getElementById("detail-back");
    if (detailBack) detailBack.addEventListener("click", closeStockDetail);

    document.querySelectorAll("[data-detail-retry]").forEach(function (button) {
      button.addEventListener("click", function () { ensureDetail(true); });
    });

    document.querySelectorAll("[data-detail-add-watchlist]").forEach(function (button) {
      button.addEventListener("click", addDetailSymbolToWatchlist);
    });

  }

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (state.account.passwordOpen) {
      state.account.passwordOpen = false;
      state.account.passwordError = "";
      render();
      return;
    }
    if (state.account.authOpen) {
      state.account.authOpen = false;
      state.account.authError = "";
      render();
      return;
    }
    if (state.detail.open) {
      closeStockDetail();
    }
  });

  window.CCCAccess = {
    snapshot: function () {
      var ctx = state.access.context;
      return ctx ? JSON.parse(JSON.stringify(ctx)) : null;
    },
    refresh: function () {
      return loadAccessContext(true).then(function (ctx) {
        return ctx ? JSON.parse(JSON.stringify(ctx)) : null;
      });
    },
    basePlanCode: basePlanCode,
    vipDayActive: vipDayActive,
    vipDayEndsAt: vipDayEndsAt,
    effectiveFullMarketAccess: effectiveFullMarketAccess,
    effectiveTechnicalScope: effectiveTechnicalScope,
    refreshEntitlement: function () { return refreshAccessEntitlement("manual_debug", true); }
  };

  window.CCCScanner = {
    snapshot: function () {
      var meta = scannerTechnicalMeta();
      return {
        mode: state.scanner.mode,
        technicalMode: scannerTechnicalMode(),
        serverPagedTechnical: scannerTechnicalMode(),
        personalWatchlistCount: scannerPersonalWatchlistCount(),
        personalWatchlistSymbols: state.scanner.personalWatchlistSymbols.slice(),
        watchlistRowsRenderedSourceCount: state.scanner.mode === "watchlist" ? state.scanner.technicalRows.length : state.scanner.watchlistRows.length,
        technicalRowsReceived: state.scanner.technicalRowsReceived,
        technicalScopeAtLoad: state.scanner.technicalScopeAtLoad,
        effectiveTechnicalScope: effectiveTechnicalScope(),
        marketRowsLoaded: state.scanner.marketRows.length,
        page: state.scanner.page,
        pageSize: scannerTechnicalMode() ? Number(meta.page_size || 50) : scannerPageSize(),
        totalMatching: scannerTechnicalMode() ? Number(meta.total_matching || 0) : null,
        totalPages: scannerTechnicalMode() ? Number(meta.total_pages || 1) : null,
        scopeTotal: scannerTechnicalMode() ? Number(meta.scope_total || 0) : null,
        vipDayActive: vipDayActive()
      };
    }
  };


  window.addEventListener("focus", function () {
    if (state.user) refreshAccessEntitlement("window_focus", false);
  });

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && state.user) {
      refreshAccessEntitlement("tab_visible", false);
    }
  });

  window.addEventListener("popstate", function () {
    if (state.detail.open) detailReset(false);
    state.route = routeFromLocation();
    render();
    if (state.route === "overview") ensureOverview(false);
    if (state.route === "scanner") ensureScanner(false);
    if (state.route === "research") ensureResearch(false);
    if (state.route === "account" && state.user) ensureAccount(false);
  });

  window.addEventListener("resize", function () {
    if (state.detail.open || state.route === "overview" || state.route === "scanner") render();
  });

  window.addEventListener("beforeunload", function () {
    if (authSubscription && typeof authSubscription.unsubscribe === "function") authSubscription.unsubscribe();
    if (countdownTimer) clearInterval(countdownTimer);
    clearVipExpiryTimer();
    if (accessNoticeTimer) clearTimeout(accessNoticeTimer);
  });

  render();
  startCountdown();
  initAuth();
})();
