#!/usr/bin/env python3
"""Fix 29 lenses that only have 4 structural_patterns by adding the 5th (and 6th)."""

import yaml
from pathlib import Path

fixes = {
    "art_counterpoint.yaml": [
        {"name": "voice_leading_economy", "abstract": "Transitions between states follow the path of minimal change — each component moves to the nearest compatible destination, avoiding unnecessary reconfiguration.", "maps_to": ["minimal_change", "smooth_transition", "nearest_compatible", "economy_constraint"]},
        {"name": "contrapuntal_restriction_productivity", "abstract": "Imposing structural constraints on how components can interact paradoxically increases creative output — the restrictions force novel combinations that unconstrained freedom would never discover.", "maps_to": ["constraint_driven_innovation", "restrictive_creativity", "combinatorial_pressure"]}
    ],
    "biology_biofilm.yaml": [
        {"name": "environmental_nucleation", "abstract": "Collective behavior initiates at specific environmental sites that lower the activation barrier for aggregation. Without these nucleation points, the system remains dispersed.", "maps_to": ["seed_site", "activation_barrier", "nucleation_point", "rapid_organization"]},
        {"name": "gradient_exploitation", "abstract": "The system positions itself to maximize access to resource gradients, actively sculpting its local environment to concentrate scarce resources while expelling waste.", "maps_to": ["gradient_maximization", "resource_concentration", "waste_expulsion", "environment_sculpting"]}
    ],
    "biology_chemotaxis.yaml": [
        {"name": "stochastic_switching_strategy", "abstract": "The agent alternates between exploratory and directional modes, with the switching rate modulated by environmental feedback.", "maps_to": ["mode_switching", "exploration_exploitation", "adaptive_switching", "environmental_feedback"]},
        {"name": "memory_based_comparison", "abstract": "The agent compares current signal levels to a remembered baseline to determine direction, rather than relying on instantaneous spatial comparison.", "maps_to": ["temporal_comparison", "memory_baseline", "gradient_direction", "navigation_by_memory"]}
    ],
    "biology_coral_reef.yaml": [
        {"name": "successional_deployment", "abstract": "Components are sequenced through distinct developmental stages, each stage creating the conditions necessary for the next.", "maps_to": ["developmental_sequencing", "stage_preparation", "complexity_buildup", "succession"]},
        {"name": "calcified_commitment", "abstract": "Each component permanently anchors itself to the growing structure, creating a shared legacy that future components depend on.", "maps_to": ["irreversible_anchoring", "shared_legacy", "forward_accumulation", "commitment_lock"]}
    ],
    "biology_quorum_sensing.yaml": [
        {"name": "signal_degradation_clock", "abstract": "The signal naturally decays over time, creating a temporal window for coordination. Decay rate determines effective communication range.", "maps_to": ["temporal_decay", "signal_lifetime", "communication_window", "stale_signal_prevention"]},
        {"name": "heterogeneous_sensitivity", "abstract": "Not all agents have identical response thresholds — a distribution of sensitivities creates a graded collective response rather than an all-or-nothing switch.", "maps_to": ["threshold_distribution", "graded_response", "sensitivity_variance", "smooth_transition"]}
    ],
    "biology_virology.yaml": [
        {"name": "host_dependency_exploitation", "abstract": "The system is stripped down to only the information needed to hijack a more complex system's machinery, outsourcing all metabolic and replicative functions.", "maps_to": ["minimal_genome", "host_hijack", "resource_parasitism", "outsourced_metabolism"]},
        {"name": "recombination_leap", "abstract": "Two distinct variants exchange structural material, producing novel combinations that gradual mutation could not achieve in reasonable time.", "maps_to": ["structural_recombination", "adaptive_jump", "variant_swap", "landscape_reset"]}
    ],
    "culinary_emulsification.yaml": [
        {"name": "mechanical_energy_input", "abstract": "The mixed state requires continuous energy input to maintain — without agitation the separated state reasserts itself. Stability is kinetic, not thermodynamic.", "maps_to": ["energy_maintenance", "kinetic_stability", "separation_pressure", "continuous_input"]},
        {"name": "droplet_size_distribution", "abstract": "Effectiveness of the mixed state depends on size distribution of dispersed elements — too large and they coalesce, too small and viscosity explodes.", "maps_to": ["optimal_distribution", "size_dependence", "coalescence_risk", "viscosity_tradeoff"]}
    ],
    "culinary_maillard.yaml": [
        {"name": "water_activity_control", "abstract": "The reaction requires intermediate moisture: too much water prevents temperature rise, too little eliminates molecular mobility. Optimal window is narrow.", "maps_to": ["optimal_moisture", "mobility_constraint", "temperature_ceiling", "narrow_window"]},
        {"name": "ph_dependent_pathways", "abstract": "Reaction pathways and product distribution shift dramatically with pH: alkaline conditions accelerate and produce different outcomes than neutral or acidic.", "maps_to": ["ph_dependence", "pathway_selection", "product_distribution", "condition_dependent_outcome"]}
    ],
    "economics_auction.yaml": [
        {"name": "bid_shading_equilibrium", "abstract": "Bidders reduce bids below true valuation by an amount depending on competitor count and valuation distribution — optimal shading is computable.", "maps_to": ["underbidding_equilibrium", "competitive_convergence", "valuation_discount", "strategic_reduction"]},
        {"name": "common_value_uncertainty", "abstract": "When the item has the same value to all but that value is unknown, the winner is the bidder who most overestimated — winner's curse is unavoidable.", "maps_to": ["overestimation_selection", "common_bias", "structural_disadvantage", "information_asymmetry"]}
    ],
    "economics_mechanism_design.yaml": [
        {"name": "monotone_allocation_rule", "abstract": "When allocation is monotonically increasing in reported value, truth-telling emerges as the dominant strategy. Allocation shape determines incentives.", "maps_to": ["monotonicity_truth", "allocation_dependence", "dominant_strategy", "shape_determined_incentive"]},
        {"name": "virtual_valuation_optimization", "abstract": "The revenue-optimal mechanism optimizes transformed virtual valuations rather than true reported values — can mean excluding the highest bidder.", "maps_to": ["virtual_objective", "revenue_optimization", "exclusion_paradox", "transformed_valuation"]}
    ],
    "economics_options.yaml": [
        {"name": "delta_hedge_replication", "abstract": "A continuously rebalanced portfolio replicates the derivative's payoff, making the derivative's price independent of beliefs about future direction.", "maps_to": ["payoff_replication", "continuous_rebalancing", "belief_independence", "hedge_equivalence"]},
        {"name": "volatility_surface_arbitrage", "abstract": "Options with different strikes and expirations encode different implied volatilities — inconsistencies create arbitrage that forces convergence.", "maps_to": ["surface_inconsistency", "arbitrage_convergence", "implied_structure", "cross_strike_arbitrage"]}
    ],
    "engineering_3d_printing.yaml": [
        {"name": "topological_constraint_design", "abstract": "Complex internal geometries impossible to machine can be printed directly, but overhangs beyond a critical angle require support structures that must later be removed.", "maps_to": ["geometry_constraint", "support_requirement", "removable_scaffold", "direct_fabrication"]},
        {"name": "material_state_transition", "abstract": "The material passes through multiple physical states during construction: solid feedstock, molten processing, then solidified structure. Each state transition introduces specific defect modes.", "maps_to": ["state_multiplicity", "transition_defects", "phase_path", "state_dependent_failure"]}
    ],
    "engineering_air_traffic.yaml": [
        {"name": "separation_minimum_invariant", "abstract": "A hard minimum distance between agents must always be maintained. All system optimization occurs subject to this non-negotiable constraint.", "maps_to": ["hard_constraint", "minimum_separation", "safety_invariant", "optimization_under_constraint"]},
        {"name": "handoff_coordination", "abstract": "Agents cross jurisdictional boundaries requiring smooth transfer of responsibility between controllers — the handoff boundary is the most failure-prone point.", "maps_to": ["responsibility_transfer", "boundary_vulnerability", "coordination_handoff", "jurisdictional_friction"]}
    ],
    "engineering_grid.yaml": [
        {"name": "inertia_as_buffer", "abstract": "Rotational mass in generators provides short-term energy buffering against sudden imbalances, giving the system seconds to respond before frequency collapses.", "maps_to": ["rotational_inertia", "short_term_buffer", "response_window", "momentum_damping"]},
        {"name": "reactive_power_management", "abstract": "Voltage stability depends on reactive power flow, which does no real work but must be supplied locally — the reactive power balance is structurally separate from the real power balance.", "maps_to": ["parallel_resource", "local_balance", "structural_separation", "voltage_stability"]}
    ],
    "engineering_semiconductor.yaml": [
        {"name": "quantum_confinement", "abstract": "When device dimensions approach the carrier wavelength, classical physics breaks down and quantum effects dominate — shrinking further changes behavior qualitatively, not just quantitatively.", "maps_to": ["scale_dependent_physics", "quantum_transition", "dimensional_crossover", "nonlinear_scaling"]},
        {"name": "leakage_power_floor", "abstract": "Even when the device is nominally off, subthreshold leakage current flows and generates heat. As dimensions shrink, the off-state leakage rises exponentially, creating a power floor.", "maps_to": ["baseline_leakage", "exponential_growth", "minimum_dissipation", "thermal_floor"]}
    ],
    "engineering_tensegrity.yaml": [
        {"name": "deployability_through_foldability", "abstract": "The structure can transition between a compact folded state and a fully deployed state through kinematic reconfiguration without component removal.", "maps_to": ["state_transition", "compact_deployment", "kinematic_path", "reversible_reconfiguration"]},
        {"name": "self_stress_optimization", "abstract": "Internal stress levels across the network must be balanced — over-stress in one cable destabilizes the entire equilibrium configuration.", "maps_to": ["stress_balancing", "equilibrium_sensitivity", "network_optimization", "cascade_instability"]}
    ],
    "linguistics_phonology.yaml": [
        {"name": "maximal_onset_assignment", "abstract": "When dividing sound sequences, the system assigns as many boundary consonants to the following position as the language's constraints permit — preferring to begin new units with maximal material.", "maps_to": ["boundary_optimization", "forward_assignment", "constraint_permit", "onset_preference"]},
        {"name": "prosodic_hierarchy", "abstract": "Sound organization operates at multiple nested scales: segment, syllable, foot, phonological word, phrase, utterance — each level constrains the ones below it.", "maps_to": ["nested_scales", "hierarchical_constraint", "multi_level_organization", "scale_dependence"]}
    ],
    "linguistics_pragmatics.yaml": [
        {"name": "shared_context_presumption", "abstract": "Communication presumes a shared background of knowledge and beliefs. What is not said is as important as what is said — the unsaid relies on shared context.", "maps_to": ["presumed_overlap", "context_dependence", "implicit_knowledge", "shared_ground"]},
        {"name": "gricean_quantity_optimization", "abstract": "Speakers provide exactly as much information as needed — no more (redundancy) and no less (ambiguity). Deviations signal intentional meaning beyond the literal.", "maps_to": ["information_calibration", "optimal_amount", "deviation_signal", "literal_bounded_meaning"]}
    ],
    "math_dynamical_systems.yaml": [
        {"name": "invariant_measure", "abstract": "Despite individual trajectory unpredictability, the proportion of time spent in any region converges to a stable distribution — statistical predictability emerges from deterministic chaos.", "maps_to": ["statistical_stability", "time_average_convergence", "ensemble_equivalence", "emergent_statistics"]},
        {"name": "lyapunov_exponent_spectrum", "abstract": "The rate of divergence in each dimension of the system's state space quantifies sensitivity, stability, and overall chaos level through the full spectrum of exponents.", "maps_to": ["divergence_rate", "dimensional_stability", "chaos_quantification", "exponent_spectrum"]}
    ],
    "math_information_theory.yaml": [
        {"name": "prefix_free_coding", "abstract": "Messages are encoded so that no codeword is a prefix of another, enabling unambiguous decoding without delimiters. The entropy of the source determines the minimum average codeword length.", "maps_to": ["unambiguous_decoding", "delimiter_free", "entropy_minimum", "optimal_encoding"]},
        {"name": "entropy_power_inequality", "abstract": "Combining two independent sources of randomness produces more entropy than either alone — the combined system is inherently less predictable than its parts.", "maps_to": ["randomness_accumulation", "combined_entropy", "independence_boost", "predictability_reduction"]}
    ],
    "math_queueing.yaml": [
        {"name": "burstable_capacity_design", "abstract": "Designing for sustained peak utilization wastes resources; instead, systems provide excess capacity for bursts with bounded overflow probability.", "maps_to": ["peak_vs_sustained", "overflow_bounding", "burst_accommodation", "probabilistic_capacity"]},
        {"name": "jackson_network_decomposition", "abstract": "Networks of queues with Poisson arrivals and exponential service decompose into independent single queues, enabling analysis of complex systems by solving each component separately.", "maps_to": ["independent_decomposition", "product_form_solution", "separable_analysis", "network_factorization"]}
    ],
    "military_deception.yaml": [
        {"name": "controlled_information_leakage", "abstract": "Selectively allowing some true information to be discovered establishes target confidence in the source, making subsequent deception more credible.", "maps_to": ["credibility_establishment", "selective_truth", "source_validation", "trust_building"]},
        {"name": "ambiguous_signal_generation", "abstract": "Rather than sending clearly false information, the system generates signals that are consistent with multiple interpretations — only the favored one becomes obvious in hindsight.", "maps_to": ["multi_interpretation", "retroactive_clarity", "plausible_deniability", "signal_ambiguity"]}
    ],
    "military_naval.yaml": [
        {"name": "depth_advantage_exploitation", "abstract": "Operating in a medium where vertical positioning confers asymmetric advantages — the agent below can detect the agent above while remaining undetected.", "maps_to": ["asymmetric_detection", "vertical_stratification", "depth_advantage", "three_dimensional_positioning"]},
        {"name": "endurance_as_weapon", "abstract": "The ability to remain on station for extended periods without resupply creates positional advantage — the endurance-limited adversary must withdraw, ceding the operational area.", "maps_to": ["endurance_advantage", "persistent_presence", "logistical_limit", "attrition_through_presence"]}
    ],
    "physics_superconductivity.yaml": [
        {"name": "macroscopic_quantum_coherence", "abstract": "Below the critical temperature, a macroscopic fraction of particles occupies a single quantum state, producing collective behavior impossible for individual particles.", "maps_to": ["collective_quantum_state", "macroscopic_coherence", "fraction_condensation", "emergent_quantum_behavior"]},
        {"name": "energy_gap_protection", "abstract": "A finite energy gap separates the ground state from excited states, protecting the coherent state from small perturbations that lack sufficient energy to break it.", "maps_to": ["energy_barrier", "perturbation_immunity", "state_protection", "threshold_defense"]}
    ],
    "psychology_prospect.yaml": [
        {"name": "framing_dependency", "abstract": "The same objective outcome, described in different frames (gain vs loss, status quo vs change), produces systematically different decisions due to reference-point dependence.", "maps_to": ["description_dependence", "reference_framing", "description_invariance_violation", "context_dependent_preference"]},
        {"name": "certainty_effect", "abstract": "Outcomes that are certain (probability = 1) are overweighted relative to outcomes that are merely probable — the gap between 99% and 100% looms larger than between 60% and 61%.", "maps_to": ["certainty_overweighting", "boundary_spike", "probability_nonlinearity", "absolute_vs_relative"]}
    ],
    "psychology_social.yaml": [
        {"name": "status_hierarchy_formation", "abstract": "Any group of interacting agents spontaneously develops a dominance hierarchy, even when members value equality. The hierarchy reasserts itself even after active suppression.", "maps_to": ["spontaneous_hierarchy", "status_dynamics", "equality_resistance", "natural_dominance"]},
        {"name": "information_cascade_failure", "abstract": "Agents sequentially make decisions based on others' prior choices rather than private information, producing collective agreement that is confident but may be entirely wrong.", "maps_to": ["sequential_agreement", "private_signal_suppression", "herding_dynamics", "confidence_accuracy_gap"]}
    ],
    "sports_boxing.yaml": [
        {"name": "energy_pacing_strategy", "abstract": "Finite energy reserves must be allocated across the full duration of engagement — early expenditure that exceeds sustainable rate creates late-stage vulnerability regardless of skill.", "maps_to": ["resource_pacing", "sustainable_rate", "duration_planning", "late_vulnerability"]},
        {"name": "distance_management_initiative", "abstract": "Control of the distance at which engagement occurs is more strategically valuable than individual technique — the agent controlling distance controls the terms of interaction.", "maps_to": ["engagement_range_control", "strategic_distance", "interaction_terms", "range_advantage"]}
    ],
    "sports_chess.yaml": [
        {"name": "zugzwang_constraint", "abstract": "Forcing the opponent into a position where any move worsens their situation — the obligation to act becomes the vulnerability itself. Passivity would be preferable but is not allowed.", "maps_to": ["forced_action_vulnerability", "obligation_as_weakness", "no_good_move", "compulsory_degradation"]},
        {"name": "endgame_principle_transformation", "abstract": "The relative valuations of components change as the game progresses: a piece that is strong with many other pieces present becomes weak in isolation, and vice versa.", "maps_to": ["context_dependent_value", "component_revaluation", "density_dependence", "stage_specific_strategies"]}
    ],
}

