# Ubiquitous Language

## Inputs & outputs

| Term             | Definition                                                                        | Aliases to avoid          |
| ---------------- | --------------------------------------------------------------------------------- | ------------------------- |
| **Manuscript**   | The markdown document a researcher submits for feedback; sole content input.      | Paper, research paper, doc |
| **Review**       | One reviewer's structured JSON output: strengths, weaknesses, suggestions, etc.   | Feedback, critique        |
| **Final Report** | The compiled markdown file aggregating all Reviews for a Run.                     | Output, summary, report   |
| **Run**          | One end-to-end execution of the pipeline on a single Manuscript.                  | Job, invocation           |

## Agents

| Term                     | Definition                                                                                 | Aliases to avoid        |
| ------------------------ | ------------------------------------------------------------------------------------------ | ----------------------- |
| **Classification Agent** | LLM agent that tags the Manuscript with ACM CCS Classes via the `lookup_acm` tool.         | Tagger, classifier      |
| **Profile Creation Agent** | Hybrid sampler + LLM agent that produces N Personas for a Run.                           | Persona agent, profiler |
| **Reviewer Agent**       | LLM agent instantiated once per Persona that writes one Review in parallel with siblings.  | Critic, judge (reserved) |
| **Judge Agent**          | LLM agent in the evaluation harness that scores a Final Report against the Rubric.        | Evaluator, grader       |
| **Renderer**             | Pure code (not an agent) that compiles Reviews + Classification into the Final Report.    | Compiler, formatter     |

## Persona & diversity

| Term        | Definition                                                                                      | Aliases to avoid          |
| ----------- | ----------------------------------------------------------------------------------------------- | ------------------------- |
| **Persona** | A concrete reviewer identity (background, voice, rubric) used as a Reviewer Agent system prompt. | Profile, character        |
| **Stance**  | One Axis of reviewer variation (e.g. `critical`, `supportive`, `devil's-advocate`).             | Attitude, tone            |
| **Focus**   | One Axis of reviewer variation denoting subject emphasis (e.g. `methods`, `clarity`, `ethics`). | Topic, area, dimension    |
| **Axis**    | A named vocabulary of Persona traits; currently two Axes exist: Stance and Focus.               | Dimension (reserved for Rubric) |
| **Board**   | The set of N Reviewer Agents configured for a single Run.                                       | Panel, committee          |
| **Diversity Constraint** | Rule that no two Personas on a Board share both Axis values.                        | Uniqueness rule           |

## Classification (ACM CCS)

| Term                     | Definition                                                                           | Aliases to avoid          |
| ------------------------ | ------------------------------------------------------------------------------------ | ------------------------- |
| **ACM CCS**              | The ACM Computing Classification System taxonomy used to tag Manuscripts.            | Taxonomy, categories      |
| **CCS Class**            | One tagged concept path with `High`/`Medium`/`Low` weight attached to a Manuscript.  | Tag, category, label      |
| **Concept Path**         | A slash- or arrow-joined traversal from CCS root to a concept (prefer leaf nodes).   | Node path, category path  |
| **Weight**               | One of `High`/`Medium`/`Low` — ACM-convention relevance marker on a CCS Class.       | Score, priority           |

## Evaluation

| Term          | Definition                                                                                                 | Aliases to avoid     |
| ------------- | ---------------------------------------------------------------------------------------------------------- | -------------------- |
| **Rubric**    | The 5-dimension Likert (1–5) scoring scheme used by the Judge Agent.                                       | Scorecard, criteria  |
| **Dimension** | One Rubric axis: `specificity`, `actionability`, `persona-fidelity`, `coverage`, `non-redundancy`.         | Metric, criterion    |
| **Evaluation** | The Judge Agent's JSON output for one Final Report — per-Dimension scores + justifications.              | Score, grading       |
| **Baseline**  | A single-shot Claude prompt on the Manuscript, scored by the same Judge for comparison.                    | Control, reference   |

## Infrastructure

