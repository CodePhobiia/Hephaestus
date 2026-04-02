# Frontier LLM Creativity / Invention Systems for Hephaestus

## 1. Executive summary

The strongest current evidence says the same thing from multiple angles: genuinely inventive LLM systems do **not** come from asking one model to “be creative.” They come from **searching over many candidates**, **preserving diversity on purpose**, and **using external feedback that can kill bad ideas and reward real gains**.

For Hephaestus, the highest-value pattern is:

- generate a **population** of candidate mechanisms or patches
- force them through **external evaluators** or executable tests
- keep a **novelty archive** so the system does not collapse into one attractor
- use **debate/tournament ranking** instead of simple consensus
- treat retrieval as a **branch-expansion operator**, not a one-time literature dump
- score novelty at the **mechanism level**, not at the wording level

The systems with the clearest evidence of real invention are the ones that operate on **code, hypotheses, or research proposals that can be externally checked**:

- [AlphaEvolve](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/AlphaEvolve.pdf) and [FunSearch](https://deepmind.google/discover/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/) use LLM-guided evolutionary search plus automated evaluators and have produced new algorithms and mathematical constructions.
- [Towards an AI co-scientist](https://arxiv.org/abs/2502.18864) and [The AI Scientist-v2](https://arxiv.org/abs/2504.08066) use generate/debate/evolve or agentic tree search to produce and refine hypotheses, with stronger results when test-time compute, ranking, and evolution are added.
- [AB-MCTS](https://arxiv.org/abs/2503.04412) and [AFLOW](https://arxiv.org/abs/2410.10762) show that adaptive branching and workflow search outperform naive repeated sampling.

The systems that mainly improve **surface diversity** rather than load-bearing novelty are usually prompt-only methods, temperature-only methods, or critique loops that are not tied to downstream improvement. [NoveltyBench](https://arxiv.org/abs/2503.19015), [RealCritic](https://arxiv.org/abs/2501.14492), [Diverse, not Short](https://arxiv.org/abs/2505.16245), and [Creative Preference Optimization](https://arxiv.org/abs/2505.14442) are useful here because they show both the progress and the limits.

Inference from the current literature: if Hephaestus wants outputs that are not just rhetorically novel but **structurally new and load-bearing**, it should push harder on:

- verifier-backed branch search
- positive and negative archives
- branch crossover / island models
- branch-specific retrieval expansion
- closed-loop critique scoring
- benchmarked repo-level invention tasks


## 2. Best current approaches to maximize novel invention from LLM systems

### A. Verifier-backed evolutionary search over executable artifacts

This is the highest-confidence approach when the problem can be externally graded.

Why it works:

- The model is not asked to hallucinate invention in one shot.
- It proposes concrete artifacts that can be **run**, **tested**, **benchmarked**, or **proved**.
- Search pressure comes from the evaluator, not from the model’s stylistic preferences.
- Diversity is maintained by keeping a population, not just one “best answer.”

Best evidence:

- [AlphaEvolve](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/AlphaEvolve.pdf) combines LLM-generated code diffs with evaluators, a program database, rich prompt context, and an evolutionary database inspired by MAP-Elites and island models. It reports new algorithms, including a 4x4 complex matrix multiplication procedure using 48 scalar multiplications, the first improvement in that setting since 1969.
- [FunSearch](https://deepmind.google/discover/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/) established the core pattern earlier: LLM proposals plus automatic evaluation plus evolutionary selection can discover new mathematical constructions.
- [AlphaResearch](https://arxiv.org/abs/2511.08522) is a later open-ended algorithm-discovery agent that adds a dual environment of execution-based verification plus simulated peer review, and introduces the open-ended benchmark AlphaResearchComp.

Usefulness for Hephaestus:

- Very high.
- This maps directly onto repo-level invention, where a candidate can be a patch, operator graph, new scheduler, caching policy, search heuristic, or experimental design that is externally graded by tests, benchmarks, or simulations.

Concrete transplant into Hephaestus:

- Convert branch candidates into executable design or patch hypotheses earlier.
- Score them against harnesses such as unit tests, property tests, microbenchmarks, token-cost models, or repo-specific stress scenarios.
- Keep both a **best-performing archive** and a **most-different-yet-viable archive**.

### B. Adaptive branch-and-refine search instead of fixed repeated sampling

Repeated sampling is cheap, but it wastes budget when the system should deepen a promising branch instead of spawning another shallow variant.

Best evidence:

- [AB-MCTS](https://arxiv.org/abs/2503.04412) explicitly compares repeated sampling, standard MCTS, and adaptive branching. Its key result is that dynamically deciding when to go wider or deeper using external feedback improves coding and engineering performance over both baselines.
- [AFLOW](https://arxiv.org/abs/2410.10762) applies MCTS to agent workflow discovery and uses operators such as `Review & Revise`, `Ensemble`, and `Test Programmer`. It reports gains over both manual workflows and prior automated workflow search.
- [The AI Scientist-v2](https://arxiv.org/abs/2504.08066) uses a progressive agentic tree-search methodology managed by an experiment manager agent to iterate through hypotheses, experiments, figures, and paper writing.

Usefulness for Hephaestus:

- Very high.
- Hephaestus already has branch lifecycle machinery in `branchgenome/arena.py` and `branchgenome/strategy.py`; the missing piece is a stronger link between branching decisions and external branch outcomes.

Concrete transplant into Hephaestus:

- Replace some fixed branch quotas with adaptive widening/deepening.
- Deepen branches when they are evaluator-promising but underexplored.
- Widen only when novelty spread falls or branch families begin to collapse into the same attractor.

### C. Generate/debate/evolve systems with ranking and tournaments

The current best multi-agent creativity systems do not rely on consensus. They rely on **structured disagreement**, **ranking**, and **iterative evolution**.

Best evidence:

- [Towards an AI co-scientist](https://arxiv.org/abs/2502.18864) uses generation, reflection, ranking, evolution, proximity, and meta-review agents inside a tournament process. It explicitly frames novelty generation as a self-improving debate/evolution loop and reports wet-lab validation in multiple biomedical settings.
- [Many Heads Are Better Than One](https://aclanthology.org/2025.acl-long.1368/) proposes VIRSCI, a multi-agent scientific idea generation system with collaborator selection, topic discussion, idea generation, novelty assessment, and abstract generation. It reports higher novelty than strong baselines and gives quantitative improvements on alignment with and impact on contemporary research.
- [The AI Scientist-v2](https://arxiv.org/abs/2504.08066) also supports the pattern: iterative branching plus review plus experiment-manager control beats more linear pipelines.

Usefulness for Hephaestus:

- High.
- The value is not “many agents” by itself. The value is having **specialized disagreement roles** and a **selection process** that can preserve minority but high-upside branches.

Concrete transplant into Hephaestus:

- Run branch tournaments with roles such as `inventor`, `skeptic`, `implementer`, `prior-art hunter`, and `kill committee`.
- Rank by pairwise wins on novelty, feasibility, and load-bearing mechanism, not just scalar novelty score.
- Keep “losing but weird” branches if they expand the search frontier.

### D. Co-evolving retrieval with idea generation

Static retrieval tends to reinforce the local neighborhood. The newer idea-generation systems increasingly treat retrieval as part of the search policy.

Best evidence:

- [FlowPIE](https://arxiv.org/abs/2603.29557) argues that static retrieval-then-generation produces homogeneous ideas. It couples literature exploration and idea evolution, using flow-guided MCTS plus a generative reward model to build a diverse initial population and then evolve it with selection, crossover, mutation, and island isolation.
- [ResearchBench](https://arxiv.org/abs/2503.21248) studies LLMs on scientific discovery tasks and finds that inspiration retrieval is one of the stronger subskills, suggesting LLMs can surface non-obvious knowledge associations even when full discovery remains hard.
- [AInstein](https://arxiv.org/abs/2510.05432) shows that solver agents can rediscover and sometimes creatively vary methods, but remain fragile and highly sensitive to framing when working from parametric knowledge alone.

Usefulness for Hephaestus:

- High.
- Hephaestus already thinks in terms of cross-domain transfer. The upgrade is to make domain retrieval **branch-conditional and adaptive**, not a one-shot stage before translation.

Concrete transplant into Hephaestus:

- If a branch stalls, retrieve new distant mechanisms targeted at that branch’s failure mode.
- Retrieve across **structural analogies**, not only keyword similarity.
- Penalize “nearest-neighbor retrieval comfort” so the system does not slide back into adjacent-domain literature search.

### E. Diversity-aware post-training and decoding

These methods matter, but mostly as **supporting infrastructure**, not as the core invention engine.

Best evidence:

- [Creative Preference Optimization](https://arxiv.org/abs/2505.14442) injects multiple creativity dimensions into preference optimization and reports more novel, diverse, and surprising outputs without losing quality.
- [DARLING](https://arxiv.org/abs/2505.19962) explicitly targets the diversity/quality tradeoff with contrastive preference optimization and a learned partition function over semantic diversity.
- [Diverse, not Short](https://arxiv.org/abs/2505.16245) shows that common diversity metrics and reward models often reward short outputs, which quietly distorts “diversity” optimization. It also finds that smaller models can act as diversity teachers for larger ones.
- [String Seed of Thought](https://arxiv.org/abs/2510.21150) is a lightweight prompting trick that injects entropy more faithfully than ordinary sampling and improves diversity on NoveltyBench.

Usefulness for Hephaestus:

- Medium.
- These methods are good for **seed generation**, **off-distribution branch creation**, and eventually model customization, but they are not sufficient by themselves to produce real inventions.

Concrete transplant into Hephaestus:

- Use a smaller or diversity-tuned model to generate seed branches.
- Use frontier models for critique, translation, and evaluation.
- Consider SSoT-style entropy injection only in the branch seeding stage, not in final synthesis.

### F. Workflow-level meta-optimization

If the invention engine itself is a workflow, then the workflow should also be searched.

Best evidence:

- [AFLOW](https://arxiv.org/abs/2410.10762) treats workflow search itself as an MCTS problem.
- [EvoAgentX](https://aclanthology.org/2025.emnlp-demos/) packages workflow evolution over prompts, tool configurations, and topologies.

Usefulness for Hephaestus:

- Medium to high.
- This is probably not the first change to make, but it is a strong second-order improvement once branch evaluators exist.

Concrete transplant into Hephaestus:

- Search over when to decompose, when to retrieve, when to translate, when to critique, and how much budget to allocate to each.


## 3. Which methods actually increase originality vs just stylistic variation

### Methods that actually increase originality

These are the approaches most likely to produce **mechanistically different** outputs rather than prettier language.

- **Evaluator-backed search over code or formal artifacts.**
  Inference from [AlphaEvolve](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/AlphaEvolve.pdf), [FunSearch](https://deepmind.google/discover/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/), and [AlphaResearch](https://arxiv.org/abs/2511.08522): the clearest path to real novelty is searching over artifacts that can be externally scored. This changes the objective from “sound original” to “be different and work.”
- **Population archives with diversity pressure.**
  AlphaEvolve’s MAP-Elites/island-style database and FlowPIE’s island evolution are important because they preserve multiple viable families of solutions rather than overfitting to one winning line.
- **Tournament/debate systems with explicit ranking.**
  [AI co-scientist](https://arxiv.org/abs/2502.18864) and [VIRSCI](https://aclanthology.org/2025.acl-long.1368/) suggest that disagreement plus selection pressure produces more novel hypotheses than single-agent generation.
- **Adaptive retrieval that broadens the search frontier.**
  [FlowPIE](https://arxiv.org/abs/2603.29557) and [ResearchBench](https://arxiv.org/abs/2503.21248) support retrieval as a frontier-expansion tool when it helps the system surface non-obvious inspirations instead of merely grounding near-neighbor answers.
- **Diversity-aware post-training when the objective is semantic and quality-aware.**
  [CrPO](https://arxiv.org/abs/2505.14442), [DARLING](https://arxiv.org/abs/2505.19962), and [Diverse, not Short](https://arxiv.org/abs/2505.16245) show that diversity can be improved in ways that are not purely lexical, but this mostly changes the prior over branch seeds rather than replacing search/evaluation.

### Methods that mostly produce stylistic variation

- **Temperature / top-p alone.**
  This increases entropy, but not direction. It is useful for branch seeding, not for invention.
- **Roleplay or persona prompts without selection pressure.**
  They can improve coverage of perspectives, but by themselves they usually produce alternate phrasings of nearby ideas.
- **Self-critique without external outcome measurement.**
  [RealCritic](https://arxiv.org/abs/2501.14492) is especially important here: in self-critique and iterative critique, classical LLMs can underperform their baseline. Critique quality must be measured by downstream correction quality.
- **Static nearest-neighbor RAG.**
  This often improves factuality and feasibility, but can reduce originality by pulling the system into the neighborhood of known solutions.
- **Lexical diversity metrics.**
  [Diverse, not Short](https://arxiv.org/abs/2505.16245) shows these metrics can silently reward shorter or more scattered outputs rather than richer invention.

### Bottom line

Inference from the literature: originality rises when the system is forced to search over **mechanisms**, not over **wording**. That usually requires one or more of:

- executable evaluation
- population diversity management
- retrieval that changes the search frontier
- ranking/tournament dynamics
- mechanism-level novelty scoring


## 4. Evaluation methods for genuine novelty/load-bearing creativity

Current benchmarks are improving, but none of them alone is enough for Hephaestus. The right evaluation stack is layered.

### A. External performance evaluation

This is the best filter against pseudo-creativity.

- [AlphaEvolve](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/AlphaEvolve.pdf), [FunSearch](https://deepmind.google/discover/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/), and [AlphaResearch](https://arxiv.org/abs/2511.08522) all rely on automatic evaluation.
- For Hephaestus repo-level tasks, this should mean:
  - test pass rate
  - benchmark uplift
  - latency / token / memory improvements
  - robustness on held-out cases
  - implementation cost / blast radius

### B. Novelty against prior art

A candidate can be useful and still not be new.

- Use literature, patent, issue, PR, and code retrieval against branch candidates.
- Compare at the **mechanism level**, not just surface embeddings.
- Existing Hephaestus components such as `convergence/detector.py` and `branchgenome/ledger.py` are a base, but embedding similarity to banal patterns is not enough.

Recommended Hephaestus checks:

- mechanism fingerprint overlap
- architecture-graph overlap
- source-domain overlap
- prior-art retrieval overlap
- baseline-equivalence tests

### C. Load-bearing subtraction tests

This is not yet standard in the literature, but it should be standard in Hephaestus.

Recommended procedure:

1. Implement or simulate the candidate mechanism.
2. Remove the supposedly novel component.
3. Re-run the evaluator.
4. If performance barely changes, the novelty was decorative.

This is the cleanest way to reject “analogy wallpaper.”

### D. Closed-loop critique evaluation

- [RealCritic](https://arxiv.org/abs/2501.14492) is the right model here: critique quality should be judged by the quality of the corrected artifact, not by how intelligent the critique sounds.
- Hephaestus should score critics by whether the revised branch actually improves novelty, feasibility, or benchmark performance.

### E. Expert rubric evaluation

For open-ended invention, some human evaluation is still necessary.

- [FrontierScience](https://cdn.openai.com/pdf/2fcd284c-b468-4c21-8ee0-7a783933efcc/frontierscience-paper.pdf) uses rubric-based grading for research-style tasks.
- [Evaluating LLMs in Scientific Discovery](https://arxiv.org/abs/2512.15567) introduces scenario-grounded tasks and shows there is still large headroom.
- [AInstein](https://arxiv.org/abs/2510.05432) is useful because it distinguishes success, rediscovery, and novelty.

Recommended rubric dimensions for Hephaestus:

- structural novelty
- mechanism clarity
- feasibility
- prior-art distance
- load-bearing contribution
- repo integration quality

### F. Benchmark suites worth using or adapting

- [NoveltyBench](https://arxiv.org/abs/2503.19015): good for raw open-ended novelty/diversity pressure, but not sufficient for invention by itself.
- [ResearchBench](https://arxiv.org/abs/2503.21248): good for scientific discovery scenarios and inspiration retrieval / hypothesis decomposition.
- [EXP-Bench](https://arxiv.org/abs/2505.24785): good for end-to-end experimental execution.
- [PaperBench](https://arxiv.org/abs/2504.01848): good for full-paper replication difficulty; useful as an upper-bound stress test.
- [FrontierScience](https://cdn.openai.com/pdf/2fcd284c-b468-4c21-8ee0-7a783933efcc/frontierscience-paper.pdf): good for expert scientific reasoning, but the OpenAI team explicitly notes it does not directly measure novel hypothesis generation.
- [NewtonBench](https://arxiv.org/abs/2510.07172): good for measuring whether tool use causes premature exploitation.
- [AlphaResearchComp](https://arxiv.org/abs/2511.08522): promising open-ended algorithm-discovery benchmark.


## 5. Failure modes: pseudo-creativity, decorative novelty, convergence collapse

### Pseudo-creativity

Symptoms:

- lots of lexical variety
- little mechanism change
- alternative outputs collapse onto one architecture class

Relevant evidence:

- [NoveltyBench](https://arxiv.org/abs/2503.19015) finds current models still lack humanlike originality and tend to underperform humans on creative generation.
- [Diverse, not Short](https://arxiv.org/abs/2505.16245) shows that many diversity metrics are confounded by response length.

### Decorative novelty

Symptoms:

- foreign-domain analogy layered on top of a standard design
- novelty exists in naming or narrative, not in control law or architecture
- removing the “novel” component does not change performance

Relevant implication:

- This is exactly why Hephaestus needs subtraction tests and executable branch evaluation.

### Convergence collapse

Symptoms:

- different branches drift back toward the same pattern
- retrieval produces progressively more adjacent-domain ideas
- critics repeatedly steer outputs toward “reasonable” defaults

Relevant evidence:

- [NoveltyBench](https://arxiv.org/abs/2503.19015) reports that even large aligned models often produce limited novelty.
- [NewtonBench](https://arxiv.org/abs/2510.07172) shows exploration can collapse when tool assistance pushes capable models into premature exploitation; [Evaluating LLMs in Scientific Discovery](https://arxiv.org/abs/2512.15567) shows discovery performance remains fragile and scenario-dependent even for frontier models.
- [RealCritic](https://arxiv.org/abs/2501.14492) shows that self-critique can regress performance.

### Premature exploitation

Symptoms:

- branch search locks onto the first feasible pattern
- tooling improves local refinement but kills frontier expansion

Relevant evidence:

- [AB-MCTS](https://arxiv.org/abs/2503.04412) exists largely because fixed repeated sampling and standard search do not manage the explore/exploit tradeoff well enough.
- [NewtonBench](https://arxiv.org/abs/2510.07172) reports that code interpreters can reduce top-model performance by shifting them from exploration to exploitation too early.

### Framing brittleness

Symptoms:

- a candidate looks novel only under one prompt decomposition
- slightly different framing makes the system rediscover the standard baseline

Relevant evidence:

- [AInstein](https://arxiv.org/abs/2510.05432) explicitly reports that problem-solving ability remains fragile and highly sensitive to framing.

### Reward hacking of “creativity”

Symptoms:

- bizarre but useless outputs score well on a novelty metric
- shorter or noisier answers inflate diversity scores

Relevant evidence:

- [Diverse, not Short](https://arxiv.org/abs/2505.16245) is the clearest warning.
- [CrPO](https://arxiv.org/abs/2505.14442) and [DARLING](https://arxiv.org/abs/2505.19962) are valuable partly because they try to optimize novelty and quality jointly, not novelty alone.


## 6. Specific recommendations for Hephaestus

### 1. Upgrade BranchGenome from branch heuristic system to quality-diversity search

Hephaestus already has useful primitives:

- branch scoring in `src/hephaestus/branchgenome/strategy.py`
- branch lifecycle control in `src/hephaestus/branchgenome/arena.py`
- rejection memory in `src/hephaestus/branchgenome/ledger.py`
- convergence scoring in `src/hephaestus/convergence/detector.py`

The next step is to make this a true **quality-diversity archive**:

- add **islands** keyed by mechanism family, source-domain family, or branch operator family
- keep **elites per cell**, not just a global best
- support **crossover** between branches that are individually viable but structurally different
- store **positive archive entries**, not just rejected patterns
- exchange elites across islands at a controlled rate

This is the most direct transplant from AlphaEvolve, FunSearch, and FlowPIE.

### 2. Make workspace invention tasks verifier-backed

`src/hephaestus/workspace/inventor.py` currently identifies interesting repo problems and runs the invention pipeline. The highest-value upgrade is to attach **repo-local evaluators** to those inventions.

Recommended loop:

1. identify a repo problem
2. generate 5-20 candidate mechanisms or patches
3. synthesize minimal implementations or scaffolds
4. run tests, microbenchmarks, linters, static checks, or simulations
5. preserve only candidates that are both non-obvious and externally better

This is the single most important change if Hephaestus wants load-bearing repo-level invention instead of elegant concept art.

### 3. Add branch-specific retrieval expansion

Instead of only retrieving distant knowledge once, retrieve **in response to branch state**.

Examples:

- if a branch is novel but infeasible, retrieve mechanism implementations from other fields
- if a branch is feasible but converging, retrieve maximally distant analogues
- if two branches are stuck in adjacent-domain comfort zones, retrieve from deliberately excluded families

This is closer to FlowPIE than to ordinary RAG.

### 4. Add debate/tournament ranking instead of one-pass critique

Suggested agents:

- `inventor`: maximize mechanism novelty
- `implementer`: maximize buildability in the target repo
- `skeptic`: attack hidden assumptions
- `prior_art_hunter`: search for rediscovery risk
- `load_bearing_judge`: run subtraction-test reasoning

Use pairwise or Swiss-style tournaments instead of simple average scoring. This prevents consensus from flattening the frontier too early.

### 5. Evaluate critics by downstream improvement only

Do not trust critiques because they sound precise. Use the RealCritic principle:

- a critique is good only if applying it improves branch outcomes

Track, per critic:

- delta in evaluator score
- delta in novelty score
- delta in prior-art overlap
- delta in implementation success

Then weight critics by historical usefulness.

### 6. Replace single novelty score with a novelty vector

Current embedding-based anti-banality is useful but too narrow.

Recommended novelty vector:

- banality similarity
- prior-art similarity
- branch-family distance
- source-domain distance
- mechanism graph distance
- evaluator gain over baseline
- subtraction-test delta
- critic disagreement magnitude

Hephaestus should not ship a single novelty scalar until these components are visible.

### 7. Use cheap diversity teachers for branch seeding

Inference from [Diverse, not Short](https://arxiv.org/abs/2505.16245): smaller models can sometimes be effective diversity teachers.

Recommended pattern:

- use a cheaper, diversity-biased model for seed generation
- use a stronger reasoning model for ranking, translation, and verification
- keep the seed model away from final synthesis

This is a practical way to expand the frontier without paying frontier-model rates for every branch.

### 8. Meta-optimize the Hephaestus workflow after evaluators exist

Once branch evaluation is real, use AFLOW-style search to optimize:

- how many branches to spawn
- when to retrieve
- when to debate
- when to mutate vs crossover
- how much budget to spend on verification vs exploration

Do this only after verifier-backed invention is working, otherwise the workflow search will optimize proxies.


## 7. Ranked implementation priorities

### Priority 1. Verifier-backed repo invention loop

Why first:

- highest leverage
- converts invention from rhetorical novelty to measured improvement
- aligns directly with the strongest evidence from AlphaEvolve/FunSearch

What to build:

- patch/prototype synthesis
- test and benchmark harnesses
- branch score updates from real outcomes

### Priority 2. Quality-diversity archive with islands and crossover

Why second:

- Hephaestus already has branch infrastructure
- this is the cleanest anti-convergence upgrade
- preserves weird but viable branches instead of collapsing to one winner

What to build:

- elite cells
- positive archive
- crossover operators
- controlled island migration

### Priority 3. Tournament/debate selection layer

Why third:

- improves originality without losing feasibility
- better than simple critique or average ranking

What to build:

- specialized agent roles
- pairwise branch comparisons
- win/loss memory

### Priority 4. Branch-conditional retrieval expansion

Why fourth:

- strong complement to cross-domain invention
- reduces adjacent-domain comfort collapse

What to build:

- failure-conditioned retrieval
- anti-nearest-neighbor retrieval
- source-domain exploration budget

### Priority 5. Closed-loop critique evaluation

Why fifth:

- prevents fake-intelligent criticism
- lets the system learn which critiques actually help

What to build:

- per-critic outcome tracking
- automatic acceptance/rejection of critique edits

### Priority 6. Novelty-vector scoring and subtraction tests

Why sixth:

- upgrades novelty proofs from embedding distance to mechanism-level evidence

What to build:

- mechanism fingerprints
- ablation / subtraction protocol
- explicit rediscovery risk scoring

### Priority 7. Diversity teacher / entropy-seeding experiments

Why seventh:

- cheap and easy to test
- useful, but not core

What to build:

- small-model branch seeding
- SSoT-style entropy prompt at seed stage

### Priority 8. Workflow meta-search

Why eighth:

- probably valuable later
- should not come before good evaluators exist


## 8. Sources / links

- [AlphaEvolve: A coding agent for scientific and algorithmic discovery](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/AlphaEvolve.pdf)
- [FunSearch: making new discoveries in mathematical sciences using large language models](https://deepmind.google/discover/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/)
- [Towards an AI co-scientist](https://arxiv.org/abs/2502.18864)
- [The AI Scientist-v2: Workshop-Level Automated Scientific Discovery via Agentic Tree Search](https://arxiv.org/abs/2504.08066)
- [Many Heads Are Better Than One: Improved Scientific Idea Generation by A LLM-Based Multi-Agent System](https://aclanthology.org/2025.acl-long.1368/)
- [Wider or Deeper? Scaling LLM Inference-Time Compute with Adaptive Branching Tree Search](https://arxiv.org/abs/2503.04412)
- [AFLOW: Automating Agentic Workflow Generation](https://arxiv.org/abs/2410.10762)
- [NoveltyBench: A Benchmark for Evaluating the Creativity of Large Language Models](https://arxiv.org/abs/2503.19015)
- [RealCritic: Towards Effectiveness-Driven Evaluation of Language Model Critiques](https://arxiv.org/abs/2501.14492)
- [Creative Preference Optimization](https://arxiv.org/abs/2505.14442)
- [Diverse, not Short: A Length-Controlled Data Selection Strategy for Improving Response Diversity of Language Models](https://arxiv.org/abs/2505.16245)
- [DARLING: Directly Aligning Language Models with Diversity and Quality of Text Generation](https://arxiv.org/abs/2505.19962)
- [ResearchBench: Benchmarking Large Language Models for Scientific Discovery via Inspiration-Based Task Decomposition](https://arxiv.org/abs/2503.21248)
- [PaperBench: Evaluating AI's Ability to Replicate AI Research](https://arxiv.org/abs/2504.01848)
- [EXP-Bench: Can AI Conduct AI Research Experiments?](https://arxiv.org/abs/2505.24785)
- [FrontierScience: Evaluating AI’s ability to perform scientific research tasks](https://cdn.openai.com/pdf/2fcd284c-b468-4c21-8ee0-7a783933efcc/frontierscience-paper.pdf)
- [Evaluating Large Language Models in Scientific Discovery: Insights from Scenario-Grounded Experiments](https://arxiv.org/abs/2512.15567)
- [AInstein: Assessing the Feasibility of AI-Generated Approaches to Research Problems](https://arxiv.org/abs/2510.05432)
- [AlphaResearch: Accelerating New Algorithm Discovery with Language Models](https://arxiv.org/abs/2511.08522)
- [DeepInnovator: Trainable Agent for Scientific Innovation and Discovery](https://arxiv.org/abs/2601.14286)
- [FlowPIE: Test-Time Scientific Idea Evolution with Flow-Guided Literature Exploration](https://arxiv.org/abs/2603.29557)
- [NewtonBench: Benchmarking Generalizable Scientific Law Discovery in LLM Agents](https://arxiv.org/abs/2510.07172)
