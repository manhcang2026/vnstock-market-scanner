function installBackendTriggers() {
  deleteBackendTriggers();
  ScriptApp.newTrigger('runDailyBaselineNow').timeBased().atHour(1).everyDays(1).create();
  ScriptApp.newTrigger('scheduledIntradayScan').timeBased().everyMinutes(10).create();
  return {ok: true};
}

function deleteBackendTriggers() {
  const names = new Set(['runDailyBaselineNow', 'scheduledIntradayScan']);
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (names.has(trigger.getHandlerFunction())) ScriptApp.deleteTrigger(trigger);
  });
  return {ok: true};
}
