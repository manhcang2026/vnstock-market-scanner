function setupNewBackend() {
  const ss = SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID);
  Object.keys(HEADERS).forEach(name => {
    let sheet = ss.getSheetByName(name);
    if (!sheet) sheet = ss.insertSheet(name);
    sheet.clear();
    const headers = HEADERS[name];
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, headers.length)
      .setFontWeight('bold')
      .setBackground('#17365D')
      .setFontColor('#FFFFFF');
  });
  PropertiesService.getScriptProperties().setProperties({
    LAST_DASHBOARD_UPDATED_AT: '',
    LAST_RUN_ID: '',
  }, true);
  return {ok: true, sheets: Object.keys(HEADERS)};
}
