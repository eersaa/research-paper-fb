# Ubiquitous Language

## Inputs & outputs

| Term             | Definition                                                                        | Aliases to avoid          |
| ---------------- | --------------------------------------------------------------------------------- | ------------------------- |
| **Manuscript**   | The markdown document a researcher submits for feedback; sole content input. PDFs are converted to Manuscripts offline. | Paper, research paper, doc |
| **Sample Manuscript** | One of the 3 published-with-CCS papers prepared offline under `samples/<paper-id>/manuscript.md`, with its `expected_acm_classes.json` ground truth. Used for evaluation, not for runtime input. | Sample, fixture paper |
| **Review**       | One reviewer's structured JSON output: three free-text aspects (strong / weak / recommended changes) plus identity fields (reviewer name, stance, primary focus, etc.). No numeric ratings. | Feedback, critique        |
| **Final Report** | The compiled markdown file aggregating all Reviews for a Run.                     | Output, summary, report   |
| **Run**          | One end-to-end execution of the pipeline on a single Manuscript.                  | Job, invocation           |

## Agents

| Term                     | Definition                                                                                 | Aliases to avoid        |
| ------------------------ | ------------------------------------------------------------------------------------------ | ----------------------- |
| **Classification Agent** | LLM agent that tags the Manuscript with ACM CCS Classes via the `lookup_acm` tool.         | Tagger, classifier      |
| **Profile Creation Agent** | Hybrid Sampler + LLM agent that produces N Personas for a Run by sampling (Specialty, Stance, Primary Focus, Secondary Focus) tuples under the Diversity Constraint with guaranteed Core Focus coverage. | Persona agent, profiler |
| **Reviewer Agent**       | LLM agent instantiated once per Persona that writes one Review in parallel with siblings.  | Critic, judge (reserved) |
| **Judge Agent**          | LLM agent in the evaluation harness that scores a Final Report against the Rubric.        | Evaluator, grader       |
| **Renderer**             | Pure code (not an agent) that compiles Reviews + Classification into the Final Report.    | Compiler, formatter     |

## Persona & diversity

| Term                     | Definition                                                                                                             | Aliases to avoid          |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| **Persona**              | A concrete reviewer identity formed from (Reviewer Name + Specialty + Stance + Primary Focus + Secondary Focus); serves as a Reviewer Agent system prompt. | Profile, character        |
| **Reviewer Name**        | A Finnish given name drawn from the Finnish nameday calendar (`data/finnish_names.json`), assigned to one Persona by the Sampler. Unique per Board; not part of the identity tuple under the Diversity Constraint. Surfaced in the rendered Review header. | Persona name, alias       |
| **Reviewer ID**          | Internal opaque identifier for one Reviewer on a Board (e.g. `r1`, `r2`); used to correlate ReviewerTuple -> ReviewerProfile -> Review across the pipeline. Not human-facing; never rendered. | Reviewer index, slot      |
| **Specialty**            | Per-Run reviewer grounding derived from one ACM CCS Class; anchors the reviewer as a domain expert. Not an Axis — drawn fresh each Run. Carried as the full CCS Class dict in-memory across Sampler → Profile Creation → Reviewer; flattened to `path` (string) at the persisted Review JSON boundary. | Background, expertise     |
| **Stance**               | Identity Axis value governing reviewer attitude (e.g. `critical`, `supportive`, `devil's-advocate`).                   | Attitude, tone            |
| **Primary Focus**        | Identity Focus Axis value for a Reviewer; subject to the Diversity Constraint.                                         | Focus (unqualified), main focus |
| **Secondary Focus**      | Supplementary Focus lens on a Reviewer; a depth dimension, allowed to overlap across the Board.                        | Extra focus, side focus   |
| **Core Focus**           | A Focus value the Sampler guarantees appears as some Reviewer's Primary Focus when N ≥ \|Core Focuses\|. Default set: `methods, results, novelty`. | Required focus            |
| **Axis**                 | A named identity vocabulary on a Persona. Two Axes exist: Stance and Primary Focus. Secondary Focus is a depth lens, not an identity Axis; Specialty is not an Axis. | Dimension (reserved for Rubric) |
| **Board**                | The set of N Reviewer Agents configured for a single Run.                                                              | Panel, committee          |
| **Diversity Constraint** | Rule that `(Stance, Primary Focus)` is unique across all Personas on a Board. Secondary Focus is allowed to overlap.   | Uniqueness rule           |

## Classification (ACM CCS)

