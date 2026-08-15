# Study: `topoteretes/cognee` — what to port into the markdown brain (no graph DB)

*Written 2026-08-12 by claude-code. Lens (a), chosen by Saurabh: mine cognee for borrowable
mechanisms, keep the markdown Obsidian vault. Grounded in cognee's source
(`cognee/tasks/temporal_awareness`, `tasks/storage/add_data_points.py`,
`modules/truth_subspace`) + the brain's own prior-art verdict [[memory-architecture-research-2026-08]].*

> **Update 2026-08-16 (claude-code, source-level re-read of `cognee-1.5.0.dev2`):** the original
> pass was framed as "adopt or reject?" and so it fixated on the graph-DB substrate and undersold
> cognee. Re-reading the source — `memify_pipelines/`, `modules/session_distillation/distill.py`,
> and the distillation prompts — surfaces cognee's real contribution: a **self-improvement loop**
> (usage/feedback weighting + session distillation) that our markdown brain almost entirely lacks.
> Mechanisms 4–6 below capture it. These are the borrowings that matter most.

## Frame: cognee is the architecture the brain already rejected — on measurement

cognee builds a knowledge graph by **LLM entity/ontology extraction** and stores it in a graph
DB (Neo4j/Kuzu) + vector DB (LanceDB/pgvector); every write needs an LLM API key. That is the
GraphRAG/Graphiti/Zep family the 2026-08-02 research evaluated and rejected for this brain:

- markdown + `[[wikilinks]]` **beat HippoRAG 2 and LightRAG by 2.0–8.1 F1** on multi-hop;
- *"Do NOT build GraphRAG-style entity extraction — our wikilinks do that at 100% precision,
  zero token cost"*;
- Zep/Graphiti scored **highest (63.8%)** but was rejected on **infra weight** (Neo4j/FalkorDB);
- human-readability is a core asset — *"nobody can hand-correct a 384-dim vector."*

So **do not adopt cognee wholesale** — it's a measured regression on a CPU-only, no-dGPU,
84%-full-C: machine. But three of its *mechanisms* map onto gaps the research itself left open,
and each ports to markdown with **zero new infrastructure**. Below, verified against the source.

## Mechanism 1 — deterministic canonical-key dedup  ✅ PORT (addresses "entity fragmentation")

**What cognee does** (`tasks/storage/add_data_points.py`): identity is a *deterministic hash of
the entity's name*, not an embedding. `generate_node_id(name)` → stable id; duplicates are
dropped with `if id in seen_ids: continue` and written via **upsert** (update-if-exists). No
similarity thresholds — reproducible across runs. **Honest limit:** this collapses *exact*
duplicates only. "Postgres" vs "PostgreSQL" hash differently — cognee does **not** semantically
merge synonyms without an extra LLM step or alias table.

**Port to the brain (no graph DB):** the vault *already* has deterministic keys — the
`permalink` slug. Turn "search before writing" from advice into a mechanical rule:
1. Before `write_note`, derive the canonical slug from the fact's subject and **check for a
   slug collision**; on hit, `edit_note` the existing note instead of creating a near-duplicate.
2. For the synonym case cognee can't do cheaply, add an **alias/redirect convention**: a note
   may carry `aliases: [Postgres, PostgreSQL, PG]` in frontmatter so a search for any surface
   form lands on the one canonical note. This is the markdown answer to entity resolution — an
   explicit alias list beats a 384-dim guess and stays hand-editable.

## Mechanism 2 — bi-temporal supersession  ✅ PORT (addresses "temporal collapse")

**What cognee does:** its temporal wrapper (`GraphitiNode`) is thin — the real logic is
**Graphiti's bi-temporal edges**. Each fact carries *event time* (`valid_at` / `invalid_at` —
when it was true in the world) and *system time* (`created_at` / `expired_at` — when the system
learned/unlearned it). When a newer fact contradicts an older one, Graphiti **sets the old
edge's `invalid_at` instead of deleting it** — history is preserved and you can ask "what was
true as of date X." This is precisely the fix for the brain's flagged **"temporal collapse"**
risk (an old fix may have been reverted since).

**Port to the brain (no graph DB):** a lightweight bi-temporal *note convention* — never
overwrite a superseded fact, mark it:
- old note gains frontmatter `superseded-by: "[[new-note]]"` and `valid-until: 2026-08-12`;
- new note gains `supersedes: "[[old-note]]"` and `valid-from: 2026-08-12`.

An agent reading the stale note immediately sees it's expired and where current truth lives —
the wikilink does the traversal. This upgrades the existing *"never delete, mark dormant"* rule
into dated supersession, and it's the **one thing worth taking from the entire Zep/Graphiti
family** the research rejected — because as a convention it costs nothing.

## Mechanism 3 — the "improve/consolidate" pass  ◑ PARTIAL (validates existing skill)

cognee's operations are `remember` / `recall` / `forget` / **`improve`**, and it has
`tasks/memify` + `modules/session_distillation` for periodic refinement. The brain has *ingest*
(write_note) and *recall* (search) but no scheduled **improve**. Good news: the
`consolidate-memory` skill already exists — cognee validates running it on a cadence (merge
duplicates via Mechanism 1, apply supersession via Mechanism 2, prune dead links). Low novelty;
it's a scheduling/discipline change, not new tech.

## Mechanism 4 — usage & feedback weighting  ✅ PORT (our brain has NO memory-strength signal)

