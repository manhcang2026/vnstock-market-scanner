(function () {
  "use strict";

  /*
    CCC v19.11.5 — Mobile auth stability guard.

    Root cause:
    The core app re-renders on window resize. On mobile, opening the
    virtual keyboard resizes the viewport, so the auth dialog DOM is
    replaced while an input is focused. This makes the keyboard/input
    appear to "jump out" or close.

    This guard is intentionally standalone and loaded BEFORE the core app.
    It blocks only resize propagation while an auth/password dialog exists,
    and restores the body scroll lock expected by auth-v19.0-alpha.15.css.
  */

  function authDialogOpen() {
    return !!document.querySelector(".ccc-auth-overlay");
  }

  function syncBodyLock() {
    if (!document.body) return;
    document.body.classList.toggle("ccc-auth-open", authDialogOpen());
  }

  window.addEventListener("resize", function (event) {
    if (!authDialogOpen()) return;
    event.stopImmediatePropagation();
  }, true);

  function boot() {
    syncBodyLock();

    var observer = new MutationObserver(function () {
      syncBodyLock();
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
