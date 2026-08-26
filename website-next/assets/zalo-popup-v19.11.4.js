(function () {
  "use strict";

  var STORAGE_KEY = "ccc_zalo_prompt_last_choice_at_v1";
  var ONE_DAY_MS = 24 * 60 * 60 * 1000;
  var ZALO_URL = "https://zalo.me/g/pqef4bm93akv1elvkqz2";
  var SHOW_DELAY_MS = 700;

  function readLastChoiceAt() {
    try {
      var value = Number(localStorage.getItem(STORAGE_KEY) || 0);
      return Number.isFinite(value) ? value : 0;
    } catch (_) {
      return 0;
    }
  }

  function rememberChoice() {
    try {
      localStorage.setItem(STORAGE_KEY, String(Date.now()));
    } catch (_) {}
  }

  function shouldShow() {
    var last = readLastChoiceAt();
    return !last || Date.now() - last >= ONE_DAY_MS;
  }

  function closePrompt(root) {
    if (!root) return;
    rememberChoice();
    document.body.classList.remove("ccc-zalo-prompt-open");
    root.remove();
  }

  function createPrompt() {
    if (!shouldShow() || document.querySelector(".ccc-zalo-prompt")) return;

    var root = document.createElement("div");
    root.className = "ccc-zalo-prompt";
    root.setAttribute("role", "presentation");
    root.innerHTML =
      '<div class="ccc-zalo-prompt__backdrop" aria-hidden="true"></div>' +
      '<section class="ccc-zalo-prompt__dialog" role="dialog" aria-modal="true" aria-labelledby="ccc-zalo-prompt-title">' +
        '<div class="ccc-zalo-prompt__brand">' +
          '<span class="ccc-zalo-prompt__logo"><img src="/assets/brand/zalo-logo.svg?v=19113" alt="Zalo"></span>' +
          '<div><p class="ccc-zalo-prompt__eyebrow">Cộng đồng Chuyện Chợ Chứng</p><h2 id="ccc-zalo-prompt-title">Chém gió Chứng Khoán</h2></div>' +
        '</div>' +
        '<div class="ccc-zalo-prompt__actions">' +
          '<a class="ccc-zalo-prompt__primary" data-zalo-choice="join" href="' + ZALO_URL + '" target="_blank" rel="noopener noreferrer">Tham gia group Zalo <span aria-hidden="true">→</span></a>' +
          '<button class="ccc-zalo-prompt__secondary" data-zalo-choice="continue" type="button">Vào Website</button>' +
        '</div>' +
      '</section>';

    document.body.appendChild(root);
    document.body.classList.add("ccc-zalo-prompt-open");

    var join = root.querySelector('[data-zalo-choice="join"]');
    var cont = root.querySelector('[data-zalo-choice="continue"]');

    if (join) {
      join.addEventListener("click", function () {
        rememberChoice();
        setTimeout(function () { closePrompt(root); }, 0);
      });
    }
    if (cont) {
      cont.addEventListener("click", function () {
        closePrompt(root);
      });
      cont.focus();
    }

    root.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.preventDefault();
        closePrompt(root);
      }
    });
  }

  function boot() {
    if (!shouldShow()) return;
    window.setTimeout(createPrompt, SHOW_DELAY_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
