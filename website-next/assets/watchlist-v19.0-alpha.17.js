(function () {
  "use strict";

  var ACCOUNT_PATH = "/tai-khoan";
  var LOGO_BASE_URL = "/assets/logos/";
  var LOGO_VERSION = "1741";
  var state = {
    client: null,
    userId: "",
    loading: false,
    saving: false,
    watchlist: null,
    originalSymbols: [],
    selectedSymbols: [],
    metadataBySymbol: Object.create(null),
    query: "",
    searchLoading: false,
    searchResults: [],
    searchSeq: 0,
    searchTimer: null,
    error: "",
    notice: ""
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function isAccountRoute() { return window.location.pathname === ACCOUNT_PATH; }

  function getClient() {
    if (state.client) return state.client;
    if (window.__cccSupabaseClient) state.client = window.__cccSupabaseClient;
    else if (Array.isArray(window.__cccSupabaseClients) && window.__cccSupabaseClients.length) state.client = window.__cccSupabaseClients[window.__cccSupabaseClients.length - 1];
    return state.client;
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

  function uniqueSorted(values) {
    var seen = Object.create(null);
    return (values || []).map(function (value) { return String(value || "").trim().toUpperCase(); }).filter(function (value) {
      if (!value || seen[value]) return false;
      seen[value] = true;
      return true;
    }).sort();
  }

  function arraysEqual(a, b) {
    var left = uniqueSorted(a), right = uniqueSorted(b);
    if (left.length !== right.length) return false;
    for (var i = 0; i < left.length; i += 1) if (left[i] !== right[i]) return false;
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

  function isFull() { return !!(state.watchlist && state.watchlist.full_market_access); }
  function capacityLimit() { return !state.watchlist || state.watchlist.watchlist_limit == null ? null : Number(state.watchlist.watchlist_limit); }
  function quotaRemaining() { return !state.watchlist || state.watchlist.change_remaining == null ? null : Number(state.watchlist.change_remaining); }
  function canAddLocally() { var limit = capacityLimit(); return limit == null || state.selectedSymbols.length < limit; }

  function logoHtml(symbol, extra) {
    var safe = String(symbol || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
    var fallback = safe.slice(0, 3) || "?";
    return '<span class="ccc-wl-logo ' + esc(extra || "") + '"><img src="' + LOGO_BASE_URL + esc(safe) + '.jpg?v=' + LOGO_VERSION + '" alt="" decoding="async" onerror="this.remove()"><span>' + esc(fallback) + '</span></span>';
  }

  function findWatchlistCard() {
    var root = document.getElementById("ccc-account-page-root");
    if (!root || !isAccountRoute()) return null;
    var cards = root.querySelectorAll(".ccc-account-card");
    for (var i = 0; i < cards.length; i += 1) {
      var kicker = cards[i].querySelector(".ccc-account-kicker");
      var title = cards[i].querySelector("h2");
      var text = ((kicker && kicker.textContent) || "") + " " + ((title && title.textContent) || "");
      if (/WATCHLIST|DANH SÁCH THEO DÕI|DS MÃ THEO DÕI/i.test(text)) return cards[i];
    }
    return null;
  }

  function relayoutAccount() {
    if (!isAccountRoute()) return;
    var root = document.getElementById("ccc-account-page-root");
    if (!root) return;
    var main = root.querySelector(".ccc-account-main");
    var side = root.querySelector(".ccc-account-side");
    var wl = findWatchlistCard();
    var membership = root.querySelector(".ccc-account-card.membership");
    if (!main || !side || !wl || !membership) return;

    wl.classList.add("ccc-watchlist-main-card");
    membership.classList.add("ccc-plan-rail-card");

    var profile = main.querySelector(".ccc-account-card.profile");
    var mobile = window.matchMedia && window.matchMedia("(max-width: 767px)").matches;
    if (mobile) {
      if (membership.parentNode !== main || (profile && profile.nextElementSibling !== membership)) {
        if (profile) profile.insertAdjacentElement("afterend", membership);
        else main.insertBefore(membership, main.firstChild);
      }
      if (wl.parentNode !== main || membership.nextElementSibling !== wl) membership.insertAdjacentElement("afterend", wl);
    } else {
      if (wl.parentNode !== main || (profile && profile.nextElementSibling !== wl)) {
        if (profile) profile.insertAdjacentElement("afterend", wl);
        else main.appendChild(wl);
      }
      if (membership.parentNode !== side || side.firstElementChild !== membership) side.insertBefore(membership, side.firstElementChild);
    }

    var currentPlanStrip = membership.querySelector(".ccc-current-plan-strip");
    if (currentPlanStrip) {
      currentPlanStrip.querySelectorAll("span").forEach(function (node) {
        if (String(node.textContent || "").trim() === "Phạm vi CCC") node.textContent = "Quyền CCC";
      });
    }

    var explorerHead = membership.querySelector(".ccc-plan-explorer-head h3");
    if (explorerHead) explorerHead.textContent = "Mở rộng gói";

    if (!membership.querySelector(".ccc-vip-day-offer")) {
      var vip = document.createElement("section");
      vip.className = "ccc-vip-day-offer";
      vip.innerHTML = '<div><span>VIP DAY</span><strong>Mở FULL trong 24 giờ</strong><small>100.000đ · Hết 24 giờ tự trở lại đúng gói và DS mã theo dõi hiện tại.</small></div><button type="button" disabled title="Thanh toán sẽ được nối ở bước billing">100.000đ / 24h</button>';
      var explorer = membership.querySelector(".ccc-plan-explorer");
      if (explorer) membership.insertBefore(vip, explorer);
      else membership.appendChild(vip);
    }

    patchUserFacingWords(root);
  }

  function patchUserFacingWords(root) {
    if (!root) return;
    root.querySelectorAll(".ccc-account-kicker,h2,h3,p,span,small,button,dt").forEach(function (node) {
      if (node.children.length) return;
      var text = String(node.textContent || "");
      if (!text) return;
      var next = text
        .replace(/WATCHLIST & LƯỢT ĐỔI/gi, "DS MÃ THEO DÕI & LƯỢT ĐỔI")
        .replace(/Watchlist capacity/gi, "Số mã theo dõi")
        .replace(/Watchlist thật/gi, "DS mã theo dõi")
        .replace(/Watchlist/gi, "DS mã theo dõi")
        .replace(/Phạm vi CCC kỹ thuật/gi, "Quyền CCC kỹ thuật");
      if (next !== text) node.textContent = next;
    });
  }

  function stateLabel() {
    if (!state.watchlist) return "Đang tải";
    if (state.watchlist.status === "GRACE") return "Chờ gia hạn";
    if (state.watchlist.setup_active) return "Đang khởi tạo";
    return "Đang hoạt động";
  }
  function stateClass() { return state.watchlist && state.watchlist.status !== "GRACE" ? "ok" : "pending"; }

  function quotaLabel() {
    if (!state.watchlist) return "—";
    if (state.watchlist.change_limit == null) return "Không giới hạn";
    return Number(state.watchlist.change_remaining || 0) + "/" + Number(state.watchlist.change_limit || 0);
  }

  function setupNoticeHtml() {
    if (!state.watchlist) return "";
    if (state.watchlist.status === "GRACE") {
      return '<div class="ccc-wl-banner danger"><strong>Gói đang chờ gia hạn.</strong><span>DS mã theo dõi vẫn được giữ đến ' + esc(formatDateTime(state.watchlist.grace_end_at)) + '. Nếu chưa thanh toán khi hết thời gian này, DS của gói trả phí sẽ bị xóa và tài khoản chuyển về FREE.</span></div>';
    }
    if (state.watchlist.setup_active) {
      return '<div class="ccc-wl-banner info"><strong>7 ngày khởi tạo miễn phí.</strong><span>Bạn có thể thêm mã đến giới hạn gói mà chưa trừ lượt đổi đến ' + esc(formatDateTime(state.watchlist.setup_window_end)) + '.</span></div>';
    }
    if (Number(state.watchlist.upgrade_free_additions_remaining || 0) > 0 && state.watchlist.upgrade_free_additions_end_at) {
      return '<div class="ccc-wl-banner info"><strong>7 ngày bổ sung sau nâng cấp.</strong><span>Còn ' + esc(state.watchlist.upgrade_free_additions_remaining) + ' mã tăng thêm được bổ sung miễn phí đến ' + esc(formatDateTime(state.watchlist.upgrade_free_additions_end_at)) + '.</span></div>';
    }
    return "";
  }

  function metaFor(symbol) { return state.metadataBySymbol[String(symbol || "").toUpperCase()] || {}; }

  function selectedListHtml() {
    if (!state.selectedSymbols.length) return '<div class="ccc-wl-empty">Chưa có mã nào trong DS mã theo dõi.</div>';
    return '<div class="ccc-wl-selected-list">' + state.selectedSymbols.map(function (symbol) {
      var meta = metaFor(symbol);
      var name = meta.display_name || meta.company_name || "Đang tải tên công ty";
      return '<article class="ccc-wl-selected-row">' + logoHtml(symbol, "small") + '<div><strong>' + esc(symbol) + '</strong><span>' + esc(name) + '</span><small>' + esc(meta.exchange || "") + '</small></div><button type="button" data-wl-remove="' + esc(symbol) + '" aria-label="Xóa ' + esc(symbol) + '">×</button></article>';
    }).join("") + '</div>';
  }

  function searchResultsHtml() {
    var q = String(state.query || "").trim();
    if (!q) return "";
    if (state.searchLoading) return '<div class="ccc-wl-search-results"><div class="ccc-wl-search-status">Đang tìm mã…</div></div>';
    if (!state.searchResults.length) return '<div class="ccc-wl-search-results"><div class="ccc-wl-search-status">Không tìm thấy mã hoặc tên công ty phù hợp.</div></div>';

    var selectedMap = Object.create(null);
    state.selectedSymbols.forEach(function (symbol) { selectedMap[symbol] = true; });
    var rows = state.searchResults.filter(function (item) { return !selectedMap[item.symbol]; }).slice(0, 8);
    if (!rows.length) return '<div class="ccc-wl-search-results"><div class="ccc-wl-search-status">Các kết quả phù hợp đã có trong DS mã theo dõi.</div></div>';

    return '<div class="ccc-wl-search-results">' + rows.map(function (item) {
      var name = item.display_name || item.company_name || "";
      return '<button type="button" class="ccc-wl-result" data-wl-add="' + esc(item.symbol) + '"' + (canAddLocally() ? '' : ' disabled') + '>' + logoHtml(item.symbol, "result") + '<span class="ccc-wl-result-copy"><b>' + esc(item.symbol) + '</b><small>' + esc(name) + '</small><em>' + esc(item.exchange || "") + '</em></span><strong>+ Thêm</strong></button>';
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
    card.setAttribute("data-ccc-watchlist-live", "1");
    card.classList.add("ccc-watchlist-live-card", "ccc-watchlist-main-card");

    if (state.loading && !state.watchlist) {
      card.innerHTML = '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">DS MÃ THEO DÕI & LƯỢT ĐỔI</span><h2>Danh sách mã theo dõi</h2><p>Đang đọc danh sách và quota thật từ hệ thống.</p></div><span class="ccc-account-status pending">Đang tải</span></header><div class="ccc-wl-loading"><span class="ccc-auth-spinner" aria-hidden="true"></span><span>Đang tải…</span></div>';
      relayoutAccount();
      return;
    }

    if (!state.watchlist) {
      card.innerHTML = '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">DS MÃ THEO DÕI & LƯỢT ĐỔI</span><h2>Danh sách mã theo dõi</h2><p>Quản lý các mã bạn muốn theo dõi theo gói hiện tại.</p></div><span class="ccc-account-status pending">Chưa sẵn sàng</span></header>' + feedbackHtml() + '<button type="button" class="ccc-account-secondary" id="ccc-wl-retry">Thử lại</button>';
      bindCard(card); relayoutAccount(); return;
    }

    var dirty = !arraysEqual(state.originalSymbols, state.selectedSymbols);
    var adds = addedSymbols().length, removes = removedSymbols().length;
    var capacity = capacityLimit(), remaining = quotaRemaining();
    var estimatedQuota = state.watchlist.setup_active || isFull() ? 0 : adds;
    var quotaWarning = "";
    if (!state.watchlist.setup_active && !isFull() && remaining != null && estimatedQuota > remaining) {
      quotaWarning = '<div class="ccc-wl-feedback error">Bạn đang thêm ' + adds + ' mã nhưng chỉ còn ' + remaining + ' lượt đổi. Hệ thống sẽ không lưu một phần.</div>';
    }

    card.innerHTML = '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">DS MÃ THEO DÕI & LƯỢT ĐỔI</span><h2>Danh sách mã theo dõi</h2><p>Danh sách được giữ xuyên suốt gói; hàng tháng chỉ reset lượt đổi mã.</p></div><span class="ccc-account-status ' + stateClass() + '">' + esc(stateLabel()) + '</span></header>' +
      '<div class="ccc-wl-metrics"><div><span>Đang theo dõi</span><strong>' + state.selectedSymbols.length + (capacity == null ? '' : '/' + capacity) + '</strong></div><div><span>Lượt đổi còn lại</span><strong>' + esc(quotaLabel()) + '</strong></div><div><span>Reset tiếp theo</span><strong>' + esc(formatDate(state.watchlist.cycle_end)) + '</strong></div></div>' +
      setupNoticeHtml() + feedbackHtml() + quotaWarning +
      '<div class="ccc-wl-editor"><div class="ccc-wl-search-wrap"><label for="ccc-wl-search">Thêm mã vào DS theo dõi</label><div class="ccc-wl-search-box"><input id="ccc-wl-search" type="search" inputmode="search" autocomplete="off" placeholder="Gõ mã hoặc tên công ty, ví dụ VIC…" value="' + esc(state.query) + '"' + (canAddLocally() ? '' : ' disabled') + '></div>' + searchResultsHtml() + '</div>' +
      '<div class="ccc-wl-list-head"><span>Mã đang theo dõi</span><small>' + (dirty ? ('Thay đổi: +' + adds + ' / -' + removes) : 'Chưa có thay đổi') + '</small></div>' + selectedListHtml() + '</div>' +
      '<div class="ccc-wl-actions"><button type="button" class="ccc-account-secondary" id="ccc-wl-reset"' + (!dirty || state.saving ? ' disabled' : '') + '>Hoàn tác</button><button type="button" class="ccc-account-primary" id="ccc-wl-save"' + (!dirty || state.saving ? ' disabled' : '') + '>' + (state.saving ? 'Đang lưu…' : 'Lưu DS mã theo dõi') + '</button></div>' +
      '<p class="ccc-wl-rule-note">Xóa mã không trừ lượt. Sau thời gian miễn phí, mỗi mã mới thêm vào DS sẽ dùng 1 lượt đổi; xóa rồi thêm lại cùng mã vẫn tính 1.</p>';

    bindCard(card);
    relayoutAccount();
  }

  function friendlyError(error) {
    var message = String(error && error.message ? error.message : error || "");
    if (message.indexOf("WATCHLIST_LIMIT_EXCEEDED") >= 0) return "Số mã vượt giới hạn của gói hiện tại.";
    if (message.indexOf("CHANGE_QUOTA_EXCEEDED") >= 0) return "Không đủ lượt đổi mã để thực hiện thay đổi này.";
    if (message.indexOf("INVALID_SYMBOL") >= 0) return "Có mã không thuộc danh sách scanner hiện tại.";
    if (message.indexOf("SUBSCRIPTION_SUSPENDED") >= 0) return "Tài khoản đang tạm ngưng quyền thay đổi DS mã theo dõi.";
    if (message.indexOf("NO_CURRENT_SUBSCRIPTION") >= 0) return "Không tìm thấy gói thành viên đang hoạt động.";
    if (message.indexOf("AUTH_REQUIRED") >= 0) return "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.";
    return "Không cập nhật được DS mã theo dõi. Vui lòng thử lại.";
  }

  async function ensureUser() {
    var client = getClient(); if (!client) return null;
    try {
      var result = await client.auth.getSession();
      if (result.error) throw result.error;
      return result.data && result.data.session ? result.data.session.user : null;
    } catch (_) { return null; }
  }

  function ingestItems(items) {
    (items || []).forEach(function (row) {
      var symbol = String(row && row.symbol || "").trim().toUpperCase();
      if (!symbol) return;
      state.metadataBySymbol[symbol] = {
        symbol: symbol,
        display_name: row.display_name || "",
        company_name: row.company_name || "",
        exchange: row.exchange || ""
      };
    });
  }

  async function searchMetadata(query) {
    var client = getClient();
    var raw = String(query || "").trim();
    if (!client || !raw) { state.searchResults = []; state.searchLoading = false; renderCard(); return; }
    var seq = ++state.searchSeq;
    state.searchLoading = true;
    var q = raw.replace(/[%_,()]/g, " ").trim();
    try {
      var requests = [
        client.from("stock_metadata").select("symbol,display_name,company_name,exchange").ilike("symbol", q.toUpperCase() + "%").limit(8),
        client.from("stock_metadata").select("symbol,display_name,company_name,exchange").ilike("display_name", "%" + q + "%").limit(8),
        client.from("stock_metadata").select("symbol,display_name,company_name,exchange").ilike("company_name", "%" + q + "%").limit(8)
      ];
      var results = await Promise.all(requests);
      if (seq !== state.searchSeq) return;
      var merged = [], seen = Object.create(null);
      results.forEach(function (result) {
        if (result.error) throw result.error;
        (result.data || []).forEach(function (row) {
          var symbol = String(row.symbol || "").toUpperCase();
          if (!symbol || seen[symbol]) return;
          seen[symbol] = true;
          var item = { symbol: symbol, display_name: row.display_name || "", company_name: row.company_name || "", exchange: row.exchange || "" };
          merged.push(item); state.metadataBySymbol[symbol] = item;
        });
      });
      merged.sort(function (a, b) {
        var aq = a.symbol === q.toUpperCase() ? 0 : a.symbol.indexOf(q.toUpperCase()) === 0 ? 1 : 2;
        var bq = b.symbol === q.toUpperCase() ? 0 : b.symbol.indexOf(q.toUpperCase()) === 0 ? 1 : 2;
        return aq - bq || a.symbol.localeCompare(b.symbol);
      });
      state.searchResults = merged.slice(0, 8);
    } catch (error) {
      console.error("CCC metadata search failed", error);
      if (seq === state.searchSeq) { state.searchResults = []; state.error = "Không tìm được mã lúc này. Vui lòng thử lại."; }
    } finally {
      if (seq === state.searchSeq) { state.searchLoading = false; renderCard(); refocusSearch(); }
    }
  }

  function scheduleSearch(value) {
    state.query = value || ""; state.error = ""; state.notice = "";
    if (state.searchTimer) clearTimeout(state.searchTimer);
    if (!String(state.query).trim()) { state.searchResults = []; state.searchLoading = false; renderCard(); return; }
    state.searchLoading = true;
    state.searchTimer = setTimeout(function () { searchMetadata(state.query); }, 220);
  }

  async function loadWatchlist(force) {
    if (!isAccountRoute() || state.loading) return;
    var client = getClient();
    if (!client) { state.error = "Chưa kết nối được Supabase cho DS mã theo dõi."; renderCard(); return; }
    var user = await ensureUser(); if (!user) return;
    if (state.userId && state.userId !== user.id) resetForAuthChange();
    if (!force && state.watchlist && state.userId === user.id) { renderCard(); return; }
    state.userId = user.id; state.loading = true; state.error = ""; renderCard();
    try {
      var result = await client.rpc("get_my_watchlist_state");
      if (result.error) throw result.error;
      state.watchlist = result.data || null;
      state.originalSymbols = uniqueSorted(state.watchlist && state.watchlist.symbols || []);
      state.selectedSymbols = state.originalSymbols.slice();
      state.metadataBySymbol = Object.create(null);
      ingestItems(state.watchlist && state.watchlist.items || []);
      state.query = ""; state.searchResults = [];
    } catch (error) {
      console.error("CCC watchlist state load failed", error);
      state.error = friendlyError(error); state.watchlist = null;
    } finally { state.loading = false; renderCard(); }
  }

  async function saveWatchlist() {
    if (state.saving || !state.watchlist) return;
    var client = getClient(); if (!client) return;
    state.saving = true; state.error = ""; state.notice = ""; renderCard();
    try {
      var result = await client.rpc("replace_my_watchlist", { p_symbols: uniqueSorted(state.selectedSymbols) });
      if (result.error) throw result.error;
      state.watchlist = result.data || state.watchlist;
      state.originalSymbols = uniqueSorted(state.watchlist.symbols || state.selectedSymbols);
      state.selectedSymbols = state.originalSymbols.slice();
      ingestItems(state.watchlist.items || []);
      state.query = ""; state.searchResults = [];
      state.notice = "Đã lưu DS mã theo dõi thành công.";
      window.dispatchEvent(new CustomEvent("ccc:watchlist-updated"));
    } catch (error) { console.error("CCC watchlist save failed", error); state.error = friendlyError(error); }
    finally { state.saving = false; renderCard(); }
  }

  function addSymbol(symbol) {
    symbol = String(symbol || "").trim().toUpperCase();
    if (!symbol || state.selectedSymbols.indexOf(symbol) >= 0) return;
    if (!canAddLocally()) { state.error = "DS mã theo dõi đã đạt giới hạn của gói hiện tại."; renderCard(); return; }
    state.selectedSymbols.push(symbol); state.selectedSymbols.sort(); state.query = ""; state.searchResults = []; state.error = ""; state.notice = ""; renderCard();
  }
  function removeSymbol(symbol) {
    symbol = String(symbol || "").trim().toUpperCase();
    state.selectedSymbols = state.selectedSymbols.filter(function (item) { return item !== symbol; });
    state.error = ""; state.notice = ""; renderCard();
  }

  function refocusSearch() {
    requestAnimationFrame(function () {
      var next = document.getElementById("ccc-wl-search");
      if (next) { next.focus(); try { next.setSelectionRange(next.value.length, next.value.length); } catch (_) {} }
    });
  }

  function bindCard(card) {
    var retry = card.querySelector("#ccc-wl-retry"); if (retry) retry.addEventListener("click", function () { loadWatchlist(true); });
    var search = card.querySelector("#ccc-wl-search");
    if (search) search.addEventListener("input", function () { scheduleSearch(search.value); refocusSearch(); });
    card.querySelectorAll("[data-wl-add]").forEach(function (button) { button.addEventListener("click", function () { addSymbol(button.getAttribute("data-wl-add")); }); });
    card.querySelectorAll("[data-wl-remove]").forEach(function (button) { button.addEventListener("click", function () { removeSymbol(button.getAttribute("data-wl-remove")); }); });
    var reset = card.querySelector("#ccc-wl-reset"); if (reset) reset.addEventListener("click", function () { state.selectedSymbols = state.originalSymbols.slice(); state.query = ""; state.searchResults = []; state.error = ""; state.notice = ""; renderCard(); });
    var save = card.querySelector("#ccc-wl-save"); if (save) save.addEventListener("click", saveWatchlist);
  }

  function patchWhenReady() {
    if (!isAccountRoute()) return;
    relayoutAccount();
    var card = findWatchlistCard();
    if (!card) return;
    if (!card.hasAttribute("data-ccc-watchlist-live")) renderCard();
    if (!state.watchlist && !state.loading) loadWatchlist(false);
  }

  function resetForAuthChange() {
    state.userId = ""; state.watchlist = null; state.originalSymbols = []; state.selectedSymbols = []; state.metadataBySymbol = Object.create(null); state.query = ""; state.searchResults = []; state.error = ""; state.notice = "";
  }

  function init() {
    var attempts = 0;
    var timer = window.setInterval(function () {
      attempts += 1; var client = getClient();
      if (client || attempts >= 60) {
        window.clearInterval(timer);
        if (client && client.auth && typeof client.auth.onAuthStateChange === "function") {
          client.auth.onAuthStateChange(function (event, session) {
            var nextUserId = session && session.user ? session.user.id : "";
            if (event === "SIGNED_OUT" || (state.userId && nextUserId && state.userId !== nextUserId)) resetForAuthChange();
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
      requestAnimationFrame(function () { scheduled = false; patchWhenReady(); });
    });
    observer.observe(root, { childList: true, subtree: true });
    window.addEventListener("popstate", function () { window.setTimeout(patchWhenReady, 0); });
    window.addEventListener("resize", function () { window.setTimeout(patchWhenReady, 0); });
    document.addEventListener("click", function () { window.setTimeout(patchWhenReady, 0); }, true);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
