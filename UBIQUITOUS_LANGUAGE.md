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
| **Reviewer Agent**       | LLM agent instantiated once per Persona that emits one Review. Siblings run sequentially in an inline fan-out loop inside `setup_review_board` (no RedundantPattern in AG2 0.12.1). | Critic, judge (reserved) |
| **Judge Agent**          | LLM agent in the evaluation harness that scores a Final Report against the Rubric.        | Evaluator, grader       |
| **Renderer**             | Pure code (not an agent) that consumes a `RunOutput` in-memory and emits the Final Report markdown; joins each Review to its ReviewerProfile by `reviewer_id`. | Compiler, formatter     |

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
| **Review Schema**     | The slim Pydantic `Review` model in `paperfb/schemas.py`: `reviewer_id` plus the three Aspect fields. Validated via AG2 `response_format=Review`. Identity metadata is NOT in `Review` — it lives on `ReviewerProfile` and is joined back in by the Renderer via `reviewer_id`. No numeric ratings. | Review form, review template |
| **Aspect**            | One of the three free-text Review Schema sections: `strong_aspects`, `weak_aspects`, `recommended_changes`. Each is a single string grounded in the reviewer's Primary Focus, with Secondary Focus colouring the depth implicitly (no separate `focus_commentary` field). | Comments, notes              |
| **Profile Summary**   | One-line reviewer blurb (`profile_summary` field on `ReviewerProfile`) emitted by the Profile Creation Agent alongside the persona prompt; rendered as the per-reviewer header (stance + primary/secondary focus). Lives on the Profile, not on the Review. | Bio, intro                   |
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
| **Pipeline** | The thin Python module (`paperfb/pipeline.py`) that builds the AG2 agents + handoffs, runs the GroupChat, and assembles a `RunOutput` from `ContextVariables` for the Renderer. Replaced the older `orchestrator.py`. | Orchestrator, runner, driver |
| **Sampler**  | Deterministic Python component inside Profile Creation that emits N (Reviewer Name, Specialty, Stance, Primary Focus, Secondary Focus) tuples: round-robin Specialty over Weight-sorted CCS Classes, Core Focuses assigned first as Primary Focuses, Secondary Focus by greedy coverage, `(Stance, Primary Focus)` kept unique, Reviewer Name drawn unique-per-Board from `data/finnish_names.json`. | Picker, chooser     |
| **Tool Call** | A structured function invocation by an agent. Two tools exist: `lookup_acm` (Classification) and `sample_board` (Profile Creation). Both are executed by the `UserProxyAgent`. The former `write_review` tool has been replaced by Pydantic structured output on the Reviewer. | Function call, action |

## Cross-agent types

The on-the-wire shapes (Pydantic) carried between agents and into the Renderer / Judge. Defined in `paperfb/schemas.py`.

| Term                     | Definition                                                                                            | Aliases to avoid       |
| ------------------------ | ----------------------------------------------------------------------------------------------------- | ---------------------- |
| **ClassificationResult** | Classification Agent's structured output: `keywords` + 2–5 `CCSClass` entries. Stashed whole into `ContextVariables["classification"]`; only the `classes` paths are forwarded to Profile Creation. | Classification (used loosely), tags |
| **ReviewerTuple**        | Output of the `sample_board` tool: one (id, name, specialty, stance, primary_focus, secondary_focus) row, pre-persona-prompt. | Tuple, sample row     |
| **ReviewerProfile**      | A `ReviewerTuple` extended by Profile Creation with `persona_prompt` (full reviewer system message) and `profile_summary` (header blurb). | Profile, reviewer record |
| **ProfileBoard**         | Profile Creation Agent's structured output: the list of N `ReviewerProfile`s for the Run.             | Board roster, profiles |
| **BoardReport**          | The aggregated Reviewer output: `reviews` (list of slim `Review`s) + `skipped` (list of `SkippedReviewer`). Built deterministically by `setup_review_board`. | Reviews bundle, panel result |
| **SkippedReviewer**      | One entry recording a Reviewer that failed to produce a valid `Review`; `id` + `reason`.              | Failed reviewer, error row |
| **RunOutput**            | Top-level Pydantic container assembled post-chat: `classification + profiles + board`. Both the in-memory handoff to the Renderer and the on-disk artefact at `evaluations/run-<ts>/run.json` consumed by the Judge. | Run JSON, run record |

## AG2 framework

