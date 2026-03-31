# Example: Fraud Detection → Antigen Presentation

**Problem:** *"I need a fraud detection system that can identify novel fraud patterns without relying on historical training data"*

**Invention:** Antigen-Presentation Fraud Sentinel (APFS)  
**Source Domain:** Biology — Adaptive Immune System (Antigen Presentation + Clonal Selection)  
**Domain Distance:** 0.94  
**Structural Fidelity:** 0.85  
**Novelty Score:** 0.92  
**Cost:** $1.27 | **Time:** 49s

---

## Why This Problem Is Hard

Traditional fraud detection has a fundamental adversarial asymmetry: **fraudsters learn from your detection system, but your detection system only learns from past fraudsters**.

Machine learning models trained on historical fraud are powerful but brittle:
- **Novel fraud patterns** are undetected until enough examples accumulate to train on
- **Concept drift** makes models stale within months
- **Label delay**: fraud may not be confirmed for weeks, creating stale training data
- **Class imbalance**: 0.1% fraud rate means the model optimizes for the 99.9%, not the 0.1%
- **Adversarial adaptation**: sophisticated fraud rings probe the detection system to find boundaries and evolve to avoid them

The result: every model works well on last year's fraud patterns and poorly on this year's new ones. The system is always fighting the last war.

What's needed is a system that can recognize *structural novelty* — not "this matches a known fraud pattern" but "this is structurally anomalous in ways that haven't been seen before." This is precisely what the adaptive immune system does when it encounters a pathogen it's never seen.

---

## Stage 1: Decompose

**Input:** "I need a fraud detection system that can identify novel fraud patterns without relying on historical training data"

**Structural Form:**
```yaml
structure: "Detect anomalous entities in a stream without relying on labeled 
           examples of the anomaly class"

constraints:
  - cannot require historical labeled fraud examples
  - must detect genuinely novel patterns (not just known fraud types)
  - must operate in real-time on transaction streams
  - low false positive rate (most transactions are legitimate)
  - must improve with confirmed fraud cases
  - adversarial actors will adapt to the detection mechanism

mathematical_shape: "Anomaly detection over a high-dimensional feature stream
                    with evolving adversarial distribution. Equivalent to
                    one-class classification with online learning and
                    adversarial concept drift."

native_domain: security
problem_maps_to: [anomaly_detection, classification, fraud, adversarial_ml]
```

---

## Stage 2: Search — Cross-Domain Candidates

| Rank | Source Domain | Mechanism | Confidence |
|------|--------------|-----------|------------|
| 1 | Immune System — Antigen Presentation | MHC-II presentation + T-cell activation | 0.91 |
| 2 | Epidemiology — Contact Tracing | Network propagation of risk signals | 0.79 |
| 3 | Military — Counterintelligence | Behavioral signature analysis | 0.74 |
| 4 | Ecology — Keystone Predators | Network destabilization detection | 0.65 |
| 5 | Chemistry — Titration | Threshold-based state detection | 0.61 |

---

## Stage 3: Score

```
Candidate: Immune System Antigen Presentation
  structural_fidelity: 0.85
  domain_distance:     0.94
  combined_score:      0.85 × 0.94^1.5 = 0.775

Candidate: Epidemiology Contact Tracing
  structural_fidelity: 0.77
  domain_distance:     0.81
  combined_score:      0.77 × 0.81^1.5 = 0.561

Candidate: Military Counterintelligence
  structural_fidelity: 0.74
  domain_distance:     0.73
  combined_score:      0.74 × 0.73^1.5 = 0.462
```

Immune system wins. Highest fidelity and distance simultaneously.

---

## Stage 4: Translate (Full Invention)

### How Antigen Presentation Actually Works

The adaptive immune system doesn't have a database of known pathogens. It has a *generative* recognition system that can detect novelty — anything that doesn't match the "self" signature gets flagged.

**Key mechanism: MHC class II antigen presentation**

When a macrophage (innate immune sentinel) encounters a suspicious entity, it doesn't immediately trigger an alarm. Instead, it **internalizes the entity, breaks it into fragments (peptides), and displays these fragments on its surface** for T-cells to inspect. This is antigen presentation.

