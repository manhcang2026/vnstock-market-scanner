/**
 * Chạy job Daily Baseline thủ công.
 */
function runDailyBaselineNow() {
  return dispatchWorkflow_(
    CONFIG.DAILY_WORKFLOW_FILE
  );
}


/**
 * Chạy Intraday production thủ công.
 *
 * Vẫn tuân thủ giờ giao dịch.
 * Nếu chạy ngoài giờ, Python sẽ tự bỏ qua.
 */
function runIntradayScanNow() {
  return dispatchWorkflow_(
    CONFIG.INTRADAY_WORKFLOW_FILE
  );
}


/**
 * Chạy Intraday thủ công ngoài giờ.
 *
 * Chỉ dùng để kiểm tra:
 * - GitHub Actions
 * - nguồn dữ liệu
 * - kết nối GAS
 * - ghi Dashboard_Current
 *
 * Không dùng cho trigger tự động.
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
 * Hàm trigger production.
 *
 * Chỉ phát lệnh từ thứ Hai đến thứ Sáu,
 * trong hai phiên giao dịch.
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

  const inMorning =
    minutes >= 9 * 60 &&
    minutes <= 11 * 60 + 30;

  const inAfternoon =
    minutes >= 13 * 60 &&
    minutes <= 15 * 60;

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
 *
 * inputs là tùy chọn.
 * Production bình thường không truyền inputs.
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

  const code =
    response.getResponseCode();

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