Terms from the [AG2](https://docs.ag2.ai/) agent framework that surface in this project's discourse. Pinned to `ag2==0.12.1`.

| Term                  | Definition                                                                                              | Aliases to avoid    |
| --------------------- | ------------------------------------------------------------------------------------------------------- | ------------------- |
| **GroupChat**         | The AG2 multi-agent conversation primitive that the Pipeline runs. Driven by `initiate_group_chat(...)`. | Conversation, chat  |
| **Default Pattern**   | The AG2 GroupChat pattern this project uses: a linear sequence of agents linked by post-turn handoffs (no built-in routing). | Linear pattern, sequential pattern |
| **UserProxyAgent**    | The AG2 agent that initiates the chat with the manuscript and doubles as the executor for `lookup_acm` and `sample_board`. `human_input_mode="NEVER"`. | User agent, proxy   |
| **ConversableAgent**  | The AG2 base agent class used for Classification, Profile Creation, and each Reviewer.                  | Agent (unqualified) |
| **Handoff**           | A post-turn transition from one agent to the next. Registered via `agent.handoffs.set_after_work(target)`; AG2 0.12.1 has no top-level `AfterWork(...)` decorator. | Edge, transition    |
| **FunctionTarget**    | Handoff target whose body is a Python function `(last_message, ctx) -> FunctionTargetResult`. Used twice: `classify_to_profile` (sub-field extraction into `ContextVariables`) and `setup_review_board` (inline reviewer fan-out + `BoardReport` assembly). | Hook, transformer   |
| **AgentTarget**       | Handoff target naming the next speaking agent (e.g. `AgentTarget(profile_agent)`).                      | Next-agent target   |
| **TerminateTarget**   | Handoff target ending the outer GroupChat. Returned after `setup_review_board` completes.               | End target, stop    |
| **ContextVariables**  | The hidden cross-agent state dict carried through the GroupChat. LLMs do not see it; Pipeline reads it post-chat to build `RunOutput`. Keys in use: `manuscript`, `run_id`, `classification`, `profiles`, `board`, `expected_reviewer_ids`. | Shared state, context |
| **structured output** | Pydantic-typed agent response enforced via `response_format=PydanticModel`. Replaces the v1 `write_review` tool and most JSON-shape prompting. | response_format, JSON output |

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
- The **Pipeline** is one **GroupChat** under the **Default Pattern** with two LLM agents (Classification, Profile Creation) plus the **UserProxyAgent** as initiator and tool executor; Reviewers fan out inline inside `setup_review_board`, not as GroupChat members.
- A **FunctionTarget** transforms each cross-agent message: `classify_to_profile` extracts `classes` paths into the prompt and stashes the full **ClassificationResult** in **ContextVariables**; `setup_review_board` builds Reviewers from a **ProfileBoard**, runs them, and writes the **BoardReport** into **ContextVariables**.
- **RunOutput** = **ClassificationResult** + **ProfileBoard** + **BoardReport**; the **Pipeline** assembles it from **ContextVariables** after the chat ends and passes it to the **Renderer**.

## Example dialogue

> **Dev:** "If the **Classification Agent** returns only two **CCS Classes** but the **Board** has N=3, what **Specialty** does the third reviewer get?"

> **Domain expert:** "The **Sampler** round-robins over Weight-sorted classes, so reviewer 3 gets the High-weight class again. Specialties can repeat — the **Diversity Constraint** only forbids duplicate **(Stance, Primary Focus)** pairs."

> **Dev:** "So two reviewers could share the same **Specialty** AND the same **Secondary Focus**?"

> **Domain expert:** "Yes. **Specialty** is not an **Axis**, and **Secondary Focus** is a depth lens, allowed to overlap. Only **Stance** and **Primary Focus** together define reviewer identity."

> **Dev:** "And the **Core Focuses** — `methods, results, novelty` — are they guaranteed?"

> **Domain expert:** "Every **Core Focus** lands as some reviewer's **Primary Focus** as long as N ≥ 3. Past N=3 the extra reviewers draw **Primary Focus** from the full pool."

> **Dev:** "When the **Judge Agent** scores the **Final Report**, what does it emit?"

> **Domain expert:** "One **Evaluation** with a Likert score per **Rubric Dimension**, equally weighted into an arithmetic mean. The Judge actually reads the **RunOutput** JSON, not the markdown — joining each **Review** to its **ReviewerProfile** by `reviewer_id` for fidelity scoring."

> **Dev:** "And the Reviewers — they really run sequentially? The README still says 'parallel'."

> **Domain expert:** "Sequential. The AG2 0.12.1 wiring fans them out inline inside `setup_review_board`; there's no **RedundantPattern** in this version. It's a **FunctionTarget** that builds the Reviewers from the **ProfileBoard**, calls each one, then writes a **BoardReport** into **ContextVariables** before returning a **TerminateTarget** to end the outer **GroupChat**."

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
- **"orchestrator" vs "Pipeline"** — historical name was *orchestrator* (`paperfb/orchestrator.py`); current name is **Pipeline** (`paperfb/pipeline.py`). The thing also became thinner: most former orchestration logic now lives in **AG2** patterns + **FunctionTarget** handoffs. Use **Pipeline** in new prose.
- **"parallel reviewers" vs sequential fan-out** — older PLAN.md / README phrasing says reviewers run "in parallel". In the AG2 0.12.1 wiring they run sequentially inside an inline loop in `setup_review_board`. Don't say "parallel" — say *fan-out* or *inline reviewer loop*.
- **"RunOutput" vs "Final Report"** — both are run-level outputs but distinct: **RunOutput** is the in-memory + on-disk Pydantic structure (`evaluations/run-<ts>/run.json`) consumed by Renderer and Judge; **Final Report** is the markdown the researcher reads (`final_report.md`). Don't conflate.
- **"agent" (unqualified)** — overloaded across our domain agents (Classification / Profile Creation / Reviewer / Judge), AG2's `ConversableAgent`, and the `UserProxyAgent`. In dialogue, qualify (e.g. **Reviewer Agent**, **UserProxyAgent**) unless context is unambiguous.
- **"tool" surface** — only `lookup_acm` and `sample_board` are tools. `write_review` was a tool in v1; it has been replaced by Pydantic **structured output** on the Reviewer. Don't mention `write_review` in new prose.
