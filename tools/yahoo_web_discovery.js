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
 *   __ccsv.save()     download the captured payloads for offline inspection
 *   __ccsv.probe(5)   re-request every captured URL with week=5 substituted
 *   __ccsv.reset()    clear captures, keep recording
 *   __ccsv.stop()     uninstall the interceptors
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
  const NOISE = /(doubleclick|scorecardresearch|googlesyndication|google-analytics|googletagmanager|adservice|beap\.|geo\.yahoo|analytics\.yahoo|csc\.beap|\.gif(\?|$)|sb\.scorecardresearch)/i;

  const captures = [];
  const seen = new Set();

  /* --- scoring against the data-source contract -------------------------- */

  // Requirement 1: per-week, per-category totals for ALL 18 teams, not just
  // the viewing manager's matchup. The hardest requirement, and the first
  // thing the contract says to verify against any new provider.
  const teamKeys = (text) => {
    const found = text.match(/\d+\.l\.\d+\.t\.\d+/g);
    return found ? new Set(found).size : 0;
  };

  // Requirement 2: FG and FT as makes and attempts, NEVER as a percentage.
  // A rounded percentage cannot be re-aggregated and the information is
  // unrecoverable afterward. "18/42" survives; ".458" is a dead end.
  const madeAttempted = (text) => {
    const found = text.match(/"\s*\d{1,3}\s*\/\s*\d{1,3}\s*"/g);
    return found ? found.slice(0, 5) : [];
  };

  // The failure mode this is looking for: a payload that carries shooting
  // only as a decimal. Reported so a surface can be ruled out fast.
  const percentOnly = (text) =>
    /"(fg|ft)_?(pct|percentage)"\s*:\s*"?\.?\d/i.test(text) ||
    /"0?\.\d{3}"/.test(text);

  // Requirement 6: historical weeks addressable, so FR-038 backfill and the
  // RECHECK_WEEKS=3 correction window both work.
  const weekAddressable = (url) => /[?&;](week|wk)=/i.test(url);

  const score = (url, text) => {
    const teams = teamKeys(text);
    const ma = madeAttempted(text);
    return {
      teams,
      allTeams: teams >= 18,
      madeAttempted: ma.length > 0,
      maSamples: ma,
      percentOnly: percentOnly(text) && ma.length === 0,
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

    const entry = { url, status, via, ...score(url, trimmed), payload: parsed };
    captures.push(entry);

    const verdict = entry.allTeams && entry.madeAttempted ? "%c✓ STRONG" : "%c  ";
    console.log(
      `${verdict}%c ${entry.teams} teams | ma:${entry.madeAttempted} | week:${entry.weekParam} | ${url.slice(0, 110)}`,
      entry.allTeams && entry.madeAttempted ? "color:#0a0;font-weight:bold" : "color:#888",
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
          madeAttempted: c.madeAttempted,
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
      console.log(
        `  all 18 teams:    ${top.allTeams ? "YES" : "NO  <- contract req 1, blocking"}\n` +
          `  made/attempted:  ${top.madeAttempted ? "YES " + JSON.stringify(top.maSamples) : "NO  <- contract req 2, blocking"}\n` +
          `  week addressable:${top.weekParam ? "YES" : "NO  <- contract req 6, breaks backfill"}`
      );
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
          console.log(`[ccsv] week=${week} -> ${r.status}`, score(probed, t), probed.slice(0, 110));
        } catch (e) {
          console.log(`[ccsv] week=${week} -> FAILED`, probed.slice(0, 110), e.message);
        }
      }
    },

    // Fallback when the pages turn out to be fully server-rendered: score the
    // current document's markup against the same requirements.
    html() {
      const text = document.documentElement.outerHTML;
      console.log("[ccsv] current document:", score(location.href, text));
      console.log(
        "  If allTeams+madeAttempted hold here, the provider parses HTML " +
          "rather than JSON — workable, but a more brittle parse target."
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