T-cells inspect the displayed fragment and check it against their surface receptors. If the fragment matches the T-cell's receptor (indicating "non-self"), the T-cell is activated. Multiple T-cells independently evaluate the same antigen. Consensus across multiple T-cells is required before an immune response is triggered — this prevents autoimmunity (false positives).

Once a T-cell is activated, **clonal selection** begins: the activated T-cell rapidly multiplies. All copies have the same receptor — the immune system has "amplified" its capacity to detect this specific antigen. If the threat returns, recognition is near-instant.

The crucial insight: **the immune system detects novelty by detecting deviation from self, not by recognizing known pathogens**. It has no pre-built database of what bad looks like. It knows what good looks like (self), and everything else is suspect.

### Element-by-Element Mapping

| Immune System | Fraud Detection System |
|--------------|----------------------|
| Macrophage (sentinel) | Transaction ingestion layer |
| Pathogen | Potentially fraudulent transaction |
| Antigen (pathogen fragment) | Behavioral feature vector of transaction |
| MHC presentation | Feature extraction and contextualization |
| T-cell | Specialized fraud detector (one per behavioral pattern class) |
| T-cell receptor | Behavioral pattern signature |
| Self-tolerance training | Normal behavior model (trained on legitimate traffic) |
| T-cell activation threshold | Fraud confidence threshold |
| Clonal selection | Amplification of detectors that catch real fraud |
| Memory T-cell | Cached pattern for fast future recognition |
| Cytokine signal | Fraud alert (triggers review queue) |
| Immune response | Transaction block or flag for review |
| Autoimmunity | False positive (blocking legitimate transaction) |
| Immunodeficiency | Under-detection (missing real fraud) |

### Architecture: Antigen-Presentation Fraud Sentinel (APFS)

**The core insight: Fraud detection as self/non-self discrimination**

Instead of training a model to recognize known fraud patterns, APFS trains a model to recognize *normal* (self). Anything that deviates significantly from the normal model is treated as a candidate fraud antigen.

This inverts the classical fraud detection problem: instead of "does this match known fraud?", the question is "does this deviate from known normal?"

**Step 1: Self-model training (Normal behavior model)**

```python
class SelfModel:
    """
    Represents 'self' — the model of normal behavior.
    Trained exclusively on legitimate transactions.
    No fraud labels required.
    """
    def __init__(self, embedding_dim: int = 128):
        self.autoencoder = FraudAutoencoder(embedding_dim)  # Reconstruction model
        self.normal_embeddings = []    # Reference distribution of normal behavior
        self.isolation_forest = None   # Outlier detector

    def train_on_normal(self, transactions: list[Transaction]) -> None:
        """
        Train only on legitimate transactions.
        No fraud examples needed.
        """
        features = [self.extract_features(t) for t in transactions]

        # Train autoencoder to reconstruct normal transactions
        self.autoencoder.fit(features)

        # Train isolation forest on normal embeddings
        embeddings = self.autoencoder.encode(features)
        self.normal_embeddings = embeddings
        self.isolation_forest = IsolationForest(contamination=0.01)
        self.isolation_forest.fit(embeddings)

    def self_similarity(self, transaction: Transaction) -> float:
        """
        How 'self-like' is this transaction?
        High = normal. Low = anomalous (potential fraud antigen).
        """
        features = self.extract_features(transaction)
        embedding = self.autoencoder.encode([features])[0]

        # Reconstruction error (high = anomalous)
        reconstruction = self.autoencoder.decode([embedding])[0]
        reconstruction_error = np.mean((features - reconstruction) ** 2)

        # Isolation forest anomaly score
        isolation_score = self.isolation_forest.score_samples([embedding])[0]

        # Combined: lower score = more anomalous = potential fraud
        self_similarity = (1 - reconstruction_error) * 0.5 + (isolation_score + 0.5) * 0.5
        return float(np.clip(self_similarity, 0, 1))

    def extract_features(self, transaction: Transaction) -> np.ndarray:
        """
        Extract the 'antigen' — the behavioral feature vector.
        Includes: time, amount, merchant category, geolocation, velocity,
                 device fingerprint, session behavior, etc.
        """
        return np.array([
            transaction.amount_normalized,
            transaction.hour_of_day / 24,
            transaction.day_of_week / 7,
            transaction.merchant_category_hash % 1000 / 1000,
            transaction.distance_from_home_km / 10000,
            transaction.velocity_1h,         # Transactions in last hour
            transaction.velocity_24h,        # Transactions in last 24 hours
            transaction.amount_vs_avg,       # Ratio to user's average
            transaction.new_merchant_flag,   # First time at this merchant?
            # ... 100+ more features
        ])
```

