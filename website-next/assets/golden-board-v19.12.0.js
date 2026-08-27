(function () {
  "use strict";

  var PATH = "/bang-vang/";
  var ACCOUNT_PATH = "/tai-khoan";
  var REFRESH_MS = 60 * 1000;
  var bootTimer = null;
  var refreshTimer = null;
  var currentDate = "";
  var lastLoadKey = "";
  var lastData = null;
  var loading = false;
  var overviewLoading = false;

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function num(value) {
    if (value === null || value === undefined || value === "") return null;
    var n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function fmt(value, digits) {
    var n = num(value);
    if (n === null) return "—";
    return n.toLocaleString("vi-VN", {
      minimumFractionDigits: digits || 0,
      maximumFractionDigits: digits || 0
    });
  }

  function pct(value, digits) {
    var n = num(value);
    if (n === null) return "—";
    return (n > 0 ? "+" : "") + n.toLocaleString("vi-VN", {
      minimumFractionDigits: digits == null ? 1 : digits,
      maximumFractionDigits: digits == null ? 1 : digits
    }) + "%";
  }

  function timeText(value) {
    var text = String(value || "");
    return text ? text.slice(0, 5) : "—";
  }

  function dateText(value) {
    var text = String(value || "");
    var m = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    return m ? (m[3] + "/" + m[2] + "/" + m[1]) : (text || "—");
  }

  function stockLogoUrl(symbol) {
    var safe = String(symbol || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
    var host = String(location.hostname || "").toLowerCase();
    var base = (host === "localhost" || host === "127.0.0.1" || host === "0.0.0.0")
      ? "/assets/logos"
      : ((document.querySelector('meta[name="ccc-stock-logo-base"]') || {}).content || "https://www.chuyenchochung.com/stock-logos");
    return String(base).replace(/\/+$/, "") + "/" + encodeURIComponent(safe) + ".webp?v=gb-local-preview";
  }

  function iconSvg(name) {
    if (name === "trophy") {
      return '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M8 4h8v3.5a4 4 0 0 1-8 0V4Z" stroke="currentColor" stroke-width="1.8"/><path d="M8 6H5v1.2A3.8 3.8 0 0 0 8.7 11M16 6h3v1.2a3.8 3.8 0 0 1-3.7 3.8M12 11.5V16m-3 3h6m-7 1h8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
    }
    return "";
  }

  function goldenNavLink(mobile) {
    var link = document.createElement("a");
    link.href = PATH;
    link.className = "shell-nav-link golden-board-nav-link";
    link.setAttribute("data-golden-board-nav", "1");
    link.setAttribute("aria-label", "Bảng vàng");
    link.innerHTML =
      '<span class="nav-ico">' + iconSvg("trophy") + '</span>' +
      '<span class="nav-label">Bảng vàng</span>' +
      '<small>' + (mobile ? "Bảng vàng" : "Bảng vàng") + "</small>";
    link.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopImmediatePropagation();
      location.href = PATH;
    });
    return link;
  }

  function ensureNavigation() {
    var desktop = document.querySelector(".desktop-nav nav");
    if (desktop && !desktop.querySelector('[data-golden-board-nav="1"]')) {
      var research = desktop.querySelector('a[href="/so-sanh-theo-nganh"]');
      var link = goldenNavLink(false);
      if (research) desktop.insertBefore(link, research);
      else desktop.appendChild(link);
    }

    var mobile = document.querySelector(".mobile-bottom");
    if (mobile) {
      var guide = mobile.querySelector('a[href="/huong-dan"]');
      if (guide) guide.remove();

      if (!mobile.querySelector('[data-golden-board-nav="1"]')) {
        var mobileResearch = mobile.querySelector('a[href="/so-sanh-theo-nganh"]');
        var mobileLink = goldenNavLink(true);
        if (mobileResearch) mobile.insertBefore(mobileLink, mobileResearch);
        else mobile.appendChild(mobileLink);
      }
    }

    if (isGoldenPath()) {
      document.querySelectorAll(".shell-nav-link.active").forEach(function (item) {
        item.classList.remove("active");
      });
      document.querySelectorAll('[data-golden-board-nav="1"]').forEach(function (item) {
        item.classList.add("active");
      });
      var routeLabel = document.querySelector(".mobile-route");
      if (routeLabel) routeLabel.textContent = "Bảng vàng";
    }
  }

  function renameFourSignalKpi() {
    if (isGoldenPath()) return;
    var root = document.querySelector("main");
    if (!root) return;
    root.querySelectorAll("span,strong,b,h2,h3,p").forEach(function (node) {
      if (String(node.textContent || "").trim() !== "4 tín hiệu") return;
      var holder = node.closest('[class*="kpi"],[class*="stat"],[class*="summary"]');
      if (holder) node.textContent = "Đang đạt 4/4";
    });
  }

  function isGoldenPath() {
    var p = (location.pathname || "/").replace(/\/+$/, "");
    return p === "/bang-vang";
  }

  function requireClient() {
    if (!window.CCCData || typeof window.CCCData.init !== "function") {
      throw new Error("CCC_DATA_UNAVAILABLE");
    }
    return window.CCCData.init();
  }

  async function sessionState() {
    if (!window.CCCData || typeof window.CCCData.getSession !== "function") {
      return { session: null };
    }
    try {
      return await window.CCCData.getSession() || { session: null };
    } catch (_) {
      return { session: null };
    }
  }

  async function loadGolden(dateValue) {
    var sb = requireClient();
    var sessionData = await sessionState();
    var signedIn = !!(sessionData && sessionData.session);
    if (signedIn) {
      var results = await Promise.all([
        sb.rpc("get_my_golden_board", { p_trading_date: dateValue || null }),
        sb.rpc("get_public_golden_board", { p_trading_date: dateValue || null })
      ]);
      if (results[0].error) throw results[0].error;
      if (results[1].error) throw results[1].error;
      var memberData = results[0].data || {};
      memberData.market_teaser = results[1].data || {};
      return { signedIn: true, data: memberData };
    }

    var result = await sb.rpc("get_public_golden_board", {
      p_trading_date: dateValue || null
    });
    if (result.error) throw result.error;
    return { signedIn: false, data: result.data || {} };
  }

  function logoHtml(row) {
    var symbol = String(row.symbol || "").toUpperCase();
    return '<span class="gb-logo-wrap"><img class="gb-logo" src="' + esc(stockLogoUrl(symbol)) + '" alt="" loading="lazy" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'grid\'"><span class="gb-logo-fallback">' + esc(symbol.slice(0, 3)) + "</span></span>";
  }

  function identityHtml(row, link) {
    var symbol = String(row.symbol || "").toUpperCase();
    var name = row.display_name || row.company_name || "Tên công ty đang cập nhật";
    var inner = logoHtml(row) +
      '<span class="gb-identity-copy"><strong>' + esc(symbol) + '</strong><span>' + esc(name) + '</span><small>' + esc(row.exchange || "") + "</small></span>";
    return link
      ? '<a class="gb-identity" href="/co-phieu/' + encodeURIComponent(symbol) + '">' + inner + "</a>"
      : '<div class="gb-identity">' + inner + "</div>";
  }

  function statusHtml(row) {
    var count = Math.max(0, Math.min(4, Number(row.latest_signal_count || 0)));
    var keep = row.still_4of4 === true || count === 4;
    return '<span class="gb-status ' + (keep ? "is-live" : "is-recorded") + '">' +
      (keep ? "Đang giữ 4/4" : "Đã ghi nhận · hiện " + count + "/4") +
      "</span>";
  }

  function fullRowHtml(row) {
    var streak = Number(row.longest_streak_hits || 0);
    var streakText = streak > 1 ? (streak + " lần quét liên tiếp") : "1 lần quét";
    return '<article class="gb-row">' +
      '<div class="gb-row-main">' +
        identityHtml(row, true) +
        '<div class="gb-row-status">' + statusHtml(row) + "</div>" +
      "</div>" +
      '<div class="gb-metrics">' +
        '<div><span>Ghi nhận đầu</span><strong>' + esc(timeText(row.first_hit_slot)) + "</strong></div>" +
        '<div><span>Lần 4/4 gần nhất</span><strong>' + esc(timeText(row.last_hit_slot)) + "</strong></div>" +
        '<div><span>Số lần 4/4</span><strong>' + fmt(row.hit_count, 0) + "</strong></div>" +
        '<div><span>Chuỗi tốt nhất</span><strong>' + esc(streakText) + "</strong></div>" +
        '<div><span>Giá lúc ghi nhận</span><strong>' + fmt(row.first_price, 0) + "</strong></div>" +
        '<div><span>Biến động giá</span><strong class="' + (num(row.first_price_change_pct) >= 0 ? "positive" : "negative") + '">' + pct(row.first_price_change_pct, 2) + "</strong></div>" +
        '<div><span>KL ngày / KLTB10</span><strong>' + pct(row.first_daily_volume_pct, 0).replace("+", "") + "</strong></div>" +
        '<div><span>Trên MA200</span><strong>' + pct(row.first_ma200_distance_pct, 1) + "</strong></div>" +
        '<div><span>RVOL30 lúc ghi nhận</span><strong>' + pct(row.first_rvol30_pct, 0).replace("+", "") + "</strong><small>nền " + fmt(row.first_rvol30_sessions, 0) + "/10</small></div>" +
      "</div>" +
    "</article>";
  }

  function teaserRowHtml(row) {
    return '<div class="gb-teaser-row">' +
      identityHtml(row, false) +
      '<span class="gb-teaser-time">Ghi nhận ' + esc(timeText(row.first_hit_slot)) + "</span>" +
    "</div>";
  }

  function weekHtml(data) {
    var rows = Array.isArray(data.week_summary) ? data.week_summary : [];
    if (!rows.length) return "";
    var leader = rows[0];
    if (Number(leader.sessions_count || 0) < 2) {
      return '<section class="gb-section gb-week"><div class="gb-section-head"><div><span class="eyebrow">TUẦN NÀY</span><h2>Mã Vàng Tuần</h2></div></div><div class="gb-empty compact">Đang tích lũy thêm phiên để xếp hạng tuần.</div></section>';
    }
    return '<section class="gb-section gb-week">' +
      '<div class="gb-section-head"><div><span class="eyebrow">TUẦN NÀY</span><h2>🏆 Mã Vàng Tuần</h2><p>Xếp theo số phiên 4/4 → chuỗi liên tiếp → tổng lần 4/4 → RVOL30 trung bình.</p></div></div>' +
      '<div class="gb-week-leader">' +
        identityHtml(leader, true) +
        '<div class="gb-week-stats"><span><b>' + fmt(leader.sessions_count, 0) + '</b> phiên</span><span><b>' + fmt(leader.best_streak_hits, 0) + '</b> lần liên tiếp</span><span><b>' + fmt(leader.total_hits, 0) + '</b> lượt 4/4</span><span><b>' + pct(leader.avg_rvol30, 0).replace("+", "") + '</b> RVOL TB</span></div>' +
      "</div>" +
    "</section>";
  }

  function datesHtml(data) {
    var dates = Array.isArray(data.available_dates) ? data.available_dates : [];
    if (!dates.length) return "";
    return '<label class="gb-date-picker"><span>Phiên</span><select id="gb-date-select">' +
      dates.map(function (d) {
        var value = String(d || "");
        return '<option value="' + esc(value) + '"' + (value === String(data.trading_date || "") ? " selected" : "") + ">" + esc(dateText(value)) + "</option>";
      }).join("") +
    "</select></label>";
  }

  function memberMarketTeaserHtml(data, accessibleRows) {
    if (data.effective_full_market_access || Number(data.hidden_count || 0) <= 0) return "";
    var teaser = data.market_teaser && Array.isArray(data.market_teaser.teaser_rows)
      ? data.market_teaser.teaser_rows
      : [];
    var allowed = Object.create(null);
    (accessibleRows || []).forEach(function (row) {
      allowed[String(row.symbol || "").toUpperCase()] = true;
    });
    teaser = teaser.filter(function (row) {
      return !allowed[String(row.symbol || "").toUpperCase()];
    }).slice(0, 2);
    if (!teaser.length) return "";
    return '<section class="gb-section gb-member-teaser"><div class="gb-section-head"><div><span class="eyebrow">HÉ MỘT CHÚT TOÀN THỊ TRƯỜNG</span><h2>Bảng vàng ngoài danh sách của bạn</h2><p>Tối đa 2 mã thật, trễ ' + fmt((data.market_teaser && data.market_teaser.teaser_delay_minutes) || 20, 0) + ' phút.</p></div></div><div class="gb-teaser-list">' + teaser.map(teaserRowHtml).join("") + "</div></section>";
  }

  function fullPageHtml(payload) {
    var data = payload.data || {};
    var rows = Array.isArray(data.rows) ? data.rows : [];
    var marketTotal = Number(data.market_total || 0);
    var accessible = Number(data.accessible_total == null ? rows.length : data.accessible_total);
    var hidden = Number(data.hidden_count || 0);
    var still = rows.filter(function (row) { return row.still_4of4 === true || Number(row.latest_signal_count || 0) === 4; }).length;

    if (!payload.signedIn) {
      var teasers = Array.isArray(data.teaser_rows) ? data.teaser_rows : [];
      return '<div class="page-shell golden-board-page">' +
        '<header class="page-header gb-page-header"><div class="page-heading"><div><span class="eyebrow">CCC TECHNICAL INTELLIGENCE</span><h1>🏆 Bảng vàng</h1><p>Sổ ghi danh những mã đã được CCC ghi nhận đạt đủ 4/4 trong phiên.</p></div><div class="gb-date-static">Phiên ' + esc(dateText(data.trading_date)) + "</div></div></header>" +
        '<section class="gb-hero-grid"><div class="gb-stat"><span>Đã ghi danh</span><strong>' + fmt(marketTotal, 0) + '</strong><small>mã trong phiên</small></div><div class="gb-stat"><span>Quyền xem</span><strong>Teaser</strong><small>trễ ' + fmt(data.teaser_delay_minutes || 20, 0) + " phút</small></div></section>" +
        '<section class="gb-section"><div class="gb-section-head"><div><h2>Hé một chút Bảng vàng</h2><p>Hiển thị tối đa 2 mã thật đã qua thời gian trễ. Dữ liệu kỹ thuật đầy đủ thuộc phạm vi thành viên.</p></div></div>' +
          (teasers.length ? '<div class="gb-teaser-list">' + teasers.map(teaserRowHtml).join("") + "</div>" : '<div class="gb-empty">Chưa có mã teaser đủ thời gian trễ trong phiên này.</div>') +
          (marketTotal > teasers.length ? '<div class="gb-lock"><strong>🔒 Còn ' + fmt(Math.max(marketTotal - teasers.length, 0), 0) + ' mã khác</strong><span>Đăng nhập để xem theo quyền thành viên.</span><a href="' + ACCOUNT_PATH + '">Đăng nhập / Tài khoản</a></div>' : "") +
        "</section>" +
      "</div>";
    }

    return '<div class="page-shell golden-board-page">' +
      '<header class="page-header gb-page-header"><div class="page-heading"><div><span class="eyebrow">CCC TECHNICAL INTELLIGENCE</span><h1>🏆 Bảng vàng</h1><p>Mã đã từng được hệ thống ghi nhận đạt đủ 4/4 sẽ được giữ lại để xem lịch sử, kể cả khi sau đó tín hiệu giảm.</p></div>' + datesHtml(data) + "</div></header>" +
      '<section class="gb-hero-grid">' +
        '<div class="gb-stat"><span>Bảng vàng phiên</span><strong>' + fmt(marketTotal, 0) + '</strong><small>mã toàn thị trường</small></div>' +
        '<div class="gb-stat"><span>Trong quyền xem</span><strong>' + fmt(accessible, 0) + '</strong><small>' + (data.effective_full_market_access ? "toàn thị trường" : "theo danh sách cá nhân") + "</small></div>" +
        '<div class="gb-stat"><span>Đang giữ 4/4</span><strong>' + fmt(still, 0) + '</strong><small>theo lần quét cuối của phiên</small></div>' +
      "</section>" +
      (hidden > 0 ? '<div class="gb-scope-note"><strong>🔒 ' + fmt(hidden, 0) + ' mã ngoài phạm vi hiện tại</strong><span>Bảng vàng không mở đường tắt qua giới hạn kỹ thuật của gói.</span></div>' : "") +
      memberMarketTeaserHtml(data, rows) +
      weekHtml(data) +
      '<section class="gb-section"><div class="gb-section-head"><div><span class="eyebrow">PHIÊN ' + esc(dateText(data.trading_date)) + '</span><h2>Danh sách ghi nhận 4/4</h2><p>RVOL30 được lưu đúng theo số phiên nền tại thời điểm ghi nhận; không dùng số phiên nền để loại mã khỏi Bảng vàng.</p></div><strong class="gb-result-count">' + fmt(rows.length, 0) + " mã</strong></div>" +
        (rows.length ? '<div class="gb-list">' + rows.map(fullRowHtml).join("") + "</div>" : '<div class="gb-empty">Chưa có mã nào trong phạm vi của bạn được ghi nhận đạt 4/4 ở phiên này.</div>') +
      "</section>" +
    "</div>";
  }

  function overviewWidgetHtml(payload) {
    var data = payload.data || {};
    var rows;
    if (payload.signedIn) {
      rows = Array.isArray(data.rows) ? data.rows.slice(0, 3) : [];
      if (!data.effective_full_market_access && rows.length < 3 && data.market_teaser && Array.isArray(data.market_teaser.teaser_rows)) {
        var seen = Object.create(null);
        rows.forEach(function (row) { seen[String(row.symbol || "").toUpperCase()] = true; });
        data.market_teaser.teaser_rows.forEach(function (row) {
          var symbol = String(row.symbol || "").toUpperCase();
          if (rows.length < 3 && symbol && !seen[symbol]) {
            row.__teaser = true;
            rows.push(row);
            seen[symbol] = true;
          }
        });
      }
    } else {
      rows = Array.isArray(data.teaser_rows) ? data.teaser_rows : [];
    }
    var marketTotal = Number(data.market_total || 0);
    var hidden = payload.signedIn ? Number(data.hidden_count || 0) : Math.max(marketTotal - rows.length, 0);

    return '<section id="golden-board-overview" class="gb-overview-card">' +
      '<div class="gb-overview-head"><div><span class="eyebrow">TÍCH LŨY TRONG PHIÊN</span><h2>🏆 Bảng vàng hôm nay</h2><p>' + (marketTotal ? fmt(marketTotal, 0) + " mã đã được CCC ghi nhận đạt đủ 4/4." : "Chưa có mã nào được ghi nhận đạt đủ 4/4 trong phiên.") + '</p></div><a href="' + PATH + '" data-golden-board-nav="1">Xem Bảng vàng →</a></div>' +
      (rows.length ? '<div class="gb-overview-list">' + rows.map(function (row) {
        return '<div class="gb-overview-row">' + identityHtml(row, false) + '<span>' + (row.__teaser ? "Teaser trễ · " : "Ghi nhận ") + esc(timeText(row.first_hit_slot)) + "</span></div>";
      }).join("") + "</div>" : "") +
      (hidden > 0 ? '<div class="gb-overview-lock">🔒 Còn ' + fmt(hidden, 0) + " mã khác theo quyền truy cập.</div>" : "") +
    "</section>";
  }

  function bindGoldenLinks(root) {
    var scope = root || document;
    scope.querySelectorAll('a[data-golden-board-nav="1"]').forEach(function (link) {
      if (link.__gbBound) return;
      link.__gbBound = true;
      link.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopImmediatePropagation();
        location.href = PATH;
      });
    });
    scope.querySelectorAll('a.gb-identity[href^="/co-phieu/"]').forEach(function (link) {
      if (link.__gbStockBound) return;
      link.__gbStockBound = true;
      link.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopImmediatePropagation();
        location.href = link.getAttribute("href");
      });
    });
  }

  async function renderGoldenPage(force) {
    if (!isGoldenPath() || loading) return;
    var main = document.querySelector("main.wrap");
    if (!main) return;

    var key = currentDate || "latest";
    if (!force && lastLoadKey === key && lastData && main.querySelector(".golden-board-page")) return;

    loading = true;
    if (!main.querySelector(".golden-board-page")) {
      main.innerHTML = '<div class="page-shell golden-board-page"><div class="gb-loading">Đang tải Bảng vàng…</div></div>';
    }

    try {
      var payload = await loadGolden(currentDate);
      lastData = payload;
      lastLoadKey = key;
      currentDate = String(payload.data && payload.data.trading_date || currentDate || "");
      main.innerHTML = fullPageHtml(payload);
      bindGoldenLinks(main);
      var select = document.getElementById("gb-date-select");
      if (select) {
        select.addEventListener("change", function () {
          currentDate = String(select.value || "");
          lastLoadKey = "";
          renderGoldenPage(true);
        });
      }
    } catch (error) {
      main.innerHTML = '<div class="page-shell golden-board-page"><div class="gb-error"><strong>Không tải được Bảng vàng</strong><span>' + esc(error && error.message || "Lỗi dữ liệu") + '</span><button type="button" id="gb-retry">Thử lại</button></div></div>';
      var retry = document.getElementById("gb-retry");
      if (retry) retry.addEventListener("click", function () { renderGoldenPage(true); });
    } finally {
      loading = false;
    }
  }

  async function renderOverviewWidget(force) {
    if (isGoldenPath() || (location.pathname || "/") !== "/" || loading || overviewLoading) return;
    var target = document.querySelector("main.wrap .content-main") || document.querySelector("main.wrap .page-shell");
    if (!target) return;
    var existing = document.getElementById("golden-board-overview");
    if (existing && !force) return;

    overviewLoading = true;
    try {
      var payload = await loadGolden("");
      var html = overviewWidgetHtml(payload);
      existing = document.getElementById("golden-board-overview");
      if (existing) existing.outerHTML = html;
      else target.insertAdjacentHTML("afterbegin", html);
      bindGoldenLinks(target);
    } catch (_) {
      /* Overview remains fully usable if Golden Board teaser is temporarily unavailable. */
    } finally {
      overviewLoading = false;
    }
  }

  function ensureGoldenPageContainer() {
    if (!isGoldenPath()) return;
    document.title = "Bảng vàng | Chuyện Chợ Chứng";
    var main = document.querySelector("main.wrap");
    if (!main) return;
    if (!main.querySelector(".golden-board-page")) {
      lastLoadKey = "";
      renderGoldenPage(true);
    }
  }

  function tick() {
    ensureNavigation();
    renameFourSignalKpi();
    ensureGoldenPageContainer();
    if (!isGoldenPath()) renderOverviewWidget(false);
  }

  function start() {
    tick();
    if (bootTimer) clearInterval(bootTimer);
    bootTimer = setInterval(tick, 500);

    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(function () {
      if (isGoldenPath()) renderGoldenPage(true);
      else renderOverviewWidget(true);
    }, REFRESH_MS);

    window.addEventListener("popstate", function () {
      currentDate = "";
      lastLoadKey = "";
      setTimeout(tick, 0);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
