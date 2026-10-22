const TEAM_COUNT = 18;
const KEY = "rosters";

const byId = (id) => document.getElementById(id);

const read = async () => (await browser.storage.local.get(KEY))[KEY] || [];
const write = (rows) => browser.storage.local.set({ [KEY]: rows });

function say(text, kind = "ok") {
  const el = byId("msg");
  el.textContent = text;
  el.className = `msg ${kind}`;
  el.hidden = false;
}

function teamIds(rows) {
  return new Set(rows.map((r) => r.team_id));
}

async function refresh() {
  const rows = await read();
  const captured = teamIds(rows);
  byId("n").textContent = String(captured.size);
  byId("bar").style.width = `${Math.min(100, (captured.size / TEAM_COUNT) * 100)}%`;
  byId("save").disabled = captured.size === 0;

  const missing = [];
  for (let i = 1; i <= TEAM_COUNT; i++) {
    const id = `t.${String(i).padStart(2, "0")}`;
    if (!captured.has(id)) missing.push(id);
  }
  byId("missing").textContent = missing.length
    ? `Still needed: ${missing.join(" ")}`
    : "All 18 teams captured — download the CSV.";
  return rows;
}

byId("grab").addEventListener("click", async () => {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  let result;
  try {
    result = await browser.tabs.sendMessage(tab.id, { type: "scrape" });
  } catch {
    say(
      "Could not reach the page. Open a team's roster page on " +
        "basketball.fantasysports.yahoo.com and reload it once.",
      "err"
    );
    return;
  }

  if (!result?.ok) {
    say(result?.error || "Capture failed.", "err");
    return;
  }

  const rows = await read();
  // Re-capturing a team replaces it rather than duplicating. The parser rejects
  // a player on two rosters, so a stale duplicate would fail the whole run.
  const kept = rows.filter((r) => r.team_id !== result.teamId);
  await write([...kept, ...result.players]);

  const replaced = kept.length !== rows.length;
  const label = result.teamName || result.teamId;
  const lines = [
    `${replaced ? "Re-captured" : "Captured"} ${label}: ${result.players.length} players`,
  ];
  if (result.warnings.length) lines.push(...result.warnings);
  say(lines.join("\n"), result.warnings.length ? "warn" : "ok");
  await refresh();
});

byId("save").addEventListener("click", async () => {
  const rows = await read();
  const head = "team_id,player_id,name,positions,status,team_name";
  const quote = (v) => (/[",]/.test(v ?? "") ? `"${String(v).replace(/"/g, '""')}"` : v ?? "");
  const body = rows.map((r) =>
    [r.team_id, r.player_id, r.name, r.positions, r.status, r.team_name]
      .map(quote)
      .join(",")
  );
  const csv = [head, ...body].join("\n") + "\n";

  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  // Safari's downloads API support varies by version, so fall back to an
  // anchor click rather than failing with the CSV already built.
  try {
    await browser.downloads.download({ url, filename: "rosters.csv", saveAs: true });
  } catch {
    const a = document.createElement("a");
    a.href = url;
    a.download = "rosters.csv";
    a.click();
  }

  const captured = teamIds(rows).size;
  say(
    captured < TEAM_COUNT
      ? `Saved ${captured}/${TEAM_COUNT} teams. The run will publish nothing ` +
          "until every team is present — that is the expected pre-draft outcome."
      : `Saved all ${TEAM_COUNT} teams. Put it at data/rosters.csv`,
    captured < TEAM_COUNT ? "warn" : "ok"
  );
});

byId("reset").addEventListener("click", async () => {
  await write([]);
  say("Cleared.", "ok");
  await refresh();
});

refresh();
