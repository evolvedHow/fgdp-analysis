/**
 * Functions.gs — Custom spreadsheet functions over the FDGA data model.
 *
 * The point of this file is that a user never has to know the underlying
 * structure. They write:
 *
 *     =FDGA_SEATS(2024, "house", "R")
 *
 * rather than knowing there is a `chamber_year` table, that the chamber is
 * spelled `state_house`, that the column is `seats_r`, or where any of it
 * lives. Chamber and party arguments accept whatever a person would naturally
 * type — "house", "GA House", "state house", "R", "rep", "Republican".
 *
 * Every function returns a friendly #N/A style message on bad input rather
 * than a bare #ERROR, and #NAME-ish guidance if the local data is missing.
 */

// ---------------------------------------------------------------------------
// Vocabulary — the friendly-name layer
// ---------------------------------------------------------------------------

/** Anything a person might type -> the chamber code in the data. */
var CHAMBER_ALIASES_ = {
  'house': 'state_house',
  'ga house': 'state_house',
  'georgia house': 'state_house',
  'state house': 'state_house',
  'state_house': 'state_house',
  'hd': 'state_house',
  'senate': 'state_senate',
  'ga senate': 'state_senate',
  'georgia senate': 'state_senate',
  'state senate': 'state_senate',
  'state_senate': 'state_senate',
  'sd': 'state_senate',
  'congress': 'us_house',
  'congressional': 'us_house',
  'us house': 'us_house',
  'u.s. house': 'us_house',
  'us_house': 'us_house',
  'cd': 'us_house'
};

var PARTY_ALIASES_ = {
  'r': 'r', 'rep': 'r', 'gop': 'r', 'republican': 'r', 'republicans': 'r',
  'd': 'd', 'dem': 'd', 'democrat': 'd', 'democratic': 'd', 'democrats': 'd'
};

/**
 * Measures exposed to users, mapped onto chamber_year columns.
 * `pct` marks a 0-1 ratio so the sidebar can suggest a percent format.
 */
var MEASURES_ = [
  { name: 'seats_r', label: 'Seats won — Republican', column: 'seats_r' },
  { name: 'seats_d', label: 'Seats won — Democratic', column: 'seats_d' },
  { name: 'seats_other', label: 'Seats won — other parties', column: 'seats_other' },
  { name: 'seat_share_r', label: 'Share of seats — Republican', column: 'pct_seats_r', pct: true },
  { name: 'seat_share_d', label: 'Share of seats — Democratic', column: 'pct_seats_d', pct: true },
  { name: 'vote_share_r', label: 'Share of votes — Republican', column: 'pct_votes_r', pct: true },
  { name: 'vote_share_d', label: 'Share of votes — Democratic', column: 'pct_votes_d', pct: true },
  {
    name: 'gap', label: 'Seats-votes gap (Republican)', column: 'seats_votes_gap_r', pct: true,
    help: 'Republican share of seats minus Republican share of votes. ' +
          'Positive means the party held more seats than its vote share alone implies.'
  },
  { name: 'races', label: 'Races on the ballot', column: 'races_total' },
  { name: 'uncontested', label: 'Uncontested races', column: 'races_uncontested',
    help: 'No opponent on the ballot, write-ins aside.' },
  { name: 'uncontested_major', label: 'Races with no major-party opponent', column: 'races_uncontested_major',
    help: 'Broader than "uncontested": a Republican facing only a Libertarian counts here.' },
  { name: 'contested', label: 'Contested races', column: 'races_contested' },
  { name: 'competitive', label: 'Competitive races', column: 'races_competitive',
    help: 'Winner took 53.5% or less of the vote.' },
  { name: 'uncontested_share', label: 'Share of races uncontested', column: 'pct_uncontested', pct: true },
  { name: 'competitive_share', label: 'Share of races competitive', column: 'pct_competitive', pct: true },
  { name: 'votes_total', label: 'Total votes cast', column: 'votes_total' },
  { name: 'votes_r', label: 'Votes — Republican', column: 'votes_r' },
  { name: 'votes_d', label: 'Votes — Democratic', column: 'votes_d' }
];

/** Competitiveness thresholds materialized in `contests`. */
var THRESHOLD_COLUMNS_ = {
  '0.52': 'is_competitive_052',
  '0.535': 'is_competitive_0535',
  '0.55': 'is_competitive_055',
  '0.6': 'is_competitive_06'
};

// ---------------------------------------------------------------------------
// Table access
// ---------------------------------------------------------------------------

