function runDailyBaselineNow() {
  return dispatchWorkflow_(CONFIG.DAILY_WORKFLOW_FILE);
}

function runIntradayScanNow() {
  return dispatchWorkflow_(CONFIG.INTRADAY_WORKFLOW_FILE);
}

function scheduledIntradayScan() {
  const now = new Date();
  const day = now.getDay();
  if (day === 0 || day === 6) return {ok: true, skipped: 'weekend'};
  const minutes = now.getHours() * 60 + now.getMinutes();
  const inMorning = minutes >= 9 * 60 && minutes <= 11 * 60 + 30;
  const inAfternoon = minutes >= 13 * 60 && minutes <= 15 * 60;
  if (!inMorning && !inAfternoon) return {ok: true, skipped: 'outside_market_hours'};
  return dispatchWorkflow_(CONFIG.INTRADAY_WORKFLOW_FILE);
}

function dispatchWorkflow_(workflowFile) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('Chua cau hinh Script Property GITHUB_TOKEN');
  const url = `https://api.github.com/repos/${CONFIG.GITHUB_OWNER}/${CONFIG.GITHUB_REPO}/actions/workflows/${workflowFile}/dispatches`;
  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    payload: JSON.stringify({ref: CONFIG.GITHUB_BRANCH}),
    muteHttpExceptions: true,
  });
  const code = response.getResponseCode();
  if (code !== 204) throw new Error(`GitHub dispatch loi ${code}: ${response.getContentText()}`);
  return {ok: true, workflow: workflowFile};
}
