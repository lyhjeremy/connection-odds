/* Deterministic itinerary reader for the lookup tool. No model, no network.
   Handles one flight per line with a flight number, two airport codes and two times, e.g.
     DL 2318 Y 14APR BOSATL HK1 0715 1012
     WN 1203  MDW > DEN  Sat Jul 18  07:10 - 08:55
     aa 2104 dca 9:00 am - mia 11:59 am 1/24/26
   Anything else returns an error and the fields stay as they were.
   scripts/check_paste_parser.py scores it on the 30 frozen itineraries in eval/. */
(function (root) {
  "use strict";
  var MON = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };

  function times(line) {
    var out = [], m, re = /(?:^|[^\d:])(\d{1,2}):(\d{2})(?!\d)\s*([ap])?\.?(?:m\.?)?(?![a-z])/gi;
    while ((m = re.exec(line))) {
      var h = +m[1], mi = +m[2], ap = (m[3] || "").toLowerCase();
      if (ap) h = h % 12 + (ap === "p" ? 12 : 0);
      if (h < 24 && mi < 60) out.push(h * 60 + mi);
    }
    return out;
  }

  function fourDigit(line, flightNo) {
    var out = [], m, re = /(?:^|\s)(\d{4})(?=\s|$)/g;
    while ((m = re.exec(line))) {
      var v = m[1], h = +v.slice(0, 2), mi = +v.slice(2);
      if (v === flightNo || /^(19|20)\d\d$/.test(v) && h >= 19) continue;
      if (h < 24 && mi < 60) out.push(h * 60 + mi);
    }
    return out;
  }

  function month(line) {
    var m = line.match(/(?:^|[^\d:])(\d{1,2})\s?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b/i) ||
            line.match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b/i);
    if (m) {
      var name = isNaN(+m[1]) ? m[1] : m[2], day = isNaN(+m[1]) ? +m[2] : +m[1];
      return { month: MON[name.slice(0, 3).toLowerCase()], day: day };
    }
    m = line.match(/\b(\d{4})-(\d{2})-(\d{2})\b/);
    if (m) return { month: +m[2], day: +m[3] };
    m = line.match(/\b(\d{1,2})\/(\d{1,2})(?:\/\d{2,4})?\b/);
    if (m && +m[1] <= 12) return { month: +m[1], day: +m[2] };
    return null;
  }

  function parseItinerary(text, airports) {
    var legs = [], lastDate = null;
    String(text).split(/\r?\n/).forEach(function (raw) {
      /* codes count only where printed in capitals, so Dallas, Spirit or Sat are not read as DAL, SPI or SAT;
         an all-lowercase line is read as if it were in capitals */
      var line = raw.replace(/\t/g, "  ");
      if (line === line.toLowerCase()) line = line.toUpperCase();
      var d = month(line);
      if (d) lastDate = d;
      var f = line.match(/\b([A-Z][A-Z0-9]|[0-9][A-Z])\s?(\d{1,4})\b/);
      if (!f) return;
      var codes = [], m, re = /\b([A-Z]{3})([A-Z]{3})?\b/g;
      while ((m = re.exec(line))) {
        [m[1], m[2]].forEach(function (c) { if (c && airports[c] && codes.length < 2) codes.push(c); });
      }
      if (codes.length < 2) return;
      var t = times(line);
      if (t.length < 2) t = fourDigit(line, f[2]);
      if (t.length < 2) return;
      d = d || lastDate;
      var plus = /\+\s?1/.test(line) ? 1 : 0;
      legs.push({ airline: f[1], flight: f[2], origin: codes[0], destination: codes[1],
                  dep: t[0], arr: t[1] + 1440 * plus + (t[1] < t[0] && !plus ? 1440 : 0), date: d });
    });
    if (legs.length < 2) return { error: "Found " + legs.length + " flight" + (legs.length === 1 ? "" : "s") + " in this text; a connection needs two." };
    var conns = [];
    for (var i = 0; i + 1 < legs.length; i++) {
      var a = legs[i], b = legs[i + 1];
      if (a.destination !== b.origin) continue;
      var arr = a.arr, lay;
      if (a.date && b.date) {
        var days = (Date.UTC(2026, b.date.month - 1, b.date.day) - Date.UTC(2026, a.date.month - 1, a.date.day)) / 864e5;
        if (days < 0) days += 365;  /* the trip runs into a new year */
        lay = b.dep + 1440 * days - arr;
      } else {
        lay = b.dep + (arr >= 1440 ? 1440 : 0) - arr;
        if (lay < 0) lay += 1440;
      }
      if (lay > 1440) continue;
      conns.push({ hub: a.destination, airline_in: a.airline, airline_out: b.airline, arrival_hour: Math.floor((arr % 1440) / 60),
                   month: a.date ? a.date.month : null, layover_min: lay });
    }
    return { legs: legs, connections: conns };
  }

  root.parseItinerary = parseItinerary;
})(typeof self !== "undefined" ? self : this);
