/**
 * Cài lại toàn bộ trigger backend production.
 *
 * QUAN TRỌNG: sau khi update các file GAS, chạy thủ công
 * installBackendTriggers() đúng MỘT LẦN để:
 * - xóa Daily Baseline 01:00 cũ;
 * - tạo EOD Finalize sau đóng cửa;
 * - giữ Intraday + Market Pulse mỗi 5 phút.
 */
function installBackendTriggers() {
  deleteBackendTriggers();

  // EOD Finalize: khoảng 15:30 giờ project (nearMinute ±15 phút).
  // Mốc sớm nhất khoảng 15:15, sau safety cutoff 15:10 của Python.
  ScriptApp
    .newTrigger('scheduledEodFinalize')
    .timeBased()
    .atHour(15)
    .nearMinute(30)
    .everyDays(1)
    .create();

  // Intraday: 5 phút/lần.
  // scheduledIntradayScan() tự lọc ngày làm việc + giờ giao dịch.
  ScriptApp
    .newTrigger('scheduledIntradayScan')
    .timeBased()
    .everyMinutes(5)
    .create();

  // Market Pulse: 5 phút/lần, 24/7.
  ScriptApp
    .newTrigger('scheduledMarketPulseScan')
    .timeBased()
    .everyMinutes(5)
    .create();

  return {
    ok: true,
    cadence_minutes: 5,
    eod_near: '15:30',
    triggers: [
      'scheduledEodFinalize',
      'scheduledIntradayScan',
      'scheduledMarketPulseScan'
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
    'runEodFinalizeNow',
    'scheduledEodFinalize',
    'scheduledIntradayScan',
    'runMarketPulseNow',
    'scheduledMarketPulseScan'
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
