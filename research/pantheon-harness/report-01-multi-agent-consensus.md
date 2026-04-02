# Multi-Agent Deliberation, Debate, and Convergence for Hephaestus Pantheon Mode

Date: 2026-04-02

## 1. Executive summary

Pantheon Mode already has the right high-level instinct: keep a strong generator (`Hephaestus`), add typed critics (`Athena`, `Hermes`, `Apollo`), and protect novelty from collapsing into baseline answers. The weak spot is that the current council still converges mostly at the **whole-answer / whole-round** level. That is where multi-agent systems most often fail: they either fail-close too early, or they converge on a polite but flattened answer.

The frontier result across 2024-2026 is not "more agents" or "more rounds." The reliable gains come from:

- branching before full commitment
- invoking debate only when uncertainty is high
- keeping agents partially independent
- limiting communication bandwidth
- localizing adjudication to disagreement points
- using external verification or evidence checks to discharge objections
- aggregating by evidence quality, not popularity

For Hephaestus specifically, the goal should be **not consensus for its own sake**, but **evidence-backed convergence around a preserved novelty core**.

The best concrete direction for Pantheon is:

1. keep the existing typed roles
2. add an independent first-pass ballot per agent
3. convert objections into a typed issue ledger
4. spawn targeted repair branches instead of a single linear reforge
5. adjudicate at the disagreement-point / claim level
6. only use unanimity for hard truth failures, not for the whole candidate
7. fail loud with unresolved objections instead of fail-closing by default

If implemented well, Pantheon can become a **novelty-preserving audit-and-repair loop** rather than a consensus machine.

## 2. Most relevant research / systems / patterns

### A. Branching and search beat monolithic debate on hard tasks

- **Self-Consistency** established the baseline lesson: sampling diverse reasoning paths and aggregating them is often stronger than trusting one trajectory. For Hephaestus, this supports `BranchGenome`-style branching before translation hardens the answer.  
  Source: Wang et al., 2022, https://arxiv.org/abs/2203.11171

- **Tree of Thoughts**, **Graph of Thoughts**, and **Adaptive Graph of Thoughts** all push the same idea further: inference improves when computation is allocated to branches and subproblems instead of a single linear chain.  
  Sources:  
  Yao et al., 2023, https://arxiv.org/abs/2305.10601  
  Besta et al., 2024, https://arxiv.org/abs/2308.09687  
  Pandey et al., 2025, https://arxiv.org/abs/2502.05078

- **Language Agent Tree Search (LATS)** and **MASTER** show that explicit search with selective expansion and focused communication is a better pattern than letting a fixed council repeatedly rewrite the same answer.  
  Sources:  
  Zhou et al., 2023, https://arxiv.org/abs/2310.04406  
  Gan et al., 2025, https://aclanthology.org/2025.naacl-long.476/

### B. Debate helps only under specific conditions

- **Debating with More Persuasive LLMs Leads to More Truthful Answers** and **On scalable oversight with weak LLMs judging strong LLMs** both show that debate can help when there is meaningful information asymmetry and a weaker judge can be informed by stronger debaters. That matters for Apollo-style adjudication, but it does **not** imply that generic debate improves every reasoning task.  
  Sources:  
  Khan et al., 2024, https://arxiv.org/abs/2402.06782  
  Kenton et al., 2024, https://arxiv.org/abs/2407.04622

- **Revisiting Multi-Agent Debate as Test-Time Scaling** is the strongest recent corrective. MAD gives limited gains over strong single-agent scaling on math, helps more when tasks are harder and models are weaker, and can increase vulnerability on safety tasks. Translation: Pantheon debate should be **conditional**, not default.  
  Source: Yang et al., 2025, https://arxiv.org/abs/2505.22960

- **Debate Only When Necessary (DOWN)** makes the same point operationally: skip debate when the first pass is already high-confidence, because unnecessary debate can propagate error and waste budget.  
  Source: anonymous ACL submission, 2025, https://openreview.net/pdf?id=UW7RqmT9f4

### C. Communication topology matters more than most agent papers admit

