/**
 * Code.gs — Menu, data refresh, and sidebar for the FDGA add-on.
 *
 * Architecture
 * ------------
 * Google Apps Script custom functions run in a restricted context: they may
 * read the *active* spreadsheet but cannot open another one, because that
 * needs authorization they never get. So the data is copied locally first:
 *
 *     data layer spreadsheet          this spreadsheet
 *     (fdp_analytics)        --->     _fdga_chamber_year   (hidden)
 *       pushed by                     _fdga_contests       (hidden)
 *       push_fdga_to_sheets.py         _fdga_statewide      (hidden)
 *                                          ^
 *                                          |  read by
 *                                     FDGA_SEATS(), FDGA_GAP(), ...
 *
 * "FDGA > Refresh data" runs as the signed-in user, which *does* carry
 * authorization, so it can read the data layer and write the hidden tabs.
 * Custom functions then only ever read local ranges.
 *
 * This also sidesteps IMPORTRANGE's ~50-100k cell ceiling: a local tab has no
 * such limit, so `contests` (87k cells) copies fine.
 */

/** Id of the data layer spreadsheet written by push_fdga_to_sheets.py. */
var DATA_LAYER_ID = '1S0SCkbao0hss1YhORCjeVtpDTbZnJLzIMP-evWTfDuI';

/** Source tab -> local hidden tab. `facts` is opt-in; see refreshFacts(). */
var SYNC_TABS = {
  chamber_year: '_fdga_chamber_year',
  contests: '_fdga_contests',
  statewide: '_fdga_statewide',
  _manifest: '_fdga_manifest'
};

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Fair Districts GA')
    .addItem('Insert a formula…', 'showSidebar')
    .addSeparator()
    .addItem('Refresh data', 'refreshData')
    .addItem('Also copy facts (32k rows)', 'refreshFacts')
    .addSeparator()
    .addItem('Show hidden data tabs', 'showDataTabs')
    .addItem('Hide data tabs', 'hideDataTabs')
    .addItem('About / data freshness', 'showAbout')
    .addToUi();
}

function onInstall() {
  onOpen();
}

function showSidebar() {
  var html = HtmlService.createHtmlOutputFromFile('Sidebar')
    .setTitle('Fair Districts GA — election data');
  SpreadsheetApp.getUi().showSidebar(html);
}

/**
 * Copy the aggregate tables from the data layer into hidden local tabs.
 * Safe to run repeatedly — each tab is cleared and rewritten.
 */
function refreshData() {
  var copied = syncTabs_(SYNC_TABS);
  SpreadsheetApp.getActive().toast(
    copied.join(', '), 'FDGA data refreshed', 8);
  return copied;
}

/**
 * Additionally copy the county-level fact table. 32k rows — only worth it if
 * you need county detail, and it makes the spreadsheet noticeably heavier.
 */
function refreshFacts() {
  var ui = SpreadsheetApp.getUi();
  var answer = ui.alert(
    'Copy the facts table?',
    'facts is 32,181 rows x 12 columns (~386,000 cells). It is only needed ' +
    'for county-level detail; every headline measure comes from ' +
    'chamber_year and contests.\n\nCopy it anyway?',
    ui.ButtonSet.YES_NO);
  if (answer !== ui.Button.YES) return;
  var copied = syncTabs_({ facts: '_fdga_facts' });
  SpreadsheetApp.getActive().toast(copied.join(', '), 'FDGA facts copied', 8);
}

/** Copy a {source: destination} map of tabs from the data layer. */
function syncTabs_(tabMap) {
  var source;
  try {
    source = SpreadsheetApp.openById(DATA_LAYER_ID);
  } catch (err) {
    throw new Error(
      'Cannot open the data layer spreadsheet (' + DATA_LAYER_ID + '). ' +
      'Ask for at least Viewer access, or correct DATA_LAYER_ID in Code.gs. ' +
      'Original error: ' + err.message);
  }

  var target = SpreadsheetApp.getActive();
  var copied = [];

  Object.keys(tabMap).forEach(function (srcName) {
    var srcSheet = source.getSheetByName(srcName);
    if (!srcSheet) {
      throw new Error(
        'The data layer has no tab named "' + srcName + '". Run ' +
        'push_fdga_to_sheets.py, then try again.');
    }
    var values = srcSheet.getDataRange().getValues();
    if (!values.length) return;

    var dstName = tabMap[srcName];
    var dst = target.getSheetByName(dstName);
    if (!dst) {
      dst = target.insertSheet(dstName);
    }
    dst.clear();
    // Grow the grid before writing; a new sheet defaults to 1000 x 26 and
    // setValues() will not expand past it.
    if (dst.getMaxRows() < values.length) {
      dst.insertRowsAfter(dst.getMaxRows(), values.length - dst.getMaxRows());
    }
    if (dst.getMaxColumns() < values[0].length) {
      dst.insertColumnsAfter(
        dst.getMaxColumns(), values[0].length - dst.getMaxColumns());
    }
    dst.getRange(1, 1, values.length, values[0].length).setValues(values);
    // hideSheet() throws if this would leave no visible tab — harmless here,
    // and the user can hide it later from the FDGA menu.
    try {
      dst.hideSheet();
    } catch (err) {
      // leave it visible
    }
    copied.push(srcName + ' (' + (values.length - 1) + ' rows)');
  });

  var cache = CacheService.getDocumentCache();
  if (cache) cache.removeAll(Object.keys(tabMap));
  PropertiesService.getDocumentProperties()
    .setProperty('fdga_last_refresh', new Date().toISOString());
  return copied;
}

function showDataTabs() {
  eachDataTab_(function (sheet) { sheet.showSheet(); });
}

function hideDataTabs() {
  eachDataTab_(function (sheet) { sheet.hideSheet(); });
}

function eachDataTab_(fn) {
  SpreadsheetApp.getActive().getSheets().forEach(function (sheet) {
    if (sheet.getName().indexOf('_fdga_') === 0) fn(sheet);
  });
}

function showAbout() {
  var props = PropertiesService.getDocumentProperties();
  var refreshed = props.getProperty('fdga_last_refresh') || 'never';
  var lines = [
    'Fair Districts GA — Georgia election results, 2000-2024',
    'Congress, state House and Senate, plus statewide races.',
    '',
    'Local copy last refreshed: ' + refreshed,
    'Data layer: ' + DATA_LAYER_ID,
    '',
    'Type =FDGA_MEASURES() in a cell for the list of available measures,',
    'or use FDGA > Insert a formula… to build one from dropdowns.'
  ];
  SpreadsheetApp.getUi().alert('FDGA', lines.join('\n'),
    SpreadsheetApp.getUi().ButtonSet.OK);
}

/** Write a formula into the user's selected cell. Called by the sidebar. */
function insertFormula(formula) {
  var range = SpreadsheetApp.getActive().getActiveRange();
  if (!range) throw new Error('Select a cell first.');
  range.getCell(1, 1).setFormula(formula);
}

/** Called by the sidebar to populate its dropdowns. */
function getSidebarOptions() {
  return {
    cycles: fdgaCycles_(),
    chambers: [
      { value: 'house', label: 'Georgia House' },
      { value: 'senate', label: 'Georgia Senate' },
      { value: 'congress', label: 'U.S. House' }
    ],
    measures: MEASURES_.map(function (m) {
      return { value: m.name, label: m.label, help: m.help };
    })
  };
}
