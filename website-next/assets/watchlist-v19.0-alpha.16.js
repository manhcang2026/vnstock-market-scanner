(function () {
  "use strict";

  var ACCOUNT_PATH = "/tai-khoan";
  var WATCHLIST_CARD_MARKER = "ccc-watchlist-live";
  var state = {
    client: null,
    userId: "",
    loading: false,
    saving: false,
    universeLoading: false,
    universeLoaded: false,
    watchlist: null,
    universe: [],
    universeBySymbol: Object.create(null),
    originalSymbols: [],
    selectedSymbols: [],
    query: "",
    error: "",
    notice: ""
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function isAccountRoute() {
    return window.location.pathname === ACCOUNT_PATH;
  }

  function getClient() {
    if (state.client) return state.client;
    if (window.__cccSupabaseClient) {
      state.client = window.__cccSupabaseClient;
      return state.client;
    }
    if (Array.isArray(window.__cccSupabaseClients) && window.__cccSupabaseClients.length) {
      state.client = window.__cccSupabaseClients[window.__cccSupabaseClients.length - 1];
      return state.client;
    }
    return null;
  }

  function formatDateTime(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "—";
    return date.toLocaleString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
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

  function addedSymbols() {
    var oldMap = Object.create(null);
    state.originalSymbols.forEach(function (symbol) { oldMap[symbol] = true; });
    return state.selectedSymbols.filter(function (symbol) { return !oldMap[symbol]; });
  }

  function removedSymbols() {
    var newMap = Object.create(null);
    state.selectedSymbols.forEach(function (symbol) { newMap[symbol] = true; });
    return state.originalSymbols.filter(function (symbol) { return !newMap[symbol]; });
  }

  function isFull() {
    return !!(state.watchlist && state.watchlist.full_market_access);
  }

  function capacityLimit() {
    if (!state.watchlist || state.watchlist.watchlist_limit == null) return null;
    return Number(state.watchlist.watchlist_limit);
  }

  function currentQuotaRemaining() {
    if (!state.watchlist || state.watchlist.change_remaining == null) return null;
    return Number(state.watchlist.change_remaining);
  }

  function canAddLocally() {
    var limit = capacityLimit();
    return limit == null || state.selectedSymbols.length < limit;
  }

  function findWatchlistCard() {
    var root = document.getElementById("ccc-account-page-root");
    if (!root || !isAccountRoute()) return null;
    var cards = root.querySelectorAll(".ccc-account-card");
    for (var i = 0; i < cards.length; i += 1) {
      var kicker = cards[i].querySelector(".ccc-account-kicker");
      if (kicker && /WATCHLIST/i.test(kicker.textContent || "")) return cards[i];
    }
    return null;
  }

  function stateLabel() {
    if (!state.watchlist) return "Đang tải";
    if (state.watchlist.status === "GRACE") return "Chờ gia hạn";
    if (state.watchlist.setup_active) return "Đang khởi tạo";
    return "Đang hoạt động";
  }

  function stateClass() {
    if (!state.watchlist) return "pending";
    if (state.watchlist.status === "GRACE") return "pending";
    return "ok";
  }

  function limitLabel(value, suffix) {
    if (value == null) return "Không giới hạn";
    return Number(value).toLocaleString("vi-VN") + (suffix || "");
  }

  function quotaLabel() {
    if (!state.watchlist) return "—";
    if (state.watchlist.change_limit == null) return "Không giới hạn";
    return Number(state.watchlist.change_remaining || 0) + "/" + Number(state.watchlist.change_limit || 0);
  }

  function setupNoticeHtml() {
    if (!state.watchlist) return "";
    if (state.watchlist.status === "GRACE") {
      return '<div class="ccc-wl-banner danger"><strong>Gói đang chờ gia hạn.</strong><span>Watchlist vẫn được giữ đến ' + esc(formatDateTime(state.watchlist.grace_end_at)) + '. Hết thời gian này nếu chưa thanh toán, Watchlist trả phí sẽ bị xóa và tài khoản chuyển về FREE.</span></div>';
    }
    if (state.watchlist.setup_active) {
      return '<div class="ccc-wl-banner info"><strong>7 ngày khởi tạo miễn phí.</strong><span>Bạn có thể thêm mã trong phạm vi gói mà chưa trừ quota đến ' + esc(formatDateTime(state.watchlist.setup_window_end)) + '.</span></div>';
    }
    if (Number(state.watchlist.upgrade_free_additions_remaining || 0) > 0 && state.watchlist.upgrade_free_additions_end_at) {
      return '<div class="ccc-wl-banner info"><strong>Quyền bổ sung sau nâng cấp.</strong><span>Còn ' + esc(state.watchlist.upgrade_free_additions_remaining) + ' mã capacity mới được thêm miễn phí đến ' + esc(formatDateTime(state.watchlist.upgrade_free_additions_end_at)) + '.</span></div>';
    }
    return "";
  }

  function selectedListHtml() {
    if (!state.selectedSymbols.length) {
      return '<div class="ccc-wl-empty">Chưa có mã nào trong Watchlist.</div>';
    }
    return '<div class="ccc-wl-selected">' + state.selectedSymbols.map(function (symbol) {
      var meta = state.universeBySymbol[symbol] || {};
      var title = meta.display_name || meta.company_name || symbol;
      return '<span class="ccc-wl-chip" title="' + esc(title) + '"><b>' + esc(symbol) + '</b><button type="button" data-wl-remove="' + esc(symbol) + '" aria-label="Xóa ' + esc(symbol) + '">×</button></span>';
    }).join("") + '</div>';
  }

  function searchResultsHtml() {
    var q = String(state.query || "").trim().toUpperCase();
    if (!q) return "";
    if (state.universeLoading) return '<div class="ccc-wl-search-results"><div class="ccc-wl-search-status">Đang tải danh sách mã…</div></div>';
    if (!state.universeLoaded) return '<div class="ccc-wl-search-results"><div class="ccc-wl-search-status">Không tải được danh sách mã.</div></div>';

    var selectedMap = Object.create(null);
    state.selectedSymbols.forEach(function (symbol) { selectedMap[symbol] = true; });

    var matches = state.universe.filter(function (item) {
      if (selectedMap[item.symbol]) return false;
      var haystack = [item.symbol, item.display_name, item.company_name].join(" ").toUpperCase();
      return haystack.indexOf(q) >= 0;
    }).slice(0, 8);

    if (!matches.length) return '<div class="ccc-wl-search-results"><div class="ccc-wl-search-status">Không tìm thấy mã phù hợp.</div></div>';

    return '<div class="ccc-wl-search-results">' + matches.map(function (item) {
      var name = item.display_name || item.company_name || "";
      return '<button type="button" class="ccc-wl-result" data-wl-add="' + esc(item.symbol) + '"' + (canAddLocally() ? '' : ' disabled') + '><span><b>' + esc(item.symbol) + '</b><small>' + esc(name) + '</small></span><em>+ Thêm</em></button>';
    }).join("") + '</div>';
  }

  function feedbackHtml() {
    if (state.error) return '<div class="ccc-wl-feedback error" role="alert">' + esc(state.error) + '</div>';
    if (state.notice) return '<div class="ccc-wl-feedback success" role="status">' + esc(state.notice) + '</div>';
    return "";
  }

  function renderCard() {
    var card = findWatchlistCard();
    if (!card) return;
    card.setAttribute("data-" + WATCHLIST_CARD_MARKER, "1");
    card.classList.add("ccc-watchlist-live-card");

    if (state.loading && !state.watchlist) {
      card.innerHTML = '' +
        '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">WATCHLIST & LƯỢT ĐỔI</span><h2>Danh sách theo dõi</h2><p>Đang đọc Watchlist và quota thật từ hệ thống.</p></div><span class="ccc-account-status pending">Đang tải</span></header>' +
        '<div class="ccc-wl-loading"><span class="ccc-auth-spinner" aria-hidden="true"></span><span>Đang tải Watchlist…</span></div>';
      return;
    }

    if (!state.watchlist) {
      card.innerHTML = '' +
        '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">WATCHLIST & LƯỢT ĐỔI</span><h2>Danh sách theo dõi</h2><p>Quản lý danh sách mã theo gói thành viên.</p></div><span class="ccc-account-status pending">Chưa sẵn sàng</span></header>' +
        feedbackHtml() +
        '<button type="button" class="ccc-account-secondary" id="ccc-wl-retry">Thử lại</button>';
      bindCard(card);
      return;
    }

    var dirty = !arraysEqual(state.originalSymbols, state.selectedSymbols);
    var adds = addedSymbols().length;
    var removes = removedSymbols().length;
    var capacity = capacityLimit();
    var quotaRemaining = currentQuotaRemaining();
    var estimatedQuota = state.watchlist.setup_active || isFull() ? 0 : adds;
    var quotaWarning = "";

    if (!state.watchlist.setup_active && !isFull() && quotaRemaining != null && estimatedQuota > quotaRemaining) {
      quotaWarning = '<div class="ccc-wl-feedback error">Bạn đang thêm ' + adds + ' mã nhưng chỉ còn ' + quotaRemaining + ' quota. Hệ thống sẽ không lưu một phần.</div>';
    }

    card.innerHTML = '' +
      '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">WATCHLIST & LƯỢT ĐỔI</span><h2>Danh sách theo dõi</h2><p>Watchlist được giữ xuyên suốt gói; hàng tháng chỉ reset quota đổi mã.</p></div><span class="ccc-account-status ' + stateClass() + '">' + esc(stateLabel()) + '</span></header>' +
      '<div class="ccc-wl-metrics">' +
        '<div><span>Đang theo dõi</span><strong>' + state.selectedSymbols.length + (capacity == null ? '' : '/' + capacity) + '</strong></div>' +
        '<div><span>Quota đổi còn lại</span><strong>' + esc(quotaLabel()) + '</strong></div>' +
        '<div><span>Reset tiếp theo</span><strong>' + esc(formatDate(state.watchlist.cycle_end)) + '</strong></div>' +
      '</div>' +
      setupNoticeHtml() +
      feedbackHtml() +
      quotaWarning +
      '<div class="ccc-wl-editor">' +
        '<div class="ccc-wl-search-wrap">' +
          '<label for="ccc-wl-search">Thêm mã</label>' +
          '<input id="ccc-wl-search" type="search" inputmode="search" autocomplete="off" placeholder="Nhập mã hoặc tên công ty…" value="' + esc(state.query) + '"' + (canAddLocally() ? '' : ' disabled') + '>' +
          searchResultsHtml() +
        '</div>' +
        '<div class="ccc-wl-list-head"><span>Mã đang chọn</span><small>' + (dirty ? ('Thay đổi: +' + adds + ' / -' + removes) : 'Chưa có thay đổi') + '</small></div>' +
        selectedListHtml() +
      '</div>' +
      '<div class="ccc-wl-actions">' +
        '<button type="button" class="ccc-account-secondary" id="ccc-wl-reset"' + (!dirty || state.saving ? ' disabled' : '') + '>Hoàn tác</button>' +
        '<button type="button" class="ccc-account-primary" id="ccc-wl-save"' + (!dirty || state.saving ? ' disabled' : '') + '>' + (state.saving ? 'Đang lưu…' : 'Lưu Watchlist') + '</button>' +
      '</div>' +
      '<p class="ccc-wl-rule-note">Xóa mã không trừ quota. Sau thời gian miễn phí, mỗi mã ADD mới trừ 1 quota; xóa rồi thêm lại cùng mã vẫn tính 1.</p>';

    bindCard(card);
  }

  function friendlyError(error) {
    var message = String(error && error.message ? error.message : error || "");
    if (message.indexOf("WATCHLIST_LIMIT_EXCEEDED") >= 0) return "Số mã vượt giới hạn Watchlist của gói hiện tại.";
    if (message.indexOf("CHANGE_QUOTA_EXCEEDED") >= 0) return "Không đủ quota đổi mã để thực hiện thay đổi này.";
    if (message.indexOf("INVALID_SYMBOL") >= 0) return "Có mã không thuộc Scanner Universe hiện tại.";
    if (message.indexOf("SUBSCRIPTION_SUSPENDED") >= 0) return "Tài khoản đang tạm ngưng quyền thay đổi Watchlist.";
    if (message.indexOf("NO_CURRENT_SUBSCRIPTION") >= 0) return "Không tìm thấy gói thành viên đang hoạt động.";
    if (message.indexOf("AUTH_REQUIRED") >= 0) return "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.";
    return "Không cập nhật được Watchlist. Vui lòng thử lại.";
  }

  async function ensureUser() {
    var client = getClient();
    if (!client) return null;
    try {
      var result = await client.auth.getSession();
      if (result.error) throw result.error;
      var user = result.data && result.data.session ? result.data.session.user : null;
      if (!user) return null;
      return user;
    } catch (_) {
      return null;
    }
  }

  async function loadUniverse() {
    if (state.universeLoading || state.universeLoaded) return;
    var client = getClient();
    if (!client) return;
    state.universeLoading = true;
    renderCard();
    try {
      var result = await client
        .from("stock_metadata")
        .select("symbol,display_name,company_name,exchange")
        .order("symbol", { ascending: true });
      if (result.error) throw result.error;
      state.universe = Array.isArray(result.data) ? result.data.map(function (row) {
        return {
          symbol: String(row.symbol || "").trim().toUpperCase(),
          display_name: row.display_name || "",
          company_name: row.company_name || "",
          exchange: row.exchange || ""
        };
      }).filter(function (row) { return !!row.symbol; }) : [];
      state.universeBySymbol = Object.create(null);
      state.universe.forEach(function (row) { state.universeBySymbol[row.symbol] = row; });
      state.universeLoaded = true;
    } catch (error) {
      console.error("CCC watchlist universe load failed", error);
      state.universeLoaded = false;
    } finally {
      state.universeLoading = false;
      renderCard();
    }
  }

  async function loadWatchlist(force) {
    if (!isAccountRoute() || state.loading) return;
    var client = getClient();
    if (!client) {
      state.error = "Chưa kết nối được Supabase cho Watchlist.";
      renderCard();
      return;
    }

    var user = await ensureUser();
    if (!user) return;
    if (state.userId && state.userId !== user.id) resetForAuthChange();
    if (!force && state.watchlist && state.userId === user.id) {
      renderCard();
      return;
    }
    state.userId = user.id;

    state.loading = true;
    state.error = "";
    renderCard();
    try {
      var result = await client.rpc("get_my_watchlist_state");
      if (result.error) throw result.error;
      state.watchlist = result.data || null;
      state.originalSymbols = uniqueSorted(state.watchlist && state.watchlist.symbols || []);
      state.selectedSymbols = state.originalSymbols.slice();
      state.query = "";
      await loadUniverse();
    } catch (error) {
      console.error("CCC watchlist state load failed", error);
      state.error = friendlyError(error);
      state.watchlist = null;
    } finally {
      state.loading = false;
      renderCard();
    }
  }

  async function saveWatchlist() {
    if (state.saving || !state.watchlist) return;
    var client = getClient();
    if (!client) return;

    state.saving = true;
    state.error = "";
    state.notice = "";
    renderCard();
    try {
      var result = await client.rpc("replace_my_watchlist", {
        p_symbols: uniqueSorted(state.selectedSymbols)
      });
      if (result.error) throw result.error;
      state.watchlist = result.data || state.watchlist;
      state.originalSymbols = uniqueSorted(state.watchlist.symbols || state.selectedSymbols);
      state.selectedSymbols = state.originalSymbols.slice();
      state.query = "";
      state.notice = "Đã lưu Watchlist thành công.";
    } catch (error) {
      console.error("CCC watchlist save failed", error);
      state.error = friendlyError(error);
    } finally {
      state.saving = false;
      renderCard();
    }
  }

  function addSymbol(symbol) {
    symbol = String(symbol || "").trim().toUpperCase();
    if (!symbol || state.selectedSymbols.indexOf(symbol) >= 0) return;
    if (!canAddLocally()) {
      state.error = "Watchlist đã đạt giới hạn của gói hiện tại.";
      renderCard();
      return;
    }
    state.selectedSymbols.push(symbol);
    state.selectedSymbols.sort();
    state.query = "";
    state.error = "";
    state.notice = "";
    renderCard();
  }

  function removeSymbol(symbol) {
    symbol = String(symbol || "").trim().toUpperCase();
    state.selectedSymbols = state.selectedSymbols.filter(function (item) { return item !== symbol; });
    state.error = "";
    state.notice = "";
    renderCard();
  }

  function bindCard(card) {
    var retry = card.querySelector("#ccc-wl-retry");
    if (retry) retry.addEventListener("click", function () { loadWatchlist(true); });

    var search = card.querySelector("#ccc-wl-search");
    if (search) {
      search.addEventListener("input", function () {
        state.query = search.value || "";
        state.error = "";
        state.notice = "";
        renderCard();
        requestAnimationFrame(function () {
          var next = document.getElementById("ccc-wl-search");
          if (next) {
            next.focus();
            try { next.setSelectionRange(next.value.length, next.value.length); } catch (_) {}
          }
        });
      });
    }

    card.querySelectorAll("[data-wl-add]").forEach(function (button) {
      button.addEventListener("click", function () { addSymbol(button.getAttribute("data-wl-add")); });
    });

    card.querySelectorAll("[data-wl-remove]").forEach(function (button) {
      button.addEventListener("click", function () { removeSymbol(button.getAttribute("data-wl-remove")); });
    });

    var reset = card.querySelector("#ccc-wl-reset");
    if (reset) reset.addEventListener("click", function () {
      state.selectedSymbols = state.originalSymbols.slice();
      state.query = "";
      state.error = "";
      state.notice = "";
      renderCard();
    });

    var save = card.querySelector("#ccc-wl-save");
    if (save) save.addEventListener("click", saveWatchlist);
  }

  function patchWhenReady() {
    if (!isAccountRoute()) return;
    var card = findWatchlistCard();
    if (!card) return;
    if (!card.hasAttribute("data-" + WATCHLIST_CARD_MARKER)) renderCard();
    if (!state.watchlist && !state.loading) loadWatchlist(false);
  }

  function resetForAuthChange() {
    state.userId = "";
    state.watchlist = null;
    state.originalSymbols = [];
    state.selectedSymbols = [];
    state.query = "";
    state.error = "";
    state.notice = "";
  }

  function init() {
    var attempts = 0;
    var timer = window.setInterval(function () {
      attempts += 1;
      var client = getClient();
      if (client || attempts >= 50) {
        window.clearInterval(timer);
        if (client && client.auth && typeof client.auth.onAuthStateChange === "function") {
          client.auth.onAuthStateChange(function (event, session) {
            var nextUserId = session && session.user ? session.user.id : "";
            if (event === "SIGNED_OUT" || (state.userId && nextUserId && state.userId !== nextUserId)) {
              resetForAuthChange();
            }
            window.setTimeout(patchWhenReady, 0);
          });
        }
        patchWhenReady();
      }
    }, 50);

    var root = document.getElementById("ccc-account-page-root") || document.body;
    var scheduled = false;
    var observer = new MutationObserver(function () {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(function () {
        scheduled = false;
        patchWhenReady();
      });
    });
    observer.observe(root, { childList: true, subtree: true });

    window.addEventListener("popstate", function () { window.setTimeout(patchWhenReady, 0); });
    document.addEventListener("click", function () { window.setTimeout(patchWhenReady, 0); }, true);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
