(function () {
  "use strict";

  var SUPABASE_URL = "https://wevtlkowpbmpdggcfbvn.supabase.co";
  var SUPABASE_KEY = "sb_publishable_qN__TQuoNBRUFhxuY5CtNw_88WZDdJw";
  var AUTH_ROOT_ID = "ccc-auth-root";
  var ACCOUNT_ROOT_ID = "ccc-account-page-root";
  var ACCOUNT_PATH = "/tai-khoan";

  var client = null;
  var lastFocused = null;
  var state = {
    open: false,
    busy: false,
    session: null,
    user: null,
    profile: null,
    subscription: null,
    plan: null,
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

  function planHeaderLabel() {
    if (!state.user) return "Email / Google";
    if (state.membershipLoading) return "Đang tải gói…";
    if (state.plan) return state.plan.plan_code + " · " + scopeLabel(state.plan);
    return "Đã đăng nhập";
  }

  function clearMembership() {
    state.profile = null;
    state.subscription = null;
    state.plan = null;
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
      var strongText = loggedIn ? "Tài khoản" : "Đăng nhập";
      var smallText = loggedIn ? planHeaderLabel() : "Email / Google";
      if (strong && strong.textContent !== strongText) strong.textContent = strongText;
      if (small && small.textContent !== smallText) small.textContent = smallText;
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

      if (!state.user || state.user.id !== userId) return;

      state.profile = profileResult.data || null;
      state.subscription = subscriptionResult.data || null;
      state.plan = plan;
      state.membershipLoadedFor = userId;

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
      '<header class="ccc-account-heading"><div><span class="eyebrow">CCC ACCOUNT</span><h1>Tài khoản</h1><p>Đăng nhập để quản lý hồ sơ, gói thành viên và thiết lập cá nhân.</p></div></header>' +
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
      '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">' + (setupMode ? 'THIẾT LẬP LẦN ĐẦU' : 'HỒ SƠ CÁ NHÂN') + '</span><h2>' + (setupMode ? 'Hoàn tất hồ sơ hội viên' : 'Thông tin cá nhân') + '</h2><p>' + (setupMode ? 'Vui lòng bổ sung thông tin cơ bản trước khi sử dụng các tính năng cá nhân.' : 'Cập nhật thông tin liên hệ của bạn.') + '</p></div>' +
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

  function membershipCardHtml() {
    if (state.membershipError) {
      return '<section class="ccc-account-card"><div class="ccc-account-form-message error">' + esc(state.membershipError) + '</div></section>';
    }
    if (!state.plan || !state.subscription) return "";

    var plan = state.plan;
    var sub = state.subscription;

    return '<section class="ccc-account-card membership">' +
      '<header class="ccc-account-card-head"><div><span class="ccc-account-kicker">GÓI THÀNH VIÊN</span><h2>' + esc(plan.display_name || plan.plan_code) + '</h2><p>Quyền truy cập hiện tại của tài khoản.</p></div><span class="ccc-account-plan-badge">' + esc(plan.plan_code) + '</span></header>' +
      '<div class="ccc-account-metrics">' +
        '<div><span>Phạm vi CCC kỹ thuật</span><strong>' + esc(scopeLabel(plan)) + '</strong></div>' +
        '<div><span>Watchlist</span><strong>' + esc(watchlistLimitLabel(plan)) + '</strong></div>' +
        '<div><span>Lượt đổi còn lại</span><strong>' + esc(remainingLabel(plan, sub)) + '</strong></div>' +
        '<div><span>Cảnh báo</span><strong>' + esc(alertLabel(plan)) + '</strong></div>' +
      '</div>' +
      '<div class="ccc-account-cycle"><span>Chu kỳ hiện tại</span><strong>' + esc(formatDate(sub.cycle_start)) + ' → ' + esc(formatDate(sub.cycle_end)) + '</strong></div>' +
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
    if (!state.user) return accountLoggedOutHtml();
    if (state.membershipLoading && !state.profile) return accountLoadingHtml();

    return '<main class="wrap ccc-account-page" id="main-content">' +
      '<header class="ccc-account-heading"><div><span class="eyebrow">CCC ACCOUNT</span><h1>Tài khoản</h1><p>Quản lý hồ sơ, gói thành viên và thiết lập cá nhân.</p></div><div class="ccc-account-identity"><span class="ccc-account-avatar">' + esc(userInitial(state.user)) + '</span><div><strong>' + esc(userLabel(state.user)) + '</strong><span>' + esc(state.user.email || "") + '</span></div></div></header>' +
      (isSetupRoute() || (state.profile && !state.profile.profile_completed) ? '<section class="ccc-account-setup-banner"><strong>Chào mừng bạn đến Chuyện Chợ Chứng</strong><p>Chỉ cần hoàn tất Họ tên và Số điện thoại. Địa chỉ có thể bổ sung sau.</p></section>' : '') +
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
    window.location.assign(ACCOUNT_PATH + "?setup=1");
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

    var logoutButton = document.getElementById("ccc-account-logout");
    if (logoutButton) logoutButton.addEventListener("click", signOut);
  }

  function interceptAccountClick(event) {
    var target = event.target && event.target.closest ? event.target.closest("#account-open,#desktop-account-open") : null;
    if (!target) return;

    event.preventDefault();
    event.stopPropagation();

    if (state.user) {
      window.location.assign(ACCOUNT_PATH);
    } else {
      openLoginDialog();
    }
  }

  function installShellBridge() {
    document.addEventListener("click", interceptAccountClick, true);
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
        if (isAccountRoute()) renderAccountPage();
      });
    });
    var app = document.getElementById("app");
    if (app) observer.observe(app, { childList: true, subtree: true });

    patchAccountButtons();
    renderAccountPage();
  }

  async function init() {
    authRoot();
    accountRoot();
    installShellBridge();

    if (!window.supabase || typeof window.supabase.createClient !== "function") {
      state.fatal = "Không tải được thư viện xác thực Supabase. Vui lòng tải lại trang.";
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
    }

    patchAccountButtons();
    renderAccountPage();

    if (maybeRedirectToProfileSetup()) return;

    client.auth.onAuthStateChange(function (_event, session) {
      var previousUserId = state.user ? state.user.id : "";
      var nextUser = session ? session.user : null;
      var nextUserId = nextUser ? nextUser.id : "";

      state.session = session || null;
      state.user = nextUser;

      if (!nextUser) {
        clearMembership();
        patchAccountButtons();
        renderAccountPage();
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