| Term         | Definition                                                                                             | Aliases to avoid    |
| ------------ | ------------------------------------------------------------------------------------------------------ | ------------------- |
| **Proxy**    | The OpenRouter-fronted AWS endpoint (`BASE_URL`) speaking OpenAI `/chat/completions`; sole network egress. | API, gateway, LLM endpoint |
| **Orchestrator** | The thin Python module that runs Classification → Profile Creation → parallel Reviewers → Renderer. | Runner, driver, engine |
| **Sampler**  | Deterministic Python component inside Profile Creation that picks N distinct (Stance, Focus) pairs.    | Picker, chooser     |
| **Tool Call** | A structured function invocation by an agent; only `lookup_acm` and `write_review` are defined in v1. | Function call, action |

## Relationships

- A **Run** processes exactly one **Manuscript** and produces exactly one **Final Report**.
- A **Final Report** aggregates N **Reviews**, one per **Reviewer Agent** on the **Board**.
- Each **Reviewer Agent** is driven by exactly one **Persona**; each **Persona** is defined by one **Stance** and one **Focus**.
- The **Diversity Constraint** applies across all **Personas** on a single **Board**.
- The **Classification Agent** emits 2–5 **CCS Classes**, each a (**Concept Path**, **Weight**) pair.
- The **Judge Agent** consumes a **Final Report** + its source **Manuscript** + **Reviews** and emits one **Evaluation** scored against the **Rubric**.
- The **Judge Agent** uses a different underlying model than the **Reviewer Agents** (bias mitigation).

## Example dialogue

> **Dev:** "When we bump the **Board** size from 3 to 5, does the **Diversity Constraint** still hold with only 8 **Stances** and 8 **Focuses**?"

> **Domain expert:** "Yes — the **Sampler** guarantees no two **Personas** share both **Axes**. Collisions only start mattering past N = 8 on either Axis."

> **Dev:** "And the **CCS Classes** from the **Classification Agent** — do those flow into each **Persona**, or only into the **Final Report** header?"

> **Domain expert:** "Both. The **Profile Creation Agent** bakes the classes into each **Persona** prompt so **Reviewer Agents** stay on-topic; the **Renderer** also puts them in the report header for the reader."

> **Dev:** "When the **Judge Agent** scores the **Final Report**, does it see the individual **Reviews** or just the rendered markdown?"

> **Domain expert:** "Both — Judge reads the Markdown **Final Report**, the **Manuscript**, and the per-**Reviewer** JSONs, then emits one **Evaluation** with a score per **Rubric Dimension**."

## Flagged ambiguities

- **"paper" vs "manuscript"** — used interchangeably in PLAN.md and the design spec. Canonical term is **Manuscript** (what the user submits to a Run); reserve "paper" for external works (e.g. arXiv sample papers for eval).
- **"report" vs "review"** — easily conflated. A **Review** is one reviewer's JSON; the **Final Report** is the compiled markdown. Never say "reports" when meaning per-reviewer outputs.
- **"judge" (verb) vs "Judge Agent"** — "judge" is also a common verb in reviewing contexts. Use **Judge Agent** (capitalized) whenever referring to the evaluator; avoid calling **Reviewer Agents** "judges."
- **"profile" vs "persona"** — the design uses "Profile Creation Agent" but its output is a **Persona**. Canonical: the agent is **Profile Creation Agent**, its product is a **Persona**; avoid "profile" as a standalone noun for the persona object.
- **"class" vs "classification"** — a **CCS Class** is a single tagged concept; **Classification** is the act/output of the Classification Agent (collection of CCS Classes). Don't say "a classification" for a single tag.
- **"dimension" (Rubric) vs "axis" (Persona)** — both are "orthogonal variation" words. Canonical: **Axis** for Persona traits (Stance, Focus); **Dimension** for Rubric scores. Don't cross-use.
- **"board" vs "reviewers"** — "the reviewers" often refers collectively to the Board. Fine informally, but use **Board** when emphasizing the N-as-a-set (e.g. Diversity Constraint applies across the Board).