var TABLE_CACHE_ = {};

/** Read a hidden local tab into {header: [...], rows: [{col: value}]}. */
function fdgaTable_(name) {
  if (TABLE_CACHE_[name]) return TABLE_CACHE_[name];

  var sheet = SpreadsheetApp.getActive().getSheetByName('_fdga_' + name);
  if (!sheet) {
    throw new Error(
      'No local copy of "' + name + '" yet. Use the FDGA menu > Refresh data.');
  }
  var values = sheet.getDataRange().getValues();
  if (values.length < 2) {
    throw new Error(
      '"' + name + '" is empty. Use the FDGA menu > Refresh data.');
  }
  var header = values[0].map(String);
  var rows = [];
  for (var i = 1; i < values.length; i++) {
    var row = {};
    for (var c = 0; c < header.length; c++) row[header[c]] = values[i][c];
    rows.push(row);
  }
  TABLE_CACHE_[name] = { header: header, rows: rows };
  return TABLE_CACHE_[name];
}

function normChamber_(input) {
  var key = String(input == null ? '' : input).trim().toLowerCase();
  var code = CHAMBER_ALIASES_[key];
  if (!code) {
    throw new Error(
      'Unknown chamber "' + input + '". Try "house", "senate" or "congress".');
  }
  return code;
}

function normParty_(input) {
  var key = String(input == null ? '' : input).trim().toLowerCase();
  var code = PARTY_ALIASES_[key];
  if (!code) {
    throw new Error('Unknown party "' + input + '". Use "R" or "D".');
  }
  return code;
}

function findMeasure_(name) {
  var key = String(name == null ? '' : name).trim().toLowerCase();
  for (var i = 0; i < MEASURES_.length; i++) {
    if (MEASURES_[i].name === key) return MEASURES_[i];
  }
  throw new Error(
    'Unknown measure "' + name + '". Run =FDGA_MEASURES() to list them.');
}

function chamberYearRow_(year, chamber) {
  var rows = fdgaTable_('chamber_year').rows;
  var target = Number(year);
  for (var i = 0; i < rows.length; i++) {
    if (Number(rows[i].cycle_year) === target && rows[i].chamber === chamber) {
      return rows[i];
    }
  }
  throw new Error(
    'No data for ' + year + ' / ' + chamber + '. Elections run every two ' +
    'years; =FDGA_CYCLES() lists the ones available.');
}

function fdgaCycles_() {
  var seen = {};
  fdgaTable_('chamber_year').rows.forEach(function (r) {
    seen[Number(r.cycle_year)] = true;
  });
  return Object.keys(seen).map(Number).sort(function (a, b) { return a - b; });
}

/** Blank rather than 0 when a measure is genuinely not derivable. */
function orBlank_(value) {
  if (value === '' || value === null || value === undefined) return '';
  return value;
}

// ---------------------------------------------------------------------------
// Custom functions
// ---------------------------------------------------------------------------

/**
 * Seats won by a party in one chamber in one election.
 *
 * @param {number} year Election year, e.g. 2024.
 * @param {string} chamber "house", "senate" or "congress".
 * @param {string} party "R" or "D".
 * @return {number} Seats won.
 * @customfunction
 */
function FDGA_SEATS(year, chamber, party) {
  var row = chamberYearRow_(year, normChamber_(chamber));
  return orBlank_(row['seats_' + normParty_(party)]);
}

/**
 * A party's share of the seats in one chamber, as a 0-1 ratio.
 *
 * @param {number} year Election year, e.g. 2024.
 * @param {string} chamber "house", "senate" or "congress".
 * @param {string} party "R" or "D".
 * @return {number} Share of seats.
 * @customfunction
 */
function FDGA_SEAT_SHARE(year, chamber, party) {
  var row = chamberYearRow_(year, normChamber_(chamber));
  return orBlank_(row['pct_seats_' + normParty_(party)]);
}

/**
 * A party's share of the votes cast in one chamber, as a 0-1 ratio.
 *
 * @param {number} year Election year, e.g. 2024.
 * @param {string} chamber "house", "senate" or "congress".
 * @param {string} party "R" or "D".
 * @return {number} Share of votes.
 * @customfunction
 */
function FDGA_VOTE_SHARE(year, chamber, party) {
  var row = chamberYearRow_(year, normChamber_(chamber));
  return orBlank_(row['pct_votes_' + normParty_(party)]);
}

