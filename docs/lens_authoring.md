# Lens Authoring Guide

Cognitive lenses are the fuel of Hephaestus. Each lens is a YAML file that captures the structural essence of a knowledge domain — its axioms, patterns, and the injection framing that activates it. Adding a new lens is one of the highest-value contributions you can make to the project.

This guide covers the complete YAML schema, shows a real lens walkthrough, and describes best practices for writing axioms and structural patterns that actually work.

---

## YAML Schema

Every lens lives in `src/hephaestus/lenses/library/` as a `.yaml` file. The filename becomes the `lens_id` (e.g., `biology_immune.yaml` → `biology_immune`).

```yaml
# Full schema with all fields
name: Human-Readable Domain Name          # REQUIRED
domain: category                           # REQUIRED — broad category
subdomain: specific_area                   # OPTIONAL — more specific

axioms:                                    # REQUIRED — list of 4-8 strings
  - "First axiom of this domain."
  - "Second axiom."
  # ...

structural_patterns:                       # REQUIRED — list of 2-6 patterns
  - name: pattern_identifier               # snake_case, no spaces
    abstract: |                            # What this pattern does abstractly
      Multi-line description allowed.
    maps_to:                               # What target concepts this maps to
      - concept_1
      - concept_2

injection_prompt: |                        # REQUIRED — the activation framing
  Multi-line instruction that tells the model to adopt this domain's perspective.
  Should be concrete and spatial ("you are inside X, every Y is Z").

tags:                                      # OPTIONAL — for search/filtering
  - optimization
  - distributed

distance_hint: 0.85                        # OPTIONAL — rough domain distance from
                                           # "technology/computing" (0=identical, 1=maximally distant)
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable name shown in output (e.g., "Immune System") |
| `domain` | string | Broad category (biology, physics, math, military, etc.) |
| `axioms` | list[string] | Core truths of this domain (4–8 axioms) |
| `structural_patterns` | list[object] | Abstract mechanisms with mapping targets |
| `injection_prompt` | string | The activation framing text |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `subdomain` | string | More specific area within the domain |
| `tags` | list[string] | Searchable tags for filtering |
| `distance_hint` | float (0-1) | Rough distance from computing/tech domains |

---

## Real Lens Walkthrough: Mycelium Networks

Here's how the `biology_mycology.yaml` lens was built, with commentary.

**Step 1: Choose a domain with rich structure**

Mycelium networks (fungal root networks) are interesting because they solve resource distribution without any central planner, using a mechanism that's completely unlike anything in distributed systems textbooks.

**Step 2: Extract the domain's core axioms**

Ask yourself: *What does this domain believe about the world that its practitioners would call obvious?* These aren't definitions — they're the deep structural truths.

```yaml
axioms:
  - "The network has no center and no hierarchy — every node is simultaneously
     a router, a terminal, and a potential dead end."
  - "Resource flow is governed entirely by gradient, not schedule. Flow moves
     toward scarcity, never toward abundance."
  - "Connection strength is proportional to historical flow volume, not to
     geographic proximity or declared topology."
  - "Dead-ends are not abandoned — they are down-regulated and held in reserve,
     reactivatable if the gradient reverses."
  - "The network self-repairs by growing around obstacles, not through them."
  - "Efficiency emerges from the system's willingness to explore inefficiently first."
