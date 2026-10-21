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

- [ ] No [NEEDS CLARIFICATION] markers remain
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

### Validation detail — iteration 1

**One item fails: two `[NEEDS CLARIFICATION]` markers remain** (limit is 3), recorded under the
spec's *Open Clarifications* heading. Both were retained deliberately rather than defaulted, because
each changes which sections of the spec are in scope at all:

1. **Whether a week-0 page is published publicly**, or the draft ranking only ever serves as the
   in-season prior. The project's own documents conflict — `docs/draft-rankings-algorithm-v1.md` §6
   specifies honest week-0 publication, while `docs/rankings-algorithm-v1.md` §4 argues an absent
   ranking beats a confidently wrong one for a casual audience. If the answer is "compute only," User
   Story 1 and all of Part 4 (FR-028–034) drop out.
2. **Whether a published week-0 page carries a generated write-up.** `001`'s article is driven by
   notable events, none of which exist before any games are played.

Neither has a defensible default: the first is a social decision about naming real congregation
members, and the second swings scope by roughly a third.

**Deliberate wording choices that could read as implementation detail but are not:**

- FR-019 requires reusing "the same all-play comparison the in-season algorithm uses." This names a
  *consistency constraint*, not a technique — and it is the load-bearing requirement of the feature,
  since a prior that disagrees with the in-season metric about what "good" means produces the
  rank discontinuity described in the design document §3.
- FR-031/FR-033 reference the existing disclosure-term screen and provenance comment. Both are
  existing published-output obligations from `001`, referenced rather than redesigned.
- FR-010's makes-and-attempts requirement is phrased as a hard ingest rejection because it is a
  go/no-go on the projection source, not a data-cleaning preference.

**Not treated as gaps:**

- The shrink constant's initial value is intentionally unspecified — the spec requires only that it be
  declared and documented. Choosing it is a planning decision, matching how `001` handled its
  movement-significance threshold.
- The projection coverage threshold (FR-026) is likewise required to exist and be documented without
  the spec fixing a number.
