(function (global) {
  "use strict";

  /* v19.12.8 responsive lock: tablet Golden Board collapses before 1024px pinch */

  var RELEASE = "v19.12.8-responsive-lock";
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
    loadedAt: 0
  };
  var overviewContextState = {
    loading: false,
    error: "",
    data: null,
    loadedAt: 0
  };
  var decoratingWatchlist = false;
  var lastWatchlistDecorateAt = 0;
  var refreshTimer = null;

  function clone(value) {
    if (!value || typeof value !== "object") return value;
    if (Array.isArray(value)) return value.slice();
    var out = {};
    Object.keys(value).forEach(function (key) { out[key] = value[key]; });
    return out;
  }

  function normalizeVipWatchlistPayload(payload) {
    var data = clone(payload) || {};
    if (data.vip_day_active === true) {
      data.__ccc_vip_unlimited = true;
      if (data.watchlist_limit == null) data.watchlist_limit = VIP_UI_SENTINEL;
      if (data.change_limit == null) data.change_limit = VIP_UI_SENTINEL;
      if (data.change_remaining == null) data.change_remaining = VIP_UI_SENTINEL;
      if (data.watchlist_remaining_slots == null) data.watchlist_remaining_slots = VIP_UI_SENTINEL;
    }
    return data;
  }

  function patchDataBridge() {
    if (!originalData || originalData.__cccV1912Patched) return;
    var patched = {};
    Object.keys(originalData).forEach(function (key) { patched[key] = originalData[key]; });

    patched.loadMembership = async function (userId) {
      var result = await originalData.loadMembership(userId);
      result = result && typeof result === "object"
        ? result
        : { profile: null, subscription: null, plan: null, catalog: [] };
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
    return date.toLocaleDateString("vi-VN", {
      day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Asia/Ho_Chi_Minh"
    });
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

  function normalizedPath() {
    var path = location.pathname || "/";
    return path.length > 1 ? path.replace(/\/+$/, "") : path;
  }

  function accessSnapshot() {
    try {
      return global.CCCAccess && typeof global.CCCAccess.snapshot === "function"
        ? global.CCCAccess.snapshot()
        : null;
    } catch (_) {
      return null;
    }
  }

  function isVipActiveUi() {
    var snapshot = accessSnapshot();
    return !!(snapshot && snapshot.vipDayActive);
  }

  function replaceTextNodes(root) {
    if (!root || !document.createTreeWalker) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var parent = node.parentElement;
        if (!parent || /^(SCRIPT|STYLE|TEXTAREA|INPUT|SELECT|OPTION)$/.test(parent.tagName)) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [], node;
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
      if (strong && strong.textContent !== "KL ≥ 200% TB10") strong.textContent = "KL ≥ 200% TB10";
      var copy = "TB10 dùng nền khối lượng 10 phiên. Trong giờ giao dịch, hệ thống so với đúng cùng mốc thời gian; ngoài giờ dùng trung bình cả phiên.";
      if (p && p.textContent !== copy) p.textContent = copy;
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
      var copy = "VIP DAY và FULL có cùng phạm vi kỹ thuật toàn thị trường và DS mã theo dõi không giới hạn. Khác nhau ở thời hạn: VIP DAY 24 giờ, FULL 1 tháng. Khi quyền hết hạn, danh sách đã lưu vẫn còn; các mã vượt gói nền sẽ khóa dữ liệu kỹ thuật.";
      if (node.textContent !== copy) node.textContent = copy;
    });

    document.querySelectorAll(".phase4-plan-choice").forEach(function (card) {
      var code = String(card.querySelector("strong") && card.querySelector("strong").textContent || "").trim().toUpperCase();
      if (code && code !== "FULL") card.remove();
    });

    document.querySelectorAll(".phase4-upgrade-head h3").forEach(function (node) {
      if (node.textContent !== "FULL 1 tháng") node.textContent = "FULL 1 tháng";
    });
    document.querySelectorAll(".phase4-upgrade-head p").forEach(function (node) {
      var copy = "Gói trả phí dài hạn duy nhất đang hiển thị. Các gói cũ được giữ cho thành viên hiện hữu nhưng không mở đăng ký mới.";
      if (node.textContent !== copy) node.textContent = copy;
    });

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
  }

  function patchLabelValue(containerSelector, label, formatter) {
    document.querySelectorAll(containerSelector + " > div").forEach(function (row) {
      var labelNode = row.querySelector("span,dt");
      var valueNode = row.querySelector("strong,dd");
      if (!labelNode || !valueNode || String(labelNode.textContent || "").trim() !== label) return;
      var next = formatter(valueNode.textContent || "");
      if (valueNode.textContent !== next) valueNode.textContent = next;
    });
  }

  function parseLeadingCount(text) {
    var match = String(text || "").match(/(\d+)/);
    return match ? Number(match[1]) : null;
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
      var dt = row.querySelector("dt"), dd = row.querySelector("dd");
      if (!dt || !dd) return;
      var key = String(dt.textContent || "").trim();
      if ((key === "DS theo dõi" || key === "Lượt đổi còn lại") && dd.textContent !== "Không giới hạn") {
        dd.textContent = "Không giới hạn";
      }
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
    if (normalizedPath() !== "/tai-khoan" || !document.querySelector(".ccc-wl-selected-row")) return;
    if (decoratingWatchlist || Date.now() - lastWatchlistDecorateAt < 1500) return;
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
      /* Best-effort UI decoration only. */
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

  async function rpc(name, body) {
    if (!global.CCCData || typeof global.CCCData.init !== "function") {
      throw new Error("CCC_DATA_UNAVAILABLE");
    }
    var sb = global.CCCData.init();
    if (!sb || typeof sb.rpc !== "function") {
      throw new Error("SUPABASE_RPC_UNAVAILABLE");
    }
    var result = await sb.rpc(name, body || {});
    if (result && result.error) throw result.error;
    return result ? result.data : null;
  }

  function requestedDate() {
    if (normalizedPath() !== GOLDEN_PATH) return "";
    var raw = new URLSearchParams(location.search).get("date") || "";
    return /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : "";
  }

  async function loadGolden(force) {
    if (goldenState.loading) return;
    var pageRoot = document.getElementById("ccc-golden-page-root");
    var overviewRoot = document.getElementById("ccc-golden-overview-root");
    if (!pageRoot && !overviewRoot) return;

    var session = await currentSession();
    var userId = session && session.user && session.user.id || "guest";
    var date = pageRoot ? requestedDate() : "";
    var key = userId + "|" + date;
    if (!force && goldenState.key === key && goldenState.data) {
      paintRoots();
      return;
    }

    goldenState.loading = true;
    goldenState.error = "";
    goldenState.key = key;
    goldenState.member = !!(session && session.user);
    paintRoots();

    try {
      if (goldenState.member) {
        var results = await Promise.all([
          rpc("get_my_golden_board", { p_trading_date: date || null }),
          rpc("get_public_golden_board", { p_trading_date: date || null })
        ]);
        goldenState.data = results[0] || {};
        goldenState.data.market_teaser = results[1] || {};
      } else {
        goldenState.data = await rpc("get_public_golden_board", { p_trading_date: date || null }) || {};
      }
      goldenState.loadedAt = Date.now();
    } catch (error) {
      goldenState.error = "Không tải được Bảng vàng. Vui lòng thử lại.";
      console.error("CCC Golden Board load failed", error);
    } finally {
      goldenState.loading = false;
      paintRoots();
    }
  }

  function stockLogoUrl(symbol) {
    var safe = String(symbol || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
    var configured = ((document.querySelector('meta[name="ccc-stock-logo-base"]') || {}).content || "").trim();
    var base = configured || "https://www.chuyenchochung.com/stock-logos";
    return String(base).replace(/\/+$/, "") + "/" + encodeURIComponent(safe) + ".webp?v=gb-v19125";
  }

  function logoHtml(row) {
    var symbol = String(row && row.symbol || "").toUpperCase();
    return '<span class="gb-logo-wrap"><img class="gb-logo" src="' + esc(stockLogoUrl(symbol)) + '" alt="" loading="lazy" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'grid\'"><span class="gb-logo-fallback">' + esc(symbol.slice(0, 3)) + '</span></span>';
  }

  function identityHtml(row, link, teaser) {
    row = row || {};
    var symbol = String(row.symbol || "").toUpperCase();
    var name = row.display_name || row.company_name || "Tên công ty đang cập nhật";
    var meta = esc(row.exchange || "");
    if (!teaser && row.signal_version) meta += (meta ? " · " : "") + esc(versionLabel(row.signal_version));
    var inner = logoHtml(row) + '<span class="gb-identity-copy"><strong>' + esc(symbol) + '</strong><span>' + esc(name) + '</span><small>' + meta + '</small></span>';
    return link
      ? '<a class="gb-identity" href="/co-phieu/' + encodeURIComponent(symbol) + '">' + inner + '</a>'
      : '<div class="gb-identity">' + inner + '</div>';
  }

  function statusHtml(row) {
    var count = Math.max(0, Math.min(4, Number(row && row.latest_signal_count || 0)));
    var keep = row && (row.still_4of4 === true || count === 4);
    return '<span class="gb-status ' + (keep ? 'is-live' : 'is-recorded') + '">' +
      (keep ? 'Đang giữ 4/4' : 'Đã ghi nhận · hiện ' + count + '/4') + '</span>';
  }

  function overviewStatusHtml(row) {
    if (row && row.__teaser) {
      return '<span class="gb-overview-status is-teaser">Teaser</span>';
    }
    var count = Math.max(0, Math.min(4, Number(row && row.latest_signal_count || 0)));
    var keep = row && (row.still_4of4 === true || count === 4);
    return '<span class="gb-overview-status ' + (keep ? 'is-live' : 'is-recorded') + '">' +
      (keep ? 'Đang 4/4' : 'Hiện ' + count + '/4') + '</span>';
  }

  function dateSelectorHtml(data) {
    var dates = Array.isArray(data && data.available_dates) ? data.available_dates : [];
    if (!dates.length) return '';
    var current = String(data.trading_date || requestedDate() || dates[0] || '');
    return '<div class="gb-date-picker gb-date-dropdown" data-golden-date-dropdown>' +
      '<span class="gb-date-label">Phiên</span>' +
      '<button type="button" class="gb-date-trigger" data-golden-date-trigger aria-haspopup="listbox" aria-expanded="false">' +
        '<strong>' + esc(formatDate(current)) + '</strong>' +
        '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
      '</button>' +
      '<div class="gb-date-menu" role="listbox" aria-label="Chọn phiên" hidden>' +
        dates.map(function (date) {
          var value = String(date || '');
          var selected = value === current;
          return '<button type="button" class="gb-date-option' + (selected ? ' is-selected' : '') + '" data-golden-date-option="' + esc(value) + '" role="option" aria-selected="' + (selected ? 'true' : 'false') + '">' +
            '<span>' + esc(formatDate(value)) + '</span><b>' + (selected ? '✓' : '') + '</b>' +
          '</button>';
        }).join('') +
      '</div>' +
    '</div>';
  }

  function fullRowHtml(row) {
    row = row || {};
    var streak = Number(row.longest_streak_hits || 0);
    var streakText = streak > 1 ? streak + ' lần quét liên tiếp' : (streak === 1 ? '1 lần quét' : '—');
    var ma200 = num(row.first_ma200_distance_pct);
    return '<article class="gb-row">' +
      '<div class="gb-row-main">' + identityHtml(row, true, false) + '<div class="gb-row-status">' + statusHtml(row) + '</div></div>' +
      '<div class="gb-metrics">' +
        '<div><span>Ghi nhận đầu</span><strong>' + esc(slot(row.first_hit_slot)) + '</strong></div>' +
        '<div><span>Lần 4/4 gần nhất</span><strong>' + esc(slot(row.last_hit_slot)) + '</strong></div>' +
        '<div><span>Số lần 4/4</span><strong>' + fmt(row.hit_count, 0) + '</strong></div>' +
        '<div><span>Chuỗi tốt nhất</span><strong>' + esc(streakText) + '</strong></div>' +
        '<div><span>Giá lúc ghi nhận</span><strong>' + fmt(row.first_price, 0) + '</strong></div>' +
        '<div><span>KL / TB10</span><strong>' + (num(row.first_daily_volume_pct) === null ? '—' : fmt(row.first_daily_volume_pct, 0) + '%') + '</strong><small>cùng mốc thời gian</small></div>' +
        '<div><span>Khoảng cách MA200</span><strong class="' + (ma200 !== null && ma200 >= 0 ? 'positive' : 'negative') + '">' + pct(row.first_ma200_distance_pct, 1) + '</strong></div>' +
        '<div><span>RVOL30 lúc ghi nhận</span><strong>' + (num(row.first_rvol30_pct) === null ? '—' : fmt(row.first_rvol30_pct, 0) + '%') + '</strong><small>nền ' + (row.first_rvol30_sessions == null ? '—' : fmt(row.first_rvol30_sessions, 0) + '/10') + '</small></div>' +
      '</div>' +
    '</article>';
  }

  function teaserRowHtml(row, delay) {
    return '<div class="gb-teaser-row">' + identityHtml(row, false, true) + '<span class="gb-teaser-time">Ghi nhận ' + esc(slot(row && row.first_hit_slot)) + (delay ? ' · trễ ' + Number(delay) + 'p' : '') + '</span></div>';
  }

  function weekLeaderHtml(data) {
    var rows = Array.isArray(data && data.week_summary) ? data.week_summary : [];
    if (!rows.length) return '';
    var leader = rows[0];
    if (Number(leader.sessions_count || 0) < 2) {
      return '<section class="gb-section gb-week"><div class="gb-section-head"><div><span class="eyebrow">TUẦN NÀY</span><h2>🏆 Mã Vàng Tuần</h2><p>Đang tích lũy thêm phiên để xếp hạng tuần.</p></div></div></section>';
    }
    return '<section class="gb-section gb-week"><div class="gb-section-head"><div><span class="eyebrow">TUẦN NÀY</span><h2>🏆 Mã Vàng Tuần</h2><p>Xếp theo số phiên 4/4 → chuỗi liên tiếp → tổng lần 4/4 → RVOL30 trung bình.</p></div><small>' + esc(formatDate(data.week_start)) + ' → ' + esc(formatDate(data.week_end)) + '</small></div>' +
      '<div class="gb-week-leader">' + identityHtml(leader, true, false) + '<div class="gb-week-stats"><span><b>' + fmt(leader.sessions_count, 0) + '</b> phiên</span><span><b>' + fmt(leader.best_streak_hits, 0) + '</b> chuỗi</span><span><b>' + fmt(leader.total_hits, 0) + '</b> lượt 4/4</span><span><b>' + (num(leader.avg_rvol30) === null ? '—' : fmt(leader.avg_rvol30, 0) + '%') + '</b> RVOL TB</span></div></div>' +
      (rows.length > 1 ? '<div class="gb-week-runner-list">' + rows.slice(1, 5).map(function (row, index) { return '<a href="/co-phieu/' + encodeURIComponent(String(row.symbol || '')) + '"><em>#' + (index + 2) + '</em><strong>' + esc(row.symbol) + '</strong><span>' + fmt(row.sessions_count, 0) + ' phiên · ' + fmt(row.total_hits, 0) + ' lượt</span></a>'; }).join('') + '</div>' : '') +
      '</section>';
  }

  function memberMarketTeaserHtml(data, accessibleRows) {
    if (!data || data.effective_full_market_access || Number(data.hidden_count || 0) <= 0) return '';
    var teaserData = data.market_teaser || {};
    var teaser = Array.isArray(teaserData.teaser_rows) ? teaserData.teaser_rows.slice() : [];
    var allowed = Object.create(null);
    (accessibleRows || []).forEach(function (row) { allowed[String(row && row.symbol || '').toUpperCase()] = true; });
    teaser = teaser.filter(function (row) { return !allowed[String(row && row.symbol || '').toUpperCase()]; }).slice(0, 2);
    if (!teaser.length) return '';
    var delay = Number(teaserData.teaser_delay_minutes || 20);
    return '<section class="gb-section gb-member-teaser"><div class="gb-section-head"><div><span class="eyebrow">HÉ MỘT CHÚT TOÀN THỊ TRƯỜNG</span><h2>Bảng vàng ngoài danh sách của bạn</h2><p>Tối đa 2 mã thật ngoài phạm vi hiện tại, hiển thị trễ ' + delay + ' phút.</p></div></div><div class="gb-teaser-list">' + teaser.map(function (row) { return teaserRowHtml(row, delay); }).join('') + '</div></section>';
  }

  function guestRightRailHtml(data, teaserCount) {
    var delay = Number(data.teaser_delay_minutes || 20);
    var marketTotal = Number(data.market_total || 0);
    var hidden = Math.max(marketTotal - Number(teaserCount || 0), 0);
    return '<aside class="gb-right-rail" aria-label="Thông tin Bảng vàng">' +
      '<section class="gb-rail-card"><span class="eyebrow">CÁCH HIỂU</span><h3>Bảng vàng là gì?</h3><p>Một mã được ghi danh khi CCC đã thực sự ghi nhận đủ <b>4/4</b> trong phiên. Sau khi vào Bảng vàng, mã vẫn nằm trong lịch sử kể cả khi tín hiệu giảm.</p><div class="gb-rail-compare"><div><strong>Đang đạt 4/4</strong><span>Trạng thái ở lần quét gần nhất</span></div><div><strong>Bảng vàng</strong><span>Đã từng đạt 4/4 trong phiên</span></div></div></section>' +
      '<section class="gb-rail-card"><span class="eyebrow">QUYỀN ĐANG XEM</span><h3>Khách · Hé một chút</h3><p>Hiển thị tối đa <b>2 mã thật</b> sau ' + delay + ' phút. Chi tiết đầy đủ theo quyền thành viên.</p>' +
        (hidden > 0 ? '<div class="gb-rail-number"><strong>' + fmt(hidden, 0) + '</strong><span>mã khác đang được giữ kín</span></div>' : '') +
        '<a class="gb-rail-action" href="/tai-khoan">Đăng nhập để xem thêm</a></section>' +
      '<section class="gb-rail-card gb-rail-note"><span class="eyebrow">LƯU Ý</span><p>Bảng vàng là nhật ký tín hiệu, không phải khuyến nghị mua/bán. Thời điểm hiển thị là lúc hệ thống ghi nhận.</p></section>' +
    '</aside>';
  }

  function memberRightRailHtml(data, rows) {
    var week = Array.isArray(data && data.week_summary) ? data.week_summary : [];
    var leader = week.length ? week[0] : null;
    var marketTotal = Number(data.market_total || 0);
    var accessible = Number(data.accessible_total == null ? (rows || []).length : data.accessible_total);
    var hidden = Number(data.hidden_count || 0);
    var still = (rows || []).filter(function (row) { return row.still_4of4 === true || Number(row.latest_signal_count || 0) === 4; }).length;
    var weekCard = '';
    if (leader && Number(leader.sessions_count || 0) >= 2) {
      weekCard = '<section class="gb-rail-card gb-rail-week"><span class="eyebrow">TUẦN NÀY</span><h3>🏆 Mã Vàng Tuần</h3>' +
        identityHtml(leader, true, false) +
        '<p class="gb-rail-week-compact"><b>' + fmt(leader.sessions_count, 0) + '</b> phiên · <b>' + fmt(leader.total_hits, 0) + '</b> lượt 4/4 · RVOL TB <b>' + (num(leader.avg_rvol30) === null ? '—' : fmt(leader.avg_rvol30, 0) + '%') + '</b></p></section>';
    } else {
      weekCard = '<section class="gb-rail-card gb-rail-week"><span class="eyebrow">TUẦN NÀY</span><h3>🏆 Mã Vàng Tuần</h3><p>Đang tích lũy thêm các phiên để xếp hạng tuần.</p></section>';
    }
    return '<aside class="gb-right-rail" aria-label="Tóm tắt Bảng vàng">' +
      '<section class="gb-rail-card"><span class="eyebrow">PHIÊN ĐANG XEM</span><h3>Tóm tắt</h3><div class="gb-rail-stats"><div><strong>' + fmt(marketTotal, 0) + '</strong><span>đã ghi danh</span></div><div><strong>' + fmt(still, 0) + '</strong><span>còn giữ 4/4</span></div><div><strong>' + fmt(accessible, 0) + '</strong><span>trong quyền xem</span></div>' + (hidden > 0 ? '<div><strong>' + fmt(hidden, 0) + '</strong><span>ngoài phạm vi</span></div>' : '') + '</div></section>' +
      weekCard +
      '<a class="gb-guide-link" href="/huong-dan">? Cách đọc Bảng vàng và các chỉ số →</a>' +
    '</aside>';
  }

  function memberPageContent(data) {
    data = data || {};
    var rows = Array.isArray(data.rows) ? data.rows : [];
    var marketTotal = Number(data.market_total || 0);
    var accessible = Number(data.accessible_total == null ? rows.length : data.accessible_total);
    var hidden = Number(data.hidden_count || 0);
    var still = rows.filter(function (row) { return row.still_4of4 === true || Number(row.latest_signal_count || 0) === 4; }).length;
    return '<div class="page-shell golden-board-page">' +
      '<header class="page-header gb-page-header"><div class="page-heading"><div><span class="eyebrow">NHẬT KÝ TÍN HIỆU</span><h1>🏆 Bảng vàng</h1><p>Mã đã từng được hệ thống ghi nhận đạt đủ 4/4 sẽ được giữ lại để xem lịch sử, kể cả khi tín hiệu sau đó giảm.</p></div>' + dateSelectorHtml(data) + '</div></header>' +
      '<div class="gb-content-grid"><div class="gb-content-main">' +
        '<section class="gb-hero-grid"><div class="gb-stat"><span>Bảng vàng phiên</span><strong>' + fmt(marketTotal, 0) + '</strong><small>mã toàn thị trường</small></div><div class="gb-stat"><span>Trong quyền xem</span><strong>' + fmt(accessible, 0) + '</strong><small>' + (data.effective_full_market_access ? 'toàn thị trường' : 'theo danh sách cá nhân') + '</small></div><div class="gb-stat"><span>Đang giữ 4/4</span><strong>' + fmt(still, 0) + '</strong><small>theo lần quét gần nhất</small></div></section>' +
        (hidden > 0 ? '<div class="gb-scope-note"><strong>🔒 ' + fmt(hidden, 0) + ' mã ngoài phạm vi hiện tại</strong><span>Bảng vàng không mở đường tắt qua giới hạn kỹ thuật của gói.</span><a href="/tai-khoan?intent=vip_day">Mở VIP DAY</a></div>' : '') +
        memberMarketTeaserHtml(data, rows) +
        '<section class="gb-section"><div class="gb-section-head"><div><span class="eyebrow">PHIÊN ' + esc(formatDate(data.trading_date)) + '</span><h2>Danh sách ghi nhận 4/4</h2><p>KL/TB10 dùng nền cùng mốc thời gian trong giờ giao dịch. RVOL30 giữ đúng số phiên nền tại thời điểm ghi nhận.</p></div><strong class="gb-result-count">' + fmt(rows.length, 0) + ' mã</strong></div>' +
          (rows.length ? '<div class="gb-list">' + rows.map(fullRowHtml).join('') + '</div>' : '<div class="gb-empty">Chưa có mã nào trong phạm vi của bạn được ghi nhận đạt 4/4 ở phiên này.</div>') +
        '</section>' +
        weekLeaderHtml(data) +
      '</div>' + memberRightRailHtml(data, rows) + '</div>' +
      '<p class="disclaimer gb-disclaimer">Bảng vàng là nhật ký tín hiệu, không phải khuyến nghị mua/bán.</p>' +
    '</div>';
  }

  function publicPageContent(data) {
    data = data || {};
    var teasers = Array.isArray(data.teaser_rows) ? data.teaser_rows : [];
    var marketTotal = Number(data.market_total || 0);
    var delay = Number(data.teaser_delay_minutes || 20);
    return '<div class="page-shell golden-board-page">' +
      '<header class="page-header gb-page-header"><div class="page-heading"><div><span class="eyebrow">NHẬT KÝ TÍN HIỆU</span><h1>🏆 Bảng vàng</h1><p>Sổ ghi danh những mã đã được CCC ghi nhận đạt đủ 4/4 trong phiên.</p></div><div class="gb-date-static">Phiên ' + esc(formatDate(data.trading_date)) + '</div></div></header>' +
      '<div class="gb-content-grid"><div class="gb-content-main">' +
        '<section class="gb-hero-grid gb-hero-grid-guest"><div class="gb-stat"><span>Đã ghi danh</span><strong>' + fmt(marketTotal, 0) + '</strong><small>mã trong phiên</small></div><div class="gb-stat"><span>Đang xem</span><strong>Khách</strong><small>tối đa 2 mã · trễ ' + delay + ' phút</small></div></section>' +
        '<section class="gb-section"><div class="gb-section-head"><div><h2>Hé một chút Bảng vàng</h2><p>Một phần nhỏ để bạn thấy Bảng vàng đang ghi nhận gì. Dữ liệu kỹ thuật đầy đủ vẫn theo quyền thành viên.</p></div></div>' +
          (teasers.length ? '<div class="gb-teaser-list">' + teasers.map(function (row) { return teaserRowHtml(row, delay); }).join('') + '</div>' : '<div class="gb-empty">Chưa có mã nào đủ ' + delay + ' phút để hé lộ ở phiên này.</div>') +
          (marketTotal > teasers.length ? '<div class="gb-lock"><strong>🔒 Còn ' + fmt(Math.max(marketTotal - teasers.length, 0), 0) + ' mã khác</strong><span>Đăng nhập để xem theo quyền thành viên; VIP DAY/FULL mở toàn thị trường.</span><a href="/tai-khoan?intent=vip_day">Đăng nhập / mở VIP DAY</a></div>' : '') +
        '</section>' +
        '<a class="gb-guide-link gb-guide-link-main" href="/huong-dan">? Xem hướng dẫn cách đọc Bảng vàng →</a>' +
      '</div>' + guestRightRailHtml(data, teasers.length) + '</div>' +
      '<p class="disclaimer gb-disclaimer">Bảng vàng là nhật ký tín hiệu, không phải khuyến nghị mua/bán.</p>' +
    '</div>';
  }

  function pageShellHtml() {
    return '<main id="main-content" class="wrap has-context-rail golden-page"><div id="ccc-golden-page-root"><div class="golden-board-page"><div class="gb-loading">Đang tải Bảng vàng…</div></div></div></main>';
  }

  function overviewShellHtml() {
    return '<section id="ccc-golden-overview-root" class="gb-overview-card"><div class="gb-overview-loading"><span></span><small>Đang tải Bảng vàng hôm nay…</small></div></section>';
  }

  function memberOverviewContent(data) {
    data = data || {};
    var sourceRows = Array.isArray(data.rows) ? data.rows : [];
    var rows = sourceRows.slice(0, 3);

    if (!data.effective_full_market_access && rows.length < 3 && data.market_teaser && Array.isArray(data.market_teaser.teaser_rows)) {
      var seen = Object.create(null);
      rows.forEach(function (row) { seen[String(row.symbol || '').toUpperCase()] = true; });
      data.market_teaser.teaser_rows.forEach(function (row) {
        var symbol = String(row && row.symbol || '').toUpperCase();
        if (rows.length < 3 && symbol && !seen[symbol]) {
          var copy = clone(row) || {};
          copy.__teaser = true;
          rows.push(copy);
          seen[symbol] = true;
        }
      });
    }

    var marketTotal = Number(data.market_total || 0);
    var hidden = Number(data.hidden_count || 0);
    var still = sourceRows.filter(function (row) {
      return row && (row.still_4of4 === true || Number(row.latest_signal_count || 0) === 4);
    }).length;
    var displayedReal = rows.filter(function (row) { return !row.__teaser; }).length;
    var remaining = Math.max(marketTotal - displayedReal, 0);

    var body = rows.length ? '<div class="gb-overview-list-rich">' + rows.map(function (row) {
      var hit = row.__teaser ? '—' : fmt(row.hit_count, 0);
      return '<div class="gb-overview-row-rich">' +
        identityHtml(row, false, !!row.__teaser) +
        '<div class="gb-overview-mini"><span>Vào</span><strong>' + esc(slot(row.first_hit_slot)) + '</strong></div>' +
        '<div class="gb-overview-mini"><span>Lượt 4/4</span><strong>' + hit + '</strong></div>' +
        '<div class="gb-overview-state">' + overviewStatusHtml(row) + '</div>' +
      '</div>';
    }).join('') + '</div>' : '';

    var foot = '';
    if (hidden > 0) {
      foot = '<div class="gb-overview-footline"><span>🔒 ' + fmt(hidden, 0) + ' mã ngoài phạm vi kỹ thuật hiện tại.</span><a href="/bang-vang">Xem theo quyền →</a></div>';
    } else if (remaining > 0) {
      foot = '<div class="gb-overview-footline"><span>+ ' + fmt(remaining, 0) + ' mã khác trong Bảng vàng.</span><a href="/bang-vang">Xem tất cả →</a></div>';
    } else {
      foot = '<div class="gb-overview-footline"><span>Mã đã vào Bảng vàng vẫn được lưu dù tín hiệu sau đó giảm.</span><a href="/bang-vang">Xem lịch sử →</a></div>';
    }

    return '<div class="gb-overview-head gb-overview-head-rich">' +
      '<div><span class="eyebrow">TÍCH LŨY TRONG PHIÊN</span><h2>🏆 Bảng vàng hôm nay</h2>' +
      '<div class="gb-overview-summary"><span><b>' + fmt(marketTotal, 0) + '</b> đã ghi danh</span><span class="is-live"><b>' + fmt(still, 0) + '</b> còn giữ 4/4</span></div></div>' +
      '<a href="/bang-vang">Xem Bảng vàng →</a></div>' +
      body + foot;
  }

  function publicOverviewContent(data) {
    data = data || {};
    var rows = Array.isArray(data.teaser_rows) ? data.teaser_rows.slice(0, 2) : [];
    var marketTotal = Number(data.market_total || 0);
    var hidden = Math.max(marketTotal - rows.length, 0);
    var delay = Number(data.teaser_delay_minutes || 20);

    var body = rows.length ? '<div class="gb-overview-list-rich">' + rows.map(function (row) {
      var copy = clone(row) || {};
      copy.__teaser = true;
      return '<div class="gb-overview-row-rich">' +
        identityHtml(copy, false, true) +
        '<div class="gb-overview-mini"><span>Vào</span><strong>' + esc(slot(copy.first_hit_slot)) + '</strong></div>' +
        '<div class="gb-overview-mini"><span>Độ trễ</span><strong>' + fmt(delay, 0) + 'p</strong></div>' +
        '<div class="gb-overview-state">' + overviewStatusHtml(copy) + '</div>' +
      '</div>';
    }).join('') + '</div>' : '<div class="gb-overview-empty-compact">Chưa có mã nào đủ thời gian để hé lộ ở phiên này.</div>';

    return '<div class="gb-overview-head gb-overview-head-rich"><div><span class="eyebrow">TÍCH LŨY TRONG PHIÊN</span><h2>🏆 Bảng vàng hôm nay</h2>' +
      '<div class="gb-overview-summary"><span><b>' + fmt(marketTotal, 0) + '</b> đã ghi danh</span><span><b>Khách</b> xem teaser trễ ' + fmt(delay, 0) + 'p</span></div></div>' +
      '<a href="/bang-vang">Xem Bảng vàng →</a></div>' +
      body +
      (hidden > 0
        ? '<div class="gb-overview-footline"><span>🔒 Còn ' + fmt(hidden, 0) + ' mã khác.</span><a href="/tai-khoan">Đăng nhập →</a></div>'
        : '<div class="gb-overview-footline"><span>Bảng vàng lưu lịch sử, không chỉ trạng thái hiện tại.</span><a href="/bang-vang">Tìm hiểu →</a></div>');
  }

  function contextUpdatedTime(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "—";
    return date.toLocaleTimeString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Ho_Chi_Minh"
    });
  }

  function overviewContextHtml(data) {
    data = data || {};
    var rows = Array.isArray(data.sample_rows) ? data.sample_rows : [];
    var row = rows[0] || {};
    var tradingDate = row.trading_date || "";
    var timeSlot = row.time_slot || "";
    var marketTotal = Number(data.market_total || 0);
    var syncedAt = data.last_updated_at || row.updated_at || "";
    var dateLabel = tradingDate ? formatDate(tradingDate) : "—";
    var slotLabel = timeSlot ? slot(timeSlot) : "—";
    var syncLabel = contextUpdatedTime(syncedAt);
    var title = "Mốc quét là thời điểm dữ liệu kỹ thuật trong stock_snapshot. Giờ đồng bộ là thời điểm bản ghi được cập nhật vào hệ thống.";

    return '<div class="ccc-data-context-main" title="' + esc(title) + '">' +
      '<span class="ccc-data-context-dot" aria-hidden="true"></span>' +
      '<strong>Dữ liệu kỹ thuật</strong>' +
      '<span class="ccc-data-context-sep" aria-hidden="true"></span>' +
      '<span>Phiên <b>' + esc(dateLabel) + '</b></span>' +
      '<span class="ccc-data-context-sep" aria-hidden="true"></span>' +
      '<span>Mốc quét <b>' + esc(slotLabel) + '</b></span>' +
      '<span class="ccc-data-context-sep" aria-hidden="true"></span>' +
      '<span><b>' + fmt(marketTotal, 0) + '</b> mã</span>' +
      '</div>' +
      '<small class="ccc-data-context-sync">Đồng bộ ' + esc(syncLabel) + '</small>';
  }

  function paintOverviewContext() {
    var root = document.getElementById("ccc-data-context-strip");
    if (!root) return;
    if (overviewContextState.data) {
      root.innerHTML = overviewContextHtml(overviewContextState.data);
      root.classList.remove("is-loading", "is-error");
      return;
    }
    if (overviewContextState.error) {
      root.classList.add("is-error");
      root.innerHTML = '<div class="ccc-data-context-main"><span class="ccc-data-context-dot"></span><strong>Dữ liệu kỹ thuật</strong><span>Chưa đọc được thời gian snapshot.</span></div>';
      return;
    }
    root.classList.add("is-loading");
    root.innerHTML = '<div class="ccc-data-context-main"><span class="ccc-data-context-dot"></span><strong>Dữ liệu kỹ thuật</strong><span>Đang đọc mốc dữ liệu…</span></div>';
  }

  function ensureOverviewContextStrip() {
    if (normalizedPath() !== "/") return;
    var header = document.querySelector(".overview-main > .page-header") ||
      document.querySelector("main.wrap .page-header");
    if (!header) return;
    var root = document.getElementById("ccc-data-context-strip");
    if (!root) {
      root = document.createElement("section");
      root.id = "ccc-data-context-strip";
      root.className = "ccc-data-context-strip";
      root.setAttribute("aria-label", "Thời gian dữ liệu kỹ thuật");
      header.insertAdjacentElement("afterend", root);
    }
    paintOverviewContext();
  }

  async function loadOverviewContext(force) {
    if (normalizedPath() !== "/") return;
    var now = Date.now();
    if (!force && overviewContextState.data && now - overviewContextState.loadedAt < 60000) {
      paintOverviewContext();
      return;
    }
    if (overviewContextState.loading) return;

    var bridge = global.CCCData || originalData;
    if (!bridge || typeof bridge.getPublicOverviewState !== "function") return;

    overviewContextState.loading = true;
    overviewContextState.error = "";
    paintOverviewContext();
    try {
      overviewContextState.data = await bridge.getPublicOverviewState() || {};
      overviewContextState.loadedAt = Date.now();
    } catch (error) {
      overviewContextState.error = "OVERVIEW_CONTEXT_UNAVAILABLE";
      console.warn("CCC overview data context load failed", error);
    } finally {
      overviewContextState.loading = false;
      paintOverviewContext();
    }
  }

  function paintPageRoot() {
    var root = document.getElementById("ccc-golden-page-root");
    if (!root) return;
    if (goldenState.loading && !goldenState.data) {
      root.innerHTML = '<section class="golden-loading"><span></span><div><strong>Đang tải Bảng vàng…</strong><p>Đang đọc lịch sử 4/4 và quyền thành viên hiện tại.</p></div></section>';
      return;
    }
    if (goldenState.error && !goldenState.data) {
      root.innerHTML = '<section class="golden-error"><strong>Không tải được Bảng vàng.</strong><p>' + esc(goldenState.error) + '</p><button type="button" data-golden-retry>Thử lại</button></section>';
      return;
    }
    if (!goldenState.data) return;
    root.innerHTML = goldenState.member ? memberPageContent(goldenState.data) : publicPageContent(goldenState.data);
  }

  function paintOverviewRoot() {
    var root = document.getElementById("ccc-golden-overview-root");
    if (!root) return;
    if (goldenState.loading && !goldenState.data) return;
    if (goldenState.error && !goldenState.data) {
      root.innerHTML = '<header class="ccc-golden-overview-head"><div><span>BẢNG VÀNG 4/4</span><h2>Bảng vàng hôm nay</h2></div><a href="/bang-vang">Xem chi tiết →</a></header><div class="ccc-golden-overview-empty">Tạm thời chưa tải được Bảng vàng.</div>';
      return;
    }
    if (!goldenState.data) return;
    root.innerHTML = goldenState.member ? memberOverviewContent(goldenState.data) : publicOverviewContent(goldenState.data);
  }

  function paintRoots() {
    paintPageRoot();
    paintOverviewRoot();
  }

  function afterCoreRender() {
    replaceTextNodes(document.getElementById("app") || document.body);
    patchTb10Help();
    patchPackages();
    patchVipUnlimitedUi();
    decorateRetainedWatchlist();
    ensureOverviewContextStrip();
    paintRoots();
    if (normalizedPath() === "/") loadOverviewContext(false);
    if ((document.getElementById("ccc-golden-page-root") || document.getElementById("ccc-golden-overview-root")) && !goldenState.loading) {
      loadGolden(false);
    }
  }

  function reload() {
    goldenState.key = "";
    goldenState.error = "";
    return loadGolden(true);
  }

  function closeGoldenDateDropdowns(except) {
    document.querySelectorAll("[data-golden-date-dropdown]").forEach(function (dropdown) {
      if (except && dropdown === except) return;
      var trigger = dropdown.querySelector("[data-golden-date-trigger]");
      var menu = dropdown.querySelector(".gb-date-menu");
      if (trigger) trigger.setAttribute("aria-expanded", "false");
      if (menu) menu.hidden = true;
      dropdown.classList.remove("is-open");
    });
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    var trigger = target && target.closest ? target.closest("[data-golden-date-trigger]") : null;
    if (trigger) {
      event.preventDefault();
      var dropdown = trigger.closest("[data-golden-date-dropdown]");
      var menu = dropdown && dropdown.querySelector(".gb-date-menu");
      var willOpen = trigger.getAttribute("aria-expanded") !== "true";
      closeGoldenDateDropdowns(dropdown);
      trigger.setAttribute("aria-expanded", willOpen ? "true" : "false");
      if (menu) menu.hidden = !willOpen;
      if (dropdown) dropdown.classList.toggle("is-open", willOpen);
      return;
    }

    var option = target && target.closest ? target.closest("[data-golden-date-option]") : null;
    if (option) {
      event.preventDefault();
      var date = String(option.getAttribute("data-golden-date-option") || "");
      closeGoldenDateDropdowns();
      var url = new URL(location.href);
      if (date) url.searchParams.set("date", date);
      else url.searchParams.delete("date");
      history.replaceState(history.state || null, "", url.pathname + url.search);
      goldenState.data = null;
      goldenState.key = "";
      loadGolden(true);
      return;
    }

    if (!target || !target.closest || !target.closest("[data-golden-date-dropdown]")) {
      closeGoldenDateDropdowns();
    }

    var retry = target && target.closest ? target.closest("[data-golden-retry]") : null;
    if (!retry) return;
    event.preventDefault();
    goldenState.data = null;
    goldenState.error = "";
    goldenState.key = "";
    loadGolden(true);
  });

  window.addEventListener("focus", function () {
    if ((document.getElementById("ccc-golden-page-root") || document.getElementById("ccc-golden-overview-root")) && Date.now() - goldenState.loadedAt > 60000) {
      reload();
    }
    if (normalizedPath() === "/" && Date.now() - overviewContextState.loadedAt > 60000) {
      loadOverviewContext(true);
    }
  });

  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(function () {
    if (document.getElementById("ccc-golden-page-root") || document.getElementById("ccc-golden-overview-root")) reload();
  }, 5 * 60 * 1000);

  global.CCCGolden = Object.freeze({
    version: RELEASE,
    tb10Help: TB10_HELP,
    pageShellHtml: pageShellHtml,
    overviewShellHtml: overviewShellHtml,
    afterCoreRender: afterCoreRender,
    reload: reload,
    reloadDataContext: function () { return loadOverviewContext(true); }
  });
})(window);