| Term                     | Definition                                                                           | Aliases to avoid          |
| ------------------------ | ------------------------------------------------------------------------------------ | ------------------------- |
| **ACM CCS**              | The ACM Computing Classification System taxonomy used to tag Manuscripts.            | Taxonomy, categories      |
| **CCS Class**            | One tagged concept path with `High`/`Medium`/`Low` weight attached to a Manuscript.  | Tag, category, label      |
| **Concept Path**         | A slash- or arrow-joined traversal from CCS root to a concept (prefer leaf nodes).   | Node path, category path  |
| **Weight**               | One of `High`/`Medium`/`Low` — ACM-convention relevance marker on a CCS Class.       | Score, priority           |
| **Keyword Extraction**   | First phase of the Classification Agent loop: collect candidate ACM-relevant keywords from the Manuscript's explicit `Keywords:` block, or synthesise them from title / abstract / headings. Keywords drive `lookup_acm` queries; they are logged with the Run but NOT included in `ClassificationResult` and never reach Profile Creation or Reviewer prompts. | Tagging, term mining      |

## Review schema (output)

| Term                  | Definition                                                                                                                       | Aliases to avoid             |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| **Review Schema**     | The Reviewer JSON shape produced by `write_review`: identity fields (`reviewer_id`, `reviewer_name`, `specialty`, `stance`, `primary_focus`, `secondary_focus`, `profile_summary`) plus the three Aspect fields. No numeric ratings. Defined by the 2026-04-27 merged-template design. | Review form, review template |
| **Aspect**            | One of the three free-text Review Schema sections: `strong_aspects`, `weak_aspects`, `recommended_changes`. Each is a single string grounded in the reviewer's Primary Focus, with Secondary Focus colouring the depth implicitly (no separate `focus_commentary` field). | Comments, notes              |
| **Profile Summary**   | Free-text reviewer self-introduction emitted alongside the three Aspects (`profile_summary` in the JSON); rendered as the per-reviewer header blurb (stance + primary/secondary focus). Not in `REVIEW_REQUIRED_FIELDS`; produced by the Reviewer Agent's persona prompt. | Bio, intro                   |
| **Rubric Language**   | The dimension wording from `review-template.txt` (EuCNC/EDAS) and `review-template2.txt` — relevance/timeliness, content/rigour, originality, clarity. Lives only as **prompt-side scaffolding** spliced into Focus Axis `description` fields in `config/axes.yaml`; never emitted in the Review JSON. | EDAS dimensions, template fields |

## Evaluation

| Term          | Definition                                                                                                 | Aliases to avoid     |
| ------------- | ---------------------------------------------------------------------------------------------------------- | -------------------- |
| **Rubric**    | The 5-Dimension Likert (1–5) scoring scheme used by the Judge Agent; Dimensions are equal-weighted and aggregated as an arithmetic mean. | Scorecard, criteria  |
| **Dimension** | One Rubric axis: `specificity`, `actionability`, `persona-fidelity`, `coverage`, `non-redundancy`.         | Metric, criterion    |
| **Evaluation** | The Judge Agent's JSON output for one Final Report — per-Dimension scores + justifications.              | Score, grading       |
| **Baseline**  | A single-shot Claude prompt on the Manuscript, scored by the same Judge for comparison.                    | Control, reference   |

## Infrastructure

| Term         | Definition                                                                                             | Aliases to avoid    |
| ------------ | ------------------------------------------------------------------------------------------------------ | ------------------- |
| **Proxy**    | The OpenRouter-fronted AWS endpoint (`BASE_URL`) speaking OpenAI `/chat/completions`; sole network egress. | API, gateway, LLM endpoint |
| **Orchestrator** | The thin Python module that runs Classification → Profile Creation → parallel Reviewers → Renderer. | Runner, driver, engine |
| **Sampler**  | Deterministic Python component inside Profile Creation that emits N (Reviewer Name, Specialty, Stance, Primary Focus, Secondary Focus) tuples: round-robin Specialty over Weight-sorted CCS Classes, Core Focuses assigned first as Primary Focuses, Secondary Focus by greedy coverage, `(Stance, Primary Focus)` kept unique, Reviewer Name drawn unique-per-Board from `data/finnish_names.json`. | Picker, chooser     |
| **Tool Call** | A structured function invocation by an agent; only `lookup_acm` and `write_review` are defined in v1. | Function call, action |

## Offline preparation

| Term                       | Definition                                                                                                                       | Aliases to avoid       |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| **Offline Prep**           | Scripts run before / outside the runtime pipeline whose outputs are committed under `data/` and `samples/`. Two exist in v1: ACM CCS dump, Finnish names list. | Prep, build step       |
| **Manuscript Ingestion**   | Conversion of a source PDF to a Manuscript (markdown). **Out of this project's scope** — performed outside this repo; the runtime pipeline consumes markdown only. | PDF parsing, conversion |
| **Finnish Nameday Calendar** | The traditional Finnish given-name calendar; source for `data/finnish_names.json`. First names only; committed; refreshed only when the pool needs to grow. | Name list, calendar    |

## Relationships

