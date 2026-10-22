/*
 * Yahoo Fantasy web-surface discovery recorder.
 *
 * Paste into the DevTools console on your league page
 * (https://basketball.fantasysports.yahoo.com/nba/{league_id}), then click
 * around — Scoreboard, a past week, the league Stats tab. Every JSON request
 * the page makes is captured and scored against the four requirements in
 * specs/001-power-ranking-article/contracts/data-source.md that a provider
 * must satisfy.
 *
 * This answers, empirically, whether a browser-session provider is viable at
 * all. It guesses nothing about Yahoo's internal routes; it records them.
 *
 *   __ccsv.report()   summary table of everything captured
 *   __ccsv.best()     the single most promising endpoint, with why
 *   __ccsv.inline()   scan <script> tags for inlined page state (see below)
 *   __ccsv.html()     score the rendered tables when the page is server-rendered
 *   __ccsv.save()     download the captured payloads for offline inspection
 *   __ccsv.probe(5)   re-request every captured URL with week=5 substituted
 *   __ccsv.reset()    clear captures, keep recording
 *   __ccsv.stop()     uninstall the interceptors
 *
 * If the recorder captures no league data, the page does not fetch it -- run
 * __ccsv.inline() next, since Yahoo often embeds page state in a script tag,
 * and only then __ccsv.html() for the markup. Order matters: inlined JSON is a
 * much more stable parse target than table markup.
 *
 * Nothing is sent anywhere. Capture lives in the tab until you close it.
 * Note: this CANNOT read your auth cookies — they are HttpOnly, which is why
 * cookie capture uses "Copy as cURL" instead (see tools/curl_to_env.py).
 */