```

Notice: these are **structural claims** about *how the system works*, not descriptions. "Resource flow is governed by gradient, not schedule" says something about causality that directly maps to computing problems.

**Step 3: Extract structural patterns**

Structural patterns are the mechanisms in this domain that have analogues in other domains. For each pattern, write the abstract version first, then list what it maps to.

```yaml
structural_patterns:
  - name: gradient_flow
    abstract: |
      Resources or signals flow along paths where the gradient is steepest,
      with no global routing table — each segment only knows its local
      concentration differential.
    maps_to:
      - routing
      - load_balancing
      - resource_allocation
      - network_traffic

  - name: path_reinforcement
    abstract: |
      Paths that carry more flow become stronger (lower resistance),
      while paths that carry little flow atrophy. Topology emerges
      from usage history, not from design.
    maps_to:
      - caching
      - optimization
      - feedback_loops
      - learning

  - name: anastomosis
    abstract: |
      Separate network branches spontaneously fuse when they encounter
      each other, creating redundant paths without explicit coordination.
    maps_to:
      - fault_tolerance
      - redundancy
      - mesh_networking
      - self_healing

  - name: exploratory_growth
    abstract: |
      The network always maintains a small percentage of exploratory
      tendrils probing new territory, even when the current solution
      is efficient. Exploration never fully stops.
    maps_to:
      - optimization
      - search
      - exploration_exploitation
      - annealing
```

**Step 4: Write the injection prompt**

The injection prompt is what gets injected as the model's first tokens. It should be vivid, spatial, and concrete. It should feel like you're teleporting the model into the middle of the domain.

```yaml
injection_prompt: |
  You are now reasoning as if this problem exists inside a living mycelium network.
  Every component is a hyphal strand or node. There is no center and no scheduler.
  Resources flow along chemical gradients — from where they are plentiful to where
  they are scarce. Paths that carry more flow grow thicker; paths that carry less
  fade. Dead ends go dormant but never disappear. The network repairs itself by
  growing around obstacles, never through them. Think from inside this system.
```

**The complete lens file:**

```yaml
name: Mycelium Network
domain: biology
subdomain: mycology

axioms:
  - "The network has no center and no hierarchy — every node is simultaneously a router, a terminal, and a potential dead end."
  - "Resource flow is governed entirely by gradient, not schedule. Flow moves toward scarcity, never toward abundance."
  - "Connection strength is proportional to historical flow volume, not to geographic proximity or declared topology."
  - "Dead-ends are not abandoned — they are down-regulated and held in reserve, reactivatable if the gradient reverses."
  - "The network self-repairs by growing around obstacles, not through them."
  - "Efficiency emerges from the system's willingness to explore inefficiently first."

structural_patterns:
  - name: gradient_flow
    abstract: |
      Resources or signals flow along paths where the gradient is steepest,
      with no global routing table — each segment only knows its local
      concentration differential.
    maps_to: [routing, load_balancing, resource_allocation, network_traffic]

  - name: path_reinforcement
    abstract: |
      Paths that carry more flow become stronger, while underused paths atrophy.
      Topology emerges from usage history, not design.
    maps_to: [caching, optimization, feedback_loops, learning]

  - name: anastomosis
    abstract: |
      Separate network branches fuse when they encounter each other,
      creating redundant paths without explicit coordination.
    maps_to: [fault_tolerance, redundancy, mesh_networking, self_healing]

  - name: exploratory_growth
    abstract: |
      The network always maintains exploratory tendrils probing new territory,
      even when current solutions are efficient.
    maps_to: [optimization, search, exploration_exploitation, annealing]

injection_prompt: |
  You are now reasoning as if this problem exists inside a living mycelium network.
  Every component is a hyphal strand or node. There is no center and no scheduler.
  Resources flow along chemical gradients — from where they are plentiful to where
  they are scarce. Paths that carry more flow grow thicker; paths that carry less
  fade. Dead ends go dormant but never disappear. The network repairs itself by
  growing around obstacles, not through them. Think from inside this system.