**What cognee does** (`memify_pipelines/apply_frequency_weights.py`, `apply_feedback_weights.py`;
algorithms in `tasks/memify/`): every graph node/edge carries two scalars.
- `frequency_weight` — incremented by `1.0` **each time the element is actually used** to answer
  (not merely stored).
- `feedback_weight` — an exponential moving average of explicit helpfulness. A 1–5 rating is
  normalized to 0–1, then `new = prev + α·(rating − prev)`, clipped to [0,1]
  (`stream_update_weight`, default `α=0.1`). Recent feedback moves it; history is not erased.

**Port to the brain (no graph DB):** optional frontmatter on any note —
`uses: <int>`, `helpfulness: <0.0–1.0>` (default 0.5), `last-used: <YYYY-MM-DD>`. An agent that
recalls a note *and* it materially helped bumps `uses` and nudges `helpfulness` up; a note that
proves stale nudges it down. Then recall can prefer high-`helpfulness`/high-`uses` notes, and
`consolidate-memory` treats `uses: 0` + old as a dormancy candidate. This gives the flat vault the
memory-strength gradient it completely lacks today — and it stays a hand-editable number, not a
384-dim vector. (Adopted into `brain-protocol` §5a on 2026-08-16.)

## Mechanism 5 — session distillation: propose → vet-against-existing → write  ✅ PORT (upgrade `checkpoint`)

**What cognee does** (`modules/session_distillation/distill.py` + two prompts): a disciplined
two-stage promotion of a finished session into durable memory.
1. LOAD session Q&A + candidate memories, **filtered by a gate**: only entries with
   `harmful_count == 0 and confidence >= MIN_GATE_CONFIDENCE` are eligible.
2. CURATE — a *curator* LLM proposes standalone "lessons", with a hard **MERGE** rule (combine
   turns/candidates expressing the same learning into ONE lesson; never restate a fact twice) and a
   **DURABLE-ONLY** rule (drop one-off requests, transient state, temp paths, formatting prefs).
3. ACCEPT — for each proposed lesson, **first search prior lessons + the entity glossary**, then a
   *writer* LLM decides `accept` with an explicit reason for rejection:
   `already_known` (a similar lesson exists), `not_durable` (session-local), or `unsupported`
   (the member entries don't back the statement). Only accepted lessons are written.
4. PERSIST — **one document per lesson** (each learning independently addressable); a **template,
   not the LLM, controls the format**; `why_learned` is stored separately from the statement and
   must not restate it. Everything is **fail-open per unit** — one bad batch drops only its own work.

**Port to the brain:** this is our `checkpoint` skill, but sharper. The two prompts
(`session_distillation_curator_system.txt`, `..._writer_system.txt`) are near-directly liftable.
The borrowings: the MERGE rule, the three named reject reasons as a vetting gate, "standalone
context-free statement", one-atomic-note-per-lesson (already our "one fact per file"), and a
separate `why` line (already our **Why:**). We already do the LLM part for free — the agent *is*
the curator/writer. (Adopted into the `checkpoint` skill on 2026-08-16.)

## Mechanism 6 — recall-before-acting as an explicit loop  ◑ PARTIAL (discipline, not tech)

cognee's agent loop (`skill.md`) is Observe → Store → Organize → Build → **Recall before every plan
/tool-use/synthesis** → Capture feedback → Consolidate → Reuse. Our `brain-protocol` §2 already says
"read before you act", but cognee makes recall a step *before each significant action* and pairs it
with *capturing whether the recall helped* (which feeds Mechanism 4). Low novelty, high discipline:
the payoff is that weighting (M4) only works if recall usefulness is actually recorded.

## What NOT to take (explicitly)

- **The graph DB + vector DB + LLM extraction pipeline** — the rejected architecture; wikilinks
  already do it at zero cost.
- **`truth_subspace/`** — conflict resolution via **embedding centroids** (`centroids.py`,
  `align.py`). It's the vector-space consensus approach the research called obsolete for agent
  memory, and it's not hand-inspectable. Skip.
- **Semantic/embedding dedup** — cognee itself avoids it for identity (deterministic hashing);
  so should the brain.

## Recommendation

Six infra-free borrowings, all policy/convention changes to hand-editable markdown — no graph DB,
no vectors, no per-write API key:

1. **(M1)** canonical-slug dedup + an `aliases:` convention.
2. **(M2)** `supersedes`/`superseded-by` + `valid-from`/`valid-until` frontmatter; never overwrite.
3. **(M3)** run `consolidate-memory` on a cadence.
4. **(M4)** `uses`/`helpfulness`/`last-used` weighting — the memory-strength signal the vault lacks.
   **APPLIED 2026-08-16** to `brain-protocol` §5a.
5. **(M5)** the propose → vet-against-existing → write distillation discipline (MERGE rule + the
   three reject reasons). **APPLIED 2026-08-16** to the `checkpoint` skill.
6. **(M6)** recall-before-acting + record whether recall helped (feeds M4).

M4 and M5 are the ones the first pass missed and the ones worth having. Everything else in cognee —
the graph DB, vector DB, LLM entity-extraction, and `truth_subspace/` embedding-centroid conflict
resolution — is the server-and-GPU substrate the brain already priced out and declined; on a
CPU-only, RAM-tight machine the markdown substrate plus these disciplines gets most of the value at
none of the weight. Prime input for **Junior's** brain design — build it self-weighting and
self-distilling from day one rather than retrofitting.
