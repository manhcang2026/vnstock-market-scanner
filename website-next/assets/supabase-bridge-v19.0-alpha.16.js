(function () {
  "use strict";

  if (!window.supabase || typeof window.supabase.createClient !== "function") return;
  if (window.__cccSupabaseCreateClientWrapped) return;

  window.__cccSupabaseCreateClientWrapped = true;
  window.__cccSupabaseClients = window.__cccSupabaseClients || [];

  var originalCreateClient = window.supabase.createClient.bind(window.supabase);

  window.supabase.createClient = function () {
    var client = originalCreateClient.apply(null, arguments);
    try {
      window.__cccSupabaseClients.push(client);
      window.__cccSupabaseClient = client;
    } catch (_) {}
    return client;
  };
})();
