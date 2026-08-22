(function () {
  "use strict";

  var GROUPS = {
    "4of4": { title: "Đạt 4/4", marketKey: "four_of_four", matcher: function (r) { return Number(r.signal_count || 0) === 4; } },
    "3plus": { title: "Từ 3 tín hiệu", marketKey: "three_plus", matcher: function (r) { return Number(r.signal_count || 0) >= 3; } },
    "2plus": { title: "Từ 2 tín hiệu", marketKey: "two_plus", matcher: function (r) { return Number(r.signal_count || 0) >= 2; } },
    "rvol30": { title: "RVOL30 nổi bật", marketKey: "rvol30", matcher: function (r) { return r.signal_rvol30_200pct === true; } }
  };
  var LOGO_BASE_URL = "/assets/logos/";
  var LOGO_VERSION = "1741";
  var state = { client: null, userId: "", loading: false, data: null, group: "", error: "", observerBusy: false };

  function esc(value) { return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) { return { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]; }); }
  function getClient() {
    if (state.client) return state.client;
    if (window.__cccSupabaseClient) state.client = window.__cccSupabaseClient;
    else if (Array.isArray(window.__cccSupabaseClients) && window.__cccSupabaseClients.length) state.client = window.__cccSupabaseClients[window.__cccSupabaseClients.length - 1];
    return state.client;
  }
  function isOverview() { return window.location.pathname === "/"; }
  function num(v) { var n = Number(v); return Number.isFinite(n) ? n : null; }
  function formatNumber(v, digits) { var n = num(v); return n == null ? "—" : n.toLocaleString("vi-VN", { minimumFractionDigits: digits || 0, maximumFractionDigits: digits || 0 }); }
  function pct(v, digits) { var n = num(v); if (n == null) return "—"; return (n > 0 ? "+" : "") + formatNumber(n, digits == null ? 2 : digits) + "%"; }
  function shortVolume(v) { var n = num(v); if (n == null) return "—"; if (n >= 1000000) return formatNumber(n/1000000,2) + " triệu"; if (n >= 1000) return formatNumber(n/1000,1) + " nghìn"; return formatNumber(n,0); }
  function metricClass(v) { var n = num(v); return n > 0 ? "positive" : n < 0 ? "negative" : ""; }
  function logoHtml(symbol) { var safe=String(symbol||"").toUpperCase().replace(/[^A-Z0-9]/g,""); return '<span class="company-logo row-logo"><img class="company-logo-img" decoding="async" src="'+LOGO_BASE_URL+esc(safe)+'.jpg?v='+LOGO_VERSION+'" alt="" onerror="this.remove()"><span class="company-logo-fallback">'+esc(safe.slice(0,3)||"?")+'</span></span>'; }
  function signalRailHtml(row) {
    var values = [row.signal_price_3pct, row.signal_daily_volume_200pct, row.signal_above_ma200, row.signal_rvol30_200pct];
    var tones = ["price","volume","trend","rvol"];
    var segments = values.map(function (passed, i) { return '<span class="ccc-segment ccc-'+tones[i]+' '+(passed?'is-on':'is-off')+'"></span>'; }).join("");
    var count = Number(row.signal_count || 0);
    var label = count === 4 ? '<em>Hội tụ mạnh</em>' : count === 3 ? '<em>Đang hội tụ</em>' : '';
    return '<span class="ccc-rail '+(count===4?'is-confluent':count===3?'is-converging':'')+'"><span class="ccc-segments">'+segments+'</span><b>'+count+'/4</b>'+label+'</span>';
  }
  function rowHtml(row) {
    var company = row.display_name || row.company_name || "";
    var volumeRatio = num(row.daily_volume_pct) == null ? "—" : formatNumber(row.daily_volume_pct,0) + "% KLTB10";
    var rvol = num(row.rvol30_pct) == null ? "—" : formatNumber(row.rvol30_pct,0) + "%";
    var ma200 = pct(row.ma200_distance_pct,1);
    return '<article class="lovable-stock-row universal-stock-card ccc-entitled-row" data-entitled-symbol="'+esc(row.symbol)+'">' +
      '<div class="stock-row-identity">'+logoHtml(row.symbol)+'<div><strong>'+esc(row.symbol)+'</strong><span title="'+esc(company)+'">'+esc(company||"Tên công ty đang cập nhật")+'</span><small>'+esc(row.exchange||"")+'</small></div></div>' +
      '<div class="stock-row-price"><strong>'+formatNumber(row.current_price,0)+'</strong><span class="'+metricClass(row.price_change_pct)+'">'+pct(row.price_change_pct,2)+'</span></div>' +
      '<div class="stock-row-volume"><small>KL hiện tại</small><strong>'+shortVolume(row.volume_accumulated)+'</strong><span class="volume-ratio">'+esc(volumeRatio)+'</span></div>' +
      '<div class="stock-row-highlights"><div class="stock-row-highlight-line highlight-rvol"><span>RVOL30</span><strong>'+esc(rvol)+'</strong></div><div class="stock-row-highlight-line highlight-trend"><span>MA200</span><strong>'+esc(ma200)+'</strong></div></div>' +
      '<div class="stock-row-ccc">'+signalRailHtml(row)+'</div></article>';
  }
  function currentGroup() {
    if (state.group && GROUPS[state.group]) return state.group;
    var active = document.querySelector(".overview-density-trigger.active[data-overview-group]");
    var key = active ? active.getAttribute("data-overview-group") : "2plus";
    state.group = GROUPS[key] ? key : "2plus";
    return state.group;
  }
  function groupCounts(key) {
    var data = state.data || {};
    var def = GROUPS[key];
    return {
      market: Number(data.market_counts && data.market_counts[def.marketKey] || 0),
      mine: Number(data.watchlist_counts && data.watchlist_counts[def.marketKey] || 0)
    };
  }
  function effectiveFull() { return !!(state.data && state.data.effective_full_market_access); }
  function vipActive() { return !!(state.data && state.data.vip_day_active); }
  function visibleRows(key) { var def=GROUPS[key]; return ((state.data && state.data.rows) || []).filter(def.matcher).slice(0,10); }
  function lockedCount(key) { var c=groupCounts(key); return effectiveFull() ? 0 : Math.max(0,c.market-c.mine); }
  function vipEndLabel() { if (!state.data || !state.data.vip_day_ends_at) return ""; var d=new Date(state.data.vip_day_ends_at); return Number.isFinite(d.getTime()) ? d.toLocaleString("vi-VN",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}) : ""; }

  function patchWords() {
    document.querySelectorAll(".shell-nav-placeholder .nav-label,.shell-nav-placeholder small,.mobile-bottom .shell-nav-placeholder .nav-label,.mobile-bottom .shell-nav-placeholder small").forEach(function (node) {
      if (node.children.length) return;
      if (String(node.textContent||"").trim() === "Watchlist") node.textContent = "DS mã theo dõi";
    });
    var overview = document.querySelector("main.lovable-overview");
    if (!overview) return;
    var subtitle = overview.querySelector(".page-heading h1 + p");
    if (subtitle) subtitle.textContent = "Theo dõi sức nóng toàn thị trường và các tín hiệu xuất hiện trong DS mã theo dõi của bạn.";
    var densityHead = overview.querySelector(".signal-density .section-bar");
    if (densityHead) {
      var span = densityHead.querySelector("div>span"); if (span) span.textContent = "Số lớn là toàn thị trường; mỗi thẻ cho biết có bao nhiêu mã trong DS của bạn.";
      var small = densityHead.querySelector("small"); if (small) small.textContent = "Không tiết lộ mã ngoài quyền xem";
    }
  }

  function patchTiles() {
    if (!state.data) return;
    document.querySelectorAll(".overview-density-trigger[data-overview-group]").forEach(function (tile) {
      var key=tile.getAttribute("data-overview-group"); if (!GROUPS[key]) return;
      var counts=groupCounts(key);
      var strong=tile.querySelector(":scope > strong"); if (strong) strong.innerHTML=counts.market+'<small> mã</small>';
      var footer=tile.querySelector(":scope > div");
      if (footer) footer.innerHTML='<em>Toàn thị trường</em><b>'+(effectiveFull() ? (vipActive()?'VIP 24h · đang mở toàn thị trường':'Bạn đang mở toàn thị trường') : 'DS mã theo dõi của bạn: '+counts.mine+' mã')+'</b>';
      tile.classList.toggle("active", key===currentGroup()); tile.setAttribute("aria-pressed",key===currentGroup()?"true":"false");
    });
  }

  function ctaHtml(key) {
    var counts=groupCounts(key), locked=lockedCount(key);
    if (effectiveFull() || locked <= 0) return "";
    return '<section class="ccc-overview-upsell"><div><span>CÒN '+locked+' MÃ KHÁC</span><strong>'+counts.market+' mã trên thị trường đang thuộc nhóm '+esc(GROUPS[key].title)+'.</strong><p>Bạn đang xem chi tiết '+counts.mine+' mã trong DS mã theo dõi. Các mã còn lại không bị tiết lộ danh tính.</p></div><div class="ccc-overview-upsell-actions"><button type="button" data-ccc-vip-preview>Mở FULL 24 giờ · 100.000đ</button><a href="/tai-khoan">Mở rộng DS mã theo dõi</a></div></section>';
  }

  function emptyHtml(key) {
    var counts=groupCounts(key);
    if (!state.data.watchlist_count && !effectiveFull()) {
      return '<div class="ccc-overview-empty"><strong>Bạn chưa có mã theo dõi</strong><span>Gói '+esc(state.data.base_plan_name||state.data.base_plan_code||"")+' cho phép bạn thiết lập DS mã theo dõi. KPI phía trên vẫn cho biết thị trường đang có bao nhiêu cơ hội tín hiệu.</span><a href="/tai-khoan">Thiết lập DS mã theo dõi</a></div>';
    }
    return '<div class="ccc-overview-empty"><strong>Thị trường hiện có '+counts.market+' mã '+esc(GROUPS[key].title.toLowerCase())+'.</strong><span>Hiện chưa có mã nào trong DS mã theo dõi của bạn đạt điều kiện này.</span><div><a href="/tai-khoan">Quản lý DS mã theo dõi</a>' + (!effectiveFull()?'<button type="button" data-ccc-vip-preview>Mở FULL 24 giờ · 100.000đ</button>':'') + '</div></div>';
  }

  function renderResults() {
    if (!state.data) return;
    var key=currentGroup(), counts=groupCounts(key), rows=visibleRows(key);
    var section=document.getElementById("overview-results"); if (!section) return;
    section.setAttribute("data-ccc-group",key);
    var h2=section.querySelector(".section-bar h2");
    if (h2) h2.textContent = effectiveFull() ? "Tín hiệu toàn thị trường" : "Tín hiệu trong DS mã theo dõi của bạn";
    var summary=document.getElementById("overview-selection-summary");
    if (summary) summary.innerHTML='Đang xem: <b>'+esc(GROUPS[key].title)+'</b> · '+counts.market+' mã toàn thị trường · '+(effectiveFull()?rows.length+' mã đang hiển thị':counts.mine+' mã trong DS của bạn');
    var count=document.getElementById("overview-selection-count"); if(count) count.textContent=rows.length+' mã hiển thị';
    var container=document.getElementById("overview-rows"); if(container) container.innerHTML=rows.length?rows.map(rowHtml).join(""):emptyHtml(key);
    var see=document.getElementById("overview-see-all-slot"); if(see) see.innerHTML="";
    var locked=document.getElementById("overview-locked-slot"); if(locked) locked.innerHTML=ctaHtml(key);
    bindVipPreview();
  }

  function vipModalHtml() {
    return '<div id="ccc-vip-preview" class="ccc-vip-backdrop"><section class="ccc-vip-dialog" role="dialog" aria-modal="true" aria-labelledby="ccc-vip-title"><button type="button" class="ccc-vip-close" aria-label="Đóng">×</button><span class="ccc-vip-kicker">VIP DAY</span><h2 id="ccc-vip-title">Mở toàn bộ CCC trong 24 giờ</h2><strong class="ccc-vip-price">100.000đ <small>/ 24 giờ</small></strong><ul><li>Xem toàn bộ tín hiệu kỹ thuật trên thị trường.</li><li>Quyền FULL tạm thời trong đúng 24 giờ kể từ khi kích hoạt.</li><li>Không thay đổi gói nền, DS mã theo dõi, quota hay ngày reset hiện tại.</li><li>Hết 24 giờ, tài khoản tự trở lại đúng trạng thái trước khi mua VIP.</li></ul><button type="button" class="ccc-vip-disabled" disabled>Thanh toán sẽ mở ở bước billing</button><p>VIP Day là quyền truy cập tạm thời, không phải khuyến nghị đầu tư hay cam kết lợi nhuận.</p></section></div>';
  }
  function openVipPreview() {
    if (document.getElementById("ccc-vip-preview")) return;
    document.body.insertAdjacentHTML("beforeend",vipModalHtml());
    var root=document.getElementById("ccc-vip-preview");
    root.querySelector(".ccc-vip-close").addEventListener("click",function(){root.remove();});
    root.addEventListener("click",function(e){if(e.target===root)root.remove();});
  }
  function bindVipPreview() { document.querySelectorAll("[data-ccc-vip-preview]").forEach(function(btn){if(btn.dataset.cccBound)return;btn.dataset.cccBound="1";btn.addEventListener("click",openVipPreview);}); }

  function showVipStatus() {
    var overview=document.querySelector("main.lovable-overview"); if(!overview || !vipActive()) return;
    var heading=overview.querySelector(".page-heading-meta");
    if (!heading) { heading=document.createElement("div"); heading.className="page-heading-meta"; overview.querySelector(".page-heading").appendChild(heading); }
    var chip=heading.querySelector(".ccc-vip-active-chip"); if(!chip){chip=document.createElement("span");chip.className="ccc-vip-active-chip";heading.appendChild(chip);}
    chip.textContent="VIP 24h · đến "+vipEndLabel();
  }

  function renderAll() { if(!isOverview()||!state.data)return; document.body.classList.remove("ccc-member-entitlement-loading"); document.body.classList.add("ccc-member-entitlement-ready"); patchWords(); patchTiles(); renderResults(); showVipStatus(); }

  async function load(force) {
    if (!isOverview() || state.loading) return;
    var client=getClient(); if(!client)return;
    try {
      var sessionResult=await client.auth.getSession(); if(sessionResult.error)throw sessionResult.error;
      var user=sessionResult.data&&sessionResult.data.session?sessionResult.data.session.user:null;
      if(!user){state.userId="";state.data=null;document.body.classList.remove("ccc-member-entitlement-loading","ccc-member-entitlement-ready");return;}
      if(!force && state.data && state.userId===user.id){renderAll();return;}
      state.userId=user.id; state.loading=true; state.error="";
      var result=await client.rpc("get_my_overview_state"); if(result.error)throw result.error;
      state.data=result.data||null; renderAll();
    } catch(error){console.error("CCC overview entitlement load failed",error);state.error="Không tải được quyền Tổng quan.";}
    finally{state.loading=false;}
  }

  function interceptTile(event) {
    var tile=event.target&&event.target.closest?event.target.closest(".overview-density-trigger[data-overview-group]"):null;
    if(!tile||!state.data||!isOverview())return;
    var key=tile.getAttribute("data-overview-group"); if(!GROUPS[key])return;
    event.preventDefault(); event.stopPropagation(); event.stopImmediatePropagation();
    state.group=key; renderAll();
  }

  function patchSoon() {
    if(!isOverview())return;
    if(state.data) requestAnimationFrame(renderAll);
    else load(false);
  }

  function init() {
    if (isOverview()) document.body.classList.add("ccc-member-entitlement-loading");
    document.addEventListener("click",interceptTile,true);
    window.addEventListener("ccc:watchlist-updated",function(){load(true);});
    var attempts=0,timer=setInterval(function(){attempts++;var client=getClient();if(client||attempts>60){clearInterval(timer);if(client&&client.auth&&client.auth.onAuthStateChange)client.auth.onAuthStateChange(function(){state.data=null;setTimeout(function(){load(true);},0);});load(true);}},50);
    var observer=new MutationObserver(function(){if(state.observerBusy)return;state.observerBusy=true;requestAnimationFrame(function(){state.observerBusy=false;patchSoon();});});
    observer.observe(document.getElementById("app")||document.body,{childList:true,subtree:true});
    window.addEventListener("popstate",function(){setTimeout(patchSoon,0);});
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init,{once:true});else init();
})();
