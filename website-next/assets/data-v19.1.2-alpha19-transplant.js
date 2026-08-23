(function (global) {
  "use strict";

  var SUPABASE_URL = "https://wevtlkowpbmpdggcfbvn.supabase.co";
  var SUPABASE_KEY = "sb_publishable_qN__TQuoNBRUFhxuY5CtNw_88WZDdJw";
  var client = null;
  var researchPromise = null;

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


  async function getMyOverviewState() {
    return throwIfError(await requireClient().rpc("get_my_overview_state"));
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

  global.CCCData = Object.freeze({
    init: requireClient,
    getSession: getSession,
    onAuthStateChange: onAuthStateChange,
    signInWithPassword: signInWithPassword,
    signInWithGoogle: signInWithGoogle,
    signOut: signOut,
    loadMembership: loadMembership,
    saveProfile: saveProfile,
    getWatchlistState: getWatchlistState,
    replaceWatchlist: replaceWatchlist,
    searchMetadata: searchMetadata,
    getMyOverviewState: getMyOverviewState,
    getPublicOverviewState: getPublicOverviewState,
    loadMarketPulse: loadMarketPulse,
    loadResearch: loadResearch
  });
})(window);