- **Improving Multi-Agent Debate with Sparse Communication Topology** shows that all-to-all communication is not required and can be worse on cost and sometimes quality. Sparse connectivity achieved comparable or better performance with lower compute.  
  Source: Li et al., 2024, https://aclanthology.org/2024.findings-emnlp.427/

- **Multi-Agent Debate with Memory Masking** directly targets a failure Pantheon is exposed to: erroneous or low-quality content from prior rounds contaminates later rounds. Their fix is to mask bad memories before the next debate turn.  
  Source: Tian et al., 2026, https://arxiv.org/abs/2603.20215

- **CONSENSAGENT** identifies sycophancy as a central failure mode and improves debates by dynamically refining prompts to reduce it. This is highly relevant to Pantheon because same-family models with role prompts are still prone to agreeing with the apparent group direction.  
  Source: Pitre et al., 2025, https://aclanthology.org/2025.findings-acl.1141/

### D. Aggregation is the real bottleneck

- **Auditing Multi-Agent LLM Reasoning Trees Outperforms Majority Vote and LLM-as-Judge** is one of the most relevant 2026 results. The core point is exactly what Pantheon needs: majority vote throws away evidential structure, and a better approach is to audit the reasoning tree at critical divergence points.  
  Source: Yang et al., 2026, https://arxiv.org/abs/2602.09341

- **Voting or Consensus? Decision-Making in Multi-Agent Debate** is useful because it shows the decision protocol should depend on task type. Consensus did better on knowledge-style tasks; voting did better on reasoning-style tasks because it preserves multiple reasoning paths longer. Pantheon is much closer to the second case.  
  Source: Kaesberg et al., 2025, https://aclanthology.org/2025.findings-acl.606.pdf

- **DecentLLMs** matters less for its blockchain framing and more for its architecture: separate workers generate answers, separate evaluators rank them, and leaderless aggregation avoids "the first acceptable proposal wins." That is a good anti-pattern check for Pantheon’s current winner-take-first-consensus loop.  
  Source: Jo and Park, 2025, https://arxiv.org/abs/2507.14928

### E. Solver-critic loops work when they are verifier-backed

- **CRITIC**, **Reflexion**, **Self-Refine**, and **RARR** all reinforce the same practical lesson: generation improves when critique is specific, revisions are targeted, and external evidence or tools constrain the loop. Pure self-agreement is weak; critique plus evidence is useful.  
  Sources:  
  Gou et al., 2023, https://arxiv.org/abs/2305.11738  
  Shinn et al., 2023, https://arxiv.org/abs/2303.11366  
  Madaan et al., 2023, https://arxiv.org/abs/2303.17651  
  Gao et al., 2022, https://arxiv.org/abs/2210.08726

### F. Useful but risky pattern: Mixture-of-Agents

- **Mixture-of-Agents** shows that layered multi-model synthesis can outperform strong single models on chat/eval benchmarks. But its architecture gives every agent all outputs from the previous layer. For invention systems, that is a direct route to homogenization unless paired with anti-collapse controls.  
  Source: Wang et al., 2024, https://arxiv.org/abs/2406.04692

## 3. Convergence mechanisms that actually work

The following mechanisms consistently show up in the literature and map well onto Hephaestus.

### 3.1 Independent first-pass judgments

Before agents see one another, collect:

- decision
- confidence
- must-preserve novelty claims
- typed objections

Why it works:

- reduces anchoring and conformity
- preserves minority-but-correct signals
- gives you actual disagreement data instead of transcript theater

Hephaestus implication:

- Pantheon should record one hidden Athena/Hermes/Apollo ballot per candidate before any cross-agent exposure

### 3.2 Typed issue ledgers instead of round-level agreement

Strong systems converge by resolving **specific disputes**, not by asking "do we all agree now?"

Issue types Pantheon should use:

- `TRUTH`: causal/mechanistic invalidity
- `STRUCTURAL`: wrong abstraction / wrong decomposition
- `REALITY`: deployment/adoption/operator mismatch
- `NOVELTY`: revision would collapse into baseline

Why it works:

- makes revision targeted
- lets you stop when open issues are low-risk
- avoids repeated global rewrites

Hephaestus implication:

- `PantheonVote` is too coarse as the main coordination object; keep it, but add per-issue state

### 3.3 Sparse and masked communication

Do not pass full transcripts by default. Pass:

- unresolved issues
- supporting evidence
- must-preserve novelty anchors
- disputed claim IDs

Why it works:

- lowers token cost
- reduces social contagion and error propagation
- forces discussion onto load-bearing claims

Hephaestus implication:

- replace raw objection replay in reforge with a masked, typed summary

### 3.4 Localized adjudication at divergence points

When two branches disagree, compare them on the exact disputed mechanism, assumption, or design commitment.

Why it works:

- majority voting loses to correlated wrong answers
- whole-answer judging is noisy
- local comparison is cheaper and more faithful to evidence

Hephaestus implication:

- Pantheon should adjudicate at claim or branch divergence points, not only at final whole-candidate consensus

### 3.5 Adaptive invocation

Only trigger multi-agent deliberation when one of these is true:

- top candidates are close
- Apollo confidence is low or mixed
- Athena/Hermes disagree materially
- verifier proxy is inconclusive
- novelty score is high but feasibility score is unstable

Why it works:

- avoids debate on easy cases
- preserves correct first answers
- saves budget for hard, high-value disagreements

Hephaestus implication:

- Pantheon should have a `skip_council_if_clear` path

### 3.6 External verification to discharge objections

Critique without verification drifts into style and rhetoric. The loop gets strong when objections become testable obligations.

Hephaestus implication:

- Apollo should emit proof obligations that are checked by verifier components or explicit tests, not just narrative objections

### 3.7 Branch-first repair rather than single linear reforge

If three objections exist, do not jam them into one rewrite. Spawn targeted branches:

- branch A resolves structural issue
- branch B resolves reality issue
- branch C resolves truth issue while preserving novelty

Why it works:

- prevents overfitting one revision to incompatible constraints
- keeps novelty alive longer
- fits Hephaestus `BranchGenome` exactly

## 4. Failure modes in multi-agent councils

These are the main ways Pantheon can underperform.

### 4.1 Confabulation consensus

Agents share the same wrong rationale and majority vote merely amplifies it. This is the exact failure AgentAuditor targets.

Pantheon risk:

- same-family models with different role prompts are still highly correlated

### 4.2 Sycophantic convergence

Agents stop criticizing and start harmonizing. Consensus becomes a politeness equilibrium.

Pantheon risk:

- repeated rounds plus visible prior objections can encourage agreement with the perceived group direction

### 4.3 Transcript poisoning / memory contamination

One plausible but wrong objection pollutes later rounds.

Pantheon risk:

- `_hephaestus_reforge()` currently consumes aggregated objections; without masking, bad objections can steer every later revision

### 4.4 Over-globalized revisions

Whole-answer rewrites in response to local objections often destroy the novel mechanism instead of repairing the specific flaw.

Pantheon risk:

- the current reforge loop is linear and global

### 4.5 Unanimity as a novelty destroyer

Unanimity is good for hard truth vetoes, but bad as a general convergence target in invention systems. It pressures the answer toward the least objectionable common denominator.

Pantheon risk:

- `require_unanimity=True` by default

### 4.6 Fail-closed on unresolved but potentially salvageable ideas

If council disagreement produces no output, the system may throw away the highest-upside branch before external verification or additional branching had a chance to rescue it.

Pantheon risk:

- `allow_fail_closed=True` plus global rejection after limited rounds

### 4.7 Cheap agreement over surface plausibility

Agents agree because wording sounds coherent, not because the mechanism is causally load-bearing.

Pantheon risk:

- votes are narrative summaries, not explicit claim/evidence objects

### 4.8 Wrong aggregation primitive

Popularity, last-speaker influence, or confidence theater can dominate actual quality.

Pantheon risk:

- current convergence condition is assent-count logic; it is not evidence-weighted

## 5. Specific recommendations for Hephaestus Pantheon Mode

### 5.1 Do not add more gods yet

The right move is not a larger council. Keep the current four-role architecture and improve the protocol.

Reason:

- current evidence says protocol quality matters more than agent count
- more agents increases correlated noise, cost, and consensus theater