(() => {
  if (window.__ccsv) {
    console.warn("[ccsv] already installed — call __ccsv.reset() to clear captures");
    return;
  }

  // Analytics and ad traffic drowns out the signal. None of it is league data.
  // Analytics, ads, and transport plumbing drown out the signal. `server.comet`
  // is Yahoo's long-poll push channel -- it carries messaging, never league
  // data, and because it streams continuously it otherwise ranks top by volume.
  const NOISE = /(doubleclick|scorecardresearch|googlesyndication|google-analytics|googletagmanager|adservice|beap\.|geo\.yahoo|analytics\.yahoo|csc\.beap|\.gif(\?|$)|sb\.scorecardresearch|server\.comet|\/comet|rapid|telemetry|\/beacon)/i;

  const captures = [];
  const seen = new Set();

  /* --- scoring against the data-source contract -------------------------- */

  // Requirement 1: per-week, per-category totals for ALL 18 teams, not just
  // the viewing manager's matchup. The hardest requirement, and the first
  // thing the contract says to verify against any new provider.
  // Counts API-style team keys AND the web form. Run 1 reported `teams: 0` on a
  // page that plainly showed a team, because only the API key shape was matched
  // and web markup never contains it -- a tool artifact that read as evidence.
  const teamKeys = (text) => {
    const found = new Set();
    (text.match(/\d+\.l\.\d+\.t\.\d+/g) || []).forEach((k) => found.add(k));
    // Web team links: /nba/{leagueId}/{teamId}
    (text.match(/\/(?:nba|nfl|mlb|nhl)\/\d+\/(\d{1,2})(?=["'/?#\s]|$)/g) || []).forEach((k) =>
      found.add(k)
    );
    return found.size;
  };

  // Requirement 2: FG and FT as makes and attempts, NEVER as a percentage.
  // A rounded percentage cannot be re-aggregated and the information is
  // unrecoverable afterward. "18/42" survives; ".458" is a dead end.
  //
  // This is the fact most likely to be wrong and the one that kills a surface
  // outright, so it is graded in two tiers rather than as a boolean. A bare
  // "d/d" regex over the raw text also matches dates ("3/15"), win-loss
  // records ("12/4"), and fractions in copy -- reporting that as YES is how a
  // dead surface survives discovery and fails in week 3.
  const MA_VALUE = /^\s*\d{1,3}\s*\/\s*\d{1,3}\s*$/;

  // STRONG: a made/attempted value sitting in a stat object, which is the
  // shape `yahoo.py:parse_team_stats` actually reads -- {stat_id, value}.
  const shootingEvidence = (parsed) => {
    const hits = [];
    const walk = (node) => {
      if (hits.length >= 6 || node === null || typeof node !== "object") return;
      if (Array.isArray(node)) return node.forEach(walk);

      const keys = Object.keys(node);
      const idKey = keys.find((k) => /^stat_?id$/i.test(k));
      const valKey = keys.find((k) => /^(value|display_?value)$/i.test(k));
      if (idKey && valKey && MA_VALUE.test(String(node[valKey]))) {
        hits.push({ stat_id: String(node[idKey]), value: String(node[valKey]) });
      }
      // Yahoo names the categories "FGM/FGA" and "FTM/FTA" in league settings.
      const nameKey = keys.find((k) => /^(display_?name|abbr|name)$/i.test(k));
      if (nameKey && /^(fgm\/fga|ftm\/fta)$/i.test(String(node[nameKey]).trim())) {
        hits.push({ category: String(node[nameKey]), via: "settings name" });
      }
      keys.forEach((k) => walk(node[k]));
    };
    walk(parsed);
    return hits;
  };

  // WEAK: the same pattern anywhere in the text. Reported separately and never
  // counted as satisfying the requirement on its own.
  //
  // Matches both the JSON form ("8/9") and the markup form (>8/9<). Run 1
  // reported no loose matches on a page whose cells visibly read 8/9, because
  // only the quoted JSON form was matched -- HTML values carry no quotes.
  const looseMadeAttempted = (text) => {
    const found = [
      ...(text.match(/"\s*\d{1,3}\s*\/\s*\d{1,3}\s*"/g) || []),
      ...(text.match(/>\s*\d{1,3}\s*\/\s*\d{1,3}\s*</g) || []),
    ].map((s) => s.replace(/^[">\s]+|["<\s]+$/g, ""));
    return [...new Set(found)].slice(0, 6);
  };

  // The failure mode this is looking for: a payload that carries shooting
  // only as a decimal. Reported so a surface can be ruled out fast.
  const percentOnly = (text) =>
    /"(fg|ft)_?(pct|percentage)"\s*:\s*"?\.?\d/i.test(text) ||
    /"0?\.\d{3}"/.test(text);

  // Requirement 6: historical weeks addressable, so FR-038 backfill and the
  // RECHECK_WEEKS=3 correction window both work.
  const weekAddressable = (url) => /[?&;](week|wk)=/i.test(url);

  // Parse the longest valid JSON object at the start of `text`, ignoring
  // whatever trails it. Inline page state is followed by more JavaScript, so
  // JSON.parse on the whole tail always fails; brace-matching finds where the
  // object actually ends. String-aware, or a brace inside a team name truncates.
  const tryParsePrefix = (text) => {
    if (text[0] !== "{" && text[0] !== "[") return null;
    let depth = 0;
    let inStr = false;
    let esc = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (inStr) {
        if (esc) esc = false;
        else if (ch === "\\") esc = true;
        else if (ch === '"') inStr = false;
        continue;
      }
      if (ch === '"') {
        inStr = true;
        continue;
      }
      if (ch === "{" || ch === "[") depth++;
      else if (ch === "}" || ch === "]") {
        depth--;
        if (depth === 0) {
          try {
            return JSON.parse(text.slice(0, i + 1));
          } catch {
            return null;
          }
        }
      }
    }
    return null;
  };

  const score = (url, text, parsed) => {
    const teams = teamKeys(text);
    const strong = parsed ? shootingEvidence(parsed) : [];
    const loose = looseMadeAttempted(text);
    return {
      teams,
      allTeams: teams >= 18,
      // Only structural evidence counts. `loose` is a hint to eyeball, not a pass.
      madeAttempted: strong.length > 0,
      shooting: strong.length ? "CONFIRMED" : loose.length ? "UNVERIFIED" : "ABSENT",
      strongSamples: strong,
      looseSamples: loose,
      percentOnly: percentOnly(text) && strong.length === 0,
      weekParam: weekAddressable(url),
      bytes: text.length,
    };
  };

  const record = (url, status, text, via) => {
    if (!url || NOISE.test(url)) return;
    if (!text || text.length < 200) return;
    const trimmed = text.trim();
    if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return;

    let parsed = null;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      return; // not JSON — HTML pages are handled by the fallback path below
    }

    const key = url.split("?")[0] + "|" + trimmed.length;
    if (seen.has(key)) return;
    seen.add(key);

    const entry = { url, status, via, ...score(url, trimmed, parsed), payload: parsed };
    captures.push(entry);

    const good = entry.allTeams && entry.madeAttempted;
    console.log(
      `${good ? "%c✓ STRONG" : "%c  "}%c ${entry.teams} teams | shooting:${entry.shooting} | week:${entry.weekParam} | ${url.slice(0, 110)}`,
      good ? "color:#0a0;font-weight:bold" : "color:#888",
      "color:inherit"
    );
  };

  /* --- interceptors ------------------------------------------------------ */

  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await origFetch.apply(this, args);
    try {
      const url = typeof args[0] === "string" ? args[0] : args[0]?.url;
      response
        .clone()
        .text()
        .then((t) => record(url, response.status, t, "fetch"))
        .catch(() => {});
    } catch {}
    return response;
  };

  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__ccsvUrl = url;
    return origOpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    this.addEventListener("load", () => {
      try {
        record(this.__ccsvUrl, this.status, this.responseText, "xhr");
      } catch {}
    });
    return origSend.apply(this, args);
  };

  /* --- public surface ---------------------------------------------------- */

  window.__ccsv = {
    captures,

    report() {
      if (!captures.length) {
        console.warn(
          "[ccsv] nothing captured yet. Navigate to Scoreboard, switch to a " +
            "past week, and open the league Stats tab. If this stays empty the " +
            "pages are fully server-rendered — see __ccsv.html() instead."
        );
        return;
      }
      console.table(
        captures.map((c) => ({
          teams: c.teams,
          allTeams: c.allTeams,
          shooting: c.shooting,
          pctOnly: c.percentOnly,
          weekParam: c.weekParam,
          kb: Math.round(c.bytes / 1024),
          url: c.url.slice(0, 90),
        }))
      );
    },

    best() {
      const ranked = [...captures].sort(
        (a, b) =>
          b.allTeams * 8 + b.madeAttempted * 4 + b.weekParam * 2 - (a.allTeams * 8 + a.madeAttempted * 4 + a.weekParam * 2)
      );
      const top = ranked[0];
      if (!top) return console.warn("[ccsv] nothing captured");
      console.log("[ccsv] best candidate:", top.url);

      const shooting = {
        CONFIRMED: "YES -- found in stat objects, the shape the parser reads",
        UNVERIFIED: "UNCONFIRMED -- a d/d pattern exists but NOT inside a stat " +
          "object. Dates, records and fractions match too. INSPECT THE SAMPLES " +
          "BELOW before trusting this surface.",
        ABSENT: "NO  <- contract req 2, blocking",
      }[top.shooting];

      console.log(
        `  all 18 teams:    ${top.allTeams ? "YES" : "NO  <- contract req 1, blocking"}\n` +
          `  made/attempted:  ${shooting}\n` +
          `  week addressable:${top.weekParam ? "YES" : "NO  <- contract req 6, breaks backfill"}`
      );

      // Printed unconditionally: the shooting verdict is the fact most likely
      // to be wrong, so the evidence is never left behind a second call.
      if (top.strongSamples.length) console.log("  confirmed:", top.strongSamples);
      if (top.looseSamples.length) console.log("  unverified matches:", top.looseSamples);
      if (top.percentOnly) {
        console.warn(
          "  This payload carries shooting as a DECIMAL. A rounded percentage " +
            "cannot be re-aggregated and the information is unrecoverable -- " +
            "this surface cannot support the algorithm. Look for another."
        );
      }
      return top;
    },

    // Requirement 6 check: can the same endpoint serve a past week?
    async probe(week) {
      const targets = captures.filter((c) => c.weekParam).map((c) => c.url);
      if (!targets.length) {
        console.warn("[ccsv] no captured URL carries a week param to vary");
        return;
      }
      for (const url of targets) {
        const probed = url.replace(/([?&;])(week|wk)=\d+/i, `$1$2=${week}`);
        try {
          const r = await fetch(probed, { credentials: "include" });
          const t = await r.text();
          let p = null;
          try {
            p = JSON.parse(t);
          } catch {}
          console.log(
            `[ccsv] week=${week} -> ${r.status}`,
            score(probed, t, p),
            probed.slice(0, 110)
          );
        } catch (e) {
          console.log(`[ccsv] week=${week} -> FAILED`, probed.slice(0, 110), e.message);
        }
      }
    },

    // Fallback when the pages turn out to be fully server-rendered: score the
    // current document's markup against the same requirements.
    // Yahoo properties often inline page state into a script tag instead of
    // fetching it. The XHR recorder is blind to that -- no request is made --
    // and it is a far better parse target than table markup. Check this BEFORE
    // concluding the data is only in HTML.
    inline() {
      let found = 0;
      [...document.querySelectorAll("script")].forEach((node, i) => {
        const src = node.textContent || "";
        if (src.length < 500) return;

        const marker = src.match(
          /(?:root\.App\.main|window\.__(?:PRELOADED_STATE|INITIAL_STATE|NEXT_DATA|APP_STATE)__|__NEXT_DATA__)\s*=\s*/
        );
        const tails = [];
        if (marker) tails.push(src.slice(marker.index + marker[0].length));
        else if (src.length > 20000 && src.indexOf("{") >= 0)
          tails.push(src.slice(src.indexOf("{")));

        tails.forEach((tail) => {
          const parsed = tryParsePrefix(tail);
          if (!parsed) return;
          found++;
          const asText = JSON.stringify(parsed);
          const result = score(`${location.href}#inline-${i}`, asText, parsed);
          console.log(
            `  script[${i}] ${Math.round(asText.length / 1024)}kb | ${result.teams} teams | shooting:${result.shooting}`,
            result
          );
          if (result.strongSamples.length) console.log("    confirmed:", result.strongSamples);
          captures.push({
            url: `${location.href}#inline-script-${i}`,
            status: 200,
            via: "inline",
            ...result,
            payload: parsed,
          });
        });
      });

      if (!found) {
        console.warn(
          "[ccsv] no inline JSON state found. The data is likely only in " +
            "markup — use __ccsv.html()."
        );
      } else {
        console.log("[ccsv] inline findings added to captures — re-run __ccsv.best()");
      }
    },

    // Table-aware markup check. Locates the shooting columns by header text and
    // reports what those cells actually contain, which is what decides G1 for a
    // server-rendered page. A regex over outerHTML cannot tell a shooting cell
    // from a date.
    html() {
      console.log("[ccsv] raw markup scan:", score(location.href, document.documentElement.outerHTML, null));

      const tables = [...document.querySelectorAll("table")];
      if (!tables.length) {
        console.warn(
          "[ccsv] no <table> on this page. Open the Scoreboard or the league " +
            "Stats tab before running this."
        );
        return;
      }

      const SHOOTING_HEADER = /^(fg|ft)(%|m\/fga|m\/fta)?$/i;
      const MA = /^\d{1,3}\s*\/\s*\d{1,3}$/;
      const PCT = /^0?\.\d+$|^\d{1,3}\.\d%?$/;

      tables.forEach((table, i) => {
        const heads = [...table.querySelectorAll("th")].map((h) => h.textContent.trim());
        const rows = [...table.querySelectorAll("tr")].filter(
          (r) => r.querySelectorAll("td").length
        );
        const shootingCols = heads
          .map((h, j) => (SHOOTING_HEADER.test(h) ? j : -1))
          .filter((j) => j >= 0);

        const made = new Set();
        const pct = new Set();
        rows.slice(0, 6).forEach((row) => {
          [...row.querySelectorAll("td")].forEach((cell) => {
            const v = cell.textContent.trim();
            if (MA.test(v)) made.add(v);
            else if (PCT.test(v)) pct.add(v);
          });
        });

        // Distinct team links inside this table is the G2 measure: 18 means the
        // league grid, 1 means a single roster however good its cells look.
        const teamsHere = teamKeys(table.innerHTML);

        console.log(
          `  table[${i}] rows=${rows.length} teams=${teamsHere} shootingHeaders=${JSON.stringify(
            shootingCols.map((j) => heads[j])
          )}${teamsHere >= 18 && made.size ? "   <-- GRID CANDIDATE" : ""}`
        );
        console.log(`    headers:        ${JSON.stringify(heads.slice(0, 14))}`);
        console.log(`    made/attempted: ${JSON.stringify([...made].slice(0, 6))}`);
        console.log(`    decimals:       ${JSON.stringify([...pct].slice(0, 6))}`);
      });

      console.log(
        "  G1 decision rule: made/attempted must be PRESENT. Yahoo renders both " +
          'forms together ("8/9" in the cell, ".889" beside it), so a decimal ' +
          "alongside is harmless — only a table with decimals and NO x/y pair " +
          "fails, because attempts are then unrecoverable.\n" +
          "  G2: this must be the LEAGUE grid, not one team. 18 data rows and 18 " +
          "distinct team links is the grid; ~13 rows with Pos/Edit headers is a " +
          "single roster, which cannot satisfy G2 no matter what its cells show."
      );
    },

    save() {
      const bundle = {
        capturedAt: new Date().toISOString(),
        pageUrl: location.href,
        userAgent: navigator.userAgent,
        captures,
      };
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "yahoo-discovery.json";
      a.click();
      console.log(
        "[ccsv] saved. This contains real league data (team and manager names) " +
          "but no cookies — JS cannot read them. Keep it out of the repo."
      );
    },

    reset() {
      captures.length = 0;
      seen.clear();
      console.log("[ccsv] cleared");
    },

    stop() {
      window.fetch = origFetch;
      XMLHttpRequest.prototype.open = origOpen;
      XMLHttpRequest.prototype.send = origSend;
      delete window.__ccsv;
      console.log("[ccsv] uninstalled");
    },
  };

  console.log(
    "%c[ccsv] recording.%c Now: open Scoreboard → switch to a past week → open the " +
      "league Stats tab. Then call __ccsv.report() and __ccsv.best().",
    "color:#0a0;font-weight:bold",
    "color:inherit"
  );
})();
