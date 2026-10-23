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
  const STORE_KEY = "ccsv.rosters.v1";

  // Persisted in localStorage, NOT in a closure.
  //
  // Navigating to the next team reloads the page, which destroys any in-memory
  // state -- so a closure-scoped array could only ever hold one team, and the
  // script had to be re-pasted every time. Capturing 18 teams that way is 18
  // separate files to merge by hand.
  const load = () => {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  };
  const persist = () => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(ROWS));
    } catch (e) {
      console.warn("[roster] could not persist:", e.message);
    }
  };

  const ROWS = load();
  const SEEN = new Set(ROWS.map((r) => r.team_id));

  /** Team id from the URL: /nba/{leagueId}/{teamId} -> "t.{teamId}". */
  const teamIdFromUrl = () => {
    const m = location.pathname.match(/\/(?:nba|nfl|mlb|nhl)\/\d+\/(\d{1,2})\b/);
    return m ? `t.${String(m[1]).padStart(2, "0")}` : "";
  };

  /** Yahoo player links look like /nba/players/{id} or carry a pid query. */
  const playerIdFrom = (row) => {
    for (const link of row.querySelectorAll("a[href]")) {
      const href = link.getAttribute("href") || "";
      const m =
        href.match(/\/players\/(\d+)/) ||
        href.match(/[?&]pid=(\d+)/) ||
        href.match(/\/nba\/players\/(\d+)/);
      if (m) return `nba.p.${m[1]}`;
    }
    // Fall back to a name slug rather than dropping the player. A missing row
    // would silently shrink the roster and read as an incomplete draft.
    const name = playerNameFrom(row);
    return name ? `name:${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}` : "";
  };

  const playerNameFrom = (row) => {
    const link = row.querySelector('a[href*="/players/"]');
    return link ? link.textContent.trim() : "";
  };

  /** The player's ELIGIBILITY, read from the "TEAM - POS" line in the player cell.
   *
   * NOT the "Pos" column. That column holds the SLOT the manager has the player
   * in -- G, FC, Util, BN, IL -- which is a different thing and changes every
   * time somebody sets a lineup. Reading it was a bug: every bench and Util
   * player came back with no eligibility at all, because "BN" and "Util" are
   * not positions, and a bench player with no eligibility can never substitute
   * into a G or FC slot when a starter has no projection.
   *
   * Yahoo renders eligibility in this league's own slot classes: "PHX - G",
   * "MIA - FC", "ORL - G,FC".
   */
  const positionsFrom = (row) => {
    const text = row.textContent.replace(/\s+/g, " ");
    // "{TEAM} - {POS}[,{POS}]" where TEAM is a 2-4 letter club abbreviation.
    const m = text.match(/\b[A-Z]{2,4}\s*-\s*((?:PG|SG|SF|PF|GF|FC|[GFC])(?:\s*,\s*(?:PG|SG|SF|PF|GF|FC|[GFC]))*)\b/);
    if (!m) return "";
    return m[1].toUpperCase().split(/\s*,\s*/).filter(Boolean).join(",");
  };

  /** The player's NBA club, from the same "PHX - G" text.
   *
   * Needed to derive `projected_games`: how many games a player plays in the
   * target week is a property of his real-world team's schedule, and FR-017
   * forbids substituting a league-average constant.
   */
  const nbaTeamFrom = (row) => {
    const text = row.textContent.replace(/\s+/g, " ");
    const m = text.match(/\b([A-Z]{2,4})\s*-\s*(?:PG|SG|SF|PF|GF|FC|[GFC])\b/);
    return m ? m[1] : "";
  };

  /** The team's display name, for the published page.
   *
   * Week 0 has no scoreboard, so this capture is the only place a name can come
   * from -- without it every row on the page reads "t.01", which is correct and
   * useless to a reader.
   *
   * Yahoo renders it in the page heading, usually glued to the record and the
   * manager ("Keyboard Cats0-0-0 | 1st Place | Doug Kang"), so anything from the
   * first digit or pipe onward is trimmed off.
   */
  const teamNameFromPage = () => {
    // The document title is the reliable source:
    //   "{League} - {Team} | Fantasy Basketball | Yahoo! Sports"
    // Verified against the live league. The <h1> is Yahoo's own site header and
    // reads "Yahoo Sports" on EVERY page -- using it silently labelled all 18
    // teams identically, which looks like data rather than a bug.
    const head = (document.title || "").split("|")[0].trim();
    const i = head.indexOf(" - ");
    const name = i >= 0 ? head.slice(i + 3).trim() : "";
    return name && name.length <= 60 ? name : "";
  };

  /** The roster SLOT: G, FC, UTIL, BN, or IL. */
  const slotFrom = (row) => {
    const cell = row.querySelector("td, th");
    const text = cell ? cell.textContent.trim().toUpperCase() : "";
    return /^(G|FC|UTIL|BN|IL|IL\+)$/.test(text) ? text.replace("+", "") : "";
  };

  /** Status carried into the parser. "IL" means the player cannot fill an
   *  active slot this week, whatever his projection says. */
  const statusFrom = (row, slot) => {
    if (slot === "IL") return "IL";
    const tag = row.querySelector(".ysf-player-status, .status, abbr");
    const text = tag ? tag.textContent.trim().toUpperCase() : "";
    return /^(INJ|O|GTD|DTD|NA|Q)$/.test(text) ? text : "";
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

      const teamName = teamNameFromPage();
      const captured = [];
      for (const row of document.querySelectorAll("tr")) {
        const playerId = playerIdFrom(row);
        if (!playerId) continue;
        const name = playerNameFrom(row);
        if (!name) continue;
        const slot = slotFrom(row);
        captured.push({
          team_id: teamId,
          player_id: playerId,
          name,
          positions: positionsFrom(row),
          nba_team: nbaTeamFrom(row),
          status: statusFrom(row, slot),
          team_name: teamName,
          slot,
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
      persist();

      console.log(
        `%c[roster] ${teamId}: ${unique.size} players%c  (${SEEN.size}/${TEAM_COUNT} teams)`,
        "color:#0a0;font-weight:bold",
        "color:inherit"
      );
      // Print what was actually read, so a mis-parse is visible BEFORE the
      // file is saved rather than as an unexplained coverage failure later.
      console.table(
        [...unique.values()].map((r) => ({
          name: r.name,
          id: r.player_id,
          eligible: r.positions,
          nba: r.nba_team,
          slot: r.slot,
          status: r.status,
          team: r.team_name,
        }))
      );

      const noPositions = [...unique.values()].filter((r) => !r.positions).length;
      if (noPositions) {
        console.warn(
          `[roster] ${noPositions} of ${unique.size} players have no eligibility. ` +
            "Such a player can fill UTIL only, so the coverage floor may reject " +
            "the team. Eligibility is read from the \"PHX - G\" text in the " +
            "player cell, not the Pos column."
        );
      }
      if (!teamName) {
        console.warn(
          "[roster] no team name found; the page will label this team by its " +
            "id. Harmless, but you can add it to the team_name column by hand."
        );
      }
      const noIds = [...unique.values()].filter((r) => /^name:/.test(r.player_id)).length;
      if (noIds) {
        console.warn(
          `[roster] ${noIds} players fell back to a name-derived id. That is ` +
            "usable as long as data/projections.csv uses the SAME ids."
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
      const head = "team_id,player_id,name,positions,nba_team,status,team_name";
      const quote = (v) => (/[",]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
      const body = ROWS.map((r) =>
        [r.team_id, r.player_id, r.name, r.positions, r.nba_team, r.status, r.team_name || ""]
          .map(quote)
          .join(",")
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
      persist();
      console.log("[roster] cleared");
    },
  };

  console.log(
    `%c[roster] ready.%c ${SEEN.size}/${TEAM_COUNT} teams already captured ` +
      "(kept in localStorage, so navigating between teams is safe). " +
      "__roster.grab() on each team page; __roster.status() shows what is left.",
    "color:#0a0;font-weight:bold",
    "color:inherit"
  );
})();