- A **Run** processes exactly one **Manuscript** and produces exactly one **Final Report**.
- A **Final Report** aggregates N **Reviews**, one per **Reviewer Agent** on the **Board**.
- Each **Reviewer Agent** is driven by exactly one **Persona**; each **Persona** is defined by one **Specialty**, one **Stance**, one **Primary Focus**, and one **Secondary Focus**.
- Each **Persona's Specialty** is drawn from one **CCS Class** emitted by the **Classification Agent** (round-robin over Weight-sorted classes).
- The **Diversity Constraint** enforces unique **(Stance, Primary Focus)** across all **Personas** on a **Board**; **Secondary Focus** may overlap.
- Every **Core Focus** appears as some **Reviewer's Primary Focus** on the **Board** whenever N ≥ |Core Focuses|.
- The **Classification Agent** emits 2–5 **CCS Classes**, each a (**Concept Path**, **Weight**) pair.
- The **Judge Agent** consumes a **Final Report** + its source **Manuscript** + **Reviews** and emits one **Evaluation** scored against the **Rubric**.
- The **Judge Agent** uses a different underlying model than the **Reviewer Agents** (bias mitigation).

## Example dialogue

> **Dev:** "If the **Classification Agent** returns only two **CCS Classes** but the **Board** has N=3, what **Specialty** does the third reviewer get?"

> **Domain expert:** "The **Sampler** round-robins over Weight-sorted classes, so reviewer 3 gets the High-weight class again. Specialties can repeat — the **Diversity Constraint** only forbids duplicate **(Stance, Primary Focus)** pairs."

> **Dev:** "So two reviewers could share the same **Specialty** AND the same **Secondary Focus**?"

> **Domain expert:** "Yes. **Specialty** is not an **Axis**, and **Secondary Focus** is a depth lens, allowed to overlap. Only **Stance** and **Primary Focus** together define reviewer identity."

> **Dev:** "And the **Core Focuses** — `methods, results, novelty` — are they guaranteed?"

> **Domain expert:** "Every **Core Focus** lands as some reviewer's **Primary Focus** as long as N ≥ 3. Past N=3 the extra reviewers draw **Primary Focus** from the full pool."

> **Dev:** "When the **Judge Agent** scores the **Final Report**, what does it emit?"

> **Domain expert:** "One **Evaluation** with a Likert score per **Rubric Dimension**, equally weighted into an arithmetic mean."

## Flagged ambiguities

- **"paper" vs "manuscript"** — used interchangeably in PLAN.md and the design spec. Canonical term is **Manuscript** (what the user submits to a Run); reserve "paper" for external works (e.g. arXiv sample papers for eval).
- **"report" vs "review"** — easily conflated. A **Review** is one reviewer's JSON; the **Final Report** is the compiled markdown. Never say "reports" when meaning per-reviewer outputs.
- **"judge" (verb) vs "Judge Agent"** — "judge" is also a common verb in reviewing contexts. Use **Judge Agent** (capitalized) whenever referring to the evaluator; avoid calling **Reviewer Agents** "judges."
- **"profile" vs "persona"** — the design uses "Profile Creation Agent" but its output is a **Persona**. Canonical: the agent is **Profile Creation Agent**, its product is a **Persona**; avoid "profile" as a standalone noun for the persona object.
- **"class" vs "classification"** — a **CCS Class** is a single tagged concept; **Classification** is the act/output of the Classification Agent (collection of CCS Classes). Don't say "a classification" for a single tag.
- **"dimension" (Rubric) vs "axis" (Persona)** — both are "orthogonal variation" words. Canonical: **Axis** for Persona identity traits (**Stance**, **Primary Focus**); **Dimension** for **Rubric** scores. **Secondary Focus** is a depth lens, not an Axis; **Specialty** is not an Axis either.
- **"focus" (bare)** — ambiguous now that Focus is split. Always qualify as **Primary Focus** or **Secondary Focus** in code, config keys, and docs. Bare "focus" is acceptable only when referring generically to the Focus Axis vocabulary (`config/axes.yaml`).
- **"specialty" vs "CCS Class"** — a **Specialty** is a Persona-level concept derived from one **CCS Class**; a **CCS Class** is a taxonomy entry on the Manuscript. Don't treat them as synonyms. Note also that **Specialty** has two on-the-wire shapes: a full dict in-memory (Sampler → Profile Creation → Reviewer Agent) and a bare `path` string in the persisted Review JSON read by the Renderer / Judge.
- **"board" vs "reviewers"** — "the reviewers" often refers collectively to the Board. Fine informally, but use **Board** when emphasizing the N-as-a-set (e.g. Diversity Constraint applies across the Board).
- **"review form" vs "Review Schema"** — the EuCNC/EDAS form in `review-template.txt` is no longer the canonical output shape. Canonical: **Review Schema** for the JSON the Reviewer emits (three Aspects + identity fields, no ratings); reserve "review form / template" for the historical EDAS source that contributed **Rubric Language** to Focus axis descriptions.
- **"rating" / "rating dimension"** — removed from the system as of 2026-04-27. The Reviewer no longer emits numeric scores; only the **Judge Agent** produces numeric output (per **Rubric Dimension**). If you see "rating" in older docs, treat it as deleted, not deferred.
