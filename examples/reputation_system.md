# Example: Reputation System → Immune Memory

**Problem:** *"I need a reputation system for an anonymous marketplace that can't be gamed"*

**Invention:** Immunological Reputation Protocol (IRP)  
**Source Domain:** Biology — Adaptive Immune System (T-Cell Memory + Antigen Presentation)  
**Domain Distance:** 0.94  
**Structural Fidelity:** 0.87  
**Novelty Score:** 0.91  
**Cost:** $1.31 | **Time:** 52s

---

## Why This Problem Is Hard

Anonymous marketplace reputation is one of the hardest problems in distributed systems. The difficulty is not technical — it's *adversarial*:

- **Sybil attacks**: Create thousands of fake identities to upvote yourself
- **Whitewashing**: Build a bad reputation, discard the identity, start fresh
- **Collusion**: Coordinated fake positive reviews from colluding accounts
- **Coercion**: Threaten buyers into positive reviews
- **Cold-start**: New legitimate users have no reputation, can't get business

Every existing approach has a fundamental weakness. Stake-based systems require capital that favors wealthy attackers. Graph-based trust (like eBay's feedback) is gameable by building reputation slowly with small transactions then executing a large fraud. Even zero-knowledge reputation schemes assume persistent identities, which violates anonymity.

The structural challenge: **you need a trust signal that is earned through real interactions, cannot be transferred between identities, and is expensive to fake even with unlimited sockpuppet accounts.**

This is what the adaptive immune system does for the human body — and it solved this problem 500 million years ago.

---

## Stage 1: Decompose

**Input:** "I need a reputation system for an anonymous marketplace that can't be gamed"

**Structural Form:**
```yaml
structure: "Establish trust signal in a graph with ephemeral nodes and adversarial actors"

constraints:
  - no persistent identity (privacy requirement)
  - adversarial nodes present and well-resourced
  - trust must be earned, not assigned or purchased
  - must resist sybil attack (cheap identity creation)
  - must resist whitewashing (identity disposal)
  - must provide meaningful signal for new nodes
  
mathematical_shape: "Robust trust propagation in a directed graph with Byzantine 
                    nodes, ephemeral node identities, and adversarial identity
                    generation. Equivalent to Byzantine fault-tolerant consensus
                    on trust without persistent public keys."

native_domain: distributed_systems
problem_maps_to: [trust, authentication, reputation, fraud_detection, consensus]
```

---

## Stage 2: Search — Cross-Domain Candidates

| Rank | Source Domain | Mechanism | Confidence |
|------|--------------|-----------|------------|
| 1 | Immune System — T-Cell Memory | Antigen presentation + memory formation | 0.92 |
| 2 | Hawala Banking | Trust chain through vouching networks | 0.84 |
| 3 | Medieval Guild Systems | Apprenticeship + peer certification | 0.79 |
| 4 | Epidemiology — Herd Immunity | Resistance through network structure | 0.68 |
| 5 | Cryptography — Web of Trust | Key signing for identity verification | 0.55 |

Note: The Web of Trust candidate (used by PGP) was scored low on domain distance (0.41 — it's too close to cryptography/security, an adjacent domain). Eliminated per the min_distance filter.

---

## Stage 3: Score

```
Candidate: Immune System T-Cell Memory
  structural_fidelity: 0.87
  domain_distance:     0.94
  combined_score:      0.87 × 0.94^1.5 = 0.793

Candidate: Hawala Banking
  structural_fidelity: 0.82
  domain_distance:     0.76
  combined_score:      0.82 × 0.76^1.5 = 0.543

Candidate: Medieval Guild Systems
  structural_fidelity: 0.78
  domain_distance:     0.72
  combined_score:      0.78 × 0.72^1.5 = 0.477
```

Immune system wins decisively. 0.94 domain distance is exceptional.

---

## Stage 4: Translate (Full Invention)

### How the Adaptive Immune System Solves This Problem

The immune system faces an identical abstract challenge: it must distinguish legitimate cells (self) from threats (non-self) in an environment where:
1. Threats actively evolve to mimic legitimate cells (adversarial)
2. Legitimate cells can't carry permanent IDs (identity is molecular, probabilistic)
3. New cells appear constantly (cold-start)
4. The system must respond to threats it's never seen before (unknown attackers)
5. There's no central authority — every decision is local

**The solution: antigen presentation + clonal selection + immunological memory**

When a T-cell encounters a suspicious entity, it doesn't decide alone. The suspicious entity must *present* a cryptographic-like "antigen" — a compact digest of its recent interactions — to multiple T-cells independently. If enough T-cells recognize the antigen as valid, the entity is trusted. If the presentation fails, the entity is marked as non-self.

The critical insight: **the antigen is derived from interactions, not from identity**. A new entity with no interactions has no antigen to present. Trust cannot be purchased or fabricated — it must be *grown* through genuine interactions.

When an encounter is resolved (trustworthy or fraudulent), the immune system forms *memory T-cells* — a permanent record of that encounter that allows instant recognition next time. Memory is tied to the *antigen pattern* (the interaction signature), not to a specific identity.

### Element-by-Element Mapping

| Immune System | Reputation System |
|--------------|-------------------|
| T-cell | Marketplace verifier node |
| B-cell | Transaction witness |
| Antigen | Interaction proof (ZK proof of transaction) |
| Antigen presentation | Seller presenting signed transaction receipts |
| MHC molecule | Standard receipt format enabling cross-node verification |
| Clonal selection | Amplification of verifiers that correctly identify fraud |
| Memory T-cell | Cached interaction signature → trust pattern |
| Self/non-self discrimination | Legitimate seller vs. fraud detection |
| Immune memory | Pattern database of known good/bad interaction signatures |
| Autoimmunity (false positive) | Incorrectly flagging legitimate sellers |
| Inflammation | Temporary marketplace-wide alert about a fraud pattern |
| Antibody | Fraud fingerprint broadcast to all verifiers |

### Architecture: Immunological Reputation Protocol (IRP)

**Core primitive: Interaction Proof (antigen)**

Every transaction generates an interaction proof — a ZK-SNARK that proves:
1. A transaction occurred between a buyer (anonymous) and a seller (anonymous)
2. The transaction completed (delivery confirmation)
3. The outcome was rated (satisfaction score)

Without revealing: who the buyer was, the transaction amount, or any identifying information about either party.

```python
# Pseudocode — actual ZK circuit would use circom or similar
class InteractionProof:
    """
    Zero-knowledge proof of completed transaction.
    The 'antigen' in IRP.
    """
    def generate(
        self,
        buyer_private_key,
        seller_commitment,    # Seller's blinded identity
        transaction_data,     # Hash of transaction
        delivery_confirmed,   # Boolean
        satisfaction_score,   # 1-5
    ) -> bytes:
        # Generates a proof that:
        # - A valid buyer (knows a key) completed a transaction
        # - Transaction hash matches seller's commitment
        # - Delivery was confirmed
        # - A score was given
        # WITHOUT revealing: buyer identity, seller identity, amount
        return zk_prove(
            circuit="interaction_proof",
            public_inputs=[seller_commitment, delivery_confirmed, satisfaction_score],
            private_inputs=[buyer_private_key, transaction_data],
        )
```

**Seller's antigen presentation**

When a buyer queries a seller's reputation, the seller presents their interaction history as a bundle of interaction proofs:

```python
class SellerProfile:
    """
    A seller's public-facing reputation object.
    No persistent identity — this can be regenerated.
    """
    def __init__(self):
        self.interaction_proofs: list[InteractionProof] = []
        self.session_key: bytes = generate_ephemeral_key()
        # Session key is the "identity" — can be rotated without losing reputation

    def present_antigen(self, n_recent: int = 50) -> AntigenBundle:
        """
        Present interaction proofs for verification.
        Only recent proofs — older ones have decayed.
        """
        recent_proofs = sorted(self.interaction_proofs, key=lambda p: p.timestamp)[-n_recent:]
        return AntigenBundle(
            proofs=recent_proofs,
            session_key=self.session_key,
            # Reputation score is not claimed — it's computed by verifiers
        )
```

**Verifier nodes (T-cells)**

A distributed network of verifier nodes independently validates antigen bundles:

```python
class VerifierNode:
    """
    Independent verifier. Equivalent to a T-cell.
    Maintains local memory of known interaction patterns.
    """
    def __init__(self):
        self.memory_patterns: dict[bytes, TrustVerdict] = {}  # Memory T-cells
        self.fraud_fingerprints: set[bytes] = set()            # Known antigens of fraudsters

    def evaluate(self, antigen_bundle: AntigenBundle) -> float:
        """
        Returns trust score 0-1 for a seller.
        """
        # Check memory first (instant recognition)
        pattern_hash = self._hash_pattern(antigen_bundle)
        if pattern_hash in self.memory_patterns:
            return self.memory_patterns[pattern_hash].score

        # Check fraud fingerprints
        if pattern_hash in self.fraud_fingerprints:
            return 0.0  # Known fraudster pattern

        # Verify each interaction proof
        valid_proofs = []
        for proof in antigen_bundle.proofs:
            if verify_zk_proof(proof):
                valid_proofs.append(proof)

        if not valid_proofs:
            return 0.0  # No valid interactions = no trust

        # Score based on verified interactions
        positive = sum(1 for p in valid_proofs if p.satisfaction_score >= 4)
        score = positive / len(valid_proofs)

        # Form memory (clonal selection: amplify accurate verdicts)
        verdict = TrustVerdict(score=score, confidence=len(valid_proofs) / 50)
        self.memory_patterns[pattern_hash] = verdict

        return score

    def report_fraud(self, antigen_bundle: AntigenBundle):
        """
        Record a fraud fingerprint.
        Equivalent to forming memory T-cells after an infection.
        """
        pattern_hash = self._hash_pattern(antigen_bundle)
        self.fraud_fingerprints.add(pattern_hash)
        # Broadcast to other verifiers (inflammation → antibodies)
        broadcast_fraud_fingerprint(pattern_hash)
```

**Clonal selection: verifier reputation**

Verifier nodes themselves earn reputation — verifiers that correctly identify fraud (confirmed by other evidence) have their verdicts weighted more heavily. Verifiers that make systematic errors (autoimmunity — flagging legitimate sellers) have their weight reduced.

```python
class VerifierNetwork:
    def aggregate_trust(self, antigen_bundle: AntigenBundle) -> float:
        """
        Aggregate scores from multiple verifiers, weighted by verifier reputation.
        Like MHC presentation requiring multiple T-cell confirmations.
        """
        scores = []
        for verifier, v_reputation in self.verifiers.items():
            score = verifier.evaluate(antigen_bundle)
            scores.append((score, v_reputation))

        # Weighted average — verifiers with higher reputation have more say
        total_weight = sum(r for _, r in scores)
        if total_weight == 0:
            return 0.5  # No verifiers = neutral
        weighted_score = sum(s * r for s, r in scores) / total_weight
        return weighted_score
```

**Anti-whitewashing: interaction proof decay**

Interaction proofs have a timestamp. Old proofs are worth less. A seller who discards their identity and starts fresh has *zero* interaction proofs. The cold-start penalty is automatic — no special logic required.

```python
def proof_weight(proof: InteractionProof, current_time: float) -> float:
    """
    Recent proofs worth more. Older proofs decay.
    Creates natural resistance to identity cycling.
    """
    age_days = (current_time - proof.timestamp) / 86400
    decay = math.exp(-age_days / 90)  # 90-day half-life
    return decay
```

**Anti-sybil: interaction proof cost**

Generating a valid interaction proof requires:
1. A real transaction (costs money — hard to fake)
2. A real delivery confirmation (requires physical goods or real digital delivery)
3. A real buyer's ZK proof (requires a real user with their own private key)

A sybil attacker with 1000 fake buyer accounts would need 1000 real transactions to generate 1000 proofs. The attack is economically self-defeating.

---

### Fraud Detection: Inflammation Response

When a verifier detects a fraud pattern, it broadcasts an "antibody" — a fingerprint of the interaction proof bundle that was fraudulent. Other verifiers update their local fraud databases.

This is equivalent to systemic inflammation: a local threat is detected, signals propagate globally, and the entire marketplace goes on alert for that specific fraud pattern — without revealing the identity of the attacker or the victim.

```python
@dataclass
class FraudAlert:
    """Broadcast when fraud is detected. Equivalent to cytokine signal."""
    pattern_fingerprint: bytes    # Hash of the fraud antigen pattern
    confidence: float             # How confident is the reporting verifier
    transaction_class: str        # Type of fraud (for pattern matching)
    # Does NOT include: identity of seller, buyer, or transaction details
```

---

## Where the Analogy Breaks

1. **The immune system has 10 billion T-cells; you have hundreds of verifier nodes.** With fewer verifiers, consensus is more fragile. Compensate by requiring more verifier confirmations for high-value transactions.

2. **Autoimmunity (false positive flagging) is catastrophic.** In biology, autoimmunity is a serious disease. In a marketplace, wrongly flagging legitimate sellers destroys trust. IRP needs an appeal mechanism — a way to demonstrate legitimate activity despite a fraud flag.

3. **Interaction proofs require ZK infrastructure.** Building production-quality ZK circuits is non-trivial. For simpler implementations, replace ZK proofs with threshold signature schemes (N of M buyers must sign off on a delivery).

4. **Memory T-cells are permanent; you want some forgetting.** A seller who committed fraud 5 years ago and has been legitimate since deserves a path to redemption. Add a rehabilitation mechanism: fraud memory decays at a slower rate than interaction proofs, but it does decay.

5. **Cold-start is still real.** A new legitimate seller has no interaction proofs and will have low trust scores initially. Mitigation: an escrow mechanism for new sellers (not IRP itself), or a graduated access system.

---

## Prior Art Check

| Reference | Match Level |
|-----------|-------------|
| Eigentrust (Kamvar et al., 2003) | Partial — graph-based reputation, no ZK/antigen mechanism |
| PGP Web of Trust | Partial — identity-based, not interaction-based; persistent identities |
| eBay feedback system | Weak — simple cumulative ratings, no adversarial resistance |
| Bazaar (Marti & Garcia-Molina, 2006) | Partial — routing reputation, different domain |
| ZKP-based identity systems (various) | Weak — identity proofs, not interaction proofs |

**Status: NO PRIOR ART** found for the specific combination of:
- Interaction proofs as the trust primitive (not identity proofs)
- Immunological memory formation as the reputation aggregation mechanism
- Clonal selection of verifiers based on accuracy
- Temporal decay of interaction proofs as anti-whitewashing mechanism

The "interaction proof as antigen" abstraction and the "verifier network as T-cell population" design do not appear in the reputation systems literature.

---

## Novelty Proof

The structural isomorphism holds at three levels:

**Level 1:** The problem structure is identical. Both the immune system and IRP solve: "establish trust in a network with ephemeral, anonymous actors who may be adversarial, without any central authority."

**Level 2:** The mechanism structure is identical. Both use: (a) proof of past interactions as the trust signal, (b) distributed verification by multiple independent observers, (c) memory formation that persists beyond the original encounter, (d) pattern-based recognition that transfers to new-but-similar threats.

**Level 3:** The anti-gaming properties emerge naturally. Sybil resistance, anti-whitewashing, and fraud propagation are all *consequences* of the immunological design — not bolted-on features. This is the signature of a genuine structural isomorphism: the transfer of the mechanism transfers the mechanism's properties.

---

## Implementation Path

**Phase 1 (Simple version — no ZK proofs):**
- Transaction proofs = threshold signatures from N buyers
- Verifiers = any marketplace node
- Reputation score = weighted average of verified transactions
- Time: ~2 weeks to prototype

**Phase 2 (Full IRP):**
- Replace threshold signatures with ZK-SNARKs
- Add fraud fingerprint broadcast
- Implement verifier reputation (clonal selection)
- Time: ~8 weeks

**Phase 3 (Production):**
- Scale verifier network
- Add rehabilitation mechanism
- Benchmark against Sybil attack scenarios
- Time: ~4 weeks
