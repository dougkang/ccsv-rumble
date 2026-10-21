# What Power Rankings Writers Actually Use to Justify Movement

**Purpose**: a review of published power-rankings prose, focused on *why a team is said to have moved
up or down*. Input to the article generator's per-team write-ups (spec SC-008, algorithm doc §5).

> **Read under strict disclosure.** Algorithm doc §5 and spec FR-032–034 permit **only rank and rank
> movement** to be published as figures; every other quantity reaches the page as prose or not at all.
> That makes this review *more* load-bearing, not less: with the decomposition table off the page, the
> prose is the only place a reader can get a "why." Part 3 below maps each justification pattern to the
> internal quantity behind it — those quantities are inputs to the sentence, never printed in it.

**Corpus** — 8 articles, three genres. Quotes below are verbatim. For most entries the surrounding
context was condensed during extraction, so treat those as true fragments rather than full paragraphs;
the four blurbs in pattern 11 were deliberately re-fetched in full, because the claim made there is
about what a blurb *omits* and a fragment cannot establish an omission.

| # | Source | Genre |
|---|---|---|
| A | [ESPN NBA Power Rankings, after one week (2025-26)](https://www.espn.com/nba/story/_/id/46749209/nba-power-rankings-where-all-30-teams-rank-one-week-2025-26-regular-season-play) | 30-team, weekly, all 30 blurbs |
| B | [NBA.com Power Rankings, Week 22](https://www.nba.com/news/power-rankings-2025-26-week-22) | 30-team, weekly, metric-driven |
| C | [NBA.com Power Rankings, Week 19](https://www.nba.com/news/power-rankings-2025-26-week-19) | same column, a low-movement week |
| D | [WTBU Fantasy Football Week 11 Power Rankings](https://sites.bu.edu/wtbu/2020/11/19/25020) | **10-team fantasy league** — the closest analog |
| E | [Around the Associations, Week 3 NFL Power Rankings](https://aroundtheassociations.substack.com/p/week-3-power-rankings-titans-and) | 32-team, weekly |
| F | [NBC/Yahoo NBA Power Rankings 2026-27, tiered](https://www.nbcsports.com/nba/news/nba-power-rankings-2026-27-championship-tiers-with-knicks-spurs-thunder-in-top-three-spots) | preseason, no results yet |
| G | [ffwrapped, How to Calculate Fantasy Football Power Rankings](https://blog.ffwrapped.com/posts/fantasy-football-power-rankings) | methodology, already cited in the algorithm doc |
| H | [CBS, NFL Power Rankings: The Top 10 doesn't look anything like it did in Week 1](https://www.cbssports.com/nfl/news/nfl-power-rankings-the-top-10-doesnt-look-anything-like-it-did-in-week-one) | 32-team, season-in-review self-audit |

---

## Part 1 — The justification taxonomy

Eleven patterns, ordered roughly by how often they carry a movement in this corpus.

### 1. The result itself — streak, record, or a scoreline

The default, and the one that carries the *biggest* moves. Every large jump in corpus A is justified
this way and nothing else:

- Spurs, 16 → 6: *"Off to its first 4-0 start since the 2019-20 season, San Antonio is finally thriving in the minutes when Wembanyama isn't on the floor."*
- Bulls, 24 → 13: *"The Bulls are one of the last undefeated teams left in the NBA, starting 3-0 for the first time in four years."*
- Cavaliers: *"After an opening-night loss to the Knicks, the Cavs have won three in a row and look poised to be one of the top teams in the conference yet again."*
- Suh-Tang Clan, holds #1 (D): *"With five straight wins, Patrick's team stays at the top spot for the third consecutive week."*
- Senior on J.V., 3 → 2 (D): *"Chad's team got back into the win column while posting the highest score of the week at over 143 points."*

Worth noting: **the simplest reason does the heaviest lifting.** Writers don't reach for sophistication
to justify a 10-spot jump; they point at 4-0 and move on. Sophistication shows up on the *small* moves.

### 2. Quality of opposition — the modifier that upgrades or downgrades a result

Same record, different meaning. This is the most common way a writer adds information to pattern 1:

- Thunder (B): *"They're a league-best 11-1 since the All-Star break, with six of those 11 wins having come within the top 10."*
- Magic (B): *"they've now won seven straight, with wins over the Wolves, Cavs and Heat included."*
- Celtics (B), the negative form: *"the Celtics are 8-12 (tied for second-worst) in games played between the top 10 teams in the league."*
- Pacers (C) dropped after losing all three post-break games to bottom-eight teams.
- Spurs (C): 8-0 in February, and *"all eight wins...by nine points or more"* — margin used as a quality proxy.

### 3. An underlying metric that explains or contradicts the record

The prestige move of the genre, and the direct analog of EMW/CAW:

- Lakers, 10 → 6 (B): *"they've now won three straight, holding the Knicks, Wolves and Nuggets...to just 107.5 points per 100."* — then the season-level consequence: *"That has them, finally, out of the bottom 10 on defense for the season."*
- Spurs (B): *"The Spurs have outscored their opponents by an amazing 23.6 points per 100 possessions in Wembanyama's 540 minutes."*
- Nuggets (B): offense 1st at 120.3, net rating only 8th at +4.1, and *"they're 17-18 in games that were within five points in the last five minutes."*
- Bengals (E): *"outgained through the air and on the ground"*, *"outplayed at virtually every position."*

Corpus B pairs **every** blurb with a fixed stat line (NetRtg, OffRtg, DefRtg, each with its league rank
in parentheses) sitting outside the prose. The prose never recites the whole stat line — it picks one
number and explains it.

### 4. Luck — the result wasn't deserved, in either direction

- Chargers (E), ranked above a team with a better record: they *"played well enough that they've just gotten unlucky."*
- Hornets, 27 → 18 (A) on a 2-2 record: *"Amazingly, the Hornets were one bad quarter from a 3-0 start."*
- Hannah's Bananas (D), **best record in the league, ranked 6th**: *"Hannah's whole team was boom-or-bust last week, and it seemed that the decision to rank her squad no higher than No. 4 was smart despite having the best record entering last week."*
- Dobbins the Free Elf (D) *won* and still fell a spot: *"Ethan got plenty of help from Josh Allen, Brandon Aiyuk and Daniel Carlson to pull off the upset."*

G is the methodology source for this and says the quiet part directly: *"Start with the teams whose
rank and record disagree, then expand their scores to see the breakdown."* On measuring it: *"A strong
power ranking beside a poor record gives you something to investigate. It doesn't tell you exactly how
many wins a team lost to its schedule. For that, I'd look at all-play record and expected wins."*

### 5. Availability and injury — the forward-looking justification

Note these move teams with *no change in results at all*:

- Timberwolves, 7 → 10 (A) at 2-2: *"Anthony Edwards...is out for two weeks with a hamstring injury."*
- Rockets, 5 → 11 (A): *"Without Fred VanVleet, Houston continues its by-committee approach to facilitation on offense with mixed results."*
- Pistons (A): *"The absence left behind by Malik Beasley and Jaden Ivey's injury has hurt the Pistons, despite their record."* — "despite their record" is the tell.
- Pacers (A): *"ultimately suffered so many injuries that their season has gone sideways from the start."*

### 6. "Not their fault" — the exogenous drop

The rarest pattern in the corpus and the most important one for this project. Exactly one clean instance:

- Texans, dropped to 32nd (E): *"Unfortunately, Houston's drop to last place in the power rankings is hardly a fault of their own."*

See Part 4 — this pattern is rare in a 30-team league and will be **routine** in an 18-team weekly one.

### 7. Roster quality, independent of results

`RosterPrior` written as prose, and D does it for a team with a losing record:

- These Ladies Love Sosi, 6 → 4 **at 4-6** (D): *"In terms of roster depth, Perry's team may be best or second-best in the whole league."*

### 8. Expectation-anchoring — confirmed or defied priors

Movement justified against what was believed before the season, not against last week:

- Celtics, 15 → 23 (A) — **dropped 8 spots for being exactly as expected**: *"We're a week into the season, and the Celtics are -- largely -- what we thought they would be."*
- Magic, 9 → 17 (A): *"The Magic opened the season with big expectations, but after beating Miami in the season opener, they've dropped three straight games."*
- 76ers, 19 → 9 (A): *"What a difference a year makes...the 76ers are leading the East with a pristine 4-0 record."*
- Knicks (A): *"It's expected, but the Knicks look a bit disjointed on the offensive end."*
- Nets (A): *"It's been an expected start for the Nets."*

### 9. Explicit non-movement

Holding a rank still gets prose, usually signalled by *again*, *continue*, or *still*:

- Thunder, holds #1 (A): *"It's been a competitive, painful, but still undefeated October for the defending champs."*
- Raptors, 22 → 22 (A): *"The Raptors opened their season with a blowout win in Atlanta...But it has been all downhill since."*
- Flavortown Trash Can Lids, holds #10 (D): *"Akshai's team once again failed to reach the 100-point threshold."*
- Celtics (C): *"The Celtics continue to do just fine without him."*

### 10. Small-sample hedging and methodological humility

Concentrated at season edges, exactly where this project's `w = n/(n+3)` is weakest:

- F states its own epistemics up front: *"this ranking is more about potential and expectations than a hard count."*
- F again: *"It's only a couple of preseason games, but he's played with confidence"*, and *"don't draw too much of a correlation between a couple of preseason games."*
- Conditional placement, F: *"This ranking may be too low for the Raptors — if Kawhi Leonard stays healthy."*
- Pete Prisco (H) opens by grading his own past failures: *"There's nothing like an NFL season to make one look like a full-fledged idiot"*, closing with *"We think we know. But do we really ever...?"*

### 11. Blurbs that don't justify the ranking at all

A substantial share of corpus A is color, not reasoning. The movement is stated by the number; the
prose entertains. This was verified by re-fetching four full multi-sentence blurbs rather than
trusting a one-sentence extract — in three of the four, **nothing anywhere in the blurb cites a
record, a streak, or a result**:

- **Nuggets, 2 → 5** — dropped three spots; the blurb is a Jamal Murray All-Star case, open to close:
  *"Could this be the season that Jamal Murray finally joins Nikola Jokic in the All-Star Game?
  Murray is off to a spectacular start, averaging 30.3 points and 6.0 assists on .530/.429/.923
  shooting splits. The new All-Star format that designates eight spots for international players
  should increase Murray's chances as a Canadian."* The team's 2-1 record is never mentioned.
- **Jazz, 29 → 24** — rose five spots; the entire blurb is Walker Kessler's contract situation and
  shooting development: *"He has made three of his four 3-point attempts this season after going
  11-of-56 from long range in his first three years in the league."*
- **Suns, 26 → 27** — the blurb profiles a backup point guard and then lists seven young players who
  *"will be important player development targets for first-year coach Jordan Ott's burgeoning program."*
- **Warriors, 8 → 3** — the one of the four that does touch a result, but subordinates it to a
  narrative: *"The Warriors had four 20-point scorers in Monday's win over the Grizzlies -- and
  Stephen Curry wasn't among them. That has happened only six times in the Curry era."* The win is a
  vehicle for the youth-leap story, not the stated reason for a five-spot jump.

So the genre's most-read column frequently writes **"one interesting thing about this team"** and lets
the rank number stand unexplained. That is affordable for ESPN because no reader is personally ranked.
See Part 4 — it is not affordable here.

---

## Part 2 — Writing style

**Length.** One to three sentences per team. Corpus A runs ~40–60 words; D runs longer and chattier;
B is shortest in prose because its numbers live in a separate stat block.

**The delta is a number, not a sentence.** Every column prints `Last Week: N` with an arrow. No blurb in
the corpus spends words saying "they moved up four spots" — the header already said it, and the prose
goes straight to why. Free structural lesson for a generated page.

**Numbers are inline but rationed.** One or two per blurb, always concrete and sourced (*"107.5 points
per 100"*, *"23.6 points per 100 possessions"*, *"over 143 points"*). B's pattern — a fixed stat line
adjacent to free prose — is the cleanest separation and the easiest to generate.

**Specificity beats adjectives.** Every memorable line in the corpus contains a number or a proper noun.
The forgettable ones are the bare assertions: *"The Hawks' season is off to a slow start"*, *"Joe's team
squeaks into the top-five once again."*

**Person and register.** All eight sources write in third person. D, the fantasy-league column, is the
outlier that matters: it uses **owners' first names, not team names**, as the grammatical subject
(*"Brady is the newest member of the league to slide from the top-five to the bottom-five"*), and the
author ranks himself and says so (*"My losing streak finally came to an end in explosive fashion"*).
That register — personal, self-implicating, gently mocking — is what a league column sounds like, and
it is a long way from ESPN's detached wit.

Two caveats before borrowing it. The page names real members of a congregation, and `config.py`'s
`DISALLOWED_TONE_TERMS` already bans the roast vocabulary ("embarrassing", "pathetic", "garbage") that
WTBU's genre leans on — so take D's *warmth and specificity*, not its edge. And D's author could mock
his own team because he was in the league; a generator has no such standing. Name teams, not people,
unless the league explicitly asks otherwise.

**Drops are softened; rises are not.** A consistent asymmetry. Falling teams get sympathy and causal
cover (*"hardly a fault of their own"*, *"played well enough that they've just gotten unlucky"*,
*"despite their record"*); rising teams just get the fact. For a congregation-facing page this is the
single most transferable stylistic habit in the corpus.

---

## Part 3 — Mapping to what v1 can actually compute

| Justification | Available from the v1 snapshot? | Source |
|---|---|---|
| 1. Record / streak | Yes | real schedule + results |
| 2. Quality of opposition | Partly — see caveat | real schedule + opponents' PowerScore |
| 3. Underlying metric vs. record | **Yes — the best fit** | EMW, CAW, schedule luck |
| 4. Luck | **Yes** | `actual win% − EMW`; "unluckiest week" |
| 5. Injury / availability | **Yes — directly** | the notable-events report (injuries, trades, roster moves) |
| 6. "Not their fault" | Yes, but needs explicit logic | ΔPowerScore vs. Δrank (Part 4) |
| 7. Roster quality | Yes | `RosterPrior` |
| 8. Expectation-anchoring | Yes, if stored | week-0 projection rank, archived per Principle III |
| 9. Non-movement | Yes | Δrank = 0 |
| 10. Hedging | Yes | `w = n/(n+3)` is literally the confidence level |
| 11. Color | No, and shouldn't be faked | — |

**Caveat on #2.** Algorithm doc §9 rules out opponent-adjusted all-play on purpose. So "who you beat"
prose must be sourced from the *real schedule*, never from the ranking input — otherwise the page
narrates a factor the number provably ignores.

**The one thing the corpus has no answer for, and this page owns outright:** the category profile.
Punt-build identification has no equivalent anywhere in these eight articles — the 9-category structure
makes it possible in a way the genre simply cannot match. That is the differentiated prose asset.

Under strict disclosure it has to be *said*, not tabulated, which §5 of the algorithm doc already
models: **"quietly dominant on the glass, giving away threes every week."** Note the useful asymmetry
§5 draws — a team's **rank within a category** is league data and safe to name outright ("best
rebounding team in the league"), whereas its per-category all-play *win rate* is a ranking output and
must stay off the page. So the vivid half of this content is fully available; only the decimals are not.

---

## Part 4 — Gaps the corpus does not cover

**1. Displacement — moving without doing anything.** In a rank-ordered list, a team falls when someone
passes it. The corpus contains exactly one explicit handling of this (the Texans line), because with 30
teams playing 3–4 games a week, genuine displacement is rare. In an **18-team league with one scored
week at a time**, it will be common: a team can post a fine week, gain PowerScore, and still drop two
spots. A blurb that says "you fell" when the cause is "someone passed you" reads as broken — and under
strict disclosure the prose is the *only* available remedy, since a reader cannot check a score column
to see that their team actually improved.

Recommendation: compute **ΔPowerScore alongside Δrank** internally, and branch the sentence on
disagreement. When ΔPowerScore ≥ 0 and Δrank < 0, the write-up must attribute the drop to the team
that passed them — the Texans sentence is the template. Disclosure-safe, because it publishes only a
direction and a rival's name, never a score. **This is the highest-value item in this review**: it is
cheap, it is invisible to the current spec, and getting it wrong produces the one output a reader can
prove is wrong about their own team.

**2. Shrinkage-driven movement — and it collides with strict disclosure.** `w = n/(n+3)` ramps the
weight on performance from 0% to 40% to 57% across weeks 0–4, so early-season rank changes are
**partly caused by the weighting itself**, with no on-court cause at all. Nobody in the corpus has
this problem, so there is no phrasing to borrow.

The collision: the natural fix is to explain it, but explaining it reveals that a projection-to-
performance weight exists and roughly how fast it moves — which is exactly what FR-032–034 forbids.
The two honest options are to **suppress** (hold week-0 ordering stable and let early movement be
reported without cause, accepting some unexplained motion) or to **generalize** (a standing,
non-numeric note that early-season rankings lean on draft projections and settle as games accumulate —
which algorithm doc §4 and `draft-v1` §6 already require in substance). I'd take the second: it is
vaguer than a reader would like but it does not leak a constant. **This one is a judgment call for the
maintainer, not something this review can settle.**

**3. (Corollary) Pattern 11 does not transfer.** Verified above: ESPN routinely moves a team several
spots and spends the whole blurb on an unrelated player profile. That works at national scale because
no reader is personally ranked — a Nuggets fan reading "Murray might make the All-Star team" is not
owed an explanation. Here, **all 18 readers are personally ranked**, and the one question each of them
opens the page to ask is why their own row moved. Every blurb should carry a reason; color is additive,
never a substitute.
