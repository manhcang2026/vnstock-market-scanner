function runDailyBaselineNow() {
  return dispatchWorkflow_(CONFIG.DAILY_WORKFLOW_FILE);
}

function scheduledDailyBaseline() {
  const day = new Date().getDay();
  if (day === 0 || day === 1) return { ok: true, skipped: 'daily_baseline_off_day' };
  return dispatchWorkflow_(CONFIG.DAILY_WORKFLOW_FILE);
}

function runIntradayScanNow() {
  return dispatchWorkflow_(CONFIG.INTRADAY_WORKFLOW_FILE);
}

function runIntradayScanForceNow() {
  return dispatchWorkflow_(CONFIG.INTRADAY_WORKFLOW_FILE, { force_run: 'true' });
}

function runMarketPulseNow() {
  return dispatchWorkflow_(CONFIG.MARKET_PULSE_WORKFLOW_FILE);
}

function scheduledIntradayScan() {
  const now = new Date();
  const day = now.getDay();
  if (day === 0 || day === 6) return { ok: true, skipped: 'weekend' };

  const minutes = now.getHours() * 60 + now.getMinutes();
  const grace = 4;
  const morning = minutes >= 9 * 60 && minutes <= 11 * 60 + 30 + grace;
  const afternoon = minutes >= 13 * 60 && minutes <= 15 * 60 + grace;
  if (!morning && !afternoon) return { ok: true, skipped: 'outside_market_hours' };

  return dispatchWorkflow_(CONFIG.INTRADAY_WORKFLOW_FILE);
}

/**
 * Market Pulse: 5 phút/lần, 24/7.
 * Không phụ thuộc giờ CK Việt Nam.
 */
function scheduledMarketPulseScan() {
  return dispatchWorkflow_(CONFIG.MARKET_PULSE_WORKFLOW_FILE);
}

function dispatchWorkflow_(workflowFile, inputs) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('Chua cau hinh Script Property GITHUB_TOKEN');

  const url =
    `https://api.github.com/repos/${CONFIG.GITHUB_OWNER}/${CONFIG.GITHUB_REPO}` +
    `/actions/workflows/${workflowFile}/dispatches`;

  const payload = { ref: CONFIG.GITHUB_BRANCH };
  if (inputs && typeof inputs === 'object') payload.inputs = inputs;

  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28'
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  const code = response.getResponseCode();
  if (code !== 204) throw new Error(`GitHub dispatch loi ${code}: ${response.getContentText()}`);
  return { ok: true, workflow: workflowFile, inputs: payload.inputs || {} };
}
