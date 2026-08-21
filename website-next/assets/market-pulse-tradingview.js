(function () {
  "use strict";

  /*
   * CCC Market Pulse — TradingView Single Ticker test bridge
   * Prepared against:
   *   branch: lovable-full-port-review
   *   HEAD:   d9261a5f5e6aca7eac3ffacd3c3f1e5deff9e33f
   *
   * Important:
   * - Does NOT modify app-v19.0-alpha.6-shell.js.
   * - Does NOT modify styles-v19.0-alpha.6-shell.css.
   * - Patches only the existing .market-pulse block after CCC renders it.
   */

  var WIDGET_SCRIPT_URL =
    "https://widgets.tradingview-widget.com/w/en/tv-single-ticker.js";

  var INSTRUMENTS = {
    "VN-INDEX": { symbol: "HOSE:VNINDEX", region: "Việt Nam" },
    "S&P 500": { symbol: "SP:SPX", region: "Hoa Kỳ" },
    "HANG SENG": { symbol: "HSI:HSI", region: "Hong Kong" },
    "DXY": { symbol: "TVC:DXY", region: "USD Index" },
    "GOLD": { symbol: "TVC:GOLD", region: "Vàng" },
    "WTI": { symbol: "TVC:USOIL", region: "Dầu thô WTI" },
    "BTC": { symbol: "BITSTAMP:BTCUSD", region: "Bitcoin" }
  };

  var patchQueued = false;

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[c];
    });
  }

  function ensureTradingViewLoader() {
    if (document.querySelector('script[data-ccc-market-pulse-tv="1"]')) return;

    var script = document.createElement("script");
    script.type = "module";
    script.src = WIDGET_SCRIPT_URL;
    script.dataset.cccMarketPulseTv = "1";

    script.addEventListener("error", function () {
      document.documentElement.classList.add("tv-market-pulse-load-failed");
      document.querySelectorAll(".market-tv-loading").forEach(function (node) {
        node.textContent = "Không tải được dữ liệu TradingView";
      });
    });

    document.head.appendChild(script);
  }

  function ensureStyles() {
    if (document.getElementById("ccc-market-pulse-tv-style")) return;

    var style = document.createElement("style");
    style.id = "ccc-market-pulse-tv-style";
    style.textContent = [
      ".market-tv-quote{min-width:0;margin-top:14px;overflow:hidden}",
      ".market-tv-quote tv-single-ticker{",
      "display:block;width:100%;min-width:0;min-height:48px;color-scheme:inherit;",
      "--tv-widget-background-color:transparent;",
      "--tv-widget-font-family:var(--font-sans);",
      "--tv-widget-text-color:var(--foreground);",
      "--tv-widget-price-text-color:var(--foreground);",
      "--tv-widget-positive-color:var(--positive);",
      "--tv-widget-negative-color:var(--negative);",
      "--tv-widget-market-status-open-color:var(--positive);",
      "--tv-widget-market-status-closed-color:var(--muted-foreground);",
      "--tv-widget-market-status-pre-color:var(--warning);",
      "--tv-widget-market-status-post-color:var(--warning)",
      "}",
      ".market-tv-loading{display:flex;min-height:48px;align-items:center;color:var(--muted-foreground);font-size:11px}",
      ".market-tile.is-primary .market-tv-quote{max-width:380px;margin-top:28px}",
      ".market-tile header em.tv-source-badge{background:var(--surface-3);color:var(--muted-foreground)}",
      ".market-tile[data-tv-pulse-patched='1'] footer{margin-top:12px}",
      ".market-tile.is-primary[data-tv-pulse-patched='1'] footer{margin-top:28px}",
      "@media(max-width:767px){",
      ".market-tile.is-primary .market-tv-quote{margin-top:18px}",
      ".market-tile.is-primary[data-tv-pulse-patched='1'] footer{margin-top:16px}",
      "}",
      "@media(max-width:420px){.market-tv-quote{margin-top:10px}}"
    ].join("\n");

    document.head.appendChild(style);
  }

  function quoteMarkup(info) {
    return (
      '<div class="market-tv-quote">' +
      '<tv-single-ticker symbol="' + esc(info.symbol) + '" transparent>' +
      '<span class="market-tv-loading">Đang tải dữ liệu thị trường…</span>' +
      "</tv-single-ticker>" +
      "</div>"
    );
  }

  function patchTile(tile) {
    if (!tile || tile.dataset.tvPulsePatched === "1") return;

    var title = tile.querySelector("header strong");
    var unavailable = tile.querySelector(".market-unavailable");
    if (!title || !unavailable) return;

    var key = String(title.textContent || "").trim().toUpperCase();
    var info = INSTRUMENTS[key];
    if (!info) return;

    unavailable.outerHTML = quoteMarkup(info);

    var badge = tile.querySelector("header em");
    if (badge) {
      badge.textContent = "TradingView";
      badge.classList.add("tv-source-badge");
      badge.title = "Nguồn dữ liệu hiển thị: TradingView";
    }

    var footer = tile.querySelector("footer");
    if (footer) {
      footer.textContent = info.region + " · nguồn TradingView";
    }

    tile.dataset.tvPulsePatched = "1";
    tile.dataset.tvSymbol = info.symbol;
  }

  function patchMarketPulse() {
    patchQueued = false;

    var pulse = document.querySelector(".market-pulse");
    if (!pulse) return;

    pulse.querySelectorAll(".market-tile").forEach(patchTile);

    var sectionMeta = pulse.querySelector(".section-bar > div > span");
    if (sectionMeta) {
      sectionMeta.textContent = "Tự động cập nhật theo nguồn";
    }

    var sectionNote = pulse.querySelector(".section-bar > small");
    if (sectionNote) {
      sectionNote.textContent = "7 chỉ số · nguồn TradingView";
    }
  }

  function queuePatch() {
    if (patchQueued) return;
    patchQueued = true;
    window.requestAnimationFrame(patchMarketPulse);
  }

  function start() {
    ensureStyles();
    ensureTradingViewLoader();
    queuePatch();

    var observer = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i += 1) {
        if (mutations[i].addedNodes && mutations[i].addedNodes.length) {
          queuePatch();
          return;
        }
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
