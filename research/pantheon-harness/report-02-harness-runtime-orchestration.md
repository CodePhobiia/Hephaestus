# Harness / Runtime / Orchestration Research for Hephaestus

## 1. Executive Summary

The strongest 2024-2026 pattern is not "find a better prompt." It is "treat reasoning as a runtime problem": explicit state, branch search, external verification, adaptive compute allocation, and evidence-backed finalization. The best systems now combine:

- search over candidate solutions or action trajectories rather than a single linear answer path,
- specialized judges or verifiers that can reject, rank, or formally validate outputs,
- durable intermediate state for evidence, objections, and branch lineage,
- adaptive routing so expensive reasoning is only used when uncertainty, disagreement, or value justifies it,
- final outputs that are explicitly tied to sources, tests, or formal checks.

For Hephaestus specifically, the most relevant external templates are:

- **AlphaProof / AlphaGeometry 2** for verifiable search in grounded environments,
- **AlphaEvolve** for generate-evaluate-retain evolutionary loops,
- **Google AI co-scientist** for supervisor-plus-specialists with debate, tournaments, and compute scaling,
- **OpenAI deep research** and **STORM / Co-STORM** for research-outline-write pipelines with evidence tracking,
- **ReWOO** for planning/execution separation,
- **LATS** and **Tree Search for Language Model Agents** for test-time search,
- **FrugalGPT / RouteLLM / PILOT** for cost-aware model routing.

Hephaestus already has several of the right pieces:

- `DeepForgeHarness` tracks attempts, pressure, pruning, and cost.
- `PantheonCoordinator` already embodies a specialized council.
- `NoveltyVerifier` already separates attack and validation.
- `RejectionLedger` and `AdaptiveExclusionLedger` already encode anti-convergence memory.

The main gap is that these pieces are still too loosely coupled. Hephaestus needs a **single typed deliberation state** that owns:

- candidate branches,
- objection ledger,
- evidence graph,
- verifier results,
- routing/budget decisions,
- promotion and kill decisions.

The most important design move is to make objections and evidence first-class runtime objects. Inference from the external systems: the missing primitive is not another critique prompt, but a durable ledger of what was challenged, what survived, what changed, and what evidence justified the resolution.

## 2. Most Relevant Runtime / Harness Architectures

