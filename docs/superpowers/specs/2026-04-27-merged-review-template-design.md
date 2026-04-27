# Merged review template — design delta

Status: approved (brainstorming). Date: 2026-04-27.
Supersedes parts of: [2026-04-24-research-paper-feedback-system-design.md](2026-04-24-research-paper-feedback-system-design.md) §4.3, §5, §14.

## 1. Why this exists

Two reviewer templates were on disk:

- `review-template.txt` — EuCNC/6G EDAS reviewer form. 5 numeric (1–5) ratings each with descriptor labels (relevance/timeliness, technical content & rigour, novelty/originality, quality of presentation, overall recommendation) + 3 free-text aspects (Strong / Weak / Recommended Changes).
- `review-template2.txt` — Second conference's form. 4 numeric (1–5) dimensions (Co=Content, O=Originality, Cl=Clarity, R=Relevance) + two categorical verdicts (`summary_of_evaluation`, `overall_recommendation`).

The original spec adopted template 1 verbatim. The implementation plan still referenced an even-earlier draft schema (`strengths`/`weaknesses`/`suggestions`/`section_comments`/`overall_assessment`). Three different shapes were drifting in three different files.

The user's intent: the *valuable* output of this system is **textual feedback**; numeric ratings produced by an LLM are noise as feedback to a researcher. The dimension *names* from both templates are useful only as **prompt-side scaffolding** — they describe what each focus axis should pay attention to.

## 2. Decision

**Output schema = three free-text fields only.** No numeric ratings in the reviewer JSON. No categorical verdicts.

```json
{
  "reviewer_id":        "r1",
  "reviewer_name":      "Aino",
  "specialty":          "<ACM class path>",
  "stance":             "...",
  "primary_focus":      "...",
  "secondary_focus":    "... | null",
  "profile_summary":    "...",
  "strong_aspects":      "...",
  "weak_aspects":        "...",
  "recommended_changes": "..."
}
```

`REVIEW_REQUIRED_FIELDS = [reviewer_id, reviewer_name, stance, primary_focus, strong_aspects, weak_aspects, recommended_changes]`.

`RATING_DIMENSIONS` is removed.

The rubric language from both templates is absorbed into focus-axis descriptions (§3) and lives only on the prompt side.

## 3. Axis enrichment

`config/axes.yaml` evolves from a flat list of strings to a list of `{name, description}` entries. The description is a 1–2-sentence prompt-fragment naming what to look for, drawn from both templates' dimension wording.

```yaml
stances:
  - {name: neutral,          description: "Balanced; weighs strengths and weaknesses without prior tilt."}
  - {name: supportive,       description: "Constructive; emphasises what works and how to extend it."}
  - {name: critical,         description: "Probing; surfaces problems the authors may have downplayed."}
  - {name: skeptical,        description: "Treats every claim as unproven until the evidence forces belief."}
  - {name: rigorous,         description: "Holds the work to formal correctness, statistical and methodological standards."}
  - {name: pragmatic,        description: "Asks whether results matter in practice, not just in theory."}
  - {name: devil's-advocate, description: "Argues the opposite of whatever the paper claims, to stress-test it."}
  - {name: visionary,        description: "Reads for long-horizon impact and what this work makes possible next."}

focuses:
  - {name: methods,         description: "Technical content and scientific rigour: completeness of analysis, soundness of models, validity of methodology. (Content / Technical Content & Rigour)"}
  - {name: results,         description: "Whether reported results actually support the claims; effect sizes, baselines, statistical strength. (Technical Content & Rigour)"}
  - {name: novelty,         description: "Originality: novel ideas vs incremental variations on a well-investigated subject. (Originality / Novelty & Originality)"}
  - {name: clarity,         description: "Quality of presentation: organisation, English, figures, references — does the paper communicate its message? (Clarity / Quality of Presentation)"}
  - {name: impact,          description: "Relevance and timeliness within the paper's research area; potential to influence the field."}
  - {name: related-work,    description: "Coverage and accuracy of references; positioning relative to existing literature."}
  - {name: reproducibility, description: "Whether a reader could rebuild the experiment from what is reported."}
  - {name: ethics,          description: "Ethical implications of methodology, dataset use, deployment, dual-use risks."}
```

`reviewers.core_focuses` stays in `config/default.yaml` (Board-composition knob, not a vocabulary entry).

## 4. Sampler & code consequences

- `AxesConfig` becomes `stances: list[AxisItem]`, `focuses: list[AxisItem]` where `AxisItem = {name: str, description: str}`.
- Sampler keeps comparing strings: it operates on `axis.name`. `core_focuses: list[str]` validates against `{f.name for f in axes.focuses}`.
- Profile Creation prompt builder splices `axis.description` into the persona prompt — both stance and primary/secondary focus descriptions are passed through verbatim.
- The Reviewer system prompt is rewritten to instruct: ground each of `strong_aspects`, `weak_aspects`, `recommended_changes` in the primary focus; let the secondary focus colour the depth where natural; cite specific manuscript text; do not rewrite the paper. **Implicit focus angle (option C)** — no separate `focus_commentary` field.
- `paperfb/contracts.py` drops `RATING_DIMENSIONS` and updates `REVIEW_REQUIRED_FIELDS` per §2.
- `tests/test_contracts.py` drops the `test_rating_dimensions_match_template` test and updates `test_review_required_fields_declared`.

## 5. Plan task changes

| Task | Change |
|------|--------|
| 2b — contracts | Use the §2 schema. Remove `RATING_DIMENSIONS`. |
| 9 — `write_review` tool | Required fields = §2; tool schema removes ratings, strengths, weaknesses, suggestions, section_comments, overall_assessment. |
| 10 — Reviewer agent | Persona/system prompt instructs implicit focus-angle. No ratings emitted. |
| 11 — Renderer | Per-reviewer header `## Review by {reviewer_name} — {specialty}` then a profile blurb (stance + primary/secondary focus) then three labeled prose sections. **No ratings table.** |
| 12 — Orchestrator tests | Fixture review uses §2 schema. |
| 14 — Judge | Fixtures use §2 schema. Judge prompt reads `review.primary_focus` (and optional `secondary_focus`). |
| 14c — EDAS rubric capture | **Removed.** No numeric ratings ⇒ no rubric to capture. |
| Spec §4.3, §4.4, §14 | Updated; the `null label` fallback and EDAS rubric follow-up disappear. |

## 6. Out of scope

- Changing the sampler's diversity rule (still `(stance, primary_focus)` unique).
- Per-focus structured commentary (option B) — explicitly rejected.
- Embedding numeric self-scores inside the prose (we considered this and dropped it; the renderer would have to special-case them).