**Step 2: Antigen presentation (feature contextualization)**

The macrophage doesn't just display the raw pathogen — it digests it and presents specific fragments. APFS contextualizes the transaction:

```python
class AntigenPresenter:
    """
    Contextualizes and enriches the transaction feature vector.
    Like MHC class II presentation: adds context to the raw antigen.
    """
    def present(
        self,
        transaction: Transaction,
        user_history: UserHistory,
        network_context: NetworkContext,
    ) -> EnrichedAntigen:
        """
        Produce the 'antigen' for T-cell inspection.
        """
        raw_features = self.self_model.extract_features(transaction)

        # Contextualize: how does this transaction fit the user's history?
        historical_context = np.array([
            transaction.amount / (user_history.avg_amount + 0.01),
            transaction.merchant_category in user_history.frequent_categories,
            transaction.country == user_history.home_country,
            (transaction.timestamp - user_history.last_transaction_time) / 3600,
        ])

        # Network context: what's happening in the broader network right now?
        network_context_features = np.array([
            network_context.current_fraud_rate,     # Recent fraud spike?
            network_context.merchant_fraud_rate,    # This merchant flagged recently?
            network_context.ip_fraud_rate,          # This IP associated with fraud?
        ])

        return EnrichedAntigen(
            raw_features=raw_features,
            historical_context=historical_context,
            network_context=network_context_features,
            self_similarity=self.self_model.self_similarity(transaction),
        )
```

**Step 3: T-cell inspection (specialized detectors)**

A population of specialized detectors, each sensitive to a different class of anomaly:

```python
class TCell:
    """
    A specialized fraud detector.
    Like a T-cell with a specific receptor: responds to specific antigen patterns.
    """
    def __init__(self, name: str, sensitivity: float = 0.5):
        self.name = name
        self.sensitivity = sensitivity
        self.activation_count = 0  # For clonal selection weighting
        self.receptor = None       # Trained pattern signature

    def inspect(self, antigen: EnrichedAntigen) -> float:
        """
        Returns activation score [0, 1].
        High = this T-cell thinks the antigen is non-self (fraud).
        """
        raise NotImplementedError


class VelocityTCell(TCell):
    """Detects velocity fraud: too many transactions too fast."""
    def inspect(self, antigen: EnrichedAntigen) -> float:
        v1h = antigen.raw_features[5]   # velocity_1h
        v24h = antigen.raw_features[6]  # velocity_24h
        if v1h > 3 or v24h > 8:
            return min(1.0, (v1h / 3 + v24h / 8) / 2)
        return 0.0


class GeographicAnomalyTCell(TCell):
    """Detects geographic impossibility: transaction in two places at once."""
    def inspect(self, antigen: EnrichedAntigen) -> float:
        distance = antigen.raw_features[4]  # distance_from_home_km
        time_since_last = antigen.historical_context[3]  # hours since last transaction
        # Speed check: could they physically be here?
        if time_since_last > 0:
            implied_speed_kmh = distance / time_since_last
            if implied_speed_kmh > 900:  # Faster than commercial flight
                return min(1.0, implied_speed_kmh / 1000)
        return 0.0


class BehavioralAnomalyTCell(TCell):
    """
    Detects behavioral anomaly: self-model deviation.
    This is the 'novel fraud' detector — no pre-built patterns required.
    """
    def inspect(self, antigen: EnrichedAntigen) -> float:
        return max(0.0, 1.0 - antigen.self_similarity)
```

**Step 4: Clonal selection and consensus**

Multiple T-cells inspect the same antigen. Consensus is required — preventing autoimmunity (false positives):

