# Specification Quality Checklist: Draft Ranking (Week 0)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-20
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Validation detail

**Iteration 1 — one item failed.** Two `[NEEDS CLARIFICATION]` markers remained (limit is 3). Both
were retained deliberately rather than defaulted, because each decided which sections of the spec
were in scope at all, and neither had a defensible default: the first is a social decision about
naming real congregation members, and the second swung scope by roughly a third.

**Iteration 2 — all items pass.** Both markers resolved in the 2026-10-20 clarification session and
recorded under the spec's *Clarifications* heading:

1. **A week-0 page is published.** The alternative — computing the draft ranking only as the in-season
   prior — would have dropped User Story 1 and all of Part 4. Note the project's two algorithm
   documents genuinely conflicted here: `docs/draft-rankings-algorithm-v1.md` §6 specifies how to
   publish week 0 honestly, while `docs/rankings-algorithm-v1.md` §4 argues an absent ranking beats a
   confidently wrong one. The resolution accepts publication *conditional on* the projection label
   required by FR-030.
2. **The week-0 article is a league-wide draft recap.** This was the largest of the three options
   offered, and it added Part 7 (FR-041–049), the Draft Results and Draft Recap Article entities,
   SC-005, SC-008, SC-011, and three edge cases. It also introduced a second acquisition input — the
   pick-by-pick draft board — which the spec previously did not require at all.

**Scope added by iteration 2**: 9 functional requirements, 2 key entities, 3 success criteria, 3 edge
cases, and 1 new user story (now User Story 2, which pushed the roster-reaction and maintainer-audit
stories to P3 and P4).

**Deliberate wording choices that could read as implementation detail but are not:**

- FR-019 requires reusing "the same all-play comparison the in-season algorithm uses." This names a
  *consistency constraint*, not a technique — and it is the load-bearing requirement of the feature,
  since a prior that disagrees with the in-season metric about what "good" means produces the rank
  discontinuity described in the design document §3.
- FR-031/FR-033/FR-045 reference the existing disclosure-term screen and provenance comment. Both are
  existing published-output obligations from `001`, referenced rather than redesigned.
- FR-044 specifies that article generation is an acquisition stage rather than a rendering stage. This
  is a determinism requirement inherited from Constitution v2.0.0 Principle I, not an architecture
  preference.
- FR-010's makes-and-attempts requirement is phrased as a hard ingest rejection because it is a
  go/no-go on the projection source, not a data-cleaning preference.

**Not treated as gaps:**

- The shrink constant's initial value is intentionally unspecified — the spec requires only that it be
  declared and documented. Choosing it is a planning decision, matching how `001` handled its
  movement-significance threshold.
- The projection coverage threshold (FR-026) is likewise required to exist and be documented without
  the spec fixing a number.
- FR-046's tone screen is stated as a requirement without naming the mechanism; an existing term
  blocklist already covers the egregious cases, and whether that is sufficient is a planning question.