tags: [biology, distributed, self_organizing, optimization, resource_distribution]
distance_hint: 0.89
```

---

## Best Practices

### Writing Axioms

**DO:**
- Make axioms **structural claims** that encode how the domain actually works
- Write in present tense, declarative voice ("Resources flow toward scarcity")
- Include the domain's characteristic *failures* as axioms (e.g., "Over-response is as dangerous as under-response" from the immune system lens)
- Include axioms about *absence* — what the domain lacks that you'd expect ("There is no central planner", "No node has global knowledge")
- Aim for 5–7 axioms. Fewer = weak interference. More = incoherent injection.

**DON'T:**
- Write definitions ("Mycelium is a network of fungal threads")
- Write descriptions of the domain ("Fungi use mycelium to absorb nutrients")
- Write analogies that contain the target domain ("This is like a routing table")
- Include domain-specific jargon without structural unpacking
- Include more than 8 axioms (injection prompt gets too long, model loses the thread)

**Good axiom test:** Can you read this axiom and immediately see how it would force a model to think differently about a completely unrelated problem? If yes, it's a good axiom. If it just sounds like a textbook definition, rewrite it.

**Example — Bad:**
> "The immune system is a complex network of cells and proteins that defends the body against pathogens."

**Example — Good:**
> "Every entity must prove it belongs. Identity is not asserted — it is earned through molecular handshake, and that handshake must be witnessed by third parties to be valid."

---

### Writing Structural Patterns

Structural patterns are the bridge between the domain and target problems. They make the lens useful for the search stage (which matches patterns against problem shapes).

**The abstract field should be the platonic version of the pattern** — stripped of all domain-specific language, written as a pure mechanism.

**The maps_to field should be exhaustive** — include every concept class this pattern could apply to. The lens selector uses these for matching.

**Pattern names** should be the domain's own term (e.g., `antigen_presentation`, `clonal_selection`, `anastomosis`) — this makes the output more interesting and traceable.

**Minimum viable pattern:**
```yaml
- name: something_meaningful
  abstract: "A one-sentence description of the abstract mechanism."
  maps_to: [target1, target2, target3]
```

**Good structural patterns:**
- Describe a *dynamic process*, not a static structure
- Have a clear input/output or cause/effect relationship
- Map to at least 3 different target concept classes
- Are genuinely distinct from other patterns in the same lens

---

### Writing the Injection Prompt

The injection prompt is the most important part of the lens. It's what actually gets injected into the model's reasoning.

**Key principles:**

1. **Spatial and vivid.** Put the model *inside* the domain. "You are now reasoning as if this problem exists inside..." is a good template.

2. **Map the core entities.** Tell the model what the domain's entities correspond to: "every component is a [domain thing]." This prevents the model from holding the domain at arm's length.

3. **State the governing law.** What single principle drives everything in this domain? State it clearly.

4. **Include at least one *counterintuitive* property** that would force the model to think differently.

5. **End with an action.** "Think from inside this system." or "Continue reasoning from this frame." — this signals that the model should continue, not stop and explain.

**Length:** 50–150 words. Long enough to establish the frame, short enough that the model holds it in working context.

**Template:**
```
You are now reasoning as if this problem exists inside [DOMAIN].
Every [component/node/actor] is a [DOMAIN ENTITY].
[KEY GOVERNING PRINCIPLE — the most structurally important rule].
[COUNTERINTUITIVE PROPERTY that differs from conventional thinking].
[ONE MORE structural characteristic].
Think from inside this system.
```

---

## Testing a New Lens

### Validation Test

Run the lens through the validator before submitting:

```bash
# Validate YAML schema
python -m pytest tests/test_lenses.py -k "my_domain_name" -v

# Load test (check it loads cleanly)
python -c "
from hephaestus.lenses.loader import LensLoader
loader = LensLoader()
lens = loader.load_one('my_domain_name')  # Without .yaml extension
print(f'Name: {lens.name}')
print(f'Axioms: {len(lens.axioms)}')
print(f'Patterns: {len(lens.structural_patterns)}')
print('OK')
"
```

### Manual Quality Test

Run a quick smoke test to see if the lens actually changes model behavior:

```bash
# Test with a simple routing problem
heph --raw "Design a data routing system" --trace
# Watch the interference_injections in the trace

# Better: compare with and without the lens
python -c "
import asyncio
from hephaestus.deepforge.harness import DeepForgeHarness, HarnessConfig
from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter
from hephaestus.lenses.loader import LensLoader