```python
class ImmuneConsensus:
    """
    Aggregate T-cell activations into a fraud decision.
    Requires consensus to prevent false positives.
    """
    def __init__(self, t_cells: list[TCell], activation_threshold: float = 0.65):
        self.t_cells = t_cells
        self.threshold = activation_threshold

    def evaluate(self, antigen: EnrichedAntigen) -> FraudVerdict:
        """
        Returns fraud verdict with confidence score.
        """
        activations = []
        activated_cells = []

        for cell in self.t_cells:
            activation = cell.inspect(antigen)
            # Weight by clonal selection score (cells that found real fraud before
            # have higher weight — they've been 'amplified')
            clonal_weight = 1.0 + cell.activation_count * 0.1
            weighted_activation = activation * min(clonal_weight, 3.0)
            activations.append(weighted_activation)
            if activation > self.threshold:
                activated_cells.append((cell.name, activation))

        # Consensus: need multiple T-cells to activate
        n_activated = sum(1 for a in activations if a > self.threshold)
        consensus_score = n_activated / len(self.t_cells)

        # Final fraud score: blend of consensus and maximum individual activation
        max_activation = max(activations) if activations else 0.0
        fraud_score = consensus_score * 0.6 + max_activation * 0.4

        return FraudVerdict(
            fraud_score=fraud_score,
            is_fraud=fraud_score > 0.7,
            activated_cells=activated_cells,
            action='block' if fraud_score > 0.9 else 'review' if fraud_score > 0.7 else 'pass',
        )
```

**Step 5: Memory formation and clonal selection**

When fraud is confirmed, form memory T-cells and amplify the detectors that caught it:

```python
class ImmuneMemory:
    """
    Forms memory from confirmed fraud cases.
    Amplifies successful T-cells (clonal selection).
    """
    def update_on_confirmed_fraud(
        self,
        antigen: EnrichedAntigen,
        verdict: FraudVerdict,
        immune_system: ImmuneConsensus,
    ) -> None:
        # Amplify T-cells that correctly identified this fraud
        for cell_name, activation in verdict.activated_cells:
            cell = next(c for c in immune_system.t_cells if c.name == cell_name)
            cell.activation_count += 1  # Clonal selection: amplify this detector

        # Form memory T-cell: store the antigen pattern for fast future recognition
        pattern = self._extract_memory_pattern(antigen)
        self.memory_patterns.append(MemoryPattern(
            pattern=pattern,
            fraud_type=self._classify_fraud_type(antigen),
            confidence=verdict.fraud_score,
        ))

        # Re-train self-model to include behavioral neighborhood of this fraud
        # (Update the self-model's boundary to better separate fraud from normal)
        self.self_model.negative_examples.append(antigen)
        if len(self.self_model.negative_examples) % 100 == 0:
            self.self_model.update_boundary()
```

**Fraud network propagation (inflammation response)**

When a fraud pattern is detected, broadcast a signal to all APFS instances in the network. Like cytokine signaling, this puts the whole system on alert:

```python
class FraudInflammationSignal:
    """
    Broadcast fraud detection signals across APFS instances.
    Equivalent to cytokine signaling during immune response.
    """
    async def broadcast(
        self,
        pattern: MemoryPattern,
        confidence: float,
        network: APFSNetwork,
    ) -> None:
        """
        Alert other nodes to this fraud pattern.
        """
        signal = InflammationSignal(
            pattern_fingerprint=pattern.fingerprint,
            fraud_type=pattern.fraud_type,
            confidence=confidence,
            merchant_category=pattern.merchant_category,  # Scope the alert
            # NOT included: transaction details, user identity
        )
        await network.broadcast(signal)

    async def receive(self, signal: InflammationSignal) -> None:
        """
        Update local T-cells based on received inflammation signal.
        """
        # Lower activation threshold for transactions matching this pattern
        self.immune_system.lower_threshold_for(
            fraud_type=signal.fraud_type,
            by=0.1 * signal.confidence,
            duration_hours=24,  # Temporary heightened alert
        )
```

---

## Complete System Flow

