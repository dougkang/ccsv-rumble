/*
 * Pull ESPN's season projections and the NBA week schedule.
 *
 * Paste into the DevTools console on https://fantasy.espn.com/ (any page on
 * that origin), then:
 *
 *   await __espn.projections()   -> CSV of per-game projections, downloads
 *   await __espn.schedule()      -> {"PHX": 4, ...} games per club, downloads
 *
 * Feed both to tools/merge_projections.py.
 *
 * WHY ESPN RATHER THAN THE OBVIOUS SOURCES
 *
 * The visible projections table shows FG% and FT% with NO attempts, which is
 * the one shape the ranking genuinely cannot use: given `.458` alone, neither
 * makes nor attempts can be recovered, and FR-010 refuses to invent them. The
 * underlying API carries raw FGM/FGA/FTM/FTA regardless, which is what this
 * reads. Free, and no subscription data is republished -- strict disclosure
 * means only rank reaches the page.
 *
 * TWO TRAPS, both found the hard way:
 *
 *   - Sending an X-Fantasy-Filter with `filterStatsForTopScoringPeriodIds`
 *     makes ESPN return every player and NO stats at all. A bare
 *     `{"players":{"limit":600}}` returns stats for ~420 players, which is
 *     ample for an 18-team league.
 *   - The API's games figure is SEASON games (65-72). Using it as the week's
 *     games would credit a player with a whole season of production in one
 *     week, so `schedule()` counts real games in the target week instead.
 */

(() => {
  const SEASON = 2027; // Yahoo/ESPN label the 2026-27 season by its end year.

  //: ESPN fantasy basketball stat ids.
  const STAT = {
    PTS: 0, BLK: 1, STL: 2, AST: 3, REB: 6, TO: 11,
    FGM: 13, FGA: 14, FTM: 15, FTA: 16, TPM: 17, GP: 42,
  };

  const download = (text, filename, type) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = filename;
    a.click();
    console.log(`[espn] saved ${filename}`);
  };

  window.__espn = {
    /** Per-game projections for every player ESPN projects. */
    async projections() {
      const response = await fetch(
        `https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/${SEASON}` +
          `/players?scoringPeriodId=0&view=kona_player_info`,
        {
          credentials: "include",
          // Deliberately minimal -- see the header comment.
          headers: { "X-Fantasy-Filter": JSON.stringify({ players: { limit: 600 } }) },
        }
      );
      const players = await response.json();

      const rows = [
        ["Name", "GP", "PTS", "REB", "AST", "STL", "BLK", "3PM", "TO",
         "FGM", "FGA", "FTM", "FTA"],
      ];
      for (const player of players) {
        // statSourceId 1 = projected; the "10…" id is the projected season set.
        const set = (player.stats || []).find(
          (s) => s.statSourceId === 1 && String(s.id).startsWith("10")
        );
        if (!set?.stats) continue;
        const games = set.stats[STAT.GP] || 0;
        if (!games) continue;
        // Season totals -> per game. The merge tool multiplies back up by the
        // games that club actually plays in the target week.
        const perGame = (id) => Math.round(((set.stats[id] || 0) / games) * 1000) / 1000;
        rows.push([
          player.fullName, games,
          perGame(STAT.PTS), perGame(STAT.REB), perGame(STAT.AST),
          perGame(STAT.STL), perGame(STAT.BLK), perGame(STAT.TPM),
          perGame(STAT.TO), perGame(STAT.FGM), perGame(STAT.FGA),
          perGame(STAT.FTM), perGame(STAT.FTA),
        ]);
      }

      const csv = rows
        .map((r) => r.map((v) => (/[",]/.test(String(v)) ? `"${v}"` : v)).join(","))
        .join("\n");
      console.log(`[espn] ${rows.length - 1} players projected`);
      download(csv, "espn-projections.csv", "text/csv");
      return csv;
    },

    /** Games each club plays between `from` and `to`, inclusive. YYYYMMDD. */
    async schedule(from, to) {
      if (!from || !to) {
        console.error('[espn] usage: __espn.schedule("20261020", "20261026")');
        return null;
      }
      const start = new Date(
        +from.slice(0, 4), +from.slice(4, 6) - 1, +from.slice(6, 8)
      );
      const end = new Date(+to.slice(0, 4), +to.slice(4, 6) - 1, +to.slice(6, 8));

      const games = {};
      for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        const stamp =
          `${d.getFullYear()}` +
          `${String(d.getMonth() + 1).padStart(2, "0")}` +
          `${String(d.getDate()).padStart(2, "0")}`;
        const r = await fetch(
          `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=${stamp}`
        );
        const j = await r.json();
        for (const event of j.events || []) {
          for (const c of event.competitions?.[0]?.competitors || []) {
            const club = c.team?.abbreviation;
            if (club) games[club] = (games[club] || 0) + 1;
          }
        }
      }

      const counts = Object.values(games);
      console.log(
        `[espn] ${Object.keys(games).length} clubs, ` +
          `${Math.min(...counts)}-${Math.max(...counts)} games in the week`
      );
      download(JSON.stringify(games, null, 2), "games.json", "application/json");
      return games;
    },
  };

  console.log(
    "%c[espn] ready.%c  await __espn.projections()  then  " +
      'await __espn.schedule("YYYYMMDD", "YYYYMMDD")',
    "color:#0a0;font-weight:bold",
    "color:inherit"
  );
})();