### 5.2 Add an explicit `PantheonIssue` ledger

Extend `src/hephaestus/pantheon/models.py` with something like:

- `issue_id`
- `candidate_id`
- `issue_type`
- `severity`
- `claim_text`
- `evidence`
- `opened_by`
- `status`
- `must_preserve`
- `discharge_test`

Why:

- this gives Pantheon real state across rounds
- enables localized repair and localized adjudication

### 5.3 Change the convergence rule

Current practical target:

- Apollo `TRUTH` issues must be discharged or explicitly downgraded by evidence
- Athena/Hermes objections should become weighted reservations, not automatic global failure
- novelty-preserve constraints remain hard

Recommended new stop condition:

- no open high-severity `TRUTH` issues
- no open high-severity `STRUCTURAL` issues
- remaining `REALITY` issues are below threshold or accepted tradeoffs
- novelty core unchanged by subtraction test
- adjudicator margin over next-best branch exceeds threshold

### 5.4 Use independent first-pass ballots before discussion

In `src/hephaestus/pantheon/coordinator.py`:

- run Athena/Hermes/Apollo review independently
- store ballots without exposing peer outputs
- create issue ledger from ballots
- only then allow restricted cross-agent interaction

This should materially reduce conformity and preserve minority signals.

### 5.5 Replace single linear reforge with targeted repair branches

When multiple issue clusters exist:

- spawn 2-3 repair branches from the same candidate
- assign each branch one dominant issue cluster
- keep a separate "novelty anchor" field that all branches must preserve

This is the strongest repo-specific recommendation because Hephaestus already has `BranchGenome` and perturbation assays. Pantheon should use that instead of acting like a one-path debate engine.

### 5.6 Add memory masking and sparse summaries

Hephaestus should not feed later rounds:

- full prior transcript
- all objections verbatim

It should feed:

- open issue IDs
- top evidence per issue
- must-preserve novelty core
- which claims changed since last round

This is a direct fit with MAD-M2 and sparse-topology results.

### 5.7 Introduce a dedicated adjudication step over surviving branches

After reforge branches:

- compare top branches pairwise at disagreement points
- use a branch auditor to pick the stronger branch per issue
- aggregate by evidence wins, not raw vote counts

Minimal implementation:

- add one new `auditor` harness or reuse Apollo in a different prompt mode
- compare branch A vs branch B on specific issue IDs

### 5.8 Make Pantheon adaptive, not always-on

Only invoke the full council when:

- branch spread is high
- top-2 candidates are close
- verifier proxy is uncertain
- novelty is high enough to justify extra scrutiny

Otherwise:

- accept translation directly
- or run Apollo-only screening

This will likely improve quality and cost simultaneously.

### 5.9 Fail loud, not fail closed

Default behavior should be:

- return top 1-2 branches with unresolved issue ledger
- send them to verification
- let final rejection happen after verification, not after council rhetoric

Use true fail-closed only when:

- all branches retain unresolved high-severity Apollo truth failures

### 5.10 Add the right observability

Track these metrics in `PantheonState`:

- `debate_invoked`
- `debate_skip_reason`
- `independent_disagreement_rate`
- `issue_count_opened`
- `issue_count_discharged`
- `novelty_drift`
- `branches_spawned_for_repair`
- `adjudicator_margin`
- `verifier_overrode_council`
- `consensus_without_verification`

Without these, Pantheon will be hard to tune and easy to overfit.

## 6. Ranked implementation priorities

### 1. Independent ballots + issue ledger

Highest impact per unit effort. This changes Pantheon from transcript-driven deliberation to stateful disagreement management.

### 2. Replace whole-answer unanimity with claim-level convergence

This is the main anti-blandness change. Keep Apollo truth gating strict; relax consensus elsewhere.

### 3. Adaptive invocation of debate

Debate should be conditional. This will cut cost and prevent unnecessary degradation on easy cases.

### 4. Targeted multi-branch repair using `BranchGenome`

This is the biggest quality upside for invention tasks. It prevents "one reforge to satisfy everyone" collapse.

### 5. Sparse communication + memory masking

