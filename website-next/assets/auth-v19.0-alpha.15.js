(function () {
  "use strict";

  var SUPABASE_URL = "https://wevtlkowpbmpdggcfbvn.supabase.co";
  var SUPABASE_KEY = "sb_publishable_qN__TQuoNBRUFhxuY5CtNw_88WZDdJw";
  var AUTH_ROOT_ID = "ccc-auth-root";
  var ACCOUNT_ROOT_ID = "ccc-account-page-root";
  var ACCOUNT_PATH = "/tai-khoan";

  var client = null;
  var lastFocused = null;
  var membershipBridgeScheduled = false;
  var membershipBridgeDispatching = false;
  var uiPolishScheduled = false;
  var refreshDeadlineMs = Date.now() + 5 * 60 * 1000;
  var refreshTimerId = null;
  var ma10BySymbol = {};
  var ma200BySymbol = {};
  var ma10CardDataLoading = false;
  var ma10CardDataLoaded = false;
  var snapshotUiMeta = { count: 0, latestUpdatedAt: "", tradingDate: "", timeSlot: "" };
  var state = {
    open: false,
    busy: false,
    authReady: false,
    session: null,
    user: null,
    profile: null,
    subscription: null,
    plan: null,
    planCatalog: [],
    previewPlanCode: "",
    membershipLoading: false,
    membershipLoadedFor: "",
    membershipError: "",
    profileSaving: false,
    profileSaveError: "",
    profileSaveSuccess: "",
    error: "",
    notice: "",
    fatal: ""
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function isAccountRoute() {
    return window.location.pathname === ACCOUNT_PATH;
  }

  function isSetupRoute() {
    return isAccountRoute() && new URLSearchParams(window.location.search).get("setup") === "1";
  }

  function authRoot() {
    var node = document.getElementById(AUTH_ROOT_ID);
    if (!node) {
      node = document.createElement("div");
      node.id = AUTH_ROOT_ID;
      document.body.appendChild(node);
    }
    return node;
  }

  function accountRoot() {
    var node = document.getElementById(ACCOUNT_ROOT_ID);
    if (!node) {
      node = document.createElement("div");
      node.id = ACCOUNT_ROOT_ID;
      document.body.appendChild(node);
    }
    return node;
  }

  function providerLabel(user) {
    if (!user) return "";
    var appMeta = user.app_metadata || {};
    var provider = String(appMeta.provider || "email").toLowerCase();
    if (provider === "google") return "Google";
    return "Email & mật khẩu";
  }

  function userLabel(user) {
    if (!user) return "Tài khoản";
    if (state.profile && state.profile.display_name) return state.profile.display_name;
    var meta = user.user_metadata || {};
    return meta.full_name || meta.name || user.email || "Tài khoản";
  }

  function userInitial(user) {
    var label = userLabel(user).trim();
    return label ? label.charAt(0).toUpperCase() : "U";
  }

  function formatDate(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "—";
    return date.toLocaleDateString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric"
    });
  }

  function scopeLabel(plan) {
    if (!plan) return "—";
    if (plan.full_market_access) return "Toàn thị trường";
    return plan.view_limit == null ? "—" : plan.view_limit + " mã";
  }

  function watchlistLimitLabel(plan) {
    if (!plan) return "—";
    if (plan.full_market_access && plan.watchlist_limit == null) return "Không dùng để giới hạn kỹ thuật";
    return plan.watchlist_limit == null ? "—" : plan.watchlist_limit + " mã";
  }

  function remainingLabel(plan, subscription) {
    if (!plan || !subscription) return "—";
    if (plan.change_limit == null) return "Không giới hạn";
    var used = Number(subscription.change_used || 0);
    var limit = Number(plan.change_limit || 0);
    return Math.max(0, limit - used) + "/" + limit;
  }

  function alertLabel(plan) {
    if (!plan) return "—";
    if (plan.email_alerts && plan.telegram_alerts) return "Email + Telegram";
    if (plan.email_alerts) return "Email";
    if (plan.telegram_alerts) return "Telegram";
    return "Chưa bao gồm";
  }

  function formatPriceVnd(value) {
    var amount = Number(value || 0);
    if (!Number.isFinite(amount) || amount <= 0) return "0đ";
    return amount.toLocaleString("vi-VN") + "đ/tháng";
  }

  function patchRealMembershipLabels() {
    if (!state.user || !state.plan || !state.subscription) return;

    document.body.classList.add("ccc-real-membership");

    var select = document.getElementById("mock-plan-select");
    if (select) {
      var desired = String(state.plan.plan_code || "FREE");
      var hasOption = Array.prototype.some.call(select.options || [], function (option) {
        return option.value === desired;
      });

      if (hasOption && select.value !== desired && !membershipBridgeDispatching) {
        membershipBridgeDispatching = true;
        select.value = desired;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        setTimeout(function () { membershipBridgeDispatching = false; }, 0);
        return;
      }

      var wrapper = select.closest("label");
      if (wrapper) wrapper.remove();
    }

    document.querySelectorAll(".mock-plan-control").forEach(function (control) {
      control.remove();
    });

    document.querySelectorAll(".plan-scope-card").forEach(function (card) {
      card.remove();
    });

    document.querySelectorAll(".page-heading-meta").forEach(function (meta) {
      var selectorLabel = meta.querySelector("label");
      if (selectorLabel && selectorLabel.querySelector("#mock-plan-select")) selectorLabel.remove();

      var chip = meta.querySelector(".ccc-real-plan-chip");
      if (!chip) {
        chip = document.createElement("span");
        chip.className = "ccc-real-plan-chip";
        meta.appendChild(chip);
      }
      chip.textContent = state.plan.plan_code + " · " + scopeLabel(state.plan);
    });

    document.querySelectorAll(".plan-scope-card .rail-kv > div").forEach(function (row) {
      var dt = row.querySelector("dt");
      var dd = row.querySelector("dd");
      if (!dt || !dd) return;
      var label = String(dt.textContent || "").trim();

      if (label === "Giá gói") dd.textContent = formatPriceVnd(state.plan.price_vnd);
      else if (label === "Phạm vi kỹ thuật") dd.textContent = scopeLabel(state.plan);
      else if (label === "Watchlist capacity") {
        dd.textContent = state.plan.watchlist_limit == null ? "Theo gói hiện tại" : state.plan.watchlist_limit + " mã";
      } else if (label === "Quota thay đổi") {
        dd.textContent = remainingLabel(state.plan, state.subscription);
      } else if (label === "Email / Telegram") {
        dd.textContent = state.plan.email_alerts && state.plan.telegram_alerts ? "Có" : "Không";
      }
    });

    document.querySelectorAll(".scanner-head-stats > div, .capacity-values > div").forEach(function (box) {
      var small = box.querySelector("small");
      var strong = box.querySelector("strong");
      if (!small || !strong) return;
      var label = String(small.textContent || "").trim();

      if (label === "Gói") strong.textContent = state.plan.display_name || state.plan.plan_code;
      else if (label === "Quyền xem hiện tại") strong.textContent = scopeLabel(state.plan);
      else if (label === "Lượt đổi còn lại") strong.textContent = remainingLabel(state.plan, state.subscription);
    });

    document.querySelectorAll(".staging-badge").forEach(function (badge) {
      if (/STAGING/.test(badge.textContent || "")) {
        badge.textContent = "GÓI " + state.plan.plan_code;
      }
    });
  }

  function scheduleRealMembershipBridge() {
    if (membershipBridgeScheduled) return;
    membershipBridgeScheduled = true;
    requestAnimationFrame(function () {
      membershipBridgeScheduled = false;
      patchAccountButtons();
      patchRealMembershipLabels();
    });
  }

  function planHeaderLabel() {
    if (!state.user) return "Email / Google";
    if (state.membershipLoading) return "Đang tải gói…";
    if (state.plan) return state.plan.plan_code + " · " + scopeLabel(state.plan);
    return "Đã đăng nhập";
  }

  function exactText(root, selector, from, to) {
    if (!root) return;
    root.querySelectorAll(selector).forEach(function (node) {
      if (String(node.textContent || "").trim() === from) node.textContent = to;
    });
  }

  function hidePreviousSeparator(node) {
    if (!node) return;
    var prev = node.previousElementSibling;
    if (prev && String(prev.textContent || "").trim() === "·") prev.style.display = "none";
  }

  function ensureRefreshIndicator() {
    var trust = document.getElementById("data-trust");
    if (!trust) return;

    var indicator = document.getElementById("ccc-refresh-indicator");
    if (!indicator) {
      var sep = document.createElement("span");
      sep.className = "trust-separator ccc-refresh-separator";
      sep.setAttribute("aria-hidden", "true");
      sep.textContent = "·";

      indicator = document.createElement("span");
      indicator.id = "ccc-refresh-indicator";
      indicator.className = "ccc-refresh-indicator";
      indicator.title = "Tự động kiểm tra dữ liệu mỗi 5 phút";
      indicator.innerHTML = 'Làm mới <b id="ccc-refresh-countdown">05:00</b>';

      var trustTime = document.getElementById("trust-time");
      if (trustTime && trustTime.parentNode === trust) {
        trustTime.insertAdjacentElement("afterend", sep);
        sep.insertAdjacentElement("afterend", indicator);
      } else {
        trust.appendChild(sep);
        trust.appendChild(indicator);
      }
    }
  }

  function updateRefreshCountdown() {
    var remaining = Math.max(0, refreshDeadlineMs - Date.now());
    var totalSeconds = Math.ceil(remaining / 1000);
    var mm = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
    var ss = String(totalSeconds % 60).padStart(2, "0");

    document.querySelectorAll("#ccc-refresh-countdown,#ccc-mobile-refresh-countdown").forEach(function (node) {
      node.textContent = mm + ":" + ss;
    });

    if (remaining <= 0) {
      refreshDeadlineMs = Date.now() + 5 * 60 * 1000;
      var refreshButton = document.getElementById("refresh-btn");
      if (refreshButton && !refreshButton.disabled) refreshButton.click();
    }
  }

  function ensureMobileRefreshIndicator() {
    patchMobileHeader433();
  }

  function formatSignedPctOne(value) {
    var n = Number(value);
    if (!Number.isFinite(n)) return "—";
    var text = Math.abs(n).toLocaleString("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    return (n > 0 ? "+" : n < 0 ? "-" : "") + text + "%";
  }

  async function loadMa10CardData() {
    if (ma10CardDataLoaded || ma10CardDataLoading) return;
    ma10CardDataLoading = true;
    try {
      var response = await fetch(
        SUPABASE_URL + "/rest/v1/stock_snapshot?select=symbol,ma10_distance_pct,ma200_distance_pct,updated_at,trading_date,time_slot&order=symbol.asc&limit=1000",
        {
          method: "GET",
          cache: "no-store",
          headers: {
            "apikey": SUPABASE_KEY,
            "Accept": "application/json"
          }
        }
      );
      if (!response.ok) throw new Error("HTTP " + response.status);
      var rows = await response.json();
      if (Array.isArray(rows)) {
        var latestMs = 0;
        var latestRow = null;
        rows.forEach(function (row) {
          var symbol = String(row && row.symbol || "").trim().toUpperCase();
          if (symbol) {
            var ma10Value = Number(row.ma10_distance_pct);
            var ma200Value = Number(row.ma200_distance_pct);
            ma10BySymbol[symbol] = Number.isFinite(ma10Value) ? ma10Value : null;
            ma200BySymbol[symbol] = Number.isFinite(ma200Value) ? ma200Value : null;
          }
          var updatedMs = Date.parse(row && row.updated_at || "");
          if (Number.isFinite(updatedMs) && updatedMs >= latestMs) {
            latestMs = updatedMs;
            latestRow = row;
          }
        });
        snapshotUiMeta.count = rows.length;
        snapshotUiMeta.latestUpdatedAt = latestRow && latestRow.updated_at ? String(latestRow.updated_at) : "";
        snapshotUiMeta.tradingDate = latestRow && latestRow.trading_date ? String(latestRow.trading_date) : "";
        snapshotUiMeta.timeSlot = latestRow && latestRow.time_slot ? String(latestRow.time_slot) : "";
        ma10CardDataLoaded = true;
      }
    } catch (_) {
      ma10CardDataLoaded = false;
    } finally {
      ma10CardDataLoading = false;
      scheduleUiPolish();
    }
  }

  function valueTone(value) {
    var n = Number(value);
    return Number.isFinite(n) ? (n > 0 ? "positive" : n < 0 ? "negative" : "neutral") : "neutral";
  }

  function patchMobileMa10Cards() {
    var cards = document.querySelectorAll(".universal-stock-card[data-symbol]");
    if (!cards.length) return;

    if (!ma10CardDataLoaded) {
      loadMa10CardData();
      return;
    }

    cards.forEach(function (card) {
      var symbol = String(card.getAttribute("data-symbol") || "").trim().toUpperCase();
      var ma10Value = Object.prototype.hasOwnProperty.call(ma10BySymbol, symbol) ? ma10BySymbol[symbol] : null;
      var ma200Value = Object.prototype.hasOwnProperty.call(ma200BySymbol, symbol) ? ma200BySymbol[symbol] : null;

      var trend = card.querySelector(".stock-row-highlight-line.highlight-trend");
      if (trend) {
        trend.classList.remove("positive", "negative", "neutral");
        trend.classList.add(valueTone(ma200Value));
        var trendStrong = trend.querySelector("strong");
        if (trendStrong && Number.isFinite(Number(ma200Value))) {
          trendStrong.textContent = formatSignedPctOne(ma200Value);
        }
      }

      var cccRow = card.querySelector(".stock-row-ccc");
      if (!cccRow) return;
      var node = cccRow.querySelector(".ccc-card-ma10");
      if (!node) {
        node = document.createElement("div");
        node.className = "ccc-card-ma10";
        cccRow.appendChild(node);
      }
      node.className = "ccc-card-ma10 " + valueTone(ma10Value);
      node.innerHTML = '<span>MA10</span><strong>' + esc(formatSignedPctOne(ma10Value)) + '</strong>';
    });
  }

  function patchMarketPulsePresentation() {
    exactText(document, ".market-pulse h2,.market-pulse h3,.market-pulse-rail h2,.market-pulse-rail h3", "Market Pulse", "Toàn cảnh thị trường");

    document.querySelectorAll(".market-live-change").forEach(function (node) {
      if (node.getAttribute("data-ccc-split") === "1") return;

      var basis = node.querySelector(".market-change-basis");
      var basisText = basis ? String(basis.textContent || "").trim() : "";
      if (basis) basis.remove();

      var raw = String(node.textContent || "").trim();
      var parts = raw.split("·").map(function (part) { return part.trim(); }).filter(Boolean);
      if (parts.length < 2) {
        if (basisText) {
          var small = document.createElement("small");
          small.className = "market-change-basis";
          small.textContent = basisText;
          node.appendChild(small);
        }
        return;
      }

      node.innerHTML =
        '<span class="ccc-market-change-value">' + esc(parts[0]) + '</span>' +
        '<span class="ccc-market-change-pct">' + esc(parts.slice(1).join(" · ")) +
          (basisText ? '<small class="market-change-basis">' + esc(basisText) + '</small>' : '') +
        '</span>';
      node.setAttribute("data-ccc-split", "1");
    });
  }

  function patchMobileHeader433() {
    var statusRow = document.getElementById("mobile-status-row");
    if (!statusRow) return;
    var primary = statusRow.querySelector(".mobile-status-primary");
    if (!primary) return;

    var now = primary.querySelector("#mobile-now");
    if (now) now.remove();

    var secondary = statusRow.querySelector(".mobile-status-secondary");
    if (secondary) secondary.remove();

    var refresh = primary.querySelector(".ccc-mobile-refresh-indicator");
    if (!refresh) {
      refresh = document.createElement("span");
      refresh.className = "ccc-mobile-refresh-indicator";
      refresh.title = "Tự động kiểm tra dữ liệu mỗi 5 phút";
      refresh.innerHTML = 'Làm mới <b id="ccc-mobile-refresh-countdown">05:00</b>';
      primary.appendChild(refresh);
    }
  }

  function updateStickyHeaderOffset() {
    if (!isAccountRoute()) {
      document.body.style.removeProperty("--ccc-sticky-header-height");
      return;
    }
    var header = document.querySelector(".app-header");
    if (!header) return;
    var height = Math.ceil(header.getBoundingClientRect().height || 0);
    if (height > 0) document.body.style.setProperty("--ccc-sticky-header-height", height + "px");
  }

  function snapshotUpdatedText() {
    var value = snapshotUiMeta.latestUpdatedAt;
    var date = new Date(value || "");
    if (!Number.isFinite(date.getTime())) return "Đang cập nhật…";
    var parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Ho_Chi_Minh",
      day: "2-digit", month: "2-digit", year: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      hour12: false
    }).formatToParts(date).reduce(function (acc, part) {
      acc[part.type] = part.value;
      return acc;
    }, {});
    return parts.hour + ":" + parts.minute + ":" + parts.second + " - " + parts.day + "/" + parts.month + "/" + parts.year;
  }

  function sourceDataCardInnerHtml() {
    var count = snapshotUiMeta.count || 0;
    return '<header><h3>Nguồn Dữ liệu</h3></header>' +
      '<div class="rail-card-body"><dl class="rail-kv ccc-source-kv">' +
        '<div><dt>Cập nhật lần cuối</dt><dd>' + esc(snapshotUpdatedText()) + '</dd></div>' +
        '<div><dt>Tổng mã quét</dt><dd>' + esc(count ? count + "" : "—") + '</dd></div>' +
        '<div><dt>Nguồn dữ liệu</dt><dd>Chuyện Chợ Chứng</dd></div>' +
      '</dl><p class="rail-note ccc-source-note"><span>Tín hiệu CCC được tính trên dữ liệu thực tế của thị trường, không dự đoán giá.</span></p></div>';
  }

  function updateSourceDataCard(card) {
    if (!card) return;
    card.classList.add("data-trust-card", "ccc-source-data-card");
    var signature = snapshotUpdatedText() + "|" + (snapshotUiMeta.count || 0);
    if (card.getAttribute("data-ccc-source-signature") === signature) return;
    card.innerHTML = sourceDataCardInnerHtml();
    card.setAttribute("data-ccc-source-signature", signature);
  }

  function newSourceDataCard() {
    var card = document.createElement("section");
    card.className = "rail-card data-trust-card ccc-source-data-card";
    updateSourceDataCard(card);
    return card;
  }

  function researchContextCard(main) {
    var card = document.createElement("section");
    card.className = "rail-card ccc-research-context-card";
    var title = main && main.querySelector(".page-intro h1") ? String(main.querySelector(".page-intro h1").textContent || "Nghiên cứu").trim() : "Nghiên cứu";
    var detail = "Dữ liệu cơ bản công khai";
    if (/ngành/i.test(title)) {
      var selected = main.querySelector(".industry-chip.active span");
      if (selected) detail = "Ngành đang xem: " + String(selected.textContent || "").trim();
    } else {
      var result = main.querySelector(".result-info strong");
      if (result) detail = "Đang hiển thị " + String(result.textContent || "").trim() + " mã";
    }
    card.innerHTML = '<header><h3>Ngữ cảnh nghiên cứu</h3></header><div class="rail-card-body"><p class="ccc-research-context-copy">' + esc(detail) + '</p><p class="rail-note"><span>Điểm số hỗ trợ sàng lọc và so sánh, không phải khuyến nghị mua/bán.</span></p></div>';
    return card;
  }

  function ensureResearchRightRail() {
    var main = document.querySelector("main.fund-main");
    if (!main) return;
    var grid = main.querySelector(":scope > .content-grid");
    if (!grid) return;
    var rail = grid.querySelector(":scope > .context-rail");
    if (!rail) {
      rail = document.createElement("aside");
      rail.className = "context-rail ccc-unified-rail";
      grid.appendChild(rail);
      grid.classList.add("has-context-rail");
      main.classList.add("has-context-rail");
    }
    if (!rail.querySelector(".ccc-research-context-card")) rail.appendChild(researchContextCard(main));
    if (!rail.querySelector(".data-trust-card")) rail.appendChild(newSourceDataCard());
  }

  function ensureAccountSourceCard() {
    if (!isAccountRoute()) return;
    var side = document.querySelector(".ccc-account-side");
    if (!side) return;
    if (!side.querySelector(".data-trust-card")) side.appendChild(newSourceDataCard());
  }

  function patchAllSourceDataCards() {
    document.querySelectorAll(".data-trust-card").forEach(updateSourceDataCard);
  }

  function patchHeader434() {
    var headerNow = document.getElementById("header-now");
    if (headerNow) headerNow.style.display = "none";
    var trustTime = document.getElementById("trust-time");
    if (trustTime) trustTime.style.display = "none";
    var trustCount = document.getElementById("trust-count");
    if (trustCount) trustCount.style.display = "none";
    patchMobileHeader433();
  }

  function patchScanner434() {
    var scanner = document.querySelector("main.lovable-scanner");
    if (!scanner) return;
    var eyebrow = scanner.querySelector(".page-heading .eyebrow");
    if (eyebrow && /CCC TECHNICAL INTELLIGENCE/i.test(String(eyebrow.textContent || ""))) eyebrow.remove();
  }

  function patchOverview434() {
    var overview = document.querySelector("main.lovable-overview");
    if (!overview) return;
    var active = overview.querySelector(".overview-density-trigger.active");
    var key = active ? String(active.getAttribute("data-overview-group") || "") : "";
    overview.querySelectorAll(".overview-density-trigger").forEach(function (tile) {
      var tileKey = String(tile.getAttribute("data-overview-group") || "");
      tile.setAttribute("data-ccc-tone", tileKey === "4of4" ? "green" : tileKey === "3plus" ? "blue" : tileKey === "2plus" ? "slate" : "purple");
    });
    var results = document.getElementById("overview-results");
    if (results && key) results.setAttribute("data-ccc-group", key);
  }

  function patchUiPolish() {
    document.body.classList.add("ccc-ui-polish", "ccc-ui-434");

    if (!ma10CardDataLoaded && !ma10CardDataLoading) loadMa10CardData();
    patchMarketPulsePresentation();
    patchMobileHeader433();
    patchMobileMa10Cards();
    patchHeader434();
    patchScanner434();
    patchOverview434();
    ensureResearchRightRail();
    ensureAccountSourceCard();
    patchAllSourceDataCards();
    updateStickyHeaderOffset();

    var overview = document.querySelector(".lovable-overview");
    if (overview) {
      var heading = overview.querySelector(".page-heading");
      if (heading) {
        var eyebrow = heading.querySelector(".eyebrow");
        if (eyebrow && /MARKET INTELLIGENCE/i.test(eyebrow.textContent || "")) eyebrow.remove();

        var subtitle = heading.querySelector("h1 + p");
        if (subtitle) subtitle.textContent = "Theo dõi thị trường, tín hiệu nổi bật và dòng tiền trong phạm vi của bạn.";

        heading.querySelectorAll(".page-heading-meta > span").forEach(function (node) {
          if (/^Scanner\s*·/i.test(String(node.textContent || "").trim())) node.remove();
        });
      }
    }

    document.querySelectorAll(".page-heading-meta > span").forEach(function (node) {
      if (/^Scanner\s*·/i.test(String(node.textContent || "").trim())) node.remove();
    });

    exactText(document, ".signal-legend-card h3,.detail-panel h3", "CCC Signal Rail", "Tín hiệu CCC");
    document.querySelectorAll(".detail-notice span").forEach(function (node) {
      if ((node.innerHTML || "").indexOf("CCC Signal Rail") >= 0) {
        node.innerHTML = node.innerHTML.replace(/CCC Signal Rail/g, "Tín hiệu CCC");
      }
    });

    var trustCount = document.getElementById("trust-count");
    if (trustCount) {
      hidePreviousSeparator(trustCount);
      trustCount.style.display = "none";
    }

    var mobileUniverse = document.getElementById("mobile-universe-count");
    if (mobileUniverse) {
      hidePreviousSeparator(mobileUniverse);
      mobileUniverse.style.display = "none";
    }

    var trust = document.getElementById("data-trust");
    var trustStatus = document.getElementById("trust-status");
    var trustTime = document.getElementById("trust-time");
    if (trust && trustTime) {
      var status = trustStatus ? String(trustStatus.textContent || "").trim() : "Đang kiểm tra";
      var timeText = String(trustTime.textContent || "").trim() || "Dữ liệu —";
      var tooltip = timeText + " · Trạng thái: " + status + " · Nguồn: Chuyện Chợ Chứng";
      trust.title = tooltip;
      trustTime.title = tooltip;
    }

    ensureRefreshIndicator();
    ensureMobileRefreshIndicator();
    updateRefreshCountdown();
  }

  function scheduleUiPolish() {
    if (uiPolishScheduled) return;
    uiPolishScheduled = true;
    requestAnimationFrame(function () {
      uiPolishScheduled = false;
      patchUiPolish();
    });
  }

  function startRefreshTimer() {
    if (refreshTimerId) return;
    refreshTimerId = window.setInterval(updateRefreshCountdown, 1000);
    document.addEventListener("click", function (event) {
      var button = event.target && event.target.closest ? event.target.closest("#refresh-btn") : null;
      if (!button) return;
      refreshDeadlineMs = Date.now() + 5 * 60 * 1000;
      updateRefreshCountdown();
    }, true);
  }

  function clearMembership() {
    state.profile = null;
    state.subscription = null;
    state.plan = null;
    state.planCatalog = [];
    state.previewPlanCode = "";
    state.membershipLoading = false;
    state.membershipLoadedFor = "";
    state.membershipError = "";
    state.profileSaveError = "";
    state.profileSaveSuccess = "";
  }

  function patchAccountButtons() {
    var loggedIn = !!state.user;
    var headerButton = document.getElementById("account-open");
    if (headerButton) {
      var strong = headerButton.querySelector("strong");
      var small = headerButton.querySelector("small");
      var strongText = loggedIn ? userLabel(state.user) : "Đăng nhập";
      if (strong && strong.textContent !== strongText) strong.textContent = strongText;
      if (small) small.textContent = "";
      headerButton.setAttribute("aria-label", loggedIn ? "Mở trang tài khoản" : "Đăng nhập Chuyện Chợ Chứng");
      headerButton.setAttribute("title", loggedIn ? userLabel(state.user) : "Đăng nhập");
    }

    var desktopButton = document.getElementById("desktop-account-open");
    if (desktopButton) {
      var navLabel = desktopButton.querySelector(".nav-label");
      var navSmall = desktopButton.querySelector("small");
      var navText = loggedIn ? "Tài khoản" : "Đăng nhập";
      if (navLabel && navLabel.textContent !== navText) navLabel.textContent = navText;
      if (navSmall && navSmall.textContent !== navText) navSmall.textContent = navText;
      desktopButton.setAttribute("aria-label", loggedIn ? "Mở trang tài khoản" : "Đăng nhập Chuyện Chợ Chứng");
      desktopButton.classList.toggle("active", isAccountRoute());
      if (isAccountRoute()) desktopButton.setAttribute("aria-current", "page");
      else desktopButton.removeAttribute("aria-current");
    }
  }

  async function loadMembership(renderAfter) {
    if (!client || !state.user || state.membershipLoading) return;

    var userId = state.user.id;
    state.membershipLoading = true;
    state.membershipError = "";
    patchAccountButtons();
    if (renderAfter) {
      if (state.open) renderAuthDialog();
      if (isAccountRoute()) renderAccountPage();
    }

    try {
      var profileResult = await client
        .from("profiles")
        .select("id,display_name,avatar_url,role,status,phone,address,profile_completed,profile_completed_at")
        .eq("id", userId)
        .maybeSingle();

      if (profileResult.error) throw profileResult.error;

      var subscriptionResult = await client
        .from("subscriptions")
        .select("id,user_id,plan_id,status,cycle_start,cycle_end,change_used,initial_setup_completed,upgrade_free_additions_remaining,created_at")
        .eq("user_id", userId)
        .in("status", ["ACTIVE", "SUSPENDED"])
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle();

      if (subscriptionResult.error) throw subscriptionResult.error;

      var plan = null;
      if (subscriptionResult.data && subscriptionResult.data.plan_id != null) {
        var planResult = await client
          .from("plans")
          .select("id,plan_code,display_name,price_vnd,view_limit,watchlist_limit,change_limit,full_market_access,email_alerts,telegram_alerts,is_recommended,is_active")
          .eq("id", subscriptionResult.data.plan_id)
          .maybeSingle();

        if (planResult.error) throw planResult.error;
        plan = planResult.data || null;
      }

      var catalogResult = await client
        .from("plans")
        .select("id,plan_code,display_name,price_vnd,view_limit,watchlist_limit,change_limit,full_market_access,email_alerts,telegram_alerts,is_recommended,is_active")
        .eq("is_active", true)
        .order("price_vnd", { ascending: true });

      if (catalogResult.error) throw catalogResult.error;

      if (!state.user || state.user.id !== userId) return;

      state.profile = profileResult.data || null;
      state.subscription = subscriptionResult.data || null;
      state.plan = plan;
      state.planCatalog = Array.isArray(catalogResult.data) ? catalogResult.data : [];
      if (state.plan && String(state.previewPlanCode || "") === String(state.plan.plan_code || "")) {
        state.previewPlanCode = "";
      }
      state.membershipLoadedFor = userId;
      scheduleRealMembershipBridge();

      if (!state.subscription || !state.plan) {
        state.membershipError = "Không tìm thấy gói thành viên đang hoạt động. Vui lòng liên hệ quản trị viên.";
      }
    } catch (error) {
      if (!state.user || state.user.id !== userId) return;
      state.membershipError = "Không tải được hồ sơ hoặc gói thành viên. Vui lòng thử lại.";
      console.error("CCC membership load failed", error);
    } finally {
      if (state.user && state.user.id === userId) {
        state.membershipLoading = false;
        patchAccountButtons();
        scheduleRealMembershipBridge();
        if (renderAfter) {
          if (state.open) renderAuthDialog();
          if (isAccountRoute()) renderAccountPage();
        }
      }
    }
  }

  function membershipMiniHtml() {
    if (state.membershipLoading) {
      return '<section class="ccc-auth-membership-loading" role="status">' +
        '<span class="ccc-auth-spinner" aria-hidden="true"></span>' +
        '<div><strong>Đang tải gói thành viên…</strong><p>Đang đọc dữ liệu từ Supabase.</p></div>' +
      '</section>';
    }

    if (state.membershipError) {
      return '<div class="ccc-auth-feedback error embedded" role="alert">' + esc(state.membershipError) + '</div>';
    }

    if (!state.plan || !state.subscription) return "";

    return '' +
      '<section class="ccc-auth-membership">' +
        '<div class="ccc-auth-plan-head">' +
          '<div><span>Gói hiện tại</span><strong>' + esc(state.plan.display_name || state.plan.plan_code) + '</strong></div>' +
          '<span class="ccc-auth-plan-code">' + esc(state.plan.plan_code) + '</span>' +
        '</div>' +
        '<dl class="ccc-auth-membership-grid">' +
          '<div><dt>Phạm vi CCC kỹ thuật</dt><dd>' + esc(scopeLabel(state.plan)) + '</dd></div>' +
          '<div><dt>Lượt đổi còn lại</dt><dd>' + esc(remainingLabel(state.plan, state.subscription)) + '</dd></div>' +
        '</dl>' +
      '</section>';
  }

  function renderAuthDialog() {
    var node = authRoot();
    patchAccountButtons();

    if (!state.open) {
      node.innerHTML = "";
      document.body.classList.remove("ccc-auth-open");
      return;
    }

    document.body.classList.add("ccc-auth-open");

    var feedback = "";
    if (state.fatal) feedback = '<div class="ccc-auth-feedback error" role="alert">' + esc(state.fatal) + "</div>";
    else if (state.error) feedback = '<div class="ccc-auth-feedback error" role="alert">' + esc(state.error) + "</div>";
    else if (state.notice) feedback = '<div class="ccc-auth-feedback success" role="status">' + esc(state.notice) + "</div>";

    var content;
    if (state.user) {
      content = '' +
        '<section class="ccc-auth-account" aria-label="Tài khoản hiện tại">' +
          '<div class="ccc-auth-user-row">' +
            '<span class="ccc-auth-user-avatar" aria-hidden="true">' + esc(userInitial(state.user)) + '</span>' +
            '<div><strong>' + esc(userLabel(state.user)) + '</strong><p>' + esc(state.user.email || "") + '</p></div>' +
          '</div>' +
          membershipMiniHtml() +
          '<a class="ccc-auth-button primary link-button" href="/tai-khoan">Mở trang Tài khoản</a>' +
          '<button id="ccc-auth-logout" class="ccc-auth-button secondary danger" type="button"' + (state.busy ? ' disabled' : '') + '>Đăng xuất</button>' +
        '</section>';
    } else {
      content = '' +
        '<button id="ccc-auth-google" class="ccc-auth-google" type="button"' + (state.busy || state.fatal ? ' disabled' : '') + '>' +
          '<span class="ccc-auth-google-mark" aria-hidden="true">G</span><span>Tiếp tục với Google</span>' +
        '</button>' +
        '<div class="ccc-auth-divider"><span>hoặc đăng nhập bằng email</span></div>' +
        '<form id="ccc-auth-email-form" class="ccc-auth-form" novalidate>' +
          '<label for="ccc-auth-email">Email</label>' +
          '<input id="ccc-auth-email" name="email" type="email" autocomplete="email" inputmode="email" placeholder="tenban@example.com" required' + (state.busy || state.fatal ? ' disabled' : '') + '>' +
          '<label for="ccc-auth-password">Mật khẩu</label>' +
          '<input id="ccc-auth-password" name="password" type="password" autocomplete="current-password" minlength="8" placeholder="Tối thiểu 8 ký tự" required' + (state.busy || state.fatal ? ' disabled' : '') + '>' +
          '<button class="ccc-auth-button primary" type="submit"' + (state.busy || state.fatal ? ' disabled' : '') + '>' + (state.busy ? 'Đang xử lý…' : 'Đăng nhập') + '</button>' +
        '</form>' +
        '<p class="ccc-auth-stage-note">Đăng nhập Google hoặc dùng tài khoản Email đã được tạo trên hệ thống.</p>';
    }

    node.innerHTML = '' +
      '<div class="ccc-auth-overlay">' +
        '<section class="ccc-auth-dialog" role="dialog" aria-modal="true" aria-labelledby="ccc-auth-title">' +
          '<header class="ccc-auth-head">' +
            '<div><span class="eyebrow">CCC ACCOUNT</span><h2 id="ccc-auth-title">' + (state.user ? 'Tài khoản của bạn' : 'Đăng nhập') + '</h2><p>' + (state.user ? 'Bạn đã đăng nhập. Quản lý hồ sơ đầy đủ tại trang Tài khoản.' : 'Đăng nhập để sử dụng phạm vi cá nhân của Chuyện Chợ Chứng.') + '</p></div>' +
            '<button id="ccc-auth-close" class="ccc-auth-close" type="button" aria-label="Đóng cửa sổ đăng nhập">×</button>' +
          '</header>' +
          feedback +
          '<div class="ccc-auth-body">' + content + '</div>' +
        '</section>' +
      '</div>';

    bindAuthDialog();
  }

  function accountLoadingHtml() {
    return '<main class="wrap ccc-account-page" id="main-content">' +
      '<section class="ccc-account-loading"><span class="ccc-auth-spinner" aria-hidden="true"></span><div><strong>Đang tải tài khoản…</strong><p>Đang đọc hồ sơ và gói thành viên từ Supabase.</p></div></section>' +
    '</main>';
  }

  function accountLoggedOutHtml() {
    return '<main class="wrap ccc-account-page" id="main-content">' +
      '<header class="ccc-account-heading"><div><h1>Tài khoản</h1><p>Đăng nhập để quản lý hồ sơ, gói thành viên và thiết lập cá nhân.</p></div></header>' +
      '<section class="ccc-account-empty"><div class="ccc-account-empty-icon">C</div><h2>Bạn chưa đăng nhập</h2><p>Đăng nhập bằng Google hoặc Email để mở trang tài khoản của bạn.</p><button id="ccc-account-login" class="ccc-account-primary" type="button">Đăng nhập</button></section>' +
    '</main>';
  }

  function profileFormHtml() {
    var profile = state.profile || {};
    var meta = state.user && state.user.user_metadata ? state.user.user_metadata : {};
    var displayName = profile.display_name || meta.full_name || meta.name || "";
    var phone = profile.phone || "";
    var address = profile.address || "";
    var completed = !!profile.profile_completed;
    var setupMode = isSetupRoute() || !completed;

    var message = "";
    if (state.profileSaveError) message = '<div class="ccc-account-form-message error" role="alert">' + esc(state.profileSaveError) + '</div>';
    else if (state.profileSaveSuccess) message = '<div class="ccc-account-form-message success" role="status">' + esc(state.profileSaveSuccess) + '</div>';

    return '<section class="ccc-account-card profile ' + (setupMode ? 'setup-required' : '') + '">' +
      '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">' + (setupMode ? 'THIẾT LẬP LẦN ĐẦU' : 'HỒ SƠ CÁ NHÂN') + '</span><h2>' + (setupMode ? 'Hoàn tất hồ sơ hội viên' : 'Thông tin cá nhân') + '</h2><p>' + (setupMode ? 'Bổ sung Họ tên và Số điện thoại để hoàn tất hồ sơ. Địa chỉ có thể thêm sau.' : 'Cập nhật thông tin liên hệ của bạn.') + '</p></div>' +
      (completed ? '<span class="ccc-account-status ok">Đã hoàn tất</span>' : '<span class="ccc-account-status pending">Cần bổ sung</span>') + '</header>' +
      message +
      '<form id="ccc-profile-form" class="ccc-account-form" novalidate>' +
        '<div class="ccc-account-field full"><label for="ccc-profile-email">Email</label><input id="ccc-profile-email" type="email" value="' + esc(state.user ? state.user.email || "" : "") + '" readonly><small>Email được quản lý bởi tài khoản đăng nhập.</small></div>' +
        '<div class="ccc-account-field"><label for="ccc-profile-name">Họ và tên <b>*</b></label><input id="ccc-profile-name" name="display_name" type="text" minlength="2" maxlength="100" autocomplete="name" value="' + esc(displayName) + '" required></div>' +
        '<div class="ccc-account-field"><label for="ccc-profile-phone">Số điện thoại <b>*</b></label><input id="ccc-profile-phone" name="phone" type="tel" inputmode="tel" autocomplete="tel" maxlength="30" placeholder="Ví dụ: 0901234567" value="' + esc(phone) + '" required></div>' +
        '<div class="ccc-account-field full"><label for="ccc-profile-address">Địa chỉ <span>(không bắt buộc)</span></label><textarea id="ccc-profile-address" name="address" rows="3" maxlength="500" autocomplete="street-address" placeholder="Có thể bổ sung sau nếu cần">' + esc(address) + '</textarea></div>' +
        '<div class="ccc-account-form-actions"><button class="ccc-account-primary" type="submit"' + (state.profileSaving ? ' disabled' : '') + '>' + (state.profileSaving ? 'Đang lưu…' : (setupMode ? 'Hoàn tất hồ sơ' : 'Lưu thay đổi')) + '</button></div>' +
      '</form>' +
    '</section>';
  }

  function planCatalogItem(code) {
    var wanted = String(code || "").toUpperCase();
    return state.planCatalog.find(function (item) {
      return String(item.plan_code || "").toUpperCase() === wanted;
    }) || null;
  }

  function planPriceLabel(plan) {
    if (!plan) return "—";
    var amount = Number(plan.price_vnd || 0);
    if (!Number.isFinite(amount) || amount <= 0) return "Miễn phí";
    return amount.toLocaleString("vi-VN") + "đ/tháng";
  }

  function planChangeLimitLabel(plan) {
    if (!plan) return "—";
    return plan.change_limit == null ? "Không giới hạn" : plan.change_limit + " lượt / chu kỳ";
  }

  function planCatalogHtml() {
    if (!state.planCatalog.length || !state.plan) return "";

    var currentCode = String(state.plan.plan_code || "");
    var selectedCode = String(state.previewPlanCode || "");
    var selected = selectedCode && selectedCode !== currentCode ? planCatalogItem(selectedCode) : null;

    var alternatives = state.planCatalog.filter(function (item) {
      return String(item.plan_code || "") !== currentCode;
    });

    if (!alternatives.length) return "";

    var choices = alternatives.map(function (item) {
      var code = String(item.plan_code || "");
      var active = selected && code === String(selected.plan_code || "");
      return '<button type="button" class="ccc-plan-choice ' + (active ? 'active ' : '') + '" data-plan-preview="' + esc(code) + '" aria-pressed="' + !!active + '">' +
        '<span>' + esc(item.display_name || code) + '</span>' +
        '<strong>' + esc(planPriceLabel(item)) + '</strong>' +
        (item.is_recommended ? '<small>Phổ biến</small>' : '<small>Xem gói</small>') +
      '</button>';
    }).join("");

    var preview = selected ? (
      '<div class="ccc-plan-preview is-selected">' +
        '<div class="ccc-plan-preview-main"><div><span>Gói đang xem</span><strong>' + esc(selected.display_name || selected.plan_code) + '</strong><small>' + esc(planPriceLabel(selected)) + '</small></div>' +
          (selected.is_recommended ? '<em>Phổ biến</em>' : '') +
        '</div>' +
        '<dl class="ccc-plan-preview-grid">' +
          '<div><dt>Phạm vi CCC kỹ thuật</dt><dd>' + esc(scopeLabel(selected)) + '</dd></div>' +
          '<div><dt>Watchlist</dt><dd>' + esc(watchlistLimitLabel(selected)) + '</dd></div>' +
          '<div><dt>Lượt đổi</dt><dd>' + esc(planChangeLimitLabel(selected)) + '</dd></div>' +
          '<div><dt>Cảnh báo</dt><dd>' + esc(alertLabel(selected)) + '</dd></div>' +
        '</dl>' +
        '<button type="button" class="ccc-plan-register" disabled>Đăng ký gói này</button>' +
        '<p class="ccc-plan-register-note">Thanh toán trực tuyến sẽ được nối ở bước billing sau.</p>' +
      '</div>'
    ) : (
      '<div class="ccc-plan-preview-empty">Chọn một gói khác để xem giá và quyền lợi chi tiết.</div>'
    );

    return '<div class="ccc-plan-explorer">' +
      '<div class="ccc-plan-explorer-head"><div><span class="ccc-account-kicker">XEM & NÂNG CẤP</span><h3>Các gói thành viên khác</h3></div><span>Chỉ xem, chưa thay đổi gói</span></div>' +
      '<div class="ccc-plan-choices" role="group" aria-label="Chọn gói để xem chi tiết">' + choices + '</div>' +
      preview +
    '</div>';
  }

  function membershipCardHtml() {
    if (state.membershipError) {
      return '<section class="ccc-account-card"><div class="ccc-account-form-message error">' + esc(state.membershipError) + '</div></section>';
    }
    if (!state.plan || !state.subscription) return "";

    var plan = state.plan;
    var sub = state.subscription;

    return '<section class="ccc-account-card membership compact-membership">' +
      '<header class="ccc-account-card-head ccc-current-plan-head"><div><span class="ccc-account-kicker">GÓI HIỆN TẠI</span><h2>' + esc(plan.display_name || plan.plan_code) + '</h2></div><span class="ccc-account-plan-badge">' + esc(plan.plan_code) + '</span></header>' +
      '<div class="ccc-current-plan-strip">' +
        '<div><span>Phạm vi CCC</span><strong>' + esc(scopeLabel(plan)) + '</strong></div>' +
        '<div><span>Lượt đổi còn lại</span><strong>' + esc(remainingLabel(plan, sub)) + '</strong></div>' +
        '<div><span>Cảnh báo</span><strong>' + esc(alertLabel(plan)) + '</strong></div>' +
      '</div>' +
      '<div class="ccc-account-cycle compact"><span>Chu kỳ hiện tại</span><strong>' + esc(formatDate(sub.cycle_start)) + ' → ' + esc(formatDate(sub.cycle_end)) + '</strong></div>' +
      planCatalogHtml() +
    '</section>';
  }

  function watchlistCardHtml() {
    var sub = state.subscription;
    return '<section class="ccc-account-card compact">' +
      '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">WATCHLIST & LƯỢT ĐỔI</span><h2>Danh sách theo dõi</h2><p>Watchlist thật sẽ được nối ở bước tiếp theo.</p></div><span class="ccc-account-status ' + (sub && sub.initial_setup_completed ? 'ok' : 'pending') + '">' + (sub && sub.initial_setup_completed ? 'Đã thiết lập' : 'Chưa thiết lập') + '</span></header>' +
      '<div class="ccc-account-placeholder">Chưa mở quản lý Watchlist trong 4C-2.</div>' +
    '</section>';
  }

  function securityCardHtml() {
    return '<section class="ccc-account-card compact">' +
      '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">BẢO MẬT</span><h2>Đăng nhập & phiên</h2><p>Quản lý phiên đăng nhập hiện tại.</p></div></header>' +
      '<div class="ccc-account-security-row"><span>Phương thức</span><strong>' + esc(providerLabel(state.user)) + '</strong></div>' +
      '<div class="ccc-account-security-row"><span>Trạng thái</span><strong>Đang hoạt động</strong></div>' +
      '<button id="ccc-account-logout" class="ccc-account-secondary danger" type="button">Đăng xuất</button>' +
    '</section>';
  }

  function accountPageHtml() {
    if (!state.authReady) return accountLoadingHtml();
    if (!state.user) return accountLoggedOutHtml();
    if (state.membershipLoading && !state.profile) return accountLoadingHtml();

    return '<main class="wrap ccc-account-page" id="main-content">' +
      '<header class="ccc-account-heading"><div><h1>Tài khoản</h1><p>Quản lý hồ sơ, gói thành viên và thiết lập cá nhân.</p></div><div class="ccc-account-identity"><span class="ccc-account-avatar">' + esc(userInitial(state.user)) + '</span><div><strong>' + esc(userLabel(state.user)) + '</strong><span>' + esc(state.user.email || "") + '</span></div></div></header>' +
      '<div class="ccc-account-layout"><div class="ccc-account-main">' + profileFormHtml() + membershipCardHtml() + '</div><aside class="ccc-account-side">' + watchlistCardHtml() + securityCardHtml() + '</aside></div>' +
    '</main>';
  }

  function renderAccountPage() {
    var node = accountRoot();
    if (!isAccountRoute()) {
      document.body.classList.remove("ccc-account-route");
      node.innerHTML = "";
      patchAccountButtons();
      return;
    }

    document.body.classList.add("ccc-account-route");
    node.innerHTML = accountPageHtml();
    patchAccountButtons();
    bindAccountPage();
    scheduleUiPolish();
  }

  function openLoginDialog() {
    state.open = true;
    state.error = "";
    state.notice = "";
    lastFocused = document.activeElement;
    renderAuthDialog();
    requestAnimationFrame(function () {
      var focusTarget = document.getElementById("ccc-auth-google");
      if (focusTarget) focusTarget.focus();
    });
  }

  function closeAuthDialog() {
    if (!state.open) return;
    state.open = false;
    state.error = "";
    state.notice = "";
    renderAuthDialog();
    if (lastFocused && typeof lastFocused.focus === "function") {
      requestAnimationFrame(function () { lastFocused.focus(); });
    }
  }

  function friendlyAuthError(error) {
    var message = error && error.message ? String(error.message) : "Không thể đăng nhập lúc này.";
    var normalized = message.toLowerCase();
    if (normalized.indexOf("invalid login credentials") >= 0) return "Email hoặc mật khẩu chưa đúng.";
    if (normalized.indexOf("email not confirmed") >= 0) return "Email chưa được xác nhận. Vui lòng kiểm tra hộp thư của bạn.";
    if (normalized.indexOf("rate limit") >= 0) return "Bạn thao tác quá nhanh. Vui lòng thử lại sau ít phút.";
    return message;
  }

  function maybeRedirectToProfileSetup() {
    if (!state.user || !state.profile || state.profile.profile_completed) return false;
    if (isAccountRoute()) return false;
    navigateAccount(ACCOUNT_PATH + "?setup=1", false);
    return true;
  }

  async function signInEmail(event) {
    event.preventDefault();
    if (!client || state.busy) return;

    var form = event.currentTarget;
    var formData = new FormData(form);
    var email = String(formData.get("email") || "").trim();
    var password = String(formData.get("password") || "");

    if (!email || !password) {
      state.error = "Vui lòng nhập đầy đủ email và mật khẩu.";
      renderAuthDialog();
      return;
    }

    state.busy = true;
    state.error = "";
    state.notice = "";
    renderAuthDialog();

    try {
      var result = await client.auth.signInWithPassword({ email: email, password: password });
      if (result.error) throw result.error;
      state.session = result.data.session || null;
      state.user = result.data.user || (state.session && state.session.user) || null;
      clearMembership();
      if (state.user) await loadMembership(false);

      if (maybeRedirectToProfileSetup()) return;

      state.notice = "Đăng nhập thành công.";
      state.open = false;
    } catch (error) {
      state.error = friendlyAuthError(error);
    } finally {
      state.busy = false;
      renderAuthDialog();
      renderAccountPage();
    }
  }

  async function signInGoogle() {
    if (!client || state.busy) return;
    state.busy = true;
    state.error = "";
    state.notice = "";
    renderAuthDialog();

    try {
      var redirectTo = window.location.origin + window.location.pathname;
      var result = await client.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: redirectTo }
      });
      if (result.error) throw result.error;
    } catch (error) {
      state.busy = false;
      state.error = friendlyAuthError(error);
      renderAuthDialog();
    }
  }

  async function signOut() {
    if (!client || state.busy) return;
    state.busy = true;
    state.error = "";

    try {
      var result = await client.auth.signOut();
      if (result.error) throw result.error;
      state.session = null;
      state.user = null;
      clearMembership();
      state.open = false;
      if (isAccountRoute()) renderAccountPage();
      else renderAuthDialog();
    } catch (error) {
      state.error = friendlyAuthError(error);
      if (state.open) renderAuthDialog();
    } finally {
      state.busy = false;
      patchAccountButtons();
    }
  }

  async function saveProfile(event) {
    event.preventDefault();
    if (!client || !state.user || state.profileSaving) return;

    var form = event.currentTarget;
    var data = new FormData(form);
    var displayName = String(data.get("display_name") || "").trim();
    var phone = String(data.get("phone") || "").trim();
    var address = String(data.get("address") || "").trim();
    var phoneDigits = phone.replace(/[^0-9]/g, "");

    state.profileSaveError = "";
    state.profileSaveSuccess = "";

    if (displayName.length < 2 || displayName.length > 100) {
      state.profileSaveError = "Họ và tên cần từ 2 đến 100 ký tự.";
      renderAccountPage();
      return;
    }
    if (phoneDigits.length < 8 || phoneDigits.length > 15) {
      state.profileSaveError = "Số điện thoại chưa hợp lệ.";
      renderAccountPage();
      return;
    }
    if (address.length > 500) {
      state.profileSaveError = "Địa chỉ tối đa 500 ký tự.";
      renderAccountPage();
      return;
    }

    state.profileSaving = true;
    renderAccountPage();

    try {
      var result = await client.rpc("save_my_profile", {
        p_display_name: displayName,
        p_phone: phone,
        p_address: address || null
      });
      if (result.error) throw result.error;

      state.membershipLoadedFor = "";
      await loadMembership(false);
      state.profileSaveSuccess = "Đã lưu hồ sơ thành công.";

      if (isSetupRoute()) {
        window.history.replaceState({}, "", ACCOUNT_PATH);
      }
    } catch (error) {
      var message = String(error && error.message ? error.message : "");
      if (message.indexOf("INVALID_DISPLAY_NAME") >= 0) state.profileSaveError = "Họ và tên chưa hợp lệ.";
      else if (message.indexOf("INVALID_PHONE") >= 0) state.profileSaveError = "Số điện thoại chưa hợp lệ.";
      else if (message.indexOf("ADDRESS_TOO_LONG") >= 0) state.profileSaveError = "Địa chỉ quá dài.";
      else state.profileSaveError = "Không lưu được hồ sơ. Vui lòng thử lại.";
      console.error("CCC profile save failed", error);
    } finally {
      state.profileSaving = false;
      renderAccountPage();
      patchAccountButtons();
    }
  }

  function bindAuthDialog() {
    var closeButton = document.getElementById("ccc-auth-close");
    if (closeButton) closeButton.addEventListener("click", closeAuthDialog);

    var overlay = authRoot().querySelector(".ccc-auth-overlay");
    if (overlay) {
      overlay.addEventListener("click", function (event) {
        if (event.target === overlay) closeAuthDialog();
      });
    }

    var emailForm = document.getElementById("ccc-auth-email-form");
    if (emailForm) emailForm.addEventListener("submit", signInEmail);

    var googleButton = document.getElementById("ccc-auth-google");
    if (googleButton) googleButton.addEventListener("click", signInGoogle);

    var logoutButton = document.getElementById("ccc-auth-logout");
    if (logoutButton) logoutButton.addEventListener("click", signOut);
  }

  function bindAccountPage() {
    var loginButton = document.getElementById("ccc-account-login");
    if (loginButton) loginButton.addEventListener("click", openLoginDialog);

    var profileForm = document.getElementById("ccc-profile-form");
    if (profileForm) profileForm.addEventListener("submit", saveProfile);

    document.querySelectorAll("[data-plan-preview]").forEach(function (button) {
      button.addEventListener("click", function () {
        var code = button.getAttribute("data-plan-preview") || "";
        if (!planCatalogItem(code)) return;
        state.previewPlanCode = code;
        renderAccountPage();
      });
    });

    var logoutButton = document.getElementById("ccc-account-logout");
    if (logoutButton) logoutButton.addEventListener("click", signOut);
  }

  function navigateAccount(path, replace) {
    var nextPath = path || ACCOUNT_PATH;
    if (replace) window.history.replaceState({ cccAccount: true }, "", nextPath);
    else window.history.pushState({ cccAccount: true }, "", nextPath);
    renderAccountPage();
    patchAccountButtons();
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function interceptAccountClick(event) {
    var target = event.target && event.target.closest ? event.target.closest("#account-open,#desktop-account-open") : null;
    if (!target) return;

    event.preventDefault();
    event.stopPropagation();

    if (state.user) {
      if (!isAccountRoute()) navigateAccount(ACCOUNT_PATH, false);
      else renderAccountPage();
    } else {
      openLoginDialog();
    }
  }

  function prepareAccountExitForShell(event) {
    if (!isAccountRoute()) return;
    var link = event.target && event.target.closest ? event.target.closest("a[href]") : null;
    if (!link) return;

    var href = link.getAttribute("href") || "";
    if (!href || href.charAt(0) === "#" || /^https?:\/\//i.test(href) && !href.startsWith(window.location.origin)) return;

    try {
      var url = new URL(link.href, window.location.origin);
      if (url.origin !== window.location.origin || url.pathname === ACCOUNT_PATH) return;
      document.body.classList.remove("ccc-account-route");
      accountRoot().innerHTML = "";
    } catch (_) {}
  }

  function installShellBridge() {
    document.addEventListener("click", prepareAccountExitForShell, true);
    document.addEventListener("click", interceptAccountClick, true);
    window.addEventListener("popstate", function () {
      renderAccountPage();
      patchAccountButtons();
      scheduleUiPolish();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && state.open) closeAuthDialog();
    });

    var scheduled = false;
    var observer = new MutationObserver(function () {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(function () {
        scheduled = false;
        patchAccountButtons();
        scheduleRealMembershipBridge();
        scheduleUiPolish();
      });
    });
    var app = document.getElementById("app");
    if (app) observer.observe(app, { childList: true, subtree: true });

    patchAccountButtons();
    renderAccountPage();
    scheduleUiPolish();
    startRefreshTimer();
  }

  async function init() {
    authRoot();
    accountRoot();
    installShellBridge();

    if (!window.supabase || typeof window.supabase.createClient !== "function") {
      state.fatal = "Không tải được thư viện xác thực Supabase. Vui lòng tải lại trang.";
      state.authReady = true;
      patchAccountButtons();
      renderAccountPage();
      return;
    }

    client = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true
      }
    });

    try {
      var sessionResult = await client.auth.getSession();
      if (sessionResult.error) throw sessionResult.error;
      state.session = sessionResult.data.session || null;
      state.user = state.session ? state.session.user : null;
      clearMembership();
      if (state.user) await loadMembership(false);
    } catch (error) {
      state.error = friendlyAuthError(error);
    } finally {
      state.authReady = true;
    }

    patchAccountButtons();
    renderAccountPage();
    scheduleRealMembershipBridge();

    if (maybeRedirectToProfileSetup()) return;

    client.auth.onAuthStateChange(function (_event, session) {
      var previousUserId = state.user ? state.user.id : "";
      var nextUser = session ? session.user : null;
      var nextUserId = nextUser ? nextUser.id : "";

      state.session = session || null;
      state.user = nextUser;
      state.authReady = true;

      if (!nextUser) {
        clearMembership();
        patchAccountButtons();
        renderAccountPage();
        scheduleRealMembershipBridge();
        if (state.open) renderAuthDialog();
        return;
      }

      if (previousUserId !== nextUserId || state.membershipLoadedFor !== nextUserId) {
        clearMembership();
        setTimeout(async function () {
          if (!state.user || state.user.id !== nextUserId) return;
          await loadMembership(false);
          patchAccountButtons();
          renderAccountPage();
          scheduleRealMembershipBridge();
          if (maybeRedirectToProfileSetup()) return;
          if (state.open) renderAuthDialog();
        }, 0);
      } else {
        patchAccountButtons();
        renderAccountPage();
        if (state.open) renderAuthDialog();
      }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
