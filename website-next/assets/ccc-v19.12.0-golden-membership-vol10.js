(function (global) {
  "use strict";

  var RELEASE = "v19.12.0-golden-membership-vol10";
  var SUPABASE_URL = "https://wevtlkowpbmpdggcfbvn.supabase.co";
  var SUPABASE_KEY = "sb_publishable_qN__TQuoNBRUFhxuY5CtNw_88WZDdJw";
  var VIP_UI_SENTINEL = 999999;
  var GOLDEN_PATH = "/bang-vang";
  var TB10_HELP = "Trong giờ giao dịch, TB10 so sánh khối lượng tích lũy hiện tại với trung bình khối lượng tích lũy tại cùng mốc thời gian của tối đa 10 phiên trước. Ngoài giờ giao dịch, TB10 là trung bình khối lượng cả phiên.";

  var originalData = global.CCCData || null;
  var goldenState = {
    loading: false,
    error: "",
    key: "",
    data: null,
    member: false,
    userId: "",
    loadedAt: 0
  };
  var observerScheduled = false;
  var decoratingWatchlist = false;
  var lastWatchlistDecorateAt = 0;
  var goldenRefreshTimer = null;

  function clone(value) {
    if (!value || typeof value !== "object") return value;
    if (Array.isArray(value)) return value.slice();
    var out = {};
    Object.keys(value).forEach(function (key) { out[key] = value[key]; });
    return out;
  }

  function normalizeVipWatchlistPayload(payload) {
    var data = clone(payload) || {};
    var vip = data.vip_day_active === true;
    if (vip) {
      data.__ccc_vip_unlimited = true;
      if (data.watchlist_limit === null || data.watchlist_limit === undefined) data.watchlist_limit = VIP_UI_SENTINEL;
      if (data.change_limit === null || data.change_limit === undefined) data.change_limit = VIP_UI_SENTINEL;
      if (data.change_remaining === null || data.change_remaining === undefined) data.change_remaining = VIP_UI_SENTINEL;
      if (data.watchlist_remaining_slots === null || data.watchlist_remaining_slots === undefined) data.watchlist_remaining_slots = VIP_UI_SENTINEL;
    }
    return data;
  }

  function patchDataBridge() {
    if (!originalData || originalData.__cccV1912Patched) return;
    var patched = {};
    Object.keys(originalData).forEach(function (key) { patched[key] = originalData[key]; });

    patched.loadMembership = async function (userId) {
      var result = await originalData.loadMembership(userId);
      result = result && typeof result === "object" ? result : { profile: null, subscription: null, plan: null, catalog: [] };
      result.catalog = (Array.isArray(result.catalog) ? result.catalog : []).filter(function (plan) {
        return String(plan && plan.plan_code || "").toUpperCase() === "FULL";
      });
      return result;
    };

    patched.getWatchlistState = async function () {
      return normalizeVipWatchlistPayload(await originalData.getWatchlistState());
    };

    patched.replaceWatchlist = async function (symbols) {
      return normalizeVipWatchlistPayload(await originalData.replaceWatchlist(symbols));
    };

    patched.__cccV1912Patched = true;
    global.CCCData = Object.freeze(patched);
  }

  patchDataBridge();

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

  function formatDate(value) {
    if (!value) return "—";
    var raw = String(value);
    var date = /^\d{4}-\d{2}-\d{2}$/.test(raw) ? new Date(raw + "T00:00:00+07:00") : new Date(raw);
    if (!Number.isFinite(date.getTime())) return "—";
    return date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Asia/Ho_Chi_Minh" });
  }

  function slot(value) {
    var match = String(value || "").match(/(\d{2}:\d{2})/);
    return match ? match[1] : "—";
  }

  function rvolX(value) {
    var parsed = num(value);
    if (parsed === null) return "—";
    var times = parsed / 100;
    if (times > 100) return ">100x";
    if (times >= 10) return times.toLocaleString("vi-VN", { maximumFractionDigits: 1 }) + "x";
    return times.toLocaleString("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "x";
  }

  function versionLabel(value) {
    var raw = String(value || "CCC_SIGNAL_V1").toUpperCase();
    var match = raw.match(/V(\d+)$/);
    return match ? "V" + match[1] : raw.replace(/^CCC_SIGNAL_/, "");
  }

  function goldenIcon() {
    return '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 4h8v3a4 4 0 0 1-8 0V4Z"/><path d="M8 6H4v1a5 5 0 0 0 5 5M16 6h4v1a5 5 0 0 1-5 5M12 11v5M8 20h8M9 16h6"/></svg>';
  }

  function normalizedPath() {
    var path = location.pathname || "/";
    return path.length > 1 ? path.replace(/\/+$/, "") : path;
  }

  function isGoldenPath() {
    return normalizedPath() === GOLDEN_PATH;
  }

  function accessSnapshot() {
    try {
      return global.CCCAccess && typeof global.CCCAccess.snapshot === "function" ? global.CCCAccess.snapshot() : null;
    } catch (_) {
      return null;
    }
  }

  function isVipActiveUi() {
    var snapshot = accessSnapshot();
    return !!(snapshot && snapshot.vipDayActive);
  }

  function patchNav() {
    document.querySelectorAll(".desktop-nav .shell-nav-placeholder").forEach(function (node) {
      if (String(node.textContent || "").indexOf("Cảnh báo") < 0) return;
      var link = document.createElement("a");
      link.href = GOLDEN_PATH;
      link.className = "shell-nav-link ccc-golden-nav";
      link.innerHTML = '<span class="nav-ico">' + goldenIcon() + '</span><span class="nav-label">Bảng vàng</span><small>Bảng vàng</small>';
      node.replaceWith(link);
    });

    var alertButton = document.querySelector(".top-actions .alert-action");
    if (alertButton && alertButton.tagName !== "A") {
      var topLink = document.createElement("a");
      topLink.href = GOLDEN_PATH;
      topLink.className = "icon-action alert-action ccc-golden-top-action";
      topLink.setAttribute("aria-label", "Mở Bảng vàng 4/4");
      topLink.setAttribute("title", "Bảng vàng 4/4");
      topLink.innerHTML = goldenIcon();
      alertButton.replaceWith(topLink);
    }

    var mobile = document.querySelector(".mobile-bottom");
    if (mobile && !mobile.querySelector('a[href="' + GOLDEN_PATH + '"]')) {
      var guide = mobile.querySelector('a[href="/huong-dan"]');
      if (guide) {
        guide.href = GOLDEN_PATH;
        guide.classList.add("ccc-golden-nav");
        var ico = guide.querySelector(".nav-ico");
        var label = guide.querySelector(".nav-label");
        var small = guide.querySelector("small");
        if (ico) ico.innerHTML = goldenIcon();
        if (label) label.textContent = "Bảng vàng";
        if (small) small.textContent = "Bảng vàng";
      }
    }

    if (isGoldenPath()) {
      document.querySelectorAll(".shell-nav-link.active").forEach(function (node) {
        node.classList.remove("active");
        node.removeAttribute("aria-current");
      });
      document.querySelectorAll('a[href="' + GOLDEN_PATH + '"]').forEach(function (node) {
        node.classList.add("active");
        node.setAttribute("aria-current", "page");
      });
      var route = document.querySelector(".mobile-route");
      if (route) route.textContent = "Bảng vàng";
      document.title = "Bảng vàng 4/4 — Chuyện Chợ Chứng";
    }
  }

  function replaceTextNodes(root) {
    if (!root || !document.createTreeWalker) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var parent = node.parentElement;
        if (!parent) return NodeFilter.FILTER_REJECT;
        if (/^(SCRIPT|STYLE|TEXTAREA|INPUT|SELECT|OPTION)$/.test(parent.tagName)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [];
    var node;
    while ((node = walker.nextNode())) nodes.push(node);
    nodes.forEach(function (textNode) {
      var value = textNode.nodeValue || "";
      var next = value
        .replace(/KL ngày \/ KLTB10/g, "KL/TB10")
        .replace(/KL ngày ≥ 200% KLTB10/g, "KL ≥ 200% TB10")
        .replace(/≥ 200% KLTB10/g, "≥ 200% TB10")
        .replace(/% KLTB10/g, "% TB10")
        .replace(/KLTB10/g, "TB10")
        .replace(/Tăng số mã theo dõi/g, "Xem FULL 1 tháng")
        .replace(/Xem các gói/g, "Xem FULL 1 tháng");
      if (next !== value) textNode.nodeValue = next;
    });
  }

  function patchTb10Help() {
    document.querySelectorAll(".signal-legend-card .rail-card-body").forEach(function (body) {
      if (body.querySelector(".ccc-tb10-note")) return;
      var note = document.createElement("p");
      note.className = "ccc-tb10-note";
      note.innerHTML = '<strong>TB10 tham chiếu:</strong> ' + esc(TB10_HELP);
      body.appendChild(note);
    });

    document.querySelectorAll(".technical-signal, .detail-metric, .volume-ratio, .market-basic-volume small, td small").forEach(function (node) {
      if (String(node.textContent || "").indexOf("TB10") >= 0) {
        node.classList.add("ccc-tb10-help");
        node.setAttribute("title", TB10_HELP);
      }
    });

    document.querySelectorAll(".guide-signal-card").forEach(function (card) {
      if (String(card.textContent || "").indexOf("KHỐI LƯỢNG") < 0) return;
      var strong = card.querySelector("strong");
      var p = card.querySelector("p");
      if (strong) strong.textContent = "KL ≥ 200% TB10";
      if (p) p.textContent = "TB10 dùng nền khối lượng 10 phiên. Trong giờ giao dịch, hệ thống so với đúng cùng mốc thời gian; ngoài giờ dùng trung bình cả phiên.";
      card.setAttribute("title", TB10_HELP);
    });
  }

  function paidOffersHtml() {
    return '<div class="ccc-offer-card vip"><b>VIP DAY</b><span>FULL toàn thị trường · DS theo dõi không giới hạn</span><small>100.000đ / 24 giờ</small></div>' +
      '<div class="ccc-offer-card full"><b>FULL</b><span>FULL toàn thị trường · DS theo dõi không giới hạn</span><small>1.000.000đ / tháng</small></div>';
  }

  function patchPackages() {
    document.querySelectorAll(".guest-plan-preview").forEach(function (box) {
      if (box.getAttribute("data-ccc-v1912") === "1") return;
      box.innerHTML = paidOffersHtml();
      box.setAttribute("data-ccc-v1912", "1");
    });

    document.querySelectorAll(".guide-plan-grid").forEach(function (box) {
      if (box.getAttribute("data-ccc-v1912") === "1") return;
      box.innerHTML = '<article><strong>VIP DAY</strong><span>100.000đ · FULL + DS không giới hạn trong 24 giờ</span></article>' +
        '<article><strong>FULL</strong><span>1.000.000đ/tháng · FULL + DS không giới hạn trong 1 tháng</span></article>';
      box.setAttribute("data-ccc-v1912", "1");
    });

    document.querySelectorAll(".guide-plan-footnote").forEach(function (node) {
      node.textContent = "VIP DAY và FULL có cùng phạm vi kỹ thuật toàn thị trường và DS mã theo dõi không giới hạn. Khác nhau ở thời hạn: VIP DAY 24 giờ, FULL 1 tháng. Khi quyền hết hạn, danh sách đã lưu vẫn còn; các mã vượt gói nền sẽ khóa dữ liệu kỹ thuật.";
    });

    document.querySelectorAll(".phase4-plan-choice").forEach(function (card) {
      var code = String(card.querySelector("strong") && card.querySelector("strong").textContent || "").trim().toUpperCase();
      if (code && code !== "FULL") card.remove();
    });

    document.querySelectorAll(".phase4-upgrade-head h3").forEach(function (node) { node.textContent = "FULL 1 tháng"; });
    document.querySelectorAll(".phase4-upgrade-head p").forEach(function (node) { node.textContent = "Gói trả phí dài hạn duy nhất đang hiển thị. Các gói cũ được giữ cho thành viên hiện hữu nhưng không mở đăng ký mới."; });

    var vipInactive = document.querySelector(".ccc-vip-day-offer.phase4-vip:not(.active) small");
    if (vipInactive) vipInactive.textContent = "100.000đ · FULL toàn thị trường + DS theo dõi không giới hạn trong 24 giờ. Khi VIP hết, danh sách đã lưu vẫn được giữ.";

    var vipActiveSmall = document.querySelector(".ccc-vip-day-offer.phase4-vip.active small");
    if (vipActiveSmall) vipActiveSmall.textContent = "VIP đang mở FULL toàn thị trường và DS theo dõi không giới hạn. Khi VIP hết, danh sách vẫn được giữ; phần vượt gói nền sẽ khóa kỹ thuật.";

    document.querySelectorAll(".overview-member-status.vip-active small").forEach(function (node) {
      node.textContent = "Trong thời gian VIP, DS của tôi không giới hạn. Khi VIP hết, danh sách vẫn được giữ; phần vượt gói nền sẽ khóa kỹ thuật.";
    });

    document.querySelectorAll(".rail-note.vip-note span").forEach(function (node) {
      node.textContent = "VIP DAY đang mở kỹ thuật toàn thị trường và DS mã theo dõi không giới hạn trong thời gian VIP.";
    });

    document.querySelectorAll(".scanner-action-copy p").forEach(function (node) {
      if (String(node.textContent || "").indexOf("VIP DAY") >= 0) {
        node.textContent = "VIP DAY và FULL đều mở kỹ thuật CCC toàn thị trường và DS mã theo dõi không giới hạn; VIP DAY dùng 24 giờ, FULL dùng 1 tháng.";
      }
    });
  }

  function parseLeadingCount(text) {
    var match = String(text || "").match(/(\d+)/);
    return match ? Number(match[1]) : null;
  }

  function patchLabelValue(containerSelector, label, formatter) {
    document.querySelectorAll(containerSelector + " > div").forEach(function (row) {
      var labelNode = row.querySelector("span,dt");
      var valueNode = row.querySelector("strong,dd");
      if (!labelNode || !valueNode) return;
      if (String(labelNode.textContent || "").trim() !== label) return;
      valueNode.textContent = formatter(valueNode.textContent || "");
    });
  }

  function patchVipUnlimitedUi() {
    if (!isVipActiveUi()) return;

    patchLabelValue(".ccc-wl-metrics", "Đang theo dõi", function (value) {
      var count = parseLeadingCount(value);
      return (count === null ? "" : count + " mã · ") + "Không giới hạn";
    });
    patchLabelValue(".ccc-wl-metrics", "Lượt đổi còn lại", function () { return "Không giới hạn"; });
    patchLabelValue(".phase4-plan-metrics", "Số mã theo dõi", function (value) {
      var count = parseLeadingCount(value);
      return (count === null ? "" : count + " mã · ") + "Không giới hạn";
    });
    patchLabelValue(".phase4-plan-metrics", "Lượt đổi còn lại", function () { return "Không giới hạn"; });

    document.querySelectorAll(".rail-kv > div").forEach(function (row) {
      var dt = row.querySelector("dt");
      var dd = row.querySelector("dd");
      if (!dt || !dd) return;
      var key = String(dt.textContent || "").trim();
      if (key === "DS theo dõi" || key === "Lượt đổi còn lại") dd.textContent = "Không giới hạn";
    });

    var metrics = document.querySelector(".ccc-wl-metrics");
    if (metrics && !document.querySelector(".ccc-vip-unlimited-banner")) {
      var banner = document.createElement("div");
      banner.className = "ccc-wl-banner info ccc-vip-unlimited-banner";
      banner.innerHTML = "<strong>VIP DAY · DS không giới hạn.</strong><span>Bạn có thể thêm mã thoải mái trong thời gian VIP. Khi VIP hết, danh sách vẫn được giữ và phần vượt gói nền sẽ khóa kỹ thuật.</span>";
      metrics.insertAdjacentElement("afterend", banner);
    }
  }

  async function decorateRetainedWatchlist() {
    if (normalizedPath() !== "/tai-khoan") return;
    if (!document.querySelector(".ccc-wl-selected-row")) return;
    if (decoratingWatchlist || Date.now() - lastWatchlistDecorateAt < 1200) return;
    if (!global.CCCData || typeof global.CCCData.getWatchlistState !== "function") return;

    decoratingWatchlist = true;
    lastWatchlistDecorateAt = Date.now();
    try {
      var data = await global.CCCData.getWatchlistState();
      var map = Object.create(null);
      (data && Array.isArray(data.items) ? data.items : []).forEach(function (item) {
        map[String(item && item.symbol || "").toUpperCase()] = item;
      });

      document.querySelectorAll(".ccc-wl-selected-row").forEach(function (row) {
        var symbolNode = row.querySelector("strong");
        var symbol = String(symbolNode && symbolNode.textContent || "").trim().toUpperCase();
        var item = map[symbol] || null;
        var locked = !!(item && item.locked === true);
        row.classList.toggle("is-retained-locked", locked);
        var old = row.querySelector(".ccc-retained-lock");
        if (old) old.remove();
        if (locked) {
          var copy = row.querySelector("div");
          if (copy) {
            var badge = document.createElement("em");
            badge.className = "ccc-retained-lock";
            badge.textContent = "🔒 Đã lưu · kỹ thuật đang khóa";
            copy.appendChild(badge);
          }
        }
      });

      var oldBanner = document.querySelector(".ccc-retained-banner");
      if (oldBanner) oldBanner.remove();
      var lockedCount = num(data && data.retained_locked_count) || 0;
      var metrics = document.querySelector(".ccc-wl-metrics");
      if (lockedCount > 0 && metrics) {
        var banner = document.createElement("div");
        banner.className = "ccc-wl-banner info ccc-retained-banner";
        banner.innerHTML = "<strong>" + lockedCount + " mã vẫn đang được lưu.</strong><span>Các mã này vượt phạm vi kỹ thuật của gói nền nên đang khóa. Kích hoạt VIP DAY hoặc FULL để mở lại toàn bộ mà không cần chọn lại danh sách.</span>";
        metrics.insertAdjacentElement("afterend", banner);
      }
    } catch (_) {
      /* UI decoration is best-effort; backend remains authoritative. */
    } finally {
      decoratingWatchlist = false;
    }
  }

  async function currentSession() {
    if (!global.CCCData || typeof global.CCCData.getSession !== "function") return null;
    try {
      var result = await global.CCCData.getSession();
      return result && result.session || null;
    } catch (_) {
      return null;
    }
  }

  async function rpc(name, body, session) {
    var headers = {
      "apikey": SUPABASE_KEY,
      "Content-Type": "application/json",
      "Accept": "application/json"
    };
    if (session && session.access_token) headers.Authorization = "Bearer " + session.access_token;
    var response = await fetch(SUPABASE_URL + "/rest/v1/rpc/" + name, {
      method: "POST",
      cache: "no-store",
      headers: headers,
      body: JSON.stringify(body || {})
    });
    if (!response.ok) {
      var text = await response.text();
      throw new Error("GOLDEN_RPC_" + response.status + ":" + text.slice(0, 180));
    }
    return await response.json();
  }

  function goldenRequestedDate() {
    var raw = new URLSearchParams(location.search).get("date") || "";
    return /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : "";
  }

  async function loadGolden(force) {
    if (!isGoldenPath() || goldenState.loading) return;
    var session = await currentSession();
    var userId = session && session.user && session.user.id || "guest";
    var date = goldenRequestedDate();
    var key = userId + "|" + date;
    if (!force && goldenState.key === key && goldenState.data) {
      renderGolden();
      return;
    }

    goldenState.loading = true;
    goldenState.error = "";
    goldenState.key = key;
    goldenState.member = !!(session && session.user);
    goldenState.userId = userId;
    renderGolden();

    try {
      if (session && session.user) {
        goldenState.data = await rpc("get_my_golden_board", { p_trading_date: date || null }, session);
        goldenState.member = true;
      } else {
        goldenState.data = await rpc("get_public_golden_board", { p_trading_date: date || null }, null);
        goldenState.member = false;
      }
      goldenState.loadedAt = Date.now();
    } catch (error) {
      goldenState.error = "Không tải được Bảng vàng. Vui lòng thử lại.";
      console.error("CCC Golden Board load failed", error);
    } finally {
      goldenState.loading = false;
      renderGolden();
    }
  }

  function dateSelectorHtml(data) {
    var dates = Array.isArray(data && data.available_dates) ? data.available_dates : [];
    if (!dates.length) return "";
    var current = data.trading_date || goldenRequestedDate() || dates[0];
    return '<label class="golden-date-picker"><span>Phiên giao dịch</span><select id="golden-date-select">' +
      dates.map(function (date) {
        return '<option value="' + esc(date) + '"' + (String(date) === String(current) ? ' selected' : '') + '>' + esc(formatDate(date)) + '</option>';
      }).join("") + '</select></label>';
  }

  function goldenKpisHtml(data, rows) {
    var marketTotal = Number(data.market_total || 0);
    var accessible = Number(data.accessible_total == null ? rows.length : data.accessible_total || 0);
    var hidden = Number(data.hidden_count || 0);
    var still = rows.filter(function (row) { return row && row.still_4of4 === true; }).length;
    var best = rows.reduce(function (max, row) { return Math.max(max, Number(row && row.longest_streak_hits || 0)); }, 0);

    return '<div class="golden-kpi-grid">' +
      '<article><span>Toàn thị trường từng đạt</span><strong>' + marketTotal + '</strong><small>mã 4/4 trong phiên</small></article>' +
      '<article><span>' + (hidden > 0 ? "Bạn xem được" : "Kết phiên còn 4/4") + '</span><strong>' + (hidden > 0 ? accessible : still) + '</strong><small>' + (hidden > 0 ? "mã theo quyền hiện tại" : "mã vẫn đủ 4/4 ở mốc cuối") + '</small></article>' +
      '<article><span>' + (hidden > 0 ? "Đang khóa" : "Chuỗi bền nhất") + '</span><strong>' + (hidden > 0 ? hidden : best) + '</strong><small>' + (hidden > 0 ? "mã ngoài phạm vi" : "lần 5 phút liên tiếp") + '</small></article>' +
    '</div>';
  }

  function goldenRowsHtml(rows) {
    if (!rows.length) return '<div class="golden-empty"><strong>Chưa có mã Bảng vàng trong phạm vi bạn được xem.</strong><span>Nếu thị trường có mã 4/4 ngoài phạm vi, số lượng vẫn được hiển thị ở phía trên.</span></div>';
    return '<div class="golden-table-wrap"><table class="golden-table"><thead><tr><th>Mã</th><th>Lần đầu 4/4</th><th>Độ bền</th><th>Giá lúc vào</th><th>KL/TB10</th><th>RVOL30</th><th>Mốc cuối</th></tr></thead><tbody>' +
      rows.map(function (row) {
        var version = versionLabel(row.signal_version);
        var currentCount = Number(row.latest_signal_count || 0);
        var statusClass = currentCount === 4 ? "is-four" : currentCount === 3 ? "is-three" : "is-lower";
        var company = row.company_name || row.display_name || "";
        return '<tr><td><a class="golden-symbol-link" href="/co-phieu/' + encodeURIComponent(String(row.symbol || "")) + '"><strong>' + esc(row.symbol) + '</strong><span>' + esc(company) + '</span><small>' + esc(row.exchange || "") + ' · ' + esc(version) + '</small></a></td>' +
          '<td><strong>' + esc(slot(row.first_hit_slot)) + '</strong><small>đầu tiên đạt 4/4</small></td>' +
          '<td><strong>' + Number(row.hit_count || 0) + ' lần</strong><small>chuỗi max ' + Number(row.longest_streak_hits || 0) + '</small></td>' +
          '<td><strong>' + esc(pct(row.first_price_change_pct, 2)) + '</strong><small>giá ' + esc(fmt(row.first_price, 0)) + '</small></td>' +
          '<td><strong>' + esc(fmt(row.first_daily_volume_pct, 0)) + '%</strong><small title="' + esc(TB10_HELP) + '">TB10 tham chiếu</small></td>' +
          '<td><strong title="' + esc(fmt(row.first_rvol30_pct, 0)) + '%">' + esc(rvolX(row.first_rvol30_pct)) + '</strong><small>' + (row.first_rvol30_sessions == null ? "—" : Number(row.first_rvol30_sessions) + '/10 phiên') + '</small></td>' +
          '<td><span class="golden-status ' + statusClass + '">' + currentCount + '/4</span><small>' + esc(slot(row.latest_observed_slot)) + '</small></td></tr>';
      }).join("") + '</tbody></table></div>';
  }

  function goldenMobileCardsHtml(rows) {
    return '<div class="golden-mobile-list">' + rows.map(function (row) {
      var currentCount = Number(row.latest_signal_count || 0);
      var statusClass = currentCount === 4 ? "is-four" : currentCount === 3 ? "is-three" : "is-lower";
      return '<article class="golden-mobile-card"><header><a href="/co-phieu/' + encodeURIComponent(String(row.symbol || "")) + '"><strong>' + esc(row.symbol) + '</strong><span>' + esc(row.company_name || row.display_name || "") + '</span><small>' + esc(row.exchange || "") + ' · ' + esc(versionLabel(row.signal_version)) + '</small></a><span class="golden-status ' + statusClass + '">' + currentCount + '/4</span></header>' +
        '<div><span><small>Lần đầu</small><b>' + esc(slot(row.first_hit_slot)) + '</b></span><span><small>Độ bền</small><b>' + Number(row.hit_count || 0) + ' lần</b></span><span><small>KL/TB10</small><b>' + esc(fmt(row.first_daily_volume_pct, 0)) + '%</b></span><span><small>RVOL30</small><b>' + esc(rvolX(row.first_rvol30_pct)) + '</b></span></div>' +
        '<footer><span>Chuỗi max ' + Number(row.longest_streak_hits || 0) + ' lần</span><span>Giá lúc vào ' + esc(pct(row.first_price_change_pct, 2)) + '</span></footer></article>';
    }).join("") + '</div>';
  }

  function weeklyHtml(data) {
    var rows = Array.isArray(data && data.week_summary) ? data.week_summary : [];
    if (!rows.length) return "";
    return '<section class="golden-week panel-anatomy"><header><div><span>WEEKLY GOLD</span><h2>Mã nổi bật trong tuần</h2></div><small>' + esc(formatDate(data.week_start)) + ' → ' + esc(formatDate(data.week_end)) + '</small></header><div class="golden-week-grid">' +
      rows.slice(0, 6).map(function (row, index) {
        return '<a href="/co-phieu/' + encodeURIComponent(String(row.symbol || "")) + '"><em>#' + (index + 1) + '</em><strong>' + esc(row.symbol) + '</strong><span>' + Number(row.sessions_count || 0) + ' phiên vào Bảng vàng</span><small>' + Number(row.total_hits || 0) + ' hit · streak max ' + Number(row.best_streak_hits || 0) + ' · RVOL TB ' + esc(rvolX(row.avg_rvol30)) + '</small></a>';
      }).join("") + '</div></section>';
  }

  function memberGoldenHtml(data) {
    data = data || {};
    var rows = Array.isArray(data.rows) ? data.rows : [];
    var hidden = Number(data.hidden_count || 0);
    var accessNote = hidden > 0
      ? '<section class="golden-lock-note"><div><strong>Còn ' + hidden + ' mã Bảng vàng ngoài phạm vi kỹ thuật của bạn.</strong><span>Tên mã không bị tiết lộ. VIP DAY hoặc FULL mở toàn bộ Bảng vàng thị trường.</span></div><a href="/tai-khoan?intent=vip_day">Mở VIP DAY · 100.000đ</a></section>'
      : '';

    return '<main id="main-content" class="wrap golden-page" data-ccc-golden-rendered="1"><section class="golden-hero"><div><span class="golden-eyebrow">BẢNG VÀNG 4/4</span><h1>Bảng vàng</h1><p>Nhật ký các cổ phiếu từng đồng thời đạt đủ 4 tín hiệu CCC trong phiên. Mã đã vào Bảng vàng vẫn được lưu dù sau đó tín hiệu giảm.</p></div>' + dateSelectorHtml(data) + '</section>' +
      goldenKpisHtml(data, rows) + accessNote +
      '<section class="golden-board panel-anatomy"><header class="golden-board-head"><div><h2>Phiên ' + esc(formatDate(data.trading_date)) + '</h2><span>' + Number(data.market_total || 0) + ' mã toàn thị trường · ' + rows.length + ' mã bạn được xem</span></div><small>Ruleset lịch sử được giữ theo V1/V2</small></header>' +
      goldenRowsHtml(rows) + goldenMobileCardsHtml(rows) + '</section>' + weeklyHtml(data) +
      '<section class="golden-method"><strong>Cách đọc lịch sử</strong><p>Badge V1/V2 cho biết bộ điều kiện tín hiệu đang có hiệu lực tại thời điểm mã được ghi nhận. Khi CCC đổi sang Signal V2, dữ liệu V1 cũ không bị tính lại hay xóa.</p><p><b>TB10:</b> ' + esc(TB10_HELP) + '</p></section><p class="disclaimer">Bảng vàng là nhật ký tín hiệu, không phải khuyến nghị mua/bán.</p></main>';
  }

  function publicGoldenHtml(data) {
    data = data || {};
    var rows = Array.isArray(data.teaser_rows) ? data.teaser_rows : [];
    return '<main id="main-content" class="wrap golden-page golden-public" data-ccc-golden-rendered="1"><section class="golden-hero"><div><span class="golden-eyebrow">BẢNG VÀNG 4/4</span><h1>Bảng vàng</h1><p>Các cổ phiếu từng đồng thời đạt đủ 4 tín hiệu CCC trong phiên.</p></div></section>' +
      '<div class="golden-public-count"><span>Phiên ' + esc(formatDate(data.trading_date)) + '</span><strong>' + Number(data.market_total || 0) + ' mã</strong><small>đã từng đạt 4/4 trên toàn thị trường</small></div>' +
      '<section class="golden-teaser"><header><div><h2>Xem thử Bảng vàng</h2><span>Tối đa 2 mã, trễ ' + Number(data.teaser_delay_minutes || 20) + ' phút</span></div></header>' +
      (rows.length ? '<div class="golden-teaser-grid">' + rows.map(function (row) {
        return '<a href="/co-phieu/' + encodeURIComponent(String(row.symbol || "")) + '"><strong>' + esc(row.symbol) + '</strong><span>' + esc(row.company_name || row.display_name || "") + '</span><small>' + esc(row.exchange || "") + ' · vào lúc ' + esc(slot(row.first_hit_slot)) + '</small></a>';
      }).join("") + '</div>' : '<div class="golden-empty"><strong>Chưa có teaser khả dụng.</strong><span>Bảng vàng vẫn đang được hệ thống theo dõi.</span></div>') +
      '<div class="golden-public-cta"><div><strong>Muốn xem ngay toàn bộ Bảng vàng?</strong><span>VIP DAY mở FULL toàn thị trường trong 24 giờ; FULL mở trong 1 tháng.</span></div><a href="/tai-khoan?intent=vip_day">Đăng nhập / mở VIP DAY</a></div></section>' +
      '<section class="golden-method"><strong>Bảng vàng lưu lịch sử, không chỉ trạng thái hiện tại.</strong><p>Một mã đã từng đạt 4/4 sẽ còn trong nhật ký của phiên đó ngay cả khi sau đó giảm xuống 3/4 hoặc 2/4.</p></section><p class="disclaimer">Bảng vàng là nhật ký tín hiệu, không phải khuyến nghị mua/bán.</p></main>';
  }

  function renderGolden() {
    if (!isGoldenPath()) return;
    patchNav();
    var main = document.getElementById("main-content");
    if (!main) return;

    if (goldenState.loading && !goldenState.data) {
      main.outerHTML = '<main id="main-content" class="wrap golden-page" data-ccc-golden-rendered="1"><section class="golden-loading"><span></span><div><strong>Đang tải Bảng vàng…</strong><p>Đang đọc lịch sử 4/4 và quyền thành viên hiện tại.</p></div></section></main>';
      return;
    }
    if (goldenState.error && !goldenState.data) {
      main.outerHTML = '<main id="main-content" class="wrap golden-page" data-ccc-golden-rendered="1"><section class="golden-error"><strong>Không tải được Bảng vàng.</strong><p>' + esc(goldenState.error) + '</p><button type="button" data-golden-retry>Thử lại</button></section></main>';
      return;
    }
    if (!goldenState.data) {
      main.outerHTML = '<main id="main-content" class="wrap golden-page" data-ccc-golden-rendered="1"><section class="golden-loading"><span></span><div><strong>Đang chuẩn bị Bảng vàng…</strong></div></section></main>';
      return;
    }

    main.outerHTML = goldenState.member ? memberGoldenHtml(goldenState.data) : publicGoldenHtml(goldenState.data);
  }

  function applyUiPatches() {
    patchNav();
    if (isGoldenPath()) {
      var main = document.getElementById("main-content");
      if (!main || main.getAttribute("data-ccc-golden-rendered") !== "1") renderGolden();
      if (!goldenState.data && !goldenState.loading) loadGolden(false);
      return;
    }

    replaceTextNodes(document.getElementById("app") || document.body);
    patchTb10Help();
    patchPackages();
    patchVipUnlimitedUi();
    decorateRetainedWatchlist();
  }

  function schedulePatches() {
    if (observerScheduled) return;
    observerScheduled = true;
    setTimeout(function () {
      observerScheduled = false;
      applyUiPatches();
    }, 20);
  }

  function startObserver() {
    var target = document.getElementById("app") || document.body;
    if (!target || !global.MutationObserver) return;
    var observer = new MutationObserver(schedulePatches);
    observer.observe(target, { childList: true, subtree: true });
    schedulePatches();
  }

  document.addEventListener("change", function (event) {
    if (!isGoldenPath()) return;
    var target = event.target;
    if (!target || target.id !== "golden-date-select") return;
    var date = String(target.value || "");
    var url = new URL(location.href);
    if (date) url.searchParams.set("date", date);
    else url.searchParams.delete("date");
    history.replaceState(history.state || null, "", url.pathname + url.search);
    goldenState.data = null;
    goldenState.key = "";
    loadGolden(true);
  });

  document.addEventListener("click", function (event) {
    if (!isGoldenPath()) return;
    var retry = event.target && event.target.closest ? event.target.closest("[data-golden-retry]") : null;
    if (retry) {
      event.preventDefault();
      goldenState.data = null;
      goldenState.error = "";
      goldenState.key = "";
      loadGolden(true);
      return;
    }
    var refresh = event.target && event.target.closest ? event.target.closest("#refresh-btn") : null;
    if (refresh) {
      event.preventDefault();
      event.stopImmediatePropagation();
      goldenState.key = "";
      loadGolden(true);
    }
  }, true);

  window.addEventListener("popstate", function () {
    goldenState.key = "";
    goldenState.data = null;
    schedulePatches();
    if (isGoldenPath()) loadGolden(true);
  });

  window.addEventListener("focus", function () {
    if (isGoldenPath() && Date.now() - goldenState.loadedAt > 60000) loadGolden(true);
  });

  if (global.CCCData && typeof global.CCCData.onAuthStateChange === "function") {
    try {
      global.CCCData.onAuthStateChange(function () {
        if (!isGoldenPath()) return;
        goldenState.key = "";
        goldenState.data = null;
        loadGolden(true);
      });
    } catch (_) {}
  }

  function start() {
    startObserver();
    if (isGoldenPath()) loadGolden(false);
    if (goldenRefreshTimer) clearInterval(goldenRefreshTimer);
    goldenRefreshTimer = setInterval(function () {
      if (isGoldenPath()) loadGolden(true);
    }, 5 * 60 * 1000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else setTimeout(start, 0);

  global.CCCReleaseV1912 = Object.freeze({
    version: RELEASE,
    tb10Help: TB10_HELP,
    reloadGolden: function () { return loadGolden(true); }
  });
})(window);