```
New Transaction arrives
        │
        ▼
AntigenPresenter.present() — extract and contextualize features
        │
        ▼
SelfModel.self_similarity() — is this transaction "self-like"?
        │
        ├─── High similarity (> 0.85): PASS (legitimate)
        │
        └─── Low similarity (< 0.85): Present to T-cells
                        │
                        ▼
               T-cell population inspects
               (VelocityTCell, GeographicTCell, BehavioralTCell, ...)
                        │
                        ▼
               ImmuneConsensus.evaluate()
                        │
                        ├─── fraud_score < 0.7: PASS
                        ├─── fraud_score 0.7-0.9: FLAG FOR REVIEW
                        └─── fraud_score > 0.9: BLOCK
                                        │
                                        ▼
                              If confirmed fraud:
                              ImmuneMemory.update_on_confirmed_fraud()
                              FraudInflammationSignal.broadcast()
```

---

## Where the Analogy Breaks

1. **Autoimmunity is catastrophic for businesses.** False positives (blocking legitimate customers) lose revenue and destroy trust. APFS must be tuned conservatively — block only for fraud_score > 0.9, flag for review at 0.7–0.9. The "two-step" defense (flag before block) reduces autoimmunity damage.

2. **The immune system has unlimited T-cell diversity; you have a fixed set.** Biological T-cells are generated with random receptor sequences — billions of possible patterns. APFS has a finite set of T-cells. Mitigate by continuously generating new T-cells based on emerging fraud patterns (adding new detector classes as fraud evolves).

3. **Self-model training requires clean data.** If training data contains mislabeled fraud transactions, the self-model learns "fraud is normal." Requires a cleaning pass on training data or a conservative self-similarity threshold.

4. **Novel fraud vs. novel legitimate behavior.** A traveler using their card abroad for the first time looks like a geographic anomaly. APFS would flag this. Real immune systems have tolerance mechanisms for edge cases; APFS needs explicit tolerance rules (e.g., "customer notified us of travel").

5. **Clonal selection can over-amplify.** If one T-cell catches 90% of confirmed fraud, it gets amplified so heavily that its false positive rate eventually dominates the consensus. Cap clonal amplification weight at 3× and periodically normalize.

---

## Prior Art Check

| Reference | Match Level |
|-----------|-------------|
| Forrest et al., "Self-nonself discrimination in computer security" (1994) | Strong match — foundational work on immune-inspired intrusion detection |
| Artificial Immune Systems (AIS) (de Castro & Timmis, 2002) | Strong match — general AIS framework |
| Negative Selection Algorithm (NSA) | Partial — self/non-self discrimination, different implementation |
| Modern fraud detection (XGBoost + feature engineering) | Weak — different architecture, supervised not anomaly-based |

**Status: PARTIAL PRIOR ART** — Artificial Immune Systems is a well-established field (1990s–2000s). However, this specific implementation with:
- Modern feature extraction (autoencoder embeddings)
- Inflammation-based network propagation
- Clonal selection-weighted consensus voting
- Integration of self-model deviation as primary signal

...represents a fresh application of AIS principles to modern fraud detection with current ML techniques. The prior art uses simpler pattern-matching negative selection rather than autoencoder-based self-model deviations.

**Novelty score: 0.92** — partially anticipated by AIS literature, but novel in its specific architecture and integration.

---

## Novelty Proof

The invention advances beyond prior AIS implementations in three specific ways:

1. **Self-model via autoencoder**: Prior AIS uses geometric negative selection (computing distance from "self patterns"). APFS uses neural autoencoder reconstruction error as the self-similarity measure, which handles high-dimensional behavioral features that geometric distance can't.

2. **Clonal selection of detectors**: Prior AIS evolves detector populations via genetic algorithms (slow, offline). APFS uses online clonal amplification — detectors that catch confirmed fraud get up-weighted in real time, without retraining.

3. **Cytokine-inspired network propagation**: Prior AIS instances operate independently. APFS instances share inflammation signals — a fraud pattern detected in São Paulo immediately reduces activation thresholds for that pattern in Lagos. This network-level immune response has no equivalent in the AIS literature.

---

## Implementation Path

**Phase 1 (2 weeks):** Deploy BehavioralAnomalyTCell + SelfModel. No fraud labels required. Connect to transaction stream.

**Phase 2 (4 weeks):** Add VelocityTCell, GeographicAnomalyTCell, ImmuneMemory. Tune thresholds on shadow traffic.

**Phase 3 (ongoing):** Deploy inflammation signal network. Add new T-cells as new fraud patterns emerge. Monitor clonal amplification weights for stability.