/**
 * Seats-votes gap: Republican share of seats minus Republican share of votes.
 * Positive means Republicans held a larger share of seats than of votes.
 *
 * @param {number} year Election year, e.g. 2024.
 * @param {string} chamber "house", "senate" or "congress".
 * @return {number} The gap, as a 0-1 ratio.
 * @customfunction
 */
function FDGA_GAP(year, chamber) {
  var row = chamberYearRow_(year, normChamber_(chamber));
  return orBlank_(row.seats_votes_gap_r);
}

/**
 * Number of uncontested races — no opponent on the ballot, write-ins aside.
 *
 * @param {number} year Election year, e.g. 2024.
 * @param {string} chamber "house", "senate" or "congress".
 * @param {boolean} includeMinorPartyOnly Optional. TRUE also counts races
 *     whose only opposition was a minor party.
 * @return {number} Count of races.
 * @customfunction
 */
function FDGA_UNCONTESTED(year, chamber, includeMinorPartyOnly) {
  var row = chamberYearRow_(year, normChamber_(chamber));
  return orBlank_(includeMinorPartyOnly
    ? row.races_uncontested_major
    : row.races_uncontested);
}

/**
 * Number of competitive races — winner took at or below the threshold.
 *
 * @param {number} year Election year, e.g. 2024.
 * @param {string} chamber "house", "senate" or "congress".
 * @param {number} threshold Optional winning share: 0.52, 0.535, 0.55 or 0.6.
 *     Defaults to 0.535.
 * @return {number} Count of races.
 * @customfunction
 */
function FDGA_COMPETITIVE(year, chamber, threshold) {
  var code = normChamber_(chamber);
  if (threshold === undefined || threshold === null || threshold === '') {
    return orBlank_(chamberYearRow_(year, code).races_competitive);
  }
  var column = THRESHOLD_COLUMNS_[String(Number(threshold))];
  if (!column) {
    throw new Error(
      'Threshold must be one of 0.52, 0.535, 0.55, 0.6 — got ' + threshold + '.');
  }
  var count = 0;
  fdgaTable_('contests').rows.forEach(function (r) {
    if (Number(r.cycle_year) === Number(year) && r.office === code &&
        String(r[column]).toLowerCase() === 'true') {
      count++;
    }
  });
  return count;
}

/**
 * Any measure for one chamber and year. The general-purpose escape hatch.
 *
 * @param {number} year Election year, e.g. 2024.
 * @param {string} chamber "house", "senate" or "congress".
 * @param {string} measure A name from =FDGA_MEASURES().
 * @return {number} The measure's value.
 * @customfunction
 */
function FDGA_VALUE(year, chamber, measure) {
  var row = chamberYearRow_(year, normChamber_(chamber));
  return orBlank_(row[findMeasure_(measure).column]);
}

/**
 * One measure across every election, as a two-column table ready to chart.
 *
 * @param {string} chamber "house", "senate" or "congress".
 * @param {string} measure A name from =FDGA_MEASURES().
 * @param {boolean} includeHeader Optional, defaults to TRUE.
 * @return {Array<Array<Object>>} Year and value per election.
 * @customfunction
 */
function FDGA_TREND(chamber, measure, includeHeader) {
  var code = normChamber_(chamber);
  var spec = findMeasure_(measure);
  var out = [];
  if (includeHeader !== false) out.push(['Year', spec.label]);

  fdgaTable_('chamber_year').rows
    .filter(function (r) { return r.chamber === code; })
    .sort(function (a, b) { return Number(a.cycle_year) - Number(b.cycle_year); })
    .forEach(function (r) {
      out.push([Number(r.cycle_year), orBlank_(r[spec.column])]);
    });

  if (out.length === (includeHeader !== false ? 1 : 0)) {
    throw new Error('No rows for chamber "' + chamber + '".');
  }
  return out;
}

/**
 * Compare every chamber for one election.
 *
 * @param {number} year Election year, e.g. 2024.
 * @param {string} measure A name from =FDGA_MEASURES().
 * @return {Array<Array<Object>>} Chamber and value.
 * @customfunction
 */
function FDGA_BY_CHAMBER(year, measure) {
  var spec = findMeasure_(measure);
  var labels = {
    us_house: 'U.S. House',
    state_senate: 'Georgia Senate',
    state_house: 'Georgia House'
  };
  var out = [['Chamber', spec.label]];
  ['us_house', 'state_senate', 'state_house'].forEach(function (code) {
    try {
      var row = chamberYearRow_(year, code);
      out.push([labels[code], orBlank_(row[spec.column])]);
    } catch (err) {
      out.push([labels[code], '']);
    }
  });
  return out;
}

