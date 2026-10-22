# Roster Capture — Safari extension

Captures league rosters into the CSV `fetch/rosters.py` reads, without pasting a
script into the console on every team page.

## Honest comparison with the console script

`tools/yahoo_roster_capture.js` does the same job and needs no Xcode. It now
persists to `localStorage`, so navigating between the 18 teams is safe — that
was the real pain, not the pasting.

What the extension adds over it:

| | Console script | Extension |
|---|---|---|
| Setup | paste once per browser session | Xcode build, one time |
| Survives navigation | yes (localStorage) | yes (extension storage) |
| Progress | `__roster.status()` | always visible in the popup |
| Re-capturing a team | appends, you must `reset()` | replaces that team cleanly |
| Works in a private window | no (no localStorage) | yes |

If the console script is working for you, **this is a convenience, not a fix.**

## Safari needs more than Chrome does

Safari cannot load an unpacked extension folder. It has to be wrapped in a macOS
app, built, and signed. That is Apple's model, not a quirk of this extension.

**Requires Xcode.** If it isn't installed, the console script is the faster path.

```bash
# 1. Convert this folder into an Xcode project
xcrun safari-web-extension-converter tools/safari-extension \
  --project-location ~/Developer/ccsv-roster-capture \
  --app-name "CCSV Roster Capture" \
  --bundle-identifier io.dgkng.ccsv.rostercapture \
  --macos-only --no-prompt

# 2. Build and run it once (this registers the extension with Safari)
open ~/Developer/ccsv-roster-capture/*.xcodeproj
#    then press ⌘R
```

Then in Safari:

1. **Settings → Advanced →** tick *Show features for web developers*
2. **Develop →** tick *Allow Unsigned Extensions*
   — needed because the app is locally built, and **it resets every time Safari
   restarts.** Re-tick it, or sign the app with a developer certificate to make
   it stick.
3. **Settings → Extensions →** enable *CCSV Roster Capture*
4. Grant it access to `basketball.fantasysports.yahoo.com` when asked

## Using it

1. Open any team's roster page in your league.
2. Click the toolbar button → **Capture this team**.
3. Navigate to the next team, capture again. The popup counts up to 18 and lists
   which team ids are still missing.
4. **Download CSV** → save to `data/rosters.csv`.

Re-capturing a team **replaces** its rows rather than appending. That matters:
the parser rejects a player appearing on two rosters, so a stale duplicate from
a trade would fail the whole run.

## What it reads, and the two traps it avoids

- **Eligibility comes from the `PHX - G` text in the player cell**, not the
  `Pos` column. That column holds the *slot* the player is in — `G`, `FC`,
  `Util`, `BN`, `IL` — which changes whenever a lineup is set. Reading it leaves
  every bench player with no eligibility, so none of them can cover a `G` or
  `FC` slot when a starter has no projection.
- **A player in the `IL` slot is marked `IL`.** He stays on the roster, counting
  toward completeness, but never enters a lineup — the format cannot deploy him,
  and crediting his production would inflate the team by a player who cannot
  play.

The popup warns when a team yields players with no eligibility, players that
fell back to a name-derived id, or no team name. None of these fail the capture;
they are things worth seeing before 17 more teams are captured the same way.

## Chrome or Firefox

The same folder loads directly, no build step:

- **Chrome** — `chrome://extensions` → Developer mode → *Load unpacked*
- **Firefox** — `about:debugging` → *Load Temporary Add-on* → pick `manifest.json`

Both need `browser` aliased to `chrome`; Chrome provides that under Manifest V3
for the APIs used here.
