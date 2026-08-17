/**
 * Cài lại toàn bộ trigger của backend.
 *
 * QUAN TRỌNG: sau khi update file này trên GAS, chạy thủ công
 * installBackendTriggers() đúng MỘT LẦN để xóa trigger 10 phút cũ
 * và tạo trigger 5 phút mới.
 */
function installBackendTriggers() {
  deleteBackendTriggers();

  // Daily Baseline: thức dậy một lần trong khoảng 01:00–02:00.
  ScriptApp
    .newTrigger('scheduledDailyBaseline')
    .timeBased()
    .atHour(1)
    .everyDays(1)
    .create();

  // Intraday: 5 phút/lần.
  // scheduledIntradayScan() tự lọc ngày làm việc + giờ giao dịch.
  ScriptApp
    .newTrigger('scheduledIntradayScan')
    .timeBased()
    .everyMinutes(5)
    .create();

  return {
    ok: true,
    cadence_minutes: 5,
    triggers: [
      'scheduledDailyBaseline',
      'scheduledIntradayScan'
    ]
  };
}


/**
 * Chỉ xóa các trigger backend do hệ thống này quản lý.
 */
function deleteBackendTriggers() {
  const managedHandlers = new Set([
    'runDailyBaselineNow',
    'scheduledDailyBaseline',
    'scheduledIntradayScan'
  ]);

  ScriptApp
    .getProjectTriggers()
    .forEach(function (trigger) {
      const handler = trigger.getHandlerFunction();
      if (managedHandlers.has(handler)) {
        ScriptApp.deleteTrigger(trigger);
      }
    });

  return {
    ok: true
  };
}
