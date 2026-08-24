(function (global) {
  "use strict";

  var SUPABASE_URL = "https://wevtlkowpbmpdggcfbvn.supabase.co";
  var SUPABASE_KEY = "sb_publishable_qN__TQuoNBRUFhxuY5CtNw_88WZDdJw";
  var client = null;
  var researchPromise = null;
  var searchUniversePromise = null;

  function requireClient() {
    if (client) return client;
    if (!global.supabase || typeof global.supabase.createClient !== "function") {
      throw new Error("SUPABASE_LIBRARY_UNAVAILABLE");
    }
    client = global.supabase.createClient(SUPABASE_URL, SUPABASE_KEY, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true
      }
    });
    return client;
  }

  function throwIfError(result) {
    if (result && result.error) throw result.error;
    return result ? result.data : null;
  }

  async function getSession() {
    return throwIfError(await requireClient().auth.getSession());
  }

  function onAuthStateChange(callback) {
    return requireClient().auth.onAuthStateChange(callback);
  }

  async function signInWithPassword(email, password) {
    return throwIfError(await requireClient().auth.signInWithPassword({
      email: email,
      password: password
    }));
  }

  async function signInWithGoogle(redirectTo) {
    return throwIfError(await requireClient().auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: redirectTo }
    }));
  }

  async function signOut() {
    return throwIfError(await requireClient().auth.signOut());
  }

  async function changePassword(currentPassword, newPassword) {
    var sb = requireClient();
    var sessionData = throwIfError(await sb.auth.getSession());
    var user = sessionData && sessionData.session && sessionData.session.user;
    var email = user && user.email;
    if (!email) throw new Error("PASSWORD_EMAIL_REQUIRED");

    throwIfError(await sb.auth.signInWithPassword({
      email: email,
      password: currentPassword
    }));

    return throwIfError(await sb.auth.updateUser({
      password: newPassword
    }));
  }

  async function loadMembership(userId) {
    var sb = requireClient();
    var results = await Promise.all([
      sb.from("profiles")
        .select("id,display_name,avatar_url,role,status,phone,address,profile_completed,profile_completed_at")
        .eq("id", userId)
        .maybeSingle(),
      sb.from("subscriptions")
        .select("id,user_id,plan_id,status,cycle_start,cycle_end,change_used,initial_setup_completed,grace_started_at,grace_end_at,upgrade_free_additions_remaining,created_at")
        .eq("user_id", userId)
        .in("status", ["ACTIVE", "GRACE", "SUSPENDED"])
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle(),
      sb.from("plans")
        .select("id,plan_code,display_name,price_vnd,view_limit,watchlist_limit,change_limit,full_market_access,email_alerts,telegram_alerts,is_recommended,is_active")
        .eq("is_active", true)
        .order("price_vnd", { ascending: true })
    ]);
    results.forEach(throwIfError);
    var profile = results[0].data || null;
    var subscription = results[1].data || null;
    var catalog = Array.isArray(results[2].data) ? results[2].data : [];
    var plan = null;
    if (subscription && subscription.plan_id != null) {
      plan = throwIfError(await sb.from("plans")
        .select("id,plan_code,display_name,price_vnd,view_limit,watchlist_limit,change_limit,full_market_access,email_alerts,telegram_alerts,is_recommended,is_active")
        .eq("id", subscription.plan_id)
        .maybeSingle()) || null;
    }
    return { profile: profile, subscription: subscription, plan: plan, catalog: catalog };
  }

  async function saveProfile(displayName, phone, address) {
    return throwIfError(await requireClient().rpc("save_my_profile", {
      p_display_name: displayName,
      p_phone: phone,
      p_address: address || null
    }));
  }

  async function getWatchlistState() {
    return throwIfError(await requireClient().rpc("get_my_watchlist_state"));
  }

  async function replaceWatchlist(symbols) {
    return throwIfError(await requireClient().rpc("replace_my_watchlist", {
      p_symbols: symbols
    }));
  }

  async function loadSearchUniverse(force) {
    if (searchUniversePromise && !force) return searchUniversePromise;
    var sb = requireClient();
    searchUniversePromise = sb.from("stock_metadata")
      .select("symbol,display_name,company_name,exchange")
      .order("symbol", { ascending: true })
      .limit(2000)
      .then(function (result) {
        var rows = throwIfError(result) || [];
        return Array.isArray(rows) ? rows : [];
      })
      .catch(function (error) {
        searchUniversePromise = null;
        throw error;
      });
    return searchUniversePromise;
  }

  async function searchMetadata(query) {
    var sb = requireClient();
    var clean = String(query || "").replace(/[%_,()]/g, " ").trim();
    if (!clean) return [];
    var upper = clean.toUpperCase();
    var results = await Promise.all([
      sb.from("stock_metadata").select("symbol,display_name,company_name,exchange").ilike("symbol", upper + "%").limit(8),
      sb.from("stock_metadata").select("symbol,display_name,company_name,exchange").ilike("display_name", "%" + clean + "%").limit(8),
      sb.from("stock_metadata").select("symbol,display_name,company_name,exchange").ilike("company_name", "%" + clean + "%").limit(8)
    ]);
    var merged = [];
    var seen = Object.create(null);
    results.forEach(function (result) {
      throwIfError(result);
      (result.data || []).forEach(function (row) {
        var symbol = String(row.symbol || "").toUpperCase();
        if (!symbol || seen[symbol]) return;
        seen[symbol] = true;
        merged.push({
          symbol: symbol,
          display_name: row.display_name || "",
          company_name: row.company_name || "",
          exchange: row.exchange || ""
        });
      });
    });
    merged.sort(function (a, b) {
      var aRank = a.symbol === upper ? 0 : a.symbol.indexOf(upper) === 0 ? 1 : 2;
      var bRank = b.symbol === upper ? 0 : b.symbol.indexOf(upper) === 0 ? 1 : 2;
      return aRank - bRank || a.symbol.localeCompare(b.symbol);
    });
    return merged.slice(0, 8);
  }



  async function loadScannerMarketBasics() {
    var rows = throwIfError(await requireClient().rpc("get_public_scanner_basics"));
    return Array.isArray(rows) ? rows : [];
  }

  async function getMyOverviewState() {
    return throwIfError(await requireClient().rpc("get_my_overview_state"));
  }

  async function getAccessContext() {
    return throwIfError(await requireClient().rpc("get_my_access_context"));
  }

  async function getMyOverviewPage(group, page, pageSize) {
    return throwIfError(await requireClient().rpc("get_my_overview_page", {
      p_group: group || "all",
      p_page: page || 1,
      p_page_size: pageSize || 20
    }));
  }

  async function getMyScannerPage(options) {
    options = options || {};
    return throwIfError(await requireClient().rpc("get_my_scanner_page", {
      p_scope: options.scope || "PERSONAL",
      p_signal: options.signal || "",
      p_exchange: options.exchange || "all",
      p_query: options.query || "",
      p_sort: options.sort || "signal_desc",
      p_page: options.page || 1,
      p_page_size: options.pageSize || 50
    }));
  }

  async function getPublicOverviewState() {
    return throwIfError(await requireClient().rpc("get_public_overview_state"));
  }

  async function loadMarketPulse() {
    var result = await requireClient()
      .from("market_pulse_current")
      .select("key,display_name,sort_order,price,previous_close,change_value,change_pct,currency,market_status,market_time,last_success_at,checked_at,data_status")
      .order("sort_order", { ascending: true });
    return throwIfError(result) || [];
  }

  async function loadResearch(force) {
    if (researchPromise && !force) return researchPromise;
    var sb = requireClient();
    researchPromise = Promise.all([
      sb.from("financial_latest").select("*").order("symbol", { ascending: true }).limit(2000),
      sb.from("stock_metadata").select("symbol,display_name,company_name,exchange").order("symbol", { ascending: true }).limit(2000)
    ]).then(function (results) {
      results.forEach(throwIfError);
      return {
        financial: Array.isArray(results[0].data) ? results[0].data : [],
        metadata: Array.isArray(results[1].data) ? results[1].data : []
      };
    }).catch(function (error) {
      researchPromise = null;
      throw error;
    });
    return researchPromise;
  }


  function detailSymbol(value) {
    var symbol = String(value || "").trim().toUpperCase();
    if (!/^[A-Z0-9]{1,12}$/.test(symbol)) throw new Error("INVALID_SYMBOL");
    return symbol;
  }

  async function publicRestRows(tableName, params) {
    var search = new URLSearchParams(params || {});
    var response = await fetch(SUPABASE_URL + "/rest/v1/" + tableName + "?" + search.toString(), {
      cache: "no-store",
      headers: {
        "apikey": SUPABASE_KEY,
        "Accept": "application/json"
      }
    });
    if (!response.ok) throw new Error("PUBLIC_REST_" + tableName.toUpperCase() + "_HTTP_" + response.status);
    var rows = await response.json();
    return Array.isArray(rows) ? rows : [];
  }

  async function loadStockDetailBasic(symbol) {
    symbol = detailSymbol(symbol);
    var result = await requireClient()
      .rpc("get_public_scanner_basics")
      .eq("symbol", symbol)
      .limit(1);
    var rows = throwIfError(result) || [];
    return Array.isArray(rows) && rows.length ? rows[0] : null;
  }

  async function loadStockDetailMetadata(symbol) {
    symbol = detailSymbol(symbol);
    var result = await requireClient()
      .from("stock_metadata")
      .select("symbol,display_name,company_name,exchange,website_group,financial_model,metadata_status,updated_at")
      .eq("symbol", symbol)
      .maybeSingle();
    return throwIfError(result) || null;
  }

  async function loadStockDetailFinancial(symbol) {
    symbol = detailSymbol(symbol);
    var rows = await publicRestRows("financial_latest", {
      select: "symbol,website_group,financial_model,period,year,quarter,profit_yoy_pct,income_yoy_pct,profit_qoq_pct,roea_pct,roaa_pct,debt_equity_pct,debt_assets_pct,pe,pb,data_status,freshness_status,updated_at",
      symbol: "eq." + symbol,
      limit: "1"
    });
    return rows.length ? rows[0] : null;
  }

  async function loadStockDetailQuarterly(symbol) {
    symbol = detailSymbol(symbol);
    return publicRestRows("financial_quarterly", {
      select: "symbol,period,year,quarter,income_bil_vnd,net_profit_bil_vnd,parent_net_profit_bil_vnd,profit_yoy_pct,roea_pct,data_status,freshness_status,updated_at",
      symbol: "eq." + symbol,
      order: "year.desc,quarter.desc",
      limit: "9"
    });
  }

  async function loadStockDetailValuationPeers(websiteGroup) {
    var group = String(websiteGroup || "").trim();
    if (!group) return [];
    return publicRestRows("financial_latest", {
      select: "pe,pb",
      website_group: "eq." + group,
      limit: "200"
    });
  }

  async function getGuestDemoTechnical(symbol) {
    symbol = detailSymbol(symbol);
    var data = await getPublicOverviewState();
    var rows = data && Array.isArray(data.sample_rows) ? data.sample_rows : [];
    return rows.find(function (row) {
      return String(row && row.symbol || "").toUpperCase() === symbol;
    }) || null;
  }

  async function getMemberStockTechnical(symbol, scope) {
    symbol = detailSymbol(symbol);
    var result = await getMyScannerPage({
      scope: scope === "MARKET" ? "MARKET" : "PERSONAL",
      signal: "",
      exchange: "all",
      query: symbol,
      sort: "symbol",
      page: 1,
      pageSize: 10
    });
    var rows = result && Array.isArray(result.rows) ? result.rows : [];
    return rows.find(function (row) {
      return String(row && row.symbol || "").toUpperCase() === symbol;
    }) || null;
  }


  global.CCCData = Object.freeze({
    init: requireClient,
    getSession: getSession,
    onAuthStateChange: onAuthStateChange,
    signInWithPassword: signInWithPassword,
    signInWithGoogle: signInWithGoogle,
    signOut: signOut,
    changePassword: changePassword,
    loadMembership: loadMembership,
    saveProfile: saveProfile,
    getWatchlistState: getWatchlistState,
    replaceWatchlist: replaceWatchlist,
    loadSearchUniverse: loadSearchUniverse,
    searchMetadata: searchMetadata,
    loadScannerMarketBasics: loadScannerMarketBasics,
    getMyOverviewState: getMyOverviewState,
    getAccessContext: getAccessContext,
    getMyOverviewPage: getMyOverviewPage,
    getMyScannerPage: getMyScannerPage,
    getPublicOverviewState: getPublicOverviewState,
    loadMarketPulse: loadMarketPulse,
    loadResearch: loadResearch,
    loadStockDetailBasic: loadStockDetailBasic,
    loadStockDetailMetadata: loadStockDetailMetadata,
    loadStockDetailFinancial: loadStockDetailFinancial,
    loadStockDetailQuarterly: loadStockDetailQuarterly,
    loadStockDetailValuationPeers: loadStockDetailValuationPeers,
    getGuestDemoTechnical: getGuestDemoTechnical,
    getMemberStockTechnical: getMemberStockTechnical
  });
})(window);