# Also need to handle files that had syntax errors (missing commas etc.)
# Those will need manual review

base = Path(__file__).parent / "library"
fixed = 0
errors = 0

for fname, new_pats in fixes.items():
    fp = base / fname
    if not fp.exists():
        print(f"  ❌ NOT FOUND: {fname}")
        errors += 1
        continue

    content = fp.read_text()
    d = yaml.safe_load(content)
    current_count = len(d.get("structural_patterns", []))

    if current_count >= 5:
        print(f"  ⏭️ {fname}: already {current_count} patterns")
        continue

    # Find injection_prompt position
    ipos = content.find('\ninjection_prompt:')
    if ipos == -1:
        ipos = content.find('injection_prompt:')
        if ipos == -1:
            print(f"  ❌ {fname}: no injection_prompt found")
            errors += 1
            continue

    # Build new patterns YAML
    entries = []
    for p in new_pats:
        # Quote abstract if it contains colons not followed by space
        abstract = p['abstract']
        if ': ' in abstract and '"' not in abstract:
            abstract = f'"{abstract}"'
        entry = f"\n  - name: {p['name']}\n    abstract: {abstract}\n    maps_to: [{', '.join(p['maps_to'])}]"
        entries.append(entry)

    insert = '\n'.join(entries) + '\n'
    new_content = content[:ipos] + insert + content[ipos:]

    # Validate
    try:
        d2 = yaml.safe_load(new_content)
        new_count = len(d2.get("structural_patterns", []))
        if new_count >= 5:
            fp.write_text(new_content)
            print(f"  ✅ {fname}: {current_count} → {new_count} patterns")
            fixed += 1
        else:
            print(f"  ❌ {fname}: after fix still only {new_count}")
            errors += 1
    except yaml.YAMLError as e:
        print(f"  ❌ {fname}: YAML error: {e}")
        errors += 1

print(f"\nDone: {fixed} fixed, {errors} errors")