/**
 * Individual races for one chamber and year.
 *
 * @param {number} year Election year, e.g. 2024.
 * @param {string} chamber "house", "senate" or "congress".
 * @param {string} filter Optional: "all" (default), "competitive",
 *     "uncontested", "contested" or "close".
 * @return {Array<Array<Object>>} District, winner, party, margin and votes.
 * @customfunction
 */
function FDGA_RACES(year, chamber, filter) {
  var code = normChamber_(chamber);
  var mode = String(filter || 'all').trim().toLowerCase();
  var allowed = ['all', 'competitive', 'uncontested', 'contested', 'close'];
  if (allowed.indexOf(mode) === -1) {
    throw new Error(
      'Unknown filter "' + filter + '". Use one of: ' + allowed.join(', ') + '.');
  }

  var isTrue = function (v) { return String(v).toLowerCase() === 'true'; };
  var rows = fdgaTable_('contests').rows.filter(function (r) {
    if (Number(r.cycle_year) !== Number(year) || r.office !== code) return false;
    if (mode === 'competitive') return isTrue(r.is_competitive);
    if (mode === 'uncontested') return isTrue(r.is_uncontested);
    if (mode === 'contested') return !isTrue(r.is_uncontested);
    if (mode === 'close') return Number(r.margin_share) < 0.05;
    return true;
  });

  if (!rows.length) {
    throw new Error(
      'No ' + mode + ' races for ' + year + ' / ' + chamber + '.');
  }

  var out = [[
    'District', 'Winner', 'Party', 'Winner share', 'Margin',
    'Votes R', 'Votes D', 'Total votes'
  ]];
  rows.sort(function (a, b) {
    return String(a.district).localeCompare(String(b.district));
  }).forEach(function (r) {
    out.push([
      String(r.district), r.winner_name, r.winner_party,
      Number(r.winner_share), Number(r.margin_share),
      Number(r.votes_r), Number(r.votes_d), Number(r.votes_total)
    ]);
  });
  return out;
}

/**
 * Statewide race vote shares — the baseline chamber results are measured against.
 *
 * @param {number} year Optional election year; omit for every year.
 * @return {Array<Array<Object>>} Year, office, winner and vote shares.
 * @customfunction
 */
function FDGA_STATEWIDE(year) {
  var rows = fdgaTable_('statewide').rows.filter(function (r) {
    return !year || Number(r.cycle_year) === Number(year);
  });
  if (!rows.length) throw new Error('No statewide races for ' + year + '.');

  var out = [['Year', 'Office', 'Winner', 'Party', 'R share', 'D share']];
  rows.sort(function (a, b) {
    return Number(a.cycle_year) - Number(b.cycle_year);
  }).forEach(function (r) {
    out.push([
      Number(r.cycle_year), r.office, r.winner_name, r.winner_party,
      Number(r.pct_votes_r), Number(r.pct_votes_d)
    ]);
  });
  return out;
}

/**
 * Every measure name accepted by FDGA_VALUE, FDGA_TREND and FDGA_BY_CHAMBER.
 *
 * @return {Array<Array<string>>} Name, description and notes.
 * @customfunction
 */
function FDGA_MEASURES() {
  var out = [['Measure', 'Description', 'Notes']];
  MEASURES_.forEach(function (m) {
    out.push([m.name, m.label, m.help || '']);
  });
  return out;
}

/**
 * Election years available in the data.
 *
 * @return {Array<Array<number>>} One year per row.
 * @customfunction
 */
function FDGA_CYCLES() {
  return fdgaCycles_().map(function (y) { return [y]; });
}

/**
 * Provenance for one election: source, row counts and checksum.
 *
 * @param {number} year Optional election year; omit for every source.
 * @return {Array<Array<Object>>} Source id, date, rows and checksum.
 * @customfunction
 */
function FDGA_SOURCE(year) {
  var rows = fdgaTable_('manifest').rows.filter(function (r) {
    return !year || Number(r.cycle_year) === Number(year);
  });
  if (!rows.length) throw new Error('No source recorded for ' + year + '.');

  var out = [['Year', 'Source', 'Election date', 'Rows', 'Votes', 'Checksum']];
  rows.forEach(function (r) {
    out.push([
      Number(r.cycle_year), r.source_id, r.election_date,
      Number(r.rows_out), Number(r.votes_total), r.sha256
    ]);
  });
  return out;
}
