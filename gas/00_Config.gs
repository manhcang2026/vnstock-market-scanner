const CONFIG = Object.freeze({
  SPREADSHEET_ID: 'DIEN_SPREADSHEET_ID',
  GITHUB_OWNER: 'manhcang2026',
  GITHUB_REPO: 'vnstock-market-scanner',
  DAILY_WORKFLOW_FILE: 'daily-baseline.yml',
  INTRADAY_WORKFLOW_FILE: 'intraday-scan.yml',
  GITHUB_BRANCH: 'main',
  SNAPSHOT_DAYS_TO_KEEP: 12,
  SHEETS: {
    DAILY: 'Daily_Baseline',
    SNAPSHOTS: 'Intraday_Snapshots',
    DASHBOARD: 'Dashboard_Current',
    LOG: 'Run_Log',
  },
});

const HEADERS = Object.freeze({
  Daily_Baseline: ['symbol','exchange','trading_date','previous_close','ma200','ma200_sessions','avg_volume_10','avg_volume_sessions','source','updated_at','data_status'],
  Intraday_Snapshots: ['trading_date','time_slot','symbol','exchange','current_price','volume_accumulated','updated_at','data_status'],
  Dashboard_Current: ['symbol','exchange','current_price','previous_close','price_change_pct','volume_accumulated','avg_volume_10','avg_volume_sessions','daily_volume_pct','ma200','ma200_sessions','ma200_distance_pct','volume_30m','avg_volume_30m_10','rvol30_pct','rvol30_sessions','signal_price_3pct','signal_daily_volume_200pct','signal_above_ma200','signal_rvol30_200pct','signal_count','trading_date','time_slot','updated_at','data_status'],
  Run_Log: ['run_id','job_type','started_at','finished_at','status','symbols_requested','symbols_success','symbols_failed','message'],
});
