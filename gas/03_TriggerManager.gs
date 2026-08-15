/**
 * Cài lại toàn bộ trigger của backend.
 *
 * Chỉ cần chạy thủ công một lần.
 */
function installBackendTriggers() {
  deleteBackendTriggers();

  // Daily Baseline:
  // GAS sẽ chạy một lần trong khoảng 01:00–02:00.
  ScriptApp
    .newTrigger('runDailyBaselineNow')
    .timeBased()
    .atHour(1)
    .everyDays(1)
    .create();

  // Intraday:
  // Trigger thức dậy mỗi 10 phút.
  // Hàm scheduledIntradayScan() tự kiểm tra
  // ngày làm việc và giờ giao dịch trước khi gọi GitHub.
  ScriptApp
    .newTrigger('scheduledIntradayScan')
    .timeBased()
    .everyMinutes(10)
    .create();

  return {
    ok: true,
    triggers: [
      'runDailyBaselineNow',
      'scheduledIntradayScan'
    ]
  };
}


/**
 * Chỉ xóa hai trigger backend do hệ thống này quản lý.
 * Không ảnh hưởng các trigger khác trong project.
 */
function deleteBackendTriggers() {
  const managedHandlers = new Set([
    'runDailyBaselineNow',
    'scheduledIntradayScan'
  ]);

  ScriptApp
    .getProjectTriggers()
    .forEach(function (trigger) {
      const handler =
        trigger.getHandlerFunction();

      if (managedHandlers.has(handler)) {
        ScriptApp.deleteTrigger(trigger);
      }
    });

  return {
    ok: true
  };
}