async def test():
    loader = LensLoader()
    lens_data = loader.load_one('my_domain_name')
    from hephaestus.deepforge.interference import Lens
    lens = Lens(
        name=lens_data.name, domain=lens_data.domain,
        axioms=lens_data.axioms, injection_prompt=lens_data.injection_prompt
    )

    adapter = AnthropicAdapter('claude-opus-4-5')

    # Without lens
    h_plain = DeepForgeHarness(adapter, HarnessConfig(
        use_interference=False, use_pruner=False, use_pressure=False
    ))
    plain = await h_plain.forge('Design a data routing system')

    # With lens
    h_lens = DeepForgeHarness(adapter, HarnessConfig(
        lenses=[lens], use_interference=True, use_pruner=False, use_pressure=False
    ))
    with_lens = await h_lens.forge('Design a data routing system')

    print('=== WITHOUT LENS ===')
    print(plain.output[:500])
    print('=== WITH LENS ===')
    print(with_lens.output[:500])

asyncio.run(test())
"
```

**A good lens produces a noticeably different approach.** If the outputs are structurally similar, the lens's axioms aren't doing enough work.

### Check Domain Distance

The `LensSelector` computes domain distance via sentence embeddings. Check where your new lens sits:

```python
from hephaestus.lenses.selector import LensSelector, EmbeddingModel
from hephaestus.lenses.loader import LensLoader

loader = LensLoader()
selector = LensSelector(loader)

# See how far your lens is from common target domains
lens_id = "my_domain_name"
for target in ["distributed_systems", "web_development", "machine_learning"]:
    dist = selector.domain_distance(lens_id, target)
    print(f"{lens_id} → {target}: {dist:.3f}")
```

Aim for distance > 0.70 from all computing-related domains. If your lens is < 0.50 from distributed systems, it's probably not novel enough to add real value.

---

## Contributing a Lens

1. **Create your YAML file** in `src/hephaestus/lenses/library/`:
   ```bash
   # Use a consistent naming convention: {domain}_{subdomain}.yaml
   touch src/hephaestus/lenses/library/geology_erosion.yaml
   ```

2. **Follow the naming convention:**
   - `biology_immune.yaml`
   - `physics_fluid_dynamics.yaml`
   - `music_theory.yaml`
   - `economics_behavioral.yaml`

3. **Run validation:**
   ```bash
   python -m pytest tests/test_lenses.py -v
   ```

4. **Test it works:**
   ```bash
   python -c "from hephaestus.lenses.loader import LensLoader; LensLoader().load_one('geology_erosion'); print('OK')"
   ```

5. **Open a PR** with:
   - The new YAML file
   - A brief description of why this domain has interesting structural patterns
   - (Optional) An example problem this lens solves well

### High-Value Domains We're Missing

- Geological erosion and sediment transport
- Embryological development (pattern formation, positional information)
- Musical counterpoint and voice leading
- Epidemiological SIR models applied to non-disease problems
- Medieval siege warfare and fortification
- Fermentation and biochemical cascades
- Ship navigation and dead reckoning
- Tidal flow and coastal dynamics
- Ant bridge-building (self-assembly)
- Bird migration and magnetic navigation

The further from computing, the better. We already have the obvious domains. Surprise us.

---

## Schema Validation Errors

Common lens validation failures and fixes:

| Error | Cause | Fix |
|-------|-------|-----|
| `missing required field: name` | No `name` field | Add `name: Your Lens Name` |
| `axioms must have at least 4 entries` | Too few axioms | Add more domain axioms |
| `structural_patterns[0] missing abstract` | Pattern has no abstract | Add `abstract: "..."` |
| `structural_patterns[0].maps_to must be a list` | `maps_to` is a string | Change to YAML list format |
| `injection_prompt must be a non-empty string` | No injection prompt | Add `injection_prompt: \|` block |
| `YAML parse error` | Malformed YAML | Check indentation and special characters |

Run `python -m pytest tests/test_lenses.py -v --tb=short` for detailed error messages.
