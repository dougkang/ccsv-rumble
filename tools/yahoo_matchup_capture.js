/*
 * Capture a week's head-to-head matchups, with each side's category totals.
 *
 * Driven by tools/chrome_capture.py (`chrome_capture.py matchups --week N`),
 * which writes data/matchups.csv. It can also be pasted into the DevTools
 * console:
 *
 *   On the scoreboard (…/nba/<league-id>?matchup_week=N&module=matchups):
 *     __matchup.pairs()   JSON list of this week's matchup pages
 *
 *   On one matchup page (…/nba/<league-id>/matchup?week=N&mid1=A&mid2=B):
 *     __matchup.grab()    JSON of both teams' totals for the week
 *
 * WHY THERE IS NO ACCUMULATOR
 *
 * Unlike `yahoo_roster_capture.js`, nothing is kept in localStorage. Each call
 * RETURNS its page's data and the Python driver collects it, so there is no
 * stale state from a previous run to reset.
 *
 * WHAT THE PAGE CARRIES
 *
 * The matchup page has a two-row team table headed
 *
 *   Team | FGM/A* | FG% | FTM/A* | FT% | 3PTM | PTS | REB | AST | ST | BLK | TO | (won)
 *
 * The starred columns are display-only stats, and they are the reason this
 * capture is worth having: they are TEAM-LEVEL makes and attempts, which
 * specs/004 research run 3 could not find (the page then showed only `.609`).
 * The percentage columns are kept only as Yahoo's rounded checksum.
 *
 * Columns are found by header TEXT, never position, and team ids come from each
 * row's own team link. Yahoo's navigation links every team in the league, so
 * reading teams off the whole document would see 18 on a two-team page --
 * research run 3 fell into exactly that.
 */

(() => {
  // Header text -> output field. The two composite columns split into two.
  const COLUMNS = {
    "FGM/A*": ["fgm", "fga"],
    "FG%": "fg_pct_display",
    "FTM/A*": ["ftm", "fta"],
    "FT%": "ft_pct_display",
    "3PTM": "tpm",
    PTS: "pts",
    REB: "reb",
    AST: "ast",
    ST: "stl",
    BLK: "blk",
    TO: "to",
  };
  const REQUIRED = Object.keys(COLUMNS);

  const clean = (t) => (t || "").replace(/\s+/g, " ").trim();
  const teamId = (n) => `t.${String(n).padStart(2, "0")}`;

  /** The team totals table: the one whose header has Team and every column. */
  const teamTable = () => {
    for (const table of document.querySelectorAll("table")) {
      const heads = [...table.querySelectorAll("thead th")].map((th) => clean(th.textContent));
      if (heads.includes("Team") && REQUIRED.every((k) => heads.includes(k))) {
        return { table, heads };
      }
    }
    return null;
  };

  window.__matchup = {
    pairs() {
      const seen = new Map();
      for (const a of document.querySelectorAll('a[href*="/matchup?"]')) {
        const url = new URL(a.getAttribute("href"), location.href);
        const week = url.searchParams.get("week");
        const mid1 = url.searchParams.get("mid1");
        const mid2 = url.searchParams.get("mid2");
        if (!week || !mid1 || !mid2) continue;
        // Keyed on the pairing, not the href: the same matchup can be linked
        // more than once on the page.
        seen.set(`${week}:${mid1}:${mid2}`, {
          url: url.href,
          week: Number(week),
          team_a: teamId(mid1),
          team_b: teamId(mid2),
        });
      }
      return JSON.stringify([...seen.values()]);
    },

    grab() {
      const found = teamTable();
      if (!found) {
        return JSON.stringify({
          error: "no team table with headers Team, " + REQUIRED.join(", "),
        });
      }
      const { table, heads } = found;
      const week = Number(new URL(location.href).searchParams.get("week")) || null;
      const rows = [];
      for (const tr of table.querySelectorAll("tbody tr")) {
        const cells = [...tr.children].map((c) => clean(c.textContent));
        const link = [...tr.querySelectorAll("a[href]")]
          .map((a) => (a.getAttribute("href") || "").match(/\/nba\/\d+\/(\d{1,2})(?:$|[/?#])/))
          .find(Boolean);
        const row = {
          team_id: link ? teamId(link[1]) : "",
          team_name: clean(tr.querySelector("a[href]")?.textContent) || cells[0] || "",
        };
        for (const [head, field] of Object.entries(COLUMNS)) {
          const value = cells[heads.indexOf(head)] ?? "";
          if (Array.isArray(field)) {
            const [made, att] = value.split("/");
            row[field[0]] = (made || "").trim();
            row[field[1]] = (att || "").trim();
          } else {
            row[field] = value;
          }
        }
        // The unlabelled column after TO is the categories this side has won.
        const won = cells[heads.indexOf("TO") + 1] ?? "";
        row.cat_wins = /^\d+(\.\d+)?$/.test(won) ? won : "";
        rows.push(row);
      }
      return JSON.stringify({ week, rows });
    },
  };
})();
