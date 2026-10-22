/*
 * Capture league rosters into the CSV `fetch/rosters.py` expects.
 *
 * Nothing in the generator acquires rosters, and the week-0 ranking cannot run
 * without them. This is the manual path that unblocks it, per
 * specs/002-draft-ranking-week-0/research.md D12.
 *
 * Usage, in the DevTools console:
 *
 *   1. Open a team's roster page in your league.
 *   2. Paste this file.
 *   3. __roster.grab()        capture the team currently on screen
 *   4. Navigate to the next team, __roster.grab() again. Repeat for all 18.
 *   5. __roster.csv()         print the CSV
 *      __roster.save()        download it as rosters.csv
 *
 * Drop the result at `data/rosters.csv`.
 *
 *   __roster.status()   what has been captured so far
 *   __roster.reset()    start over
 *
 * Captures only team, player, position and status -- no projections. Those come
 * from a separate file on purpose: a projections file cannot express a rostered
 * player who HAS no projection, and FR-025 requires counting exactly those.
 */

(() => {
  const TEAM_COUNT = 18;
  const ROWS = [];
  const SEEN = new Set();

  /** Team id from the URL: /nba/{leagueId}/{teamId} -> "t.{teamId}". */
  const teamIdFromUrl = () => {
    const m = location.pathname.match(/\/(?:nba|nfl|mlb|nhl)\/\d+\/(\d{1,2})\b/);
    return m ? `t.${String(m[1]).padStart(2, "0")}` : "";
  };

  /** Yahoo player links look like /nba/players/{id} or carry a pid query. */
  const playerIdFrom = (row) => {
    const link = row.querySelector('a[href*="/players/"]');
    if (link) {
      const m = link.getAttribute("href").match(/\/players\/(\d+)/);
      if (m) return `nba.p.${m[1]}`;
    }
    return "";
  };

  const playerNameFrom = (row) => {
    const link = row.querySelector('a[href*="/players/"]');
    return link ? link.textContent.trim() : "";
  };

  /** Raw eligibility, e.g. "PG,SG". Yahoo renders it as "PG,SG" or "PG - SG". */
  const positionsFrom = (row) => {
    const cells = [...row.querySelectorAll("td")].map((c) => c.textContent.trim());
    for (const value of cells) {
      // A positions cell is short and made only of position tokens.
      if (/^(PG|SG|SF|PF|C|G|F)([,\-/\s]+(PG|SG|SF|PF|C|G|F))*$/i.test(value)) {
        return value.toUpperCase().split(/[,\-/\s]+/).filter(Boolean).join(",");
      }
    }
    return "";
  };

  /** IL / injury designation, if Yahoo shows one. Informational only. */
  const statusFrom = (row) => {
    const tag = row.querySelector(".ysf-player-status, .status, abbr");
    const text = tag ? tag.textContent.trim().toUpperCase() : "";
    return /^(IL|IL\+|INJ|O|GTD|DTD|NA)$/.test(text) ? text : "";
  };

  window.__roster = {
    rows: ROWS,

    grab() {
      const teamId = teamIdFromUrl();
      if (!teamId) {
        console.error(
          "[roster] could not read a team id from the URL. Open a TEAM page " +
            "(…/nba/{leagueId}/{teamId}), not the league home."
        );
        return;
      }
      if (SEEN.has(teamId)) {
        console.warn(`[roster] ${teamId} already captured — skipping`);
        return;
      }

      const captured = [];
      for (const row of document.querySelectorAll("tr")) {
        const playerId = playerIdFrom(row);
        if (!playerId) continue;
        const name = playerNameFrom(row);
        if (!name) continue;
        captured.push({
          team_id: teamId,
          player_id: playerId,
          name,
          positions: positionsFrom(row),
          status: statusFrom(row),
        });
      }

      if (!captured.length) {
        console.error(
          "[roster] no player rows found. Is this the roster view rather than " +
            "the matchup view?"
        );
        return;
      }

      // De-duplicate within the page: Yahoo renders some players twice
      // (a sticky header row, or a comparison panel).
      const unique = new Map(captured.map((r) => [r.player_id, r]));
      SEEN.add(teamId);
      ROWS.push(...unique.values());

      console.log(
        `%c[roster] ${teamId}: ${unique.size} players%c  (${SEEN.size}/${TEAM_COUNT} teams)`,
        "color:#0a0;font-weight:bold",
        "color:inherit"
      );
      const noPositions = [...unique.values()].filter((r) => !r.positions).length;
      if (noPositions) {
        console.warn(
          `[roster] ${noPositions} of ${unique.size} players have no positions. ` +
            "A player with no positions is eligible for UTIL only, so the " +
            "coverage floor will reject the team. Check the Pos column is visible."
        );
      }
    },

    status() {
      const missing = [];
      for (let i = 1; i <= TEAM_COUNT; i++) {
        const id = `t.${String(i).padStart(2, "0")}`;
        if (!SEEN.has(id)) missing.push(id);
      }
      console.log(`[roster] ${SEEN.size}/${TEAM_COUNT} teams, ${ROWS.length} players`);
      if (missing.length) console.log("  still needed:", missing.join(" "));
      else console.log("  complete — run __roster.save()");
      return { teams: SEEN.size, players: ROWS.length, missing };
    },

    csv() {
      const head = "team_id,player_id,name,positions,status";
      const quote = (v) => (/[",]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
      const body = ROWS.map((r) =>
        [r.team_id, r.player_id, r.name, r.positions, r.status].map(quote).join(",")
      );
      const text = [head, ...body].join("\n") + "\n";
      console.log(text);
      return text;
    },

    save() {
      if (SEEN.size < TEAM_COUNT) {
        console.warn(
          `[roster] only ${SEEN.size}/${TEAM_COUNT} teams captured. Saving ` +
            "anyway, but the run will classify as PRE_DRAFT and publish nothing " +
            "until every team is present."
        );
      }
      const blob = new Blob([this.csv()], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "rosters.csv";
      a.click();
      console.log("[roster] saved. Put it at data/rosters.csv (gitignored).");
    },

    reset() {
      ROWS.length = 0;
      SEEN.clear();
      console.log("[roster] cleared");
    },
  };

  console.log(
    "%c[roster] ready.%c Open each team's roster page and call __roster.grab(). " +
      "__roster.status() shows what is left.",
    "color:#0a0;font-weight:bold",
    "color:inherit"
  );
})();
