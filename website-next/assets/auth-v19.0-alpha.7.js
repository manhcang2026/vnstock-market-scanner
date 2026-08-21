(function () {
  "use strict";

  var SUPABASE_URL = "https://wevtlkowpbmpdggcfbvn.supabase.co";
  var SUPABASE_KEY = "sb_publishable_qN__TQuoNBRUFhxuY5CtNw_88WZDdJw";
  var ROOT_ID = "ccc-auth-root";

  var client = null;
  var lastFocused = null;
  var state = {
    open: false,
    busy: false,
    session: null,
    user: null,
    error: "",
    notice: "",
    fatal: ""
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function root() {
    var node = document.getElementById(ROOT_ID);
    if (!node) {
      node = document.createElement("div");
      node.id = ROOT_ID;
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
    var meta = user.user_metadata || {};
    return meta.full_name || meta.name || user.email || "Tài khoản";
  }

  function userInitial(user) {
    var label = userLabel(user).trim();
    return label ? label.charAt(0).toUpperCase() : "U";
  }

  function patchAccountButtons() {
    var loggedIn = !!state.user;
    var headerButton = document.getElementById("account-open");
    if (headerButton) {
      var strong = headerButton.querySelector("strong");
      var small = headerButton.querySelector("small");
      var strongText = loggedIn ? "Tài khoản" : "Đăng nhập";
      var smallText = loggedIn ? "Đã đăng nhập" : "Email / Google";
      if (strong && strong.textContent !== strongText) strong.textContent = strongText;
      if (small && small.textContent !== smallText) small.textContent = smallText;
      headerButton.setAttribute("aria-label", loggedIn ? "Mở tài khoản" : "Đăng nhập Chuyện Chợ Chứng");
      headerButton.setAttribute("title", loggedIn ? userLabel(state.user) : "Đăng nhập");
    }

    var desktopButton = document.getElementById("desktop-account-open");
    if (desktopButton) {
      var navLabel = desktopButton.querySelector(".nav-label");
      var navSmall = desktopButton.querySelector("small");
      var navText = loggedIn ? "Tài khoản" : "Đăng nhập";
      if (navLabel && navLabel.textContent !== navText) navLabel.textContent = navText;
      if (navSmall && navSmall.textContent !== navText) navSmall.textContent = navText;
      desktopButton.setAttribute("aria-label", loggedIn ? "Mở tài khoản" : "Đăng nhập Chuyện Chợ Chứng");
    }
  }

  function render() {
    var node = root();
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
        '<section class="ccc-auth-account" aria-label="Phiên đăng nhập hiện tại">' +
          '<div class="ccc-auth-user-row">' +
            '<span class="ccc-auth-user-avatar" aria-hidden="true">' + esc(userInitial(state.user)) + '</span>' +
            '<div><strong>' + esc(userLabel(state.user)) + '</strong><p>' + esc(state.user.email || "") + '</p></div>' +
          '</div>' +
          '<dl class="ccc-auth-session-grid">' +
            '<div><dt>Phương thức</dt><dd>' + esc(providerLabel(state.user)) + '</dd></div>' +
            '<div><dt>Phiên đăng nhập</dt><dd>Đang hoạt động</dd></div>' +
          '</dl>' +
          '<p class="ccc-auth-stage-note">Auth 4A đã kết nối thật. Hồ sơ và gói thành viên sẽ được nối ở bước 4B.</p>' +
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
        '<p class="ccc-auth-stage-note">Staging Auth 4A: chưa mở đăng ký email công khai. Đăng nhập Google có thể tạo tài khoản mới theo cấu hình Supabase.</p>';
    }

    node.innerHTML = '' +
      '<div class="ccc-auth-overlay">' +
        '<section class="ccc-auth-dialog" role="dialog" aria-modal="true" aria-labelledby="ccc-auth-title">' +
          '<header class="ccc-auth-head">' +
            '<div><span class="eyebrow">CCC ACCOUNT</span><h2 id="ccc-auth-title">' + (state.user ? 'Tài khoản của bạn' : 'Đăng nhập') + '</h2><p>' + (state.user ? 'Phiên đăng nhập Supabase đang hoạt động.' : 'Đăng nhập để bắt đầu sử dụng phạm vi cá nhân của Chuyện Chợ Chứng.') + '</p></div>' +
            '<button id="ccc-auth-close" class="ccc-auth-close" type="button" aria-label="Đóng cửa sổ đăng nhập">×</button>' +
          '</header>' +
          feedback +
          '<div class="ccc-auth-body">' + content + '</div>' +
        '</section>' +
      '</div>';

    bindDialog();
  }

  function openDialog() {
    state.open = true;
    state.error = "";
    state.notice = "";
    lastFocused = document.activeElement;
    render();
    requestAnimationFrame(function () {
      var focusTarget = state.user ? document.getElementById("ccc-auth-logout") : document.getElementById("ccc-auth-google");
      if (focusTarget) focusTarget.focus();
    });
  }

  function closeDialog() {
    if (!state.open) return;
    state.open = false;
    state.error = "";
    state.notice = "";
    render();
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

  async function signInEmail(event) {
    event.preventDefault();
    if (!client || state.busy) return;

    var form = event.currentTarget;
    var formData = new FormData(form);
    var email = String(formData.get("email") || "").trim();
    var password = String(formData.get("password") || "");

    if (!email || !password) {
      state.error = "Vui lòng nhập đầy đủ email và mật khẩu.";
      render();
      return;
    }

    state.busy = true;
    state.error = "";
    state.notice = "";
    render();

    try {
      var result = await client.auth.signInWithPassword({ email: email, password: password });
      if (result.error) throw result.error;
      state.session = result.data.session || null;
      state.user = result.data.user || (state.session && state.session.user) || null;
      state.notice = "Đăng nhập thành công.";
    } catch (error) {
      state.error = friendlyAuthError(error);
    } finally {
      state.busy = false;
      render();
    }
  }

  async function signInGoogle() {
    if (!client || state.busy) return;
    state.busy = true;
    state.error = "";
    state.notice = "";
    render();

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
      render();
    }
  }

  async function signOut() {
    if (!client || state.busy) return;
    state.busy = true;
    state.error = "";
    render();

    try {
      var result = await client.auth.signOut();
      if (result.error) throw result.error;
      state.session = null;
      state.user = null;
      state.notice = "Đã đăng xuất.";
    } catch (error) {
      state.error = friendlyAuthError(error);
    } finally {
      state.busy = false;
      render();
    }
  }

  function bindDialog() {
    var closeButton = document.getElementById("ccc-auth-close");
    if (closeButton) closeButton.addEventListener("click", closeDialog);

    var overlay = root().querySelector(".ccc-auth-overlay");
    if (overlay) {
      overlay.addEventListener("click", function (event) {
        if (event.target === overlay) closeDialog();
      });
    }

    var emailForm = document.getElementById("ccc-auth-email-form");
    if (emailForm) emailForm.addEventListener("submit", signInEmail);

    var googleButton = document.getElementById("ccc-auth-google");
    if (googleButton) googleButton.addEventListener("click", signInGoogle);

    var logoutButton = document.getElementById("ccc-auth-logout");
    if (logoutButton) logoutButton.addEventListener("click", signOut);
  }

  function interceptAccountClick(event) {
    var target = event.target && event.target.closest ? event.target.closest("#account-open,#desktop-account-open") : null;
    if (!target) return;
    event.preventDefault();
    event.stopPropagation();
    openDialog();
  }

  function installShellBridge() {
    document.addEventListener("click", interceptAccountClick, true);
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && state.open) closeDialog();
    });

    var observer = new MutationObserver(function () {
      patchAccountButtons();
    });
    var app = document.getElementById("app");
    if (app) observer.observe(app, { childList: true, subtree: true });
    patchAccountButtons();
  }

  async function init() {
    root();
    installShellBridge();

    if (!window.supabase || typeof window.supabase.createClient !== "function") {
      state.fatal = "Không tải được thư viện xác thực Supabase. Vui lòng tải lại trang.";
      patchAccountButtons();
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
    } catch (error) {
      state.error = friendlyAuthError(error);
    }

    client.auth.onAuthStateChange(function (_event, session) {
      state.session = session || null;
      state.user = session ? session.user : null;
      patchAccountButtons();
      if (state.open) render();
    });

    patchAccountButtons();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
