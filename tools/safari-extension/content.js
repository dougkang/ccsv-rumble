/*
 * Roster extraction, injected automatically on league pages.
 *
 * The parsing rules here are the same ones `tools/yahoo_roster_capture.js`
 * uses, and each exists because the obvious alternative was wrong against a
 * real page:
 *
 *   - Eligibility comes from the "PHX - G" text in the player cell, NOT the
 *     "Pos" column. That column holds the SLOT the manager has the player in
 *     (G, FC, Util, BN, IL), which changes whenever a lineup is set, and leaves
 *     every bench player with no eligibility at all.
 *   - A player in the IL slot is recorded as such, so the generator can keep
 *     him on the roster while refusing to put him in a lineup.
 *   - State lives in extension storage, so navigating between the 18 teams does
 *     not lose what has been captured.
 */

const TEAM_COUNT = 18;

const teamIdFromUrl = () => {
  const m = location.pathname.match(/\/(?:nba|nfl|mlb|nhl)\/\d+\/(\d{1,2})\b/);
  return m ? `t.${String(m[1]).padStart(2, "0")}` : "";
};

const playerNameFrom = (row) => {
  const link = row.querySelector('a[href*="/players/"]');
  return link ? link.textContent.trim() : "";
};

const playerIdFrom = (row) => {
  for (const link of row.querySelectorAll("a[href]")) {
    const href = link.getAttribute("href") || "";
    const m = href.match(/\/players\/(\d+)/) || href.match(/[?&]pid=(\d+)/);
    if (m) return `nba.p.${m[1]}`;
  }
  // A name slug rather than dropping the row: a missing player would silently
  // shrink the roster and read as an incomplete draft.
  const name = playerNameFrom(row);
  return name ? `name:${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}` : "";
};

const positionsFrom = (row) => {
  const text = row.textContent.replace(/\s+/g, " ");
  const m = text.match(
    /\b[A-Z]{2,4}\s*-\s*((?:PG|SG|SF|PF|GF|FC|[GFC])(?:\s*,\s*(?:PG|SG|SF|PF|GF|FC|[GFC]))*)\b/
  );
  return m ? m[1].toUpperCase().split(/\s*,\s*/).filter(Boolean).join(",") : "";
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

const slotFrom = (row) => {
  const cell = row.querySelector("td, th");
  const text = cell ? cell.textContent.trim().toUpperCase() : "";
  return /^(G|FC|UTIL|BN|IL|IL\+)$/.test(text) ? text.replace("+", "") : "";
};

const statusFrom = (row, slot) => {
  if (slot === "IL") return "IL";
  const tag = row.querySelector(".ysf-player-status, .status, abbr");
  const text = tag ? tag.textContent.trim().toUpperCase() : "";
  return /^(INJ|O|GTD|DTD|NA|Q)$/.test(text) ? text : "";
};

const teamNameFromPage = () => {
  const nodes = [
    document.querySelector("h1"),
    document.querySelector('[class*="team-name"]'),
  ].filter(Boolean);
  for (const node of nodes) {
    const raw = (node.textContent || "").replace(/\s+/g, " ").trim();
    // Yahoo glues the record and manager on: "Keyboard Cats0-0-0 | 1st | Doug".
    const cleaned = raw.split(/\s*[|·]\s*|\d+-\d+-\d+/)[0].trim();
    if (cleaned && cleaned.length <= 60) return cleaned;
  }
  const title = (document.title || "").split(/\s+-\s+|\s*\|\s*/)[0].trim();
  return title && title.length <= 60 ? title : "";
};

function scrapeRoster() {
  const teamId = teamIdFromUrl();
  if (!teamId) {
    return { ok: false, error: "Not a team page. Open a team's roster first." };
  }

  const teamName = teamNameFromPage();
  const rows = [];
  for (const row of document.querySelectorAll("tr")) {
    const playerId = playerIdFrom(row);
    const name = playerNameFrom(row);
    if (!playerId || !name) continue;
    const slot = slotFrom(row);
    rows.push({
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

  if (!rows.length) {
    return { ok: false, error: "No player rows found. Is this the roster view?" };
  }

  // Yahoo renders some players twice (sticky header, comparison panel).
  const unique = [...new Map(rows.map((r) => [r.player_id, r])).values()];
  return {
    ok: true,
    teamId,
    teamName,
    players: unique,
    warnings: [
      unique.filter((r) => !r.positions).length &&
        `${unique.filter((r) => !r.positions).length} players have no eligibility`,
      unique.filter((r) => r.player_id.startsWith("name:")).length &&
        `${unique.filter((r) => r.player_id.startsWith("name:")).length} fell back to name ids`,
      !teamName && "no team name found",
    ].filter(Boolean),
  };
}

browser.runtime.onMessage.addListener((message) => {
  if (message?.type === "scrape") return Promise.resolve(scrapeRoster());
  return undefined;
});