Cheap to implement, directly addresses contamination and sycophancy.

### 6. Pairwise branch adjudication / reasoning-tree auditor

Important once multiple repair branches exist. This is how Pantheon graduates beyond majority-vote heuristics.

### 7. Heterogeneous model routing for council roles

Apollo especially should differ from the main forge model when possible. Same-family critics produce correlated blind spots.

### 8. Benchmark harness focused on convergence quality

Measure:

- verifier pass rate after council
- novelty retention after repair
- rate of no-output under fail-closed
- number of times verifier rescues branches council would reject
- number of times council consensus is later invalidated

## 7. Sources / links

- Hephaestus Pantheon implementation  
  `src/hephaestus/pantheon/coordinator.py`  
  `src/hephaestus/pantheon/models.py`  
  `src/hephaestus/pantheon/prompts.py`  
  `src/hephaestus/core/genesis.py`  
  `src/hephaestus/branchgenome/assay.py`

- Wang et al., 2022. Self-Consistency Improves Chain of Thought Reasoning in Language Models.  
  https://arxiv.org/abs/2203.11171

- Yao et al., 2023. Tree of Thoughts: Deliberate Problem Solving with Large Language Models.  
  https://arxiv.org/abs/2305.10601

- Besta et al., 2024. Graph of Thoughts: Solving Elaborate Problems with Large Language Models.  
  https://arxiv.org/abs/2308.09687

- Pandey et al., 2025. Adaptive Graph of Thoughts: Test-Time Adaptive Reasoning Unifying Chain, Tree, and Graph Structures.  
  https://arxiv.org/abs/2502.05078

- Zhou et al., 2023. Language Agent Tree Search Unifies Reasoning Acting and Planning in Language Models.  
  https://arxiv.org/abs/2310.04406

- Gan et al., 2025. MASTER: A Multi-Agent System with LLM Specialized MCTS.  
  https://aclanthology.org/2025.naacl-long.476/

- Khan et al., 2024. Debating with More Persuasive LLMs Leads to More Truthful Answers.  
  https://arxiv.org/abs/2402.06782

- Kenton et al., 2024. On scalable oversight with weak LLMs judging strong LLMs.  
  https://arxiv.org/abs/2407.04622

- Li et al., 2024. Improving Multi-Agent Debate with Sparse Communication Topology.  
  https://aclanthology.org/2024.findings-emnlp.427/

- Yang et al., 2025. Revisiting Multi-Agent Debate as Test-Time Scaling: A Systematic Study of Conditional Effectiveness.  
  https://arxiv.org/abs/2505.22960

- Pitre et al., 2025. CONSENSAGENT: Towards Efficient and Effective Consensus in Multi-Agent LLM Interactions Through Sycophancy Mitigation.  
  https://aclanthology.org/2025.findings-acl.1141/

- Kaesberg et al., 2025. Voting or Consensus? Decision-Making in Multi-Agent Debate.  
  https://aclanthology.org/2025.findings-acl.606.pdf

- Jo and Park, 2025. Byzantine-Robust Decentralized Coordination of LLM Agents.  
  https://arxiv.org/abs/2507.14928

- Tian et al., 2026. Multi-Agent Debate with Memory Masking.  
  https://arxiv.org/abs/2603.20215

- Yang et al., 2026. Auditing Multi-Agent LLM Reasoning Trees Outperforms Majority Vote and LLM-as-Judge.  
  https://arxiv.org/abs/2602.09341

- Gou et al., 2023. CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing.  
  https://arxiv.org/abs/2305.11738

- Shinn et al., 2023. Reflexion: Language Agents with Verbal Reinforcement Learning.  
  https://arxiv.org/abs/2303.11366

- Madaan et al., 2023. Self-Refine: Iterative Refinement with Self-Feedback.  
  https://arxiv.org/abs/2303.17651

- Gao et al., 2022. RARR: Researching and Revising What Language Models Say, Using Language Models.  
  https://arxiv.org/abs/2210.08726

- Wang et al., 2024. Mixture-of-Agents Enhances Large Language Model Capabilities.  
  https://arxiv.org/abs/2406.04692
