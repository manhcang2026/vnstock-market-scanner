/**
 * Cài lại toàn bộ trigger của backend.
 *
 * Chỉ cần chạy thủ công một lần sau khi update code GAS.
 */
function installBackendTriggers() {
  deleteBackendTriggers();

  // Daily Baseline:
  // Trigger thức dậy một lần trong khoảng 01:00–02:00 mỗi ngày.
  // scheduledDailyBaseline() tự lọc: chỉ chạy thứ Ba -> thứ Bảy.
  ScriptApp
    .newTrigger('scheduledDailyBaseline')
    .timeBased()
    .atHour(1)
    .everyDays(1)
    .create();

  // Intraday:
  // Trigger thức dậy mỗi 10 phút.
  // scheduledIntradayScan() tự kiểm tra
  // ngày làm việc và giờ giao dịch trước khi gọi GitHub.
  ScriptApp
    .newTrigger('scheduledIntradayScan')
    .timeBased()
    .everyMinutes(10)
    .create();

  return {
    ok: true,
    triggers: [
      'scheduledDailyBaseline',
      'scheduledIntradayScan'
    ]
  };
}


/**
 * Chỉ xóa các trigger backend do hệ thống này quản lý.
 *
 * Có giữ tên runDailyBaselineNow trong danh sách để dọn trigger cũ
 * nếu project đang còn trigger daily phiên bản trước.
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
