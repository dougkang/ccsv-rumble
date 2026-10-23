/*
 * Capture the draft board from Yahoo's draft-results page.
 *
 * Paste into the DevTools console on:
 *   https://basketball.fantasysports.yahoo.com/nba/<league-id>/draftresults
 *
 * Then:
 *   __draft.save()      downloads draft-results.csv
 *   __draft.csv()       returns the CSV as a string, if you would rather copy it
 *
 * Move the file to data/draft-results.csv. It is gitignored.
 *
 * WHY THIS IS ONE CALL AND THE ROSTER CAPTURE IS EIGHTEEN
 *
 * The whole draft is on a single page -- one table per round -- so there is no
 * navigation to survive and no need for the localStorage accumulation that
 * `yahoo_roster_capture.js` requires.
 *
 * ON THE PARSING
 *
 * The round comes from each table's OWN header rather than from a counter, so a
 * page that renders rounds out of order or omits one still yields correct round
 * numbers. `overall` is computed rather than read, because the page shows only
 * the pick within the round.
 *
 * The player cell reads "Nikola Jokić (DEN - FC)". Name, club and eligibility
 * are split out of it; the id comes from the player link, not the text, so a
 * name with a parenthesis in it cannot corrupt it.
 *
 * WHAT THE PIPELINE DOES WITH IT
 *
 * `team_name` is the display name, which is all the page offers. The loader
 * resolves it against data/rosters.csv to get the `t.NN` id every other stage
 * uses -- so BOTH files must come from the same league, and a name present here
 * but not there makes the board unusable rather than silently dropping a team.
 *
 * A board with a gap in it is also treated as unusable: the run then publishes
 * the ranking and omits the recap (FR-049). So capture AFTER the draft is
 * finished, not during.
 */

(() => {
  const TEAMS = 18;

  const txt = (n) => (n.textContent || "").replace(/\s+/g, " ").trim();

  const build = () => {
    const rows = [
      ["round", "pick_in_round", "overall", "player_id", "player_name",
       "nba_team", "positions", "team_name"],
    ];

    for (const table of document.querySelectorAll("table")) {
      // The round lives in this table's own header: "Round 3".
      const head = [...table.querySelectorAll("th")]
        .map(txt)
        .find((t) => /^Round \d+$/.test(t));
      if (!head) continue;
      const round = parseInt(head.split(" ")[1], 10);

      for (const tr of table.querySelectorAll("tr")) {
        const cells = [...tr.querySelectorAll("td")];
        if (cells.length < 3) continue;
        const pick = parseInt(txt(cells[0]).replace(".", ""), 10);
        if (!pick) continue;

        const link = cells[1].querySelector('a[href*="/players/"]');
        const id = ((link && link.getAttribute("href")) || "").match(
          /\/players\/(\d+)/
        );
        const raw = txt(cells[1]); //: "Nikola Jokić (DEN - FC)"
        const parsed = raw.match(/^(.*?)\s*\(([A-Z]{2,4})\s*-\s*([A-Z,]+)\)/);

        rows.push([
          round,
          pick,
          (round - 1) * TEAMS + pick,
          id ? "nba.p." + id[1] : "",
          parsed ? parsed[1].trim() : link ? txt(link) : raw,
          parsed ? parsed[2] : "",
          parsed ? parsed[3] : "",
          txt(cells[2]),
        ]);
      }
    }
    return rows;
  };

  const quote = (v) =>
    /[",]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : v;

  window.__draft = {
    csv() {
      const rows = build();
      const picks = rows.length - 1;
      if (!picks) {
        console.error(
          "[draft] no picks found. Is this the draftresults page, and has the " +
            "board finished loading?"
        );
        return "";
      }
      // Say the count out loud: a short board is the one failure that looks
      // like success, and the loader will refuse it later without explaining
      // which pick is missing.
      console.log(
        `[draft] ${picks} picks over ${Math.ceil(picks / TEAMS)} rounds, ` +
          `${new Set(rows.slice(1).map((r) => r[7])).size} teams`
      );
      return rows.map((r) => r.map(quote).join(",")).join("\n");
    },

    save() {
      const csv = this.csv();
      if (!csv) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      a.download = "draft-results.csv";
      a.click();
      console.log("[draft] saved draft-results.csv");
    },
  };

  console.log(
    "%c[draft] ready.%c  __draft.save()",
    "color:#0a0;font-weight:bold",
    "color:inherit"
  );
})();
