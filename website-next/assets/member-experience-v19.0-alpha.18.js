(function () {
  "use strict";

  var SCANNER_PATH = "/danh-sach";
  var ACCOUNT_PATH = "/tai-khoan";
  var LOGO_BASE_URL = "/assets/logos/";
  var LOGO_VERSION = "1741";
  var DESKTOP_PAGE_SIZE = 50;
  var MOBILE_CHUNK_SIZE = 20;

  var GROUPS = {
    "4of4": { title: "Đạt 4/4", marketKey: "four_of_four", matcher: function (r) { return Number(r.signal_count || 0) === 4; } },
    "3plus": { title: "Từ 3 tín hiệu", marketKey: "three_plus", matcher: function (r) { return Number(r.signal_count || 0) >= 3; } },
    "2plus": { title: "Từ 2 tín hiệu", marketKey: "two_plus", matcher: function (r) { return Number(r.signal_count || 0) >= 2; } },
    "rvol30": { title: "RVOL30 nổi bật", marketKey: "rvol30", matcher: function (r) { return r.signal_rvol30_200pct === true; } }
  };

  var state = {
    client: null,
    userId: "",
    overviewData: null,
    overviewGroup: "",
    overviewPage: 1,
    overviewMobileVisible: MOBILE_CHUNK_SIZE,
    overviewLoading: false,
    scannerData: null,
    marketRows: null,
    metadataBySymbol: Object.create(null),
    scannerTab: "",
    scannerSearch: "",
    scannerExchange: "all",
    scannerSignal: "all",
    scannerQuick: "all",
    scannerSort: "signal",
    scannerPage: 1,
    scannerMobileVisible: MOBILE_CHUNK_SIZE,
    scannerLoading: false,
    shellObserverBusy: false,
    lastPath: ""
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c];
    });
  }
  function num(value) { var n = Number(value); return Number.isFinite(n) ? n : null; }
  function isMobile() { return !!(window.matchMedia && window.matchMedia("(max-width: 767px)").matches); }
  function formatNumber(value, digits) {
    var n = num(value); if (n == null) return "—";
    return n.toLocaleString("vi-VN", { minimumFractionDigits: digits || 0, maximumFractionDigits: digits || 0 });
  }
  function pct(value, digits) {
    var n = num(value); if (n == null) return "—";
    return (n > 0 ? "+" : "") + formatNumber(n, digits == null ? 2 : digits) + "%";
  }
  function shortVolume(value) {
    var n = num(value); if (n == null) return "—";
    if (n >= 1000000) return formatNumber(n / 1000000, 2) + " triệu";
    if (n >= 1000) return formatNumber(n / 1000, 1) + " nghìn";
    return formatNumber(n, 0);
  }
  function metricClass(value) { var n = num(value); return n > 0 ? "positive" : n < 0 ? "negative" : ""; }
  function logoHtml(symbol, extra) {
    var safe = String(symbol || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
    var fallback = safe.slice(0, 3) || "?";
    return '<span class="company-logo ' + esc(extra || "") + '"><img class="company-logo-img" decoding="async" src="' +
      LOGO_BASE_URL + esc(safe) + '.jpg?v=' + LOGO_VERSION +
      '" alt="" onerror="this.remove()"><span class="company-logo-fallback">' + esc(fallback) + '</span></span>';
  }
  function getClient() {
    if (state.client) return state.client;
    if (window.__cccSupabaseClient) state.client = window.__cccSupabaseClient;
    else if (Array.isArray(window.__cccSupabaseClients) && window.__cccSupabaseClients.length) {
      state.client = window.__cccSupabaseClients[window.__cccSupabaseClients.length - 1];
    }
    return state.client;
  }
  function currentPath() { return window.location.pathname || "/"; }
  function replaceUrlTab(tab) {
    var url = new URL(window.location.href);
    if (tab === "watchlist") url.searchParams.delete("tab");
    else url.searchParams.set("tab", tab);
    history.replaceState(history.state, "", url.pathname + (url.search ? url.search : "") + url.hash);
  }

  /* ------------------------------------------------------------------ */
  /* Navigation: remove "Bộ quét", turn DS mã theo dõi into real link. */
  /* ------------------------------------------------------------------ */

  function elementText(el) { return String(el && el.textContent || "").replace(/\s+/g, " ").trim(); }

  function convertPlaceholderToLink(el) {
    if (!el || el.tagName === "A") {
      if (el) el.setAttribute("href", SCANNER_PATH);
      return el;
    }
    var a = document.createElement("a");
    for (var i = 0; i < el.attributes.length; i += 1) {
      var attr = el.attributes[i];
      if (attr.name !== "class") a.setAttribute(attr.name, attr.value);
    }
    a.className = String(el.className || "").replace(/\bshell-nav-placeholder\b/g, "shell-nav-link") + " ccc-ds-nav-link";
    a.href = SCANNER_PATH;
    while (el.firstChild) a.appendChild(el.firstChild);
    el.replaceWith(a);
    return a;
  }

  function patchNavigation() {
    document.querySelectorAll(".shell-nav-link,.shell-nav-placeholder,.mobile-bottom a,.mobile-bottom button").forEach(function (item) {
      var text = elementText(item);
      var label = item.querySelector && item.querySelector(".nav-label");
      var labelText = elementText(label);
      if (labelText === "Bộ quét" || (!labelText && /^Bộ quét\b/i.test(text))) {
        item.style.display = "none";
        item.setAttribute("aria-hidden", "true");
        return;
      }
      if (labelText === "Watchlist" || labelText === "DS mã theo dõi" || /^(Watchlist|DS mã theo dõi)\b/i.test(text)) {
        if (label) label.textContent = "DS mã theo dõi";
        var link = item.classList && item.classList.contains("shell-nav-placeholder") ? convertPlaceholderToLink(item) : item;
        if (link && link.tagName === "A") link.setAttribute("href", SCANNER_PATH);
        if (link) {
          link.style.removeProperty("display");
          link.removeAttribute("aria-hidden");
          link.classList.add("ccc-ds-nav-link");
        }
      }
    });
  }

  function patchAccountAnchors() {
    if (currentPath() !== ACCOUNT_PATH) return;
    var root = document.getElementById("ccc-account-page-root"); if (!root) return;
    root.querySelectorAll(".ccc-account-card").forEach(function (card) {
      var text = elementText(card.querySelector(".ccc-account-kicker")) + " " + elementText(card.querySelector("h2"));
      if (/DS MÃ THEO DÕI|DANH SÁCH MÃ THEO DÕI|WATCHLIST/i.test(text)) card.id = "ds-ma-theo-doi";
      if (card.classList.contains("membership") || /GÓI HIỆN TẠI|GÓI THÀNH VIÊN/i.test(text)) card.id = "goi-thanh-vien";
    });
    if (window.location.hash === "#ds-ma-theo-doi" || window.location.hash === "#goi-thanh-vien") {
      var target = document.querySelector(window.location.hash);
      if (target && !target.dataset.cccScrolled) {
        target.dataset.cccScrolled = "1";
        setTimeout(function () {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
          target.classList.add("ccc-anchor-flash");
          setTimeout(function () { target.classList.remove("ccc-anchor-flash"); }, 1800);
        }, 120);
      }
    }
  }

  /* ----------------------- Overview ---------------------------------- */

  function overviewRowsForGroup() {
    var rows = state.overviewData && Array.isArray(state.overviewData.rows) ? state.overviewData.rows.slice() : [];
    if (!state.overviewGroup) return rows;
    var group = GROUPS[state.overviewGroup];
    return group ? rows.filter(group.matcher) : rows;
  }

  function overviewCounts(key) {
    var data = state.overviewData || {};
    var def = GROUPS[key];
    return {
      market: Number(data.market_counts && data.market_counts[def.marketKey] || 0),
      mine: Number(data.watchlist_counts && data.watchlist_counts[def.marketKey] || 0)
    };
  }
  function overviewEffectiveFull() { return !!(state.overviewData && state.overviewData.effective_full_market_access); }
  function overviewVipActive() { return !!(state.overviewData && state.overviewData.vip_day_active); }

  function signalRailHtml(row) {
    var values = [row.signal_price_3pct, row.signal_daily_volume_200pct, row.signal_above_ma200, row.signal_rvol30_200pct];
    var tones = ["price","volume","trend","rvol"];
    var segs = values.map(function (passed, i) {
      return '<span class="ccc-segment ccc-' + tones[i] + ' ' + (passed ? 'is-on' : 'is-off') + '"></span>';
    }).join("");
    var count = Number(row.signal_count || 0);
    var label = count === 4 ? "<em>Hội tụ mạnh</em>" : count === 3 ? "<em>Đang hội tụ</em>" : "";
    return '<span class="ccc-rail ' + (count === 4 ? "is-confluent" : count === 3 ? "is-converging" : "") +
      '"><span class="ccc-segments">' + segs + '</span><b>' + count + '/4</b>' + label + '</span>';
  }

  function detailedRowHtml(row, allowDetail) {
    var company = row.display_name || row.company_name || "";
    var attrs = allowDetail ? ' data-symbol="' + esc(row.symbol) + '" tabindex="0"' : "";
    var volumeRatio = num(row.daily_volume_pct) == null ? "—" : formatNumber(row.daily_volume_pct, 0) + "% KLTB10";
    return '<article class="lovable-stock-row universal-stock-card ccc-alpha18-stock-row' + (allowDetail ? " is-clickable" : "") + '"' + attrs + '>' +
      '<div class="stock-row-identity">' + logoHtml(row.symbol, "row-logo") + '<div><strong>' + esc(row.symbol) + '</strong><span title="' + esc(company) + '">' +
      esc(company || "Tên công ty đang cập nhật") + '</span><small>' + esc(row.exchange || "") + '</small></div></div>' +
      '<div class="stock-row-price"><strong>' + formatNumber(row.current_price, 0) + '</strong><span class="' + metricClass(row.price_change_pct) + '">' + pct(row.price_change_pct, 2) + '</span></div>' +
      '<div class="stock-row-volume"><small>KL hiện tại</small><strong>' + shortVolume(row.volume_accumulated) + '</strong><span class="volume-ratio">' + esc(volumeRatio) + '</span></div>' +
      '<div class="stock-row-highlights"><div class="stock-row-highlight-line highlight-rvol"><span>RVOL30</span><strong>' + (num(row.rvol30_pct) == null ? "—" : formatNumber(row.rvol30_pct, 0) + "%") +
      '</strong></div><div class="stock-row-highlight-line highlight-trend"><span>MA200</span><strong>' + pct(row.ma200_distance_pct, 1) + '</strong></div></div>' +
      '<div class="stock-row-ccc">' + signalRailHtml(row) + '</div></article>';
  }

  function overviewPaginationHtml(total) {
    if (total <= 0) return "";
    if (isMobile()) {
      var shown = Math.min(total, state.overviewMobileVisible);
      return '<div class="ccc-alpha18-mobile-more"><span>Đang hiển thị ' + shown + '/' + total + ' mã</span>' +
        (shown < total ? '<button type="button" data-ccc-overview-more>Xem thêm ' + Math.min(MOBILE_CHUNK_SIZE, total - shown) + ' mã</button>' : '') + '</div>';
    }
    var pages = Math.max(1, Math.ceil(total / DESKTOP_PAGE_SIZE));
    state.overviewPage = Math.min(state.overviewPage, pages);
    if (pages <= 1) return "";
    return '<div class="ccc-alpha18-pagination"><button type="button" data-ccc-overview-page="-1"' + (state.overviewPage <= 1 ? " disabled" : "") + '>← Trước</button>' +
      '<span>Trang <b>' + state.overviewPage + '</b> / ' + pages + ' · ' + total + ' mã</span>' +
      '<button type="button" data-ccc-overview-page="1"' + (state.overviewPage >= pages ? " disabled" : "") + '>Sau →</button></div>';
  }

  function overviewVisibleRows() {
    var rows = overviewRowsForGroup();
    if (isMobile()) return rows.slice(0, state.overviewMobileVisible);
    var start = (state.overviewPage - 1) * DESKTOP_PAGE_SIZE;
    return rows.slice(start, start + DESKTOP_PAGE_SIZE);
  }

  function overviewUpsellHtml() {
    if (!state.overviewGroup || overviewEffectiveFull()) return "";
    var c = overviewCounts(state.overviewGroup);
    var locked = Math.max(0, c.market - c.mine);
    if (locked <= 0) return "";
    return '<section class="ccc-overview-upsell"><div><span>CÒN ' + locked + ' MÃ KHÁC</span><strong>' + c.market + ' mã trên thị trường đang thuộc nhóm ' +
      esc(GROUPS[state.overviewGroup].title) + '.</strong><p>Bạn đang xem chi tiết ' + c.mine + ' mã trong DS mã theo dõi. Danh tính các mã còn lại không được tiết lộ.</p></div>' +
      '<div class="ccc-overview-upsell-actions"><button type="button" data-ccc-vip-preview>Mở FULL 24 giờ · 100.000đ</button><a href="' + ACCOUNT_PATH + '#goi-thanh-vien">Mở rộng DS mã theo dõi</a></div></section>';
  }

  function renderOverview() {
    if (currentPath() !== "/" || !state.overviewData) return;
    var overview = document.querySelector("main.lovable-overview"); if (!overview) return;
    overview.dataset.cccAlpha18 = "1";

    var subtitle = overview.querySelector(".page-heading h1 + p");
    var desiredSubtitle = "Theo dõi sức nóng toàn thị trường và các tín hiệu xuất hiện trong DS mã theo dõi của bạn.";
    if (subtitle && subtitle.textContent !== desiredSubtitle) subtitle.textContent = desiredSubtitle;

    document.querySelectorAll(".overview-density-trigger[data-overview-group]").forEach(function (tile) {
      var key = tile.getAttribute("data-overview-group"); if (!GROUPS[key]) return;
      var c = overviewCounts(key);
      var strong = tile.querySelector(":scope > strong"); if (strong) strong.innerHTML = c.market + "<small> mã</small>";
      var footer = tile.querySelector(":scope > div");
      if (footer) {
        footer.innerHTML = '<em>Toàn thị trường</em><b>' +
          (overviewEffectiveFull() ? (overviewVipActive() ? "VIP 24h · toàn bộ thị trường" : "DS của bạn: toàn bộ thị trường") : "DS mã theo dõi của bạn: " + c.mine + " mã") +
          '</b>';
      }
      var active = state.overviewGroup === key;
      tile.classList.toggle("active", active);
      tile.setAttribute("aria-pressed", active ? "true" : "false");
    });

    var section = document.getElementById("overview-results"); if (!section) return;
    section.setAttribute("data-ccc-group", state.overviewGroup || "all");

    var allRows = overviewRowsForGroup();
    var rows = overviewVisibleRows();
    var h2 = section.querySelector(".section-bar h2");
    if (h2) h2.textContent = state.overviewGroup ? "Tín hiệu trong DS mã theo dõi của bạn" : "DS mã theo dõi của bạn";

    var summary = document.getElementById("overview-selection-summary");
    if (summary) {
      if (state.overviewGroup) {
        var c = overviewCounts(state.overviewGroup);
        summary.innerHTML = 'Đang xem: <b>' + esc(GROUPS[state.overviewGroup].title) + '</b> · ' + c.market + ' mã toàn thị trường · ' +
          (overviewEffectiveFull() ? allRows.length + ' mã trong DS của bạn' : c.mine + ' mã trong DS của bạn') +
          ' <button type="button" class="ccc-overview-reset" data-ccc-overview-reset>← Xem tất cả DS mã theo dõi</button>';
      } else {
        summary.innerHTML = '<b>Tất cả DS mã theo dõi</b> · ' + allRows.length + ' mã';
      }
    }

    var count = document.getElementById("overview-selection-count");
    if (count) count.textContent = allRows.length + " mã";

    var container = document.getElementById("overview-rows");
    if (container) {
      if (!allRows.length) {
        container.innerHTML = '<div class="ccc-overview-empty"><strong>Bạn chưa có mã theo dõi.</strong><span>KPI phía trên vẫn cho biết sức nóng toàn thị trường.</span><a href="' +
          ACCOUNT_PATH + '#ds-ma-theo-doi">Thiết lập DS mã theo dõi</a></div>';
      } else {
        container.innerHTML = rows.map(function (r) { return detailedRowHtml(r, true); }).join("") + overviewPaginationHtml(allRows.length);
      }
    }

    var see = document.getElementById("overview-see-all-slot"); if (see) see.innerHTML = "";
    var locked = document.getElementById("overview-locked-slot"); if (locked) locked.innerHTML = overviewUpsellHtml();
    bindVipPreview();
  }

  function interceptOverviewTile(event) {
    var tile = event.target && event.target.closest ? event.target.closest(".overview-density-trigger[data-overview-group]") : null;
    if (!tile || currentPath() !== "/" || !state.overviewData) return;
    var key = tile.getAttribute("data-overview-group"); if (!GROUPS[key]) return;
    event.preventDefault(); event.stopPropagation(); event.stopImmediatePropagation();
    state.overviewGroup = state.overviewGroup === key ? "" : key;
    state.overviewPage = 1;
    state.overviewMobileVisible = MOBILE_CHUNK_SIZE;
    renderOverview();
  }

  /* ---------------------- Scanner ------------------------------------ */

  function scannerTabFromUrl() {
    var tab = new URLSearchParams(window.location.search).get("tab");
    return tab === "market" ? "market" : "watchlist";
  }

  function scannerRowsForTab() {
    if (state.scannerTab === "market") return Array.isArray(state.marketRows) ? state.marketRows.slice() : [];
    return state.scannerData && Array.isArray(state.scannerData.rows) ? state.scannerData.rows.slice() : [];
  }

  function companyName(row) {
    if (row.display_name || row.company_name) return row.display_name || row.company_name;
    var meta = state.metadataBySymbol[String(row.symbol || "").toUpperCase()] || {};
    return meta.display_name || meta.company_name || "";
  }

  function normalizeMarketRow(r) {
    return {
      symbol: String(r.symbol || "").toUpperCase(),
      exchange: r.exchange || "",
      current_price: r.current_price,
      price_change_pct: r.price_change_pct,
      volume_accumulated: r.volume_accumulated,
      ma200_distance_pct: r.ma200_distance_pct,
      ma10_distance_pct: r.ma10_distance_pct,
      display_name: companyName(r),
      company_name: companyName(r)
    };
  }

  function scannerFilterRows() {
    var rows = scannerRowsForTab();
    var q = state.scannerSearch.trim().toLowerCase();

    if (q) rows = rows.filter(function (r) {
      return String(r.symbol || "").toLowerCase().indexOf(q) >= 0 || companyName(r).toLowerCase().indexOf(q) >= 0;
    });
    if (state.scannerExchange !== "all") rows = rows.filter(function (r) { return String(r.exchange || "").toUpperCase() === state.scannerExchange; });

    if (state.scannerTab === "watchlist") {
      if (state.scannerQuick === "4") rows = rows.filter(GROUPS["4of4"].matcher);
      else if (state.scannerQuick === "3") rows = rows.filter(GROUPS["3plus"].matcher);
      else if (state.scannerQuick === "2") rows = rows.filter(GROUPS["2plus"].matcher);
      else if (state.scannerQuick === "rvol") rows = rows.filter(GROUPS["rvol30"].matcher);

      if (state.scannerSignal === "price") rows = rows.filter(function (r) { return r.signal_price_3pct === true; });
      if (state.scannerSignal === "volume") rows = rows.filter(function (r) { return r.signal_daily_volume_200pct === true; });
      if (state.scannerSignal === "ma200") rows = rows.filter(function (r) { return r.signal_above_ma200 === true; });
      if (state.scannerSignal === "rvol") rows = rows.filter(function (r) { return r.signal_rvol30_200pct === true; });
      if (state.scannerSignal === "4") rows = rows.filter(GROUPS["4of4"].matcher);
      if (state.scannerSignal === "3") rows = rows.filter(GROUPS["3plus"].matcher);
      if (state.scannerSignal === "2") rows = rows.filter(GROUPS["2plus"].matcher);
    }

    function val(r, key) { var n = num(r[key]); return n == null ? -Infinity : n; }
    var sort = state.scannerSort;
    rows.sort(function (a, b) {
      if (sort === "az") return String(a.symbol).localeCompare(String(b.symbol));
      if (sort === "price_desc") return val(b, "price_change_pct") - val(a, "price_change_pct");
      if (sort === "price_asc") return val(a, "price_change_pct") - val(b, "price_change_pct");
      if (sort === "volume_desc") return val(b, "volume_accumulated") - val(a, "volume_accumulated");
      if (sort === "ma200_desc") return val(b, "ma200_distance_pct") - val(a, "ma200_distance_pct");
      if (sort === "ma200_asc") return val(a, "ma200_distance_pct") - val(b, "ma200_distance_pct");
      if (sort === "rvol_desc") return val(b, "rvol30_pct") - val(a, "rvol30_pct");
      if (sort === "rvol_asc") return val(a, "rvol30_pct") - val(b, "rvol30_pct");
      if (sort === "signal") return val(b, "signal_count") - val(a, "signal_count") || val(b, "rvol30_pct") - val(a, "rvol30_pct") || String(a.symbol).localeCompare(String(b.symbol));
      return String(a.symbol).localeCompare(String(b.symbol));
    });
    return rows;
  }

  function scannerPageRows(rows) {
    if (isMobile()) return rows.slice(0, state.scannerMobileVisible);
    var pages = Math.max(1, Math.ceil(rows.length / DESKTOP_PAGE_SIZE));
    state.scannerPage = Math.min(state.scannerPage, pages);
    var start = (state.scannerPage - 1) * DESKTOP_PAGE_SIZE;
    return rows.slice(start, start + DESKTOP_PAGE_SIZE);
  }

  function scannerPaginationHtml(total) {
    if (isMobile()) {
      var shown = Math.min(total, state.scannerMobileVisible);
      return '<div class="ccc-alpha18-mobile-more"><span>Đang hiển thị ' + shown + '/' + total + ' mã</span>' +
        (shown < total ? '<button type="button" data-ccc-scanner-more>Xem thêm ' + Math.min(MOBILE_CHUNK_SIZE, total - shown) + ' mã</button>' : '') + '</div>';
    }
    var pages = Math.max(1, Math.ceil(total / DESKTOP_PAGE_SIZE));
    if (pages <= 1) return '<div class="ccc-alpha18-page-summary">' + total + ' mã</div>';
    return '<div class="ccc-alpha18-pagination"><button type="button" data-ccc-scanner-page="-1"' + (state.scannerPage <= 1 ? " disabled" : "") + '>← Trước</button>' +
      '<span>Trang <b>' + state.scannerPage + '</b> / ' + pages + ' · ' + total + ' mã</span>' +
      '<button type="button" data-ccc-scanner-page="1"' + (state.scannerPage >= pages ? " disabled" : "") + '>Sau →</button></div>';
  }

  function marketRowHtml(row) {
    var company = companyName(row);
    return '<article class="ccc-market-basic-row">' +
      '<div class="ccc-market-company">' + logoHtml(row.symbol, "row-logo") + '<div><strong>' + esc(row.symbol) + '</strong><span>' + esc(company || "Tên công ty đang cập nhật") +
      '</span><small>' + esc(row.exchange || "") + '</small></div></div>' +
      '<div class="ccc-market-metric"><small>Giá</small><strong>' + formatNumber(row.current_price, 0) + '</strong></div>' +
      '<div class="ccc-market-metric"><small>Thay đổi</small><strong class="' + metricClass(row.price_change_pct) + '">' + pct(row.price_change_pct, 2) + '</strong></div>' +
      '<div class="ccc-market-metric"><small>KL hiện tại</small><strong>' + shortVolume(row.volume_accumulated) + '</strong></div>' +
      '<div class="ccc-market-metric"><small>MA200</small><strong class="' + metricClass(row.ma200_distance_pct) + '">' + pct(row.ma200_distance_pct, 1) + '</strong></div>' +
      '<div class="ccc-market-metric ccc-market-ma10"><small>MA10</small><strong class="' + metricClass(row.ma10_distance_pct) + '">' + pct(row.ma10_distance_pct, 1) + '</strong></div>' +
      '</article>';
  }

  function scannerQuickHtml() {
    if (state.scannerTab !== "watchlist") return "";
    var rows = state.scannerData && Array.isArray(state.scannerData.rows) ? state.scannerData.rows : [];
    function count(fn) { return rows.filter(fn).length; }
    return '<div class="scanner-signal-summary ccc-alpha18-quick">' +
      '<button type="button" data-ccc-quick="all" class="' + (state.scannerQuick === "all" ? "active" : "") + '"><span>Tất cả</span><strong>' + rows.length + '</strong></button>' +
      '<button type="button" data-ccc-quick="4" class="' + (state.scannerQuick === "4" ? "active" : "") + '"><span>4/4</span><strong>' + count(GROUPS["4of4"].matcher) + '</strong></button>' +
      '<button type="button" data-ccc-quick="3" class="' + (state.scannerQuick === "3" ? "active" : "") + '"><span>≥3</span><strong>' + count(GROUPS["3plus"].matcher) + '</strong></button>' +
      '<button type="button" data-ccc-quick="2" class="' + (state.scannerQuick === "2" ? "active" : "") + '"><span>≥2</span><strong>' + count(GROUPS["2plus"].matcher) + '</strong></button>' +
      '<button type="button" data-ccc-quick="rvol" class="' + (state.scannerQuick === "rvol" ? "active" : "") + '"><span>RVOL30</span><strong>' + count(GROUPS["rvol30"].matcher) + '</strong></button>' +
      '</div>';
  }

  function exchangesForTab() {
    var seen = {};
    scannerRowsForTab().forEach(function (r) { var ex = String(r.exchange || "").toUpperCase(); if (ex) seen[ex] = true; });
    return Object.keys(seen).sort();
  }

  function scannerFiltersHtml() {
    var exchanges = exchangesForTab();
    var sortOptions = state.scannerTab === "market"
      ? [
          ["az","Mã A → Z"], ["price_desc","Tăng giá nhiều nhất"], ["price_asc","Giảm giá nhiều nhất"],
          ["volume_desc","KL hiện tại cao nhất"], ["ma200_desc","Trên MA200 nhiều nhất"], ["ma200_asc","Dưới MA200 nhiều nhất"]
        ]
      : [
          ["signal","Nhiều tín hiệu nhất"], ["price_desc","Tăng giá nhiều nhất"], ["price_asc","Giảm giá nhiều nhất"],
          ["volume_desc","KL hiện tại cao nhất"], ["rvol_desc","RVOL30 cao nhất"], ["rvol_asc","RVOL30 thấp nhất"],
          ["ma200_desc","MA200 cao nhất"], ["ma200_asc","MA200 thấp nhất"], ["az","Mã A → Z"]
        ];
    if (state.scannerTab === "market" && ["signal","rvol_desc","rvol_asc"].indexOf(state.scannerSort) >= 0) state.scannerSort = "az";
    if (state.scannerTab === "watchlist" && !state.scannerSort) state.scannerSort = "signal";

    return '<section class="ccc-alpha18-filters">' +
      '<label class="ccc-alpha18-search"><span>Tìm mã / công ty</span><input type="search" data-ccc-scanner-search value="' + esc(state.scannerSearch) + '" placeholder="VD: VIC, FPT, Vingroup…"></label>' +
      '<label><span>Sàn</span><select data-ccc-scanner-exchange><option value="all">Tất cả sàn</option>' +
      exchanges.map(function (ex) { return '<option value="' + esc(ex) + '"' + (state.scannerExchange === ex ? " selected" : "") + '>' + esc(ex) + '</option>'; }).join("") + '</select></label>' +
      (state.scannerTab === "watchlist" ? '<label><span>Tín hiệu</span><select data-ccc-scanner-signal>' +
        [['all','Tất cả tín hiệu'],['4','Đạt 4/4'],['3','Từ 3 tín hiệu'],['2','Từ 2 tín hiệu'],['price','Giá ≥ 3%'],['volume','KL ngày ≥ 200%'],['ma200','Trên MA200'],['rvol','RVOL30 ≥ 200%']].map(function (o) {
          return '<option value="' + o[0] + '"' + (state.scannerSignal === o[0] ? " selected" : "") + '>' + o[1] + '</option>';
        }).join("") + '</select></label>' : '') +
      '<label><span>Sắp xếp</span><select data-ccc-scanner-sort>' +
      sortOptions.map(function (o) { return '<option value="' + o[0] + '"' + (state.scannerSort === o[0] ? " selected" : "") + '>' + o[1] + '</option>'; }).join("") +
      '</select></label></section>';
  }

  function scannerHeaderHtml() {
    return '<div class="page-heading"><div><span class="eyebrow">THEO DÕI THỊ TRƯỜNG</span><h1>DS mã theo dõi</h1><p>Tab DS mã theo dõi hiển thị toàn bộ tín hiệu theo quyền gói. Tab Toàn bộ thị trường cho phép xem dữ liệu cơ bản của toàn bộ danh sách hệ thống.</p></div></div>' +
      '<div class="ccc-alpha18-scanner-tabs" role="tablist">' +
      '<button type="button" role="tab" data-ccc-scanner-tab="watchlist" class="' + (state.scannerTab === "watchlist" ? "active" : "") + '">DS mã theo dõi</button>' +
      '<button type="button" role="tab" data-ccc-scanner-tab="market" class="' + (state.scannerTab === "market" ? "active" : "") + '">Toàn bộ thị trường</button>' +
      '</div>';
  }

  function renderScanner() {
    if (currentPath() !== SCANNER_PATH) return;
    var main = document.querySelector("main.lovable-scanner"); if (!main) return;
    main.dataset.cccAlpha18 = "1";
    var rows = scannerFilterRows();
    var pageRows = scannerPageRows(rows);
    var market = state.scannerTab === "market";

    main.innerHTML = scannerHeaderHtml() +
      scannerQuickHtml() +
      scannerFiltersHtml() +
      '<section class="ccc-alpha18-scanner-results">' +
      '<div class="section-bar"><div><span>' + (market ? "TOÀN BỘ THỊ TRƯỜNG" : "DS MÃ THEO DÕI") + '</span><h2>' +
      (market ? "Dữ liệu cơ bản toàn thị trường" : "Tín hiệu trong DS mã theo dõi") + '</h2></div><small>' + rows.length + ' mã</small></div>' +
      (market
        ? '<div class="ccc-market-basic-head"><span>Công ty</span><span>Giá</span><span>Thay đổi</span><span>KL hiện tại</span><span>MA200</span><span>MA10</span></div>'
        : '<div class="overview-row-head"><span>Công ty</span><span>Giá</span><span>Khối lượng</span><span>Điểm nhấn</span><span>CCC 4/4</span></div>') +
      '<div class="ccc-alpha18-scanner-list">' +
      (pageRows.length
        ? pageRows.map(function (r) { return market ? marketRowHtml(r) : detailedRowHtml(r, true); }).join("")
        : '<div class="ccc-overview-empty"><strong>Không có mã phù hợp.</strong><span>Thử thay đổi từ khóa hoặc bộ lọc.</span></div>') +
      '</div>' +
      scannerPaginationHtml(rows.length) +
      (!market ? '<div class="ccc-alpha18-watchlist-footer"><span>Muốn thay đổi hoặc mở rộng DS mã theo dõi?</span><div><a href="' + ACCOUNT_PATH + '#ds-ma-theo-doi">Thay đổi DS mã</a><a href="' + ACCOUNT_PATH + '#goi-thanh-vien">Nâng cấp gói</a></div></div>' : '') +
      '</section>';
  }

  async function loadMarketRows() {
    if (state.marketRows) return;
    var client = getClient(); if (!client) return;
    var parts = await Promise.all([
      client.from("stock_snapshot").select("symbol,exchange,current_price,price_change_pct,volume_accumulated,ma200_distance_pct,ma10_distance_pct").order("symbol", { ascending: true }),
      client.from("stock_metadata").select("symbol,exchange,display_name,company_name").order("symbol", { ascending: true })
    ]);
    if (parts[0].error) throw parts[0].error;
    if (parts[1].error) throw parts[1].error;
    state.metadataBySymbol = Object.create(null);
    (parts[1].data || []).forEach(function (m) { state.metadataBySymbol[String(m.symbol || "").toUpperCase()] = m; });
    state.marketRows = (parts[0].data || []).map(function (r) {
      var meta = state.metadataBySymbol[String(r.symbol || "").toUpperCase()] || {};
      return normalizeMarketRow(Object.assign({}, r, {
        display_name: meta.display_name || meta.company_name || "",
        company_name: meta.company_name || "",
        exchange: r.exchange || meta.exchange || ""
      }));
    });
  }

  async function loadMemberData(force) {
    var client = getClient(); if (!client) return;
    var sessionResult = await client.auth.getSession();
    if (sessionResult.error) throw sessionResult.error;
    var user = sessionResult.data && sessionResult.data.session ? sessionResult.data.session.user : null;
    if (!user) {
      state.userId = "";
      state.overviewData = null;
      state.scannerData = null;
      return;
    }
    if (!force && state.userId === user.id && state.overviewData && state.scannerData) return;
    state.userId = user.id;
    var res = await client.rpc("get_my_overview_state");
    if (res.error) throw res.error;
    state.overviewData = res.data || null;
    state.scannerData = res.data || null;
  }

  async function ensureScannerLoaded(force) {
    if (currentPath() !== SCANNER_PATH || state.scannerLoading) return;
    var client = getClient(); if (!client) return;
    state.scannerLoading = true;
    try {
      state.scannerTab = scannerTabFromUrl();
      await Promise.all([loadMemberData(!!force), loadMarketRows()]);
      renderScanner();
    } catch (error) {
      console.error("CCC alpha18 scanner load failed", error);
      var main = document.querySelector("main.lovable-scanner");
      if (main) main.innerHTML = '<div class="ccc-overview-empty"><strong>Không tải được DS mã theo dõi.</strong><span>Vui lòng thử tải lại trang.</span></div>';
    } finally {
      state.scannerLoading = false;
    }
  }

  async function ensureOverviewLoaded(force) {
    if (currentPath() !== "/" || state.overviewLoading) return;
    var client = getClient(); if (!client) return;
    state.overviewLoading = true;
    try {
      await loadMemberData(!!force);
      renderOverview();
    } catch (error) {
      console.error("CCC alpha18 overview load failed", error);
    } finally {
      state.overviewLoading = false;
    }
  }

  /* -------------------- VIP preview ---------------------------------- */

  function vipModalHtml() {
    return '<div id="ccc-vip-preview" class="ccc-vip-backdrop"><section class="ccc-vip-dialog" role="dialog" aria-modal="true" aria-labelledby="ccc-vip-title">' +
      '<button type="button" class="ccc-vip-close" aria-label="Đóng">×</button><span class="ccc-vip-kicker">VIP DAY</span><h2 id="ccc-vip-title">Mở toàn bộ CCC trong 24 giờ</h2>' +
      '<strong class="ccc-vip-price">100.000đ <small>/ 24 giờ</small></strong><ul><li>Xem toàn bộ tín hiệu kỹ thuật trên thị trường.</li><li>Quyền FULL tạm thời trong đúng 24 giờ kể từ khi kích hoạt.</li>' +
      '<li>Không thay đổi gói nền, DS mã theo dõi, quota hay ngày reset hiện tại.</li><li>Hết 24 giờ, tài khoản tự trở lại đúng trạng thái trước khi mua VIP.</li></ul>' +
      '<button type="button" class="ccc-vip-disabled" disabled>Thanh toán sẽ mở ở bước billing</button><p>VIP Day là quyền truy cập tạm thời, không phải khuyến nghị đầu tư hay cam kết lợi nhuận.</p></section></div>';
  }
  function openVipPreview() {
    if (document.getElementById("ccc-vip-preview")) return;
    document.body.insertAdjacentHTML("beforeend", vipModalHtml());
    var root = document.getElementById("ccc-vip-preview");
    root.querySelector(".ccc-vip-close").addEventListener("click", function () { root.remove(); });
    root.addEventListener("click", function (e) { if (e.target === root) root.remove(); });
  }
  function bindVipPreview() {
    document.querySelectorAll("[data-ccc-vip-preview]").forEach(function (btn) {
      if (btn.dataset.cccBound) return;
      btn.dataset.cccBound = "1";
      btn.addEventListener("click", openVipPreview);
    });
  }

  /* ------------------ Delegated events -------------------------------- */

  document.addEventListener("click", function (event) {
    if (currentPath() === "/") {
      var reset = event.target.closest && event.target.closest("[data-ccc-overview-reset]");
      if (reset) {
        event.preventDefault();
        state.overviewGroup = "";
        state.overviewPage = 1;
        state.overviewMobileVisible = MOBILE_CHUNK_SIZE;
        renderOverview();
        return;
      }
      var p = event.target.closest && event.target.closest("[data-ccc-overview-page]");
      if (p) {
        event.preventDefault();
        state.overviewPage = Math.max(1, state.overviewPage + Number(p.getAttribute("data-ccc-overview-page") || 0));
        renderOverview();
        return;
      }
      var more = event.target.closest && event.target.closest("[data-ccc-overview-more]");
      if (more) {
        event.preventDefault();
        state.overviewMobileVisible += MOBILE_CHUNK_SIZE;
        renderOverview();
        return;
      }
    }

    if (currentPath() === SCANNER_PATH) {
      var tab = event.target.closest && event.target.closest("[data-ccc-scanner-tab]");
      if (tab) {
        event.preventDefault();
        state.scannerTab = tab.getAttribute("data-ccc-scanner-tab") === "market" ? "market" : "watchlist";
        state.scannerQuick = "all";
        state.scannerSignal = "all";
        state.scannerSort = state.scannerTab === "market" ? "az" : "signal";
        state.scannerPage = 1;
        state.scannerMobileVisible = MOBILE_CHUNK_SIZE;
        replaceUrlTab(state.scannerTab);
        renderScanner();
        return;
      }
      var quick = event.target.closest && event.target.closest("[data-ccc-quick]");
      if (quick) {
        event.preventDefault();
        state.scannerQuick = quick.getAttribute("data-ccc-quick") || "all";
        state.scannerPage = 1;
        state.scannerMobileVisible = MOBILE_CHUNK_SIZE;
        renderScanner();
        return;
      }
      var sp = event.target.closest && event.target.closest("[data-ccc-scanner-page]");
      if (sp) {
        event.preventDefault();
        state.scannerPage = Math.max(1, state.scannerPage + Number(sp.getAttribute("data-ccc-scanner-page") || 0));
        renderScanner();
        window.scrollTo({ top: Math.max(0, document.querySelector(".ccc-alpha18-scanner-results").getBoundingClientRect().top + window.scrollY - 100), behavior: "smooth" });
        return;
      }
      var sm = event.target.closest && event.target.closest("[data-ccc-scanner-more]");
      if (sm) {
        event.preventDefault();
        state.scannerMobileVisible += MOBILE_CHUNK_SIZE;
        renderScanner();
        return;
      }
    }

    var vip = event.target.closest && event.target.closest("[data-ccc-vip-preview]");
    if (vip) { event.preventDefault(); openVipPreview(); }
  }, false);

  document.addEventListener("click", interceptOverviewTile, true);

  document.addEventListener("input", function (event) {
    if (currentPath() !== SCANNER_PATH) return;
    if (event.target.matches("[data-ccc-scanner-search]")) {
      state.scannerSearch = event.target.value || "";
      state.scannerPage = 1; state.scannerMobileVisible = MOBILE_CHUNK_SIZE;
      renderScanner();
      var input = document.querySelector("[data-ccc-scanner-search]");
      if (input) { input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
    }
  });

  document.addEventListener("change", function (event) {
    if (currentPath() !== SCANNER_PATH) return;
    if (event.target.matches("[data-ccc-scanner-exchange]")) state.scannerExchange = event.target.value;
    else if (event.target.matches("[data-ccc-scanner-signal]")) state.scannerSignal = event.target.value;
    else if (event.target.matches("[data-ccc-scanner-sort]")) state.scannerSort = event.target.value;
    else return;
    state.scannerPage = 1; state.scannerMobileVisible = MOBILE_CHUNK_SIZE;
    renderScanner();
  });

  /* ----------------- Idempotent shell patching ------------------------ */

  function ensureExperience() {
    patchNavigation();
    patchAccountAnchors();
    var path = currentPath();
    if (path !== state.lastPath) {
      state.lastPath = path;
      state.overviewGroup = "";
      state.overviewPage = 1;
      state.overviewMobileVisible = MOBILE_CHUNK_SIZE;
      state.scannerTab = scannerTabFromUrl();
      state.scannerPage = 1;
      state.scannerMobileVisible = MOBILE_CHUNK_SIZE;
    }
    if (path === "/") {
      var overview = document.querySelector("main.lovable-overview");
      /* Important: do not render again for mutations created by Alpha.18 itself.
         If the shell really replaces the page, the marker disappears and we patch once. */
      if (overview && overview.dataset.cccAlpha18 !== "1") ensureOverviewLoaded(true);
    } else if (path === SCANNER_PATH) {
      var scanner = document.querySelector("main.lovable-scanner");
      if (scanner && scanner.dataset.cccAlpha18 !== "1") ensureScannerLoaded(true);
    }
  }

  function init() {
    state.scannerTab = scannerTabFromUrl();
    patchNavigation();
    var tries = 0;
    var wait = setInterval(function () {
      tries += 1;
      var client = getClient();
      if (client || tries > 80) {
        clearInterval(wait);
        if (client && client.auth && client.auth.onAuthStateChange) {
          client.auth.onAuthStateChange(function () {
            state.userId = "";
            state.overviewData = null;
            state.scannerData = null;
            setTimeout(function () {
              if (currentPath() === "/") ensureOverviewLoaded(true);
              if (currentPath() === SCANNER_PATH) ensureScannerLoaded(true);
              patchAccountAnchors();
            }, 0);
          });
        }
        if (currentPath() === "/") ensureOverviewLoaded(true);
        if (currentPath() === SCANNER_PATH) ensureScannerLoaded(true);
      }
    }, 50);

    var app = document.getElementById("app") || document.body;
    var observer = new MutationObserver(function () {
      if (state.shellObserverBusy) return;
      state.shellObserverBusy = true;
      requestAnimationFrame(function () {
        state.shellObserverBusy = false;
        ensureExperience();
      });
    });
    observer.observe(app, { childList: true, subtree: true });

    window.addEventListener("popstate", function () { setTimeout(ensureExperience, 0); });
    window.addEventListener("resize", function () {
      state.overviewPage = 1; state.overviewMobileVisible = MOBILE_CHUNK_SIZE;
      state.scannerPage = 1; state.scannerMobileVisible = MOBILE_CHUNK_SIZE;
      if (currentPath() === "/") renderOverview();
      if (currentPath() === SCANNER_PATH) renderScanner();
    });
    window.addEventListener("ccc:watchlist-updated", function () {
      state.overviewData = null; state.scannerData = null;
      if (currentPath() === "/") ensureOverviewLoaded(true);
      if (currentPath() === SCANNER_PATH) ensureScannerLoaded(true);
    });
    setTimeout(ensureExperience, 250);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();