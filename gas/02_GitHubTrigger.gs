/**
 * Chạy job Daily Baseline thủ công.
 *
 * Hàm này KHÔNG kiểm tra thứ trong tuần.
 * Dùng khi cần test / chạy phục hồi thủ công từ GAS.
 */
function runDailyBaselineNow() {
  return dispatchWorkflow_(
    CONFIG.DAILY_WORKFLOW_FILE
  );
}


/**
 * Daily Baseline production tự động.
 *
 * Chỉ dispatch GitHub từ thứ Ba đến thứ Bảy:
 * - Thứ Ba sáng lấy phiên chốt thứ Hai.
 * - ...
 * - Thứ Bảy sáng lấy phiên chốt thứ Sáu.
 */
function scheduledDailyBaseline() {
  const now = new Date();
  const day = now.getDay();

  if (day === 0 || day === 1) {
    return {
      ok: true,
      skipped: 'daily_baseline_off_day'
    };
  }

  return dispatchWorkflow_(
    CONFIG.DAILY_WORKFLOW_FILE
  );
}


/**
 * Chạy Intraday production thủ công.
 * Vẫn tuân thủ giờ giao dịch; Python tự bỏ qua nếu ngoài giờ.
 */
function runIntradayScanNow() {
  return dispatchWorkflow_(
    CONFIG.INTRADAY_WORKFLOW_FILE
  );
}


/**
 * Chạy Intraday thủ công ngoài giờ để test kết nối.
 */
function runIntradayScanForceNow() {
  return dispatchWorkflow_(
    CONFIG.INTRADAY_WORKFLOW_FILE,
    {
      force_run: 'true'
    }
  );
}


/**
 * Trigger Intraday production.
 *
 * Cadence: 5 phút.
 * Cho phép grace 4 phút sau 11:30 và 15:00 vì Apps Script trigger
 * thường thức dậy trễ ~1 phút. Python sẽ clamp các run này về
 * snapshot 11:30 hoặc 15:00.
 */
function scheduledIntradayScan() {
  const now = new Date();
  const day = now.getDay();

  if (day === 0 || day === 6) {
    return {
      ok: true,
      skipped: 'weekend'
    };
  }

  const minutes =
    now.getHours() * 60 +
    now.getMinutes();

  const closeGraceMinutes = 4;

  const inMorning =
    minutes >= 9 * 60 &&
    minutes <= 11 * 60 + 30 + closeGraceMinutes;

  const inAfternoon =
    minutes >= 13 * 60 &&
    minutes <= 15 * 60 + closeGraceMinutes;

  if (!inMorning && !inAfternoon) {
    return {
      ok: true,
      skipped: 'outside_market_hours'
    };
  }

  return dispatchWorkflow_(
    CONFIG.INTRADAY_WORKFLOW_FILE
  );
}


/**
 * Phát workflow_dispatch đến GitHub.
 */
function dispatchWorkflow_(
  workflowFile,
  inputs
) {
  const token = PropertiesService
    .getScriptProperties()
    .getProperty('GITHUB_TOKEN');

  if (!token) {
    throw new Error(
      'Chua cau hinh Script Property GITHUB_TOKEN'
    );
  }

  const url =
    `https://api.github.com/repos/` +
    `${CONFIG.GITHUB_OWNER}/` +
    `${CONFIG.GITHUB_REPO}/` +
    `actions/workflows/` +
    `${workflowFile}/dispatches`;

  const payload = {
    ref: CONFIG.GITHUB_BRANCH
  };

  if (
    inputs &&
    typeof inputs === 'object'
  ) {
    payload.inputs = inputs;
  }

  const response = UrlFetchApp.fetch(
    url,
    {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    }
  );

  const code = response.getResponseCode();

  if (code !== 204) {
    throw new Error(
      `GitHub dispatch loi ${code}: ` +
      response.getContentText()
    );
  }

  return {
    ok: true,
    workflow: workflowFile,
    inputs: payload.inputs || {}
  };
}