| Architecture | Canonical systems | Core runtime idea | Why it matters for Hephaestus |
| --- | --- | --- | --- |
| Verifiable search | [AlphaProof](https://www.nature.com/articles/s41586-025-09833-y), [AlphaGeometry 2](https://jmlr.org/papers/v26/25-1654.html) | Search happens inside a grounded environment with an external verifier or symbolic engine. Hard cases get more inference-time search. | Best template for structural-validity checks, proof obligations, and any part of "novelty proof" that can be formalized. |
| Evolutionary candidate runtime | [AlphaEvolve](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/) | Prompt sampler generates candidates, evaluators score them, survivors enter a database, future prompts are conditioned on the best survivors. | Strong fit for invention search where Hephaestus can mutate architectures and preserve high-value substructures. |
| Supervisor + specialists + tournaments | [AI co-scientist](https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/) | A supervisor decomposes the goal, assigns specialized agents, and uses debate, ranking tournaments, and evolution to improve hypotheses as compute increases. | Directly applicable to Pantheon: Athena, Hermes, Apollo, and Hephaestus should become a tournament-driven council instead of a mostly linear council. |
| Research -> outline -> synthesis | [OpenAI deep research](https://openai.com/index/introducing-deep-research/), [STORM](https://storm-project.stanford.edu/research/storm/), [Co-STORM](https://aclanthology.org/2024.emnlp-main.554/) | First gather and structure evidence, then synthesize. Preserve citations and discourse trace instead of collapsing everything into one generation. | Best pattern for prior-art review, evidence-backed invention reports, and "unknown unknown" discovery. |
| Planner / executor split | [ReWOO](https://arxiv.org/abs/2305.18323) | Reason once, compile a plan with variable bindings, then execute tools without repeatedly re-running the whole reasoning context. | Reduces token burn and context drift in tool-heavy prior-art, repo, and web-search stages. |
| Tree search at inference time | [LATS](https://proceedings.mlr.press/v235/zhou24r.html), [Tree Search for Language Model Agents](https://arxiv.org/abs/2407.01476) | Search over action/state trajectories with value estimates, reflection, and environment feedback. | Strongest runtime pattern for difficult open-ended reasoning when a single linear retry loop is too weak. |
| Sampling + filtering + clustering + reranking | [AlphaCode 2](https://deepmind.google/AlphaCode2_Tech_Report.pdf), [OpenAI o1](https://openai.com/index/learning-to-reason-with-llms/) | Generate many candidates, reject invalid ones, cluster near-duplicates, and rerank before spending scarce final attempts. | Hephaestus should do this for invention candidates to avoid spending top-model tokens on variants of the same idea. |
| Cost-aware routing / cascades | [FrugalGPT](https://arxiv.org/abs/2305.05176), [RouteLLM](https://arxiv.org/abs/2406.18665), [Adaptive LLM Routing under Budget Constraints (PILOT)](https://aclanthology.org/2025.findings-emnlp.1301/) | Route each query or stage to a model based on hardness, quality targets, and budget. Update routing policy online. | Necessary if Pantheon-style multi-agent reasoning is to be used routinely rather than only as a luxury mode. |

## 3. Patterns for Quality Under Hard Reasoning Tasks

### 3.1 Broad First, Then Deep

The best systems do not start by spending maximum compute on one answer. They start with broad exploration and only deepen on survivors.

- AlphaEvolve uses a broad generator/evaluator/database loop rather than a single shot.
- AlphaCode 2 uses massive sampling, filtering, clustering, and scoring before final submission.
- AI co-scientist improves as it spends more time in compute and uses tournaments to rank alternatives.
- OpenAI o1 improves materially from test-time compute, majority vote, and learned reranking.

**Recommendation for Hephaestus:** use cheap broad generation for candidate mechanisms, then expensive deep verification only on a small frontier.

### 3.2 Separate Search, Judgment, and Synthesis

Search quality collapses when the same context window must both discover and defend an answer. STORM, Co-STORM, and deep research all separate gathering/structuring from final writing. ReWOO separates planning from execution. AlphaProof separates proof search from formal checking.

**Recommendation for Hephaestus:** maintain at least three distinct phases:

1. discovery,
2. adversarial evaluation,
3. final synthesis.

Do not allow the final report writer to introduce claims that never passed through discovery and objection stages.

### 3.3 Use External Feedback Wherever Possible

CRITIC shows that self-correction becomes more reliable when the model interacts with tools instead of only reflecting in text. AlphaProof and AlphaGeometry 2 go further: the environment itself verifies correctness. OpenAI deep research trains on browsing tasks with backtracking, file handling, and Python-based analysis.

**Recommendation for Hephaestus:** prefer objective or semi-objective feedback over purely linguistic critique:

- retrieval-backed prior-art contradiction checks,
- baseline-overlap scoring,
- constraint validators,
- code/simulation checks when architectures can be instantiated,
- formalized mapping validators for structural claims.

### 3.4 Preserve Diversity Explicitly

Hard reasoning systems plateau when they repeatedly sample nearby variants. AlphaCode 2 addresses this with clustering of semantically similar candidates. Hephaestus already has convergence pruning and rejection ledgers; the next step is to make diversity preservation branch-aware.

**Recommendation for Hephaestus:** attach structural fingerprints to every candidate and cluster before escalation. Expensive judges should compare cluster representatives, not raw samples.

### 3.5 Make Test-Time Compute Adaptive

OpenAI o1, AlphaProof, Tree Search for LM Agents, and AI co-scientist all show the same principle: more inference-time compute can improve quality, but only if allocated intelligently. ReWOO and routing papers show the complementary principle: not every request deserves that compute.

**Recommendation for Hephaestus:** define escalation triggers such as:

- severe disagreement between Athena/Hermes/Apollo,
- low evidence density for a high-impact claim,
- high novelty claim with weak feasibility support,
- repeated objection recurrence across revisions,
- candidate frontier too homogeneous.

### 3.6 Track Evidence and Unknown Unknowns

STORM and Co-STORM are especially relevant because invention work often fails from premature narrowing, not just hallucination. Their key contribution is to maintain perspective diversity and discourse structure before final writing. Deep research similarly emphasizes clear citations and step tracking.

**Recommendation for Hephaestus:** add an evidence graph plus a topic/mind-map layer for adjacent concepts, neighboring mechanisms, and competing baselines discovered during search.

## 4. Objection / Verification / State-Tracking Mechanisms

This section is partly an inference from the above systems and partly a direct application to Hephaestus.

### 4.1 Objection Ledger

`PantheonVote.must_change`, `PantheonVote.must_preserve`, and `ApolloAudit` already point toward the right abstraction. They should become a persistent append-only ledger.

Suggested object shape:

```yaml
objection_id: O-...
candidate_id: C-...
source_agent: apollo|athena|hermes|verifier|human
type: structural|prior_art|feasibility|evidence_gap|baseline_overlap|operator_risk
severity: critical|major|minor
claim_refs: [CL-...]
evidence_refs: [EV-...]
must_change: ["..."]
must_preserve: ["..."]
disproof_test: "What observation or check would invalidate the candidate?"
status: open|resolved|waived|superseded
resolution_refs: [FX-...]
introduced_round: 2
```

Operational rules:

- No final answer if any `critical` objection is still `open`.
- A revision must explicitly state which objections it resolved and which it intentionally left unresolved.
- Recurrent objections should increase branch penalty and feed the rejection ledger.

### 4.2 Evidence Ledger

Anthropic's citations primitives, OpenAI deep research's citation discipline, and STORM's grounded writing all point to the same requirement: evidence should not be implicit prompt residue.

Suggested object shape:

```yaml
evidence_id: EV-...
kind: web|paper|repo|tool_run|simulation|formal_check|human_note
source_url: https://...
locator: page/span/line/query/hash
captured_at: 2026-04-02T...
claim_summary: "..."
raw_excerpt_hash: "..."
trust_tier: primary|secondary|internal
freshness: stable|volatile
used_by_claims: [CL-...]
```

Operational rules:

- Every nontrivial final claim must reference at least one evidence object.
- High-novelty claims should require at least one negative-evidence object too, for example "searched for prior art and did not find X".
- Evidence should be cached separately from model-written summaries.

### 4.3 Claim Graph

The final invention should be reconstructable from:

- claim nodes,
- supporting evidence nodes,
- objection nodes,
- fix/resolution nodes,
- verdict nodes.

This is more useful than a plain transcript because it supports:

- replay,
- audit,
- regression testing,
- partial re-verification after small edits,
- "show me why this survived Apollo" style UX.

### 4.4 Candidate State Card

Each candidate branch should carry a small machine-readable state card:

```yaml
candidate_id: C-...
parent_ids: [C-...]
fingerprint: "..."
source_domain: "..."
novelty_axes: ["..."]
evidence_coverage: 0.68
unresolved_objections: 2
structural_validity: 0.74
feasibility: 0.61
baseline_overlap: 0.22
compute_spent_usd: 0.47
route_history: [cheap_gen, medium_verify, expensive_council]
status: alive|promoted|killed|finalist
```

This connects cleanly to Hephaestus's existing `ForgeTrace`, `PantheonAccounting`, `RejectionLedger`, and exclusion ledger logic.

### 4.5 Verifier Stack

Hephaestus should move from "critic model plus search" to a layered verifier stack:

1. deterministic filters,
2. retrieval-backed contradiction/prior-art checks,
3. adversarial language-model critiques,
4. tournament ranking among finalists,
5. optional simulation / code execution / DSL checks.

AlphaProof and AlphaGeometry 2 suggest a general lesson: formalize any subproblem you can. Even partial formalization drastically improves trust.

## 5. Tradeoffs: Quality vs Latency / Cost

| Pattern | Quality upside | Latency / cost effect | Notes |
| --- | --- | --- | --- |
| Planner/executor split | Moderate to high on tool-heavy tasks | Often reduces cost materially | ReWOO reports **5x token efficiency** and accuracy gains on HotpotQA. This is low-risk and practical for Hephaestus search stages. |
| Research -> outline -> write | High for breadth, grounding, and fewer red herrings | Adds retrieval time and extra model calls | Deep research operates on a **minutes-scale** runtime; STORM shows pre-writing quality correlates with final report quality. |
| Parallel critics / council | High robustness and better failure discovery | Expensive | Anthropic's 2026 guide says multi-agent systems can use roughly **10-15x** more tokens than single agents. Use selectively. |
| Sampling + clustering + reranking | High on hard search spaces | Compute-heavy but controllable | Strong fit for Hephaestus because cheap models can do most of the sampling work. |
| Tree search / evolutionary loops | Highest upside on the hardest tasks | Can expand dramatically with budget | Worth it only when there is a strong scoring signal or verifier. |
| Formal / deterministic validators | Very high reliability where applicable | High upfront engineering, low marginal runtime | Best used on recurring subproblems: mapping validity, baseline overlap, lineage consistency, protocol feasibility. |
| Routing / cascades | Can improve both cost and quality | Requires calibration and monitoring | FrugalGPT reports up to **98% cost reduction**; RouteLLM and PILOT provide more principled routing policies. |

The main implication is that Hephaestus should not have a single "depth" knob. It should have a **budget policy** that decides when to spend on:

- more branches,
- better retrieval,
- stronger judges,
- longer debate,
- deeper formal or simulation checks.

## 6. Specific Recommendations for Hephaestus Runtime Evolution

### 6.1 Introduce a Typed Deliberation Graph

Add a first-class runtime object, likely near `session/` and `pantheon/`, that owns:

- goal,
- plan,
- candidate frontier,
- evidence ledger,
- objection ledger,
- routing history,
- cost/accounting,
- stop conditions.

This should become the substrate across `deepforge`, `pantheon`, `verifier`, and report generation.

### 6.2 Turn Pantheon into a Tournament Council

Current Pantheon already has the right roles. What it lacks is tournament structure.

Recommended change:

- Athena/Hermes/Apollo evaluate multiple candidates in parallel.
- Surviving candidates enter pairwise or bracketed comparisons.
- Use Elo or Bradley-Terry style scores for promotion.
- Mutate finalists with explicit `must_change` and `must_preserve` constraints.

This mirrors AI co-scientist more closely and is better suited to invention ranking than linear council rounds.

### 6.3 Make Objections Durable Across Rounds and Sessions

Extend the current vote/audit structures into a persistent objection ledger. This should integrate with:

- `PantheonVote`,
- `ApolloAudit`,
- `NoveltyVerifier`,
- `RejectionLedger`.

A candidate that "fixes" one flaw by collapsing into a baseline should be catchable because the ledger preserves both the old objection and the preservation constraints.

### 6.4 Add Evidence Graphs and Citation Enforcement

Final invention reports should not merely include prose prior-art summaries. They should include machine-readable evidence references. Borrow the discipline from deep research, STORM, and Anthropic citations:

- claims map to evidence IDs,
- evidence IDs map to URL/page/span/query,
- final formatter emits a human-readable report plus a structured annex.

This is especially important if Hephaestus wants users to trust novelty claims.

### 6.5 Replace Linear Retry with Frontier Search

`DeepForgeHarness.forge()` is already a useful anti-convergence loop, but the next evolution is a frontier:

- generate many structurally distinct candidate branches cheaply,
- dedupe and cluster by fingerprint,
- run fast veto filters,
- spend expensive compute only on the frontier.

AlphaCode 2, LATS, Tree Search for LM Agents, and AlphaEvolve all support this move.

### 6.6 Add a Budget Policy and Router

Introduce a small policy component that decides:

- which model family to use,
- whether to branch further,
- whether to escalate to Pantheon,
- whether to run expensive prior-art verification,
- whether to stop.

Start with heuristics. Later, learn from historical runs using success/failure outcomes and user acceptance signals. RouteLLM and PILOT are the best direct references here.

### 6.7 Use ReWOO-Style Planning for Tool-Heavy Stages

For prior-art search, repo grounding, competitor scanning, or evidence gathering:

- plan once,
- compile tool calls with variable placeholders,
- execute tools,
- synthesize from structured tool outputs.

This is a cleaner fit than full ReAct loops when the work is mostly retrieval and analysis.

### 6.8 Formalize the Most Repeated Verifier Subproblems

Inference from AlphaProof / AlphaGeometry 2: reliability jumps when the hard part is embedded in a grounded environment.

For Hephaestus, promising candidates for formalization are:

- required constraints satisfied / violated,
- structural mapping edge completeness,
- baseline mechanism overlap,
- lineage consistency,
- proof-token and fingerprint validity,
- report claim coverage by evidence.

This does not require a full theorem prover. A small DSL plus deterministic validators would already be a substantial improvement.

### 6.9 Train or Distill Specialized Critics Later

Recent work on critique training such as CTRL suggests a later-phase optimization: use a dedicated critic or reward model, not only a generic frontier model, for objection generation and revision scoring.

This is a second-order improvement. It is worth doing only after the objection/evidence substrate exists.

## 7. Ranked Implementation Priorities

1. **Typed deliberation state across runtime components.** Highest leverage because it lets every later feature share the same objects instead of passing prompt text around.
2. **Persistent objection ledger with severity gates.** This is the clearest path to better reliability and better objection handling.
3. **Evidence graph plus claim-to-source enforcement.** Necessary if Hephaestus wants trusted novelty and prior-art claims.
4. **Broad-cheap / narrow-expensive frontier search with clustering.** Best quality gain per dollar for hard invention tasks.
5. **Pantheon tournament ranking and mutation loop.** Strong upgrade over linear council rounds for open-ended idea quality.
6. **Adaptive routing and budget policy.** Required to keep the above affordable in production.
7. **ReWOO-style planning/execution split for retrieval-heavy stages.** Practical efficiency improvement with limited architectural risk.
8. **Deterministic validators / mini-DSL for recurring checks.** High trust payoff, but only after state and evidence are structured.
9. **Replay, observability, and branch analytics.** Important for evaluation, but easier once the main state objects exist.
10. **Specialized learned critics or reward models.** Valuable later, but not the first bottleneck.

## 8. Sources / Links

- Anthropic, *Building Effective AI Agents: Architecture Patterns and Implementation Frameworks*: https://resources.anthropic.com/hubfs/Building%20Effective%20AI%20Agents-%20Architecture%20Patterns%20and%20Implementation%20Frameworks.pdf?hsLang=en
- Anthropic Docs, *Citations*: https://docs.anthropic.com/en/docs/build-with-claude/citations
- Anthropic Docs, *Search results*: https://docs.anthropic.com/en/docs/build-with-claude/search-results
- OpenAI, *Learning to reason with LLMs* (2024): https://openai.com/index/learning-to-reason-with-llms/
- OpenAI, *Introducing deep research*: https://openai.com/index/introducing-deep-research/
- OpenAI, *Deep research system card*: https://cdn.openai.com/deep-research-system-card.pdf
- OpenAI, *ChatGPT Agent System Card* (July 17, 2025): https://cdn.openai.com/pdf/6bcccca6-3b64-43cb-a66e-4647073142d7/chatgpt_agent_system_card_launch.pdf
- Google DeepMind, *AlphaEvolve: A Gemini-powered coding agent for designing advanced algorithms* (May 14, 2025): https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/
- Nature, *Olympiad-level formal mathematical reasoning with reinforcement learning* (AlphaProof, published November 12, 2025): https://www.nature.com/articles/s41586-025-09833-y
- JMLR, *Gold-medalist Performance in Solving Olympiad Geometry with AlphaGeometry2* (2025): https://jmlr.org/papers/v26/25-1654.html
- Google DeepMind, *AlphaCode 2 Technical Report* (2023): https://deepmind.google/AlphaCode2_Tech_Report.pdf
- Google Research, *Accelerating scientific breakthroughs with an AI co-scientist* (February 19, 2025): https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/
- Stanford STORM project, *Assisting in Writing Wikipedia-like Articles From Scratch with Large Language Models* (NAACL 2024): https://storm-project.stanford.edu/research/storm/
- Jiang et al., *Co-STORM* (EMNLP 2024): https://aclanthology.org/2024.emnlp-main.554/
- Xu et al., *ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language Models* (2023): https://arxiv.org/abs/2305.18323
- Zhou et al., *Language Agent Tree Search Unifies Reasoning, Acting, and Planning in Language Models* (ICML 2024): https://proceedings.mlr.press/v235/zhou24r.html
- Koh et al., *Tree Search for Language Model Agents* (2024): https://arxiv.org/abs/2407.01476
- Gou et al., *CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing* (ICLR 2024): https://arxiv.org/abs/2305.11738
- Shinn et al., *Reflexion: Language Agents with Verbal Reinforcement Learning* (NeurIPS 2023): https://arxiv.org/abs/2303.11366
- Xie et al., *Teaching Language Models to Critique via Reinforcement Learning* (2025): https://arxiv.org/abs/2502.03492
- Chen et al., *FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance* (2023): https://arxiv.org/abs/2305.05176
- Ong et al., *RouteLLM: Learning to Route LLMs with Preference Data* (2024): https://arxiv.org/abs/2406.18665
- Panda et al., *Adaptive LLM Routing under Budget Constraints* (EMNLP Findings 2025): https://aclanthology.org/2025.findings-emnlp.1301/
