function installBackendTriggers() {
  deleteBackendTriggers();

  ScriptApp.newTrigger('scheduledDailyBaseline').timeBased().atHour(1).everyDays(1).create();
  ScriptApp.newTrigger('scheduledIntradayScan').timeBased().everyMinutes(5).create();
  ScriptApp.newTrigger('scheduledMarketPulseScan').timeBased().everyMinutes(5).create();

  return {
    ok: true,
    cadence_minutes: 5,
    triggers: ['scheduledDailyBaseline','scheduledIntradayScan','scheduledMarketPulseScan']
  };
}

function deleteBackendTriggers() {
  const managedHandlers = new Set([
    'runDailyBaselineNow',
    'scheduledDailyBaseline',
    'scheduledIntradayScan',
    'runMarketPulseNow',
    'scheduledMarketPulseScan'
  ]);

  ScriptApp.getProjectTriggers().forEach(function (trigger) {
    if (managedHandlers.has(trigger.getHandlerFunction())) ScriptApp.deleteTrigger(trigger);
  });

  return { ok: true };
}
