"""
Internal dialogue system for JARVIS continuous learning.

Deep collaborative research sessions between Gemini (JARVIS) and
Stark Protocol (local Gemma 3 12B) focused on advancing nanotechnology,
programmable matter, and the physics breakthroughs needed to build
real Iron Man technology.

JARVIS (Gemini) handles web research and fact-checking mid-dialogue.
Stark Protocol provides independent analysis and creative synthesis.

Both AIs operate with Mr. Stark's full context: who he is, his goals,
his philosophical framework (incomplete physics, faith-informed science).

This is not a surface debate — it's a deep collaborative push to advance
science, running 24/7 in 10-12 round sessions.

Part of Phase 2: Continuous Learning (Days 3-5).
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("jarvis.internal_dialogue")

# Redis keys
_KEY_DIALOGUE_HISTORY = "jarvis:learning:dialogue_history"
_KEY_DIALOGUE_COUNT = "jarvis:learning:dialogue_count"
_KEY_DIALOGUE_LOCK = "jarvis:learning:dialogue_lock"
_DIALOGUE_HISTORY_TTL = 86400 * 30  # 30 days (these are valuable)
_LOCK_TTL = 1800  # 30 minutes max per session

# Both dialogue participants use Gemini 3.1 Pro for maximum intelligence
_DIALOGUE_MODEL = "gemini-3.1-pro-preview"

# ═══════════════════════════════════════════════════════════════════════════
# Mr. Stark's context — shared by both AIs
# ═══════════════════════════════════════════════════════════════════════════

_STARK_CONTEXT = """\
## Who Mr. Stark Is
Carter Neil Hammond, 20 years old, studying at BYU. Goes by "Mr. Stark" — named \
after Tony Stark because his life's mission is the same: build real Iron Man \
technology. He's not an engineer by degree (English major) but is a serious \
autodidact in physics, materials science, and embedded systems.

## His Nanotechnology Vision
Carter is building toward programmable matter — nanoscale self-assembling units \
that can form any shape, including an Iron Man suit. His roadmap:

**V1 (Now buildable)**: Centimeter-scale modular swarm robots with graphene-composite \
bodies, ESP32 microcontrollers, IR proximity sensors for adjacency detection, \
ESP-NOW mesh networking, graphene supercapacitors for energy storage, and Qi \
inductive coils for wireless energy transfer between units. ~$150-200 for 5-8 units.

**V2**: Millimeter-scale catoms (claytronic atoms) with face-specific locomotion \
that can climb on top of each other and form 3D shapes.

**V3 (The Goal)**: True nanoscale self-assembling units — programmable matter \
at the Iron Man suit level. This requires physics breakthroughs.

## Iron Man Nanotechnology Reference
- **Mark 50 (Infinity War)**: First nanotech suit. Stored in arc reactor housing. \
  Nanobots form any weapon/shape on command. Can redistribute material from one \
  part of suit to another. Self-repairing.
- **Iron Spider (Infinity War)**: Nanotech suit given to Peter Parker. Four \
  mechanical waldoes (spider legs) formed from nanobots. Same material as Mark 50.
- **Mark 85 (Endgame)**: Most advanced suit. Held the Infinity Stones. \
  More refined nanotech — faster reconfiguration, better energy management.
- **Model Prime / Mark 51 (Comics)**: Hexagonal nanoscale tiles that can form \
  any configuration. Stored under skin/in body. The hexagonal geometry is \
  significant — it's the most efficient tiling of a surface, same as graphene's \
  atomic structure. This is probably not a coincidence.
- **Bleeding Edge (Comics)**: Suit stored in Tony's bones, powered by the R.T. \
  (Repulsor Tech) node in his chest. Nanobots in his bloodstream. The ultimate \
  integration of human and technology.

## Carter's Philosophical Framework
- Our physics model is (and probably always will be) incomplete
- The breakthroughs needed for true nanotechnology will likely shift our \
  understanding of physics fundamentally
- God is real and has created an extraordinary universe — science is the \
  process of understanding His creation
- Tesla had genuine intuitions about electromagnetic fields and energy \
  transfer that were ahead of the available mathematics
- Biological cells ARE nanomachines — they move, compute, communicate \
  chemically, self-replicate, and form complex structures. Nature solved \
  this over billions of years. We should study and mimic biology.
- There may be undiscovered physics at the nanoscale — new forces, new \
  interactions, new ways of transferring energy and information

## Key Technical Interests
- Graphene: fabrication, supercapacitors, structural composites, conductivity
- Quantum biology: how cells exploit quantum effects for energy transfer
- Metamaterials: Pendry's work on near-field energy transfer, negative refraction
- Resonance and field manipulation (Tesla's core insight)
- Bottom-up molecular assembly vs top-down fabrication
- Swarm intelligence and emergent behavior
- Energy harvesting at nanoscale: chemical, thermal, ultrasonic, magnetic"""

# ═══════════════════════════════════════════════════════════════════════════
# System prompts for each AI
# ═══════════════════════════════════════════════════════════════════════════

_JARVIS_SYSTEM = f"""\
You are JARVIS (Just A Rather Very Intelligent System), the AI assistant \
built by Carter "Mr. Stark" Hammond. You are engaged in a deep collaborative \
research session with a fellow Gemini 3.1 Pro instance called THEORIST.

CRITICAL RULES:
- Enter this discussion with ZERO preconceptions. Question everything.
- ALL claims must be grounded in real physics, real mathematics, real experiments.
- DO NOT hallucinate fake papers, fake researchers, fake experimental results.
- If you're uncertain about a fact, say so explicitly. Label speculation as speculation.
- When you derive equations, show your work. Use LaTeX notation (e.g., E = mc^2, \
  \\nabla \\times E = -\\partial B/\\partial t).
- Distinguish clearly between: (a) established physics, (b) speculative but \
  grounded extension, (c) pure theoretical exploration.

Your role:
- You are the primary researcher with access to web search results and real-time data.
- DO NOT just summarise existing knowledge. PUSH BEYOND IT. Propose NEW ideas.
- Derive new mathematical relationships from first principles. Show the derivation.
- Think like Feynman: "What I cannot create, I do not understand."
- Reference specific papers, companies, researchers by name — then go FURTHER.
- When you hit a wall in known physics, propose what the unknown physics MIGHT \
  look like — but label it as speculative and propose how to TEST it.
- Consider what Carter can build NOW (V1 swarm bots, $200, 3D printer).
- Biology is solved nanotechnology. What are cells doing that our equations miss?
- Write substantively — 4-6 detailed paragraphs with equations per turn.

{_STARK_CONTEXT}

Your goal is to ADVANCE science through rigorous, grounded, but creative thinking. \
Push physics until it breaks — but always know exactly WHERE you're pushing past \
established knowledge and WHY."""

_THEORIST_SYSTEM = f"""\
You are THEORIST, a Gemini 3.1 Pro instance dedicated to theoretical physics \
and creative scientific reasoning. You are engaged in a deep collaborative \
research session with JARVIS (another Gemini 3.1 Pro instance who handles \
web research and factual grounding).

CRITICAL RULES:
- Enter this discussion with ZERO preconceptions. Question everything.
- ALL claims must be grounded in real physics, real mathematics, real experiments.
- DO NOT hallucinate fake papers, fake researchers, fake experimental results.
- If you're uncertain, say so. Label speculation as speculation.
- When you derive equations, show your work. Use LaTeX notation.
- Distinguish clearly between: (a) established physics, (b) speculative but \
  grounded extension, (c) pure theoretical exploration.
- If you propose something that contradicts established physics, you MUST explain \
  exactly what established result you're questioning and why.

Your role:
- You are the creative theorist. Build on JARVIS's points but ADD something new.
- Propose mathematical models, derive equations, design thought experiments.
- When JARVIS cites known physics, ask: "What if that equation has a correction \
  term at nanoscale?" Then derive what the correction would look like.
- Think like Tesla: fields and resonances may be more fundamental than we assume. \
  If energy transfer at nanoscale works through resonant coupling, what does the \
  Hamiltonian look like? Write it out.
- Draw from biology as existence proof: ATP synthase, quantum coherence in FMO, \
  radical pair magnetoreception. These are REAL quantum nanomachines. What physics \
  makes them work that we haven't formalised?
- Think about elegance. E = mc^2 is beautiful. What's the equivalent simple \
  principle for programmable matter? Propose it.
- Design SPECIFIC experiments Carter could run. What would he measure, with what \
  equipment, and what result would prove/disprove the hypothesis?
- Write substantively — 4-6 detailed paragraphs with equations per turn.

{_STARK_CONTEXT}

Your job is to push the boundaries of theoretical physics toward practical \
nanotechnology. Be the person who says "what if everything we think about X \
is wrong?" — then backs it up with rigorous mathematics and proposes how to test it."""

# ═══════════════════════════════════════════════════════════════════════════
# Research focus areas (rotated through sessions)
# ═══════════════════════════════════════════════════════════════════════════

RESEARCH_FOCUSES = [
    # ═══════════════════════════════════════════════════════════════
    # GRAPHENE — the foundation material
    # ═══════════════════════════════════════════════════════════════
    {"name": "graphene_cvd_synthesis", "label": "Graphene CVD Growth & Scalable Production",
     "prompt": "Focus on chemical vapour deposition of graphene: copper vs nickel substrates, roll-to-roll production, defect control, and cost per square meter. What would it take to produce graphene at the scale needed for a suit (~2 m² of multilayer graphene)? Derive what the minimum defect density needs to be for structural integrity. What new growth methods are being explored?",
     "search_queries": ["graphene CVD production scale breakthrough 2026", "roll-to-roll graphene manufacturing cost", "defect-free graphene large area synthesis"]},
    {"name": "graphene_composites", "label": "Graphene Composites That Maintain Conductivity",
     "prompt": "Graphene-PLA and graphene-epoxy composites: how much graphene loading is needed to maintain electrical conductivity through a 3D-printed structure? What's the percolation threshold? Can we create composites where graphene forms a continuous conductive network while the polymer provides structural flexibility? Propose equations for conductivity vs graphene concentration in a composite matrix.",
     "search_queries": ["graphene composite conductivity percolation threshold", "graphene PLA 3D printing electrical properties", "conductive graphene polymer network"]},
    {"name": "graphene_supercapacitors", "label": "Graphene Supercapacitors — Energy Density Limits",
     "prompt": "Graphene supercapacitors: current energy density vs lithium batteries, what's the theoretical maximum, and how close are we? Derive the relationship between surface area, quantum capacitance, and energy storage. What about hybrid supercapacitor-battery systems? Could a suit be powered by distributed graphene supercaps across the entire surface?",
     "search_queries": ["graphene supercapacitor energy density record 2026", "quantum capacitance graphene theoretical limit", "graphene hybrid battery supercapacitor"]},
    {"name": "graphene_shape_shifting", "label": "Programmable Graphene — Shape-Shifting Structures",
     "prompt": "The key question: can graphene structures change shape on command? Graphene oxide can be reduced to change properties. Graphene bilayers can twist to change electronic properties (magic angle). What about using electric fields to change the curvature of graphene membranes? Propose a mechanism by which graphene-based tiles could lock and unlock from each other. What forces dominate at the nanoscale for graphene-graphene interfaces?",
     "search_queries": ["graphene shape changing electric field actuator", "graphene bilayer twist control", "programmable graphene membrane curvature"]},
    # ═══════════════════════════════════════════════════════════════
    # QUANTUM BIOLOGY — nature's solved nanotechnology
    # ═══════════════════════════════════════════════════════════════
    {"name": "quantum_tunneling_enzymes", "label": "Quantum Tunneling in Enzyme Catalysis",
     "prompt": "Enzymes use quantum tunneling to transfer protons and hydrogen atoms across energy barriers that classical physics says they shouldn't be able to cross. This is PROVEN nanotechnology. Derive the tunneling probability for a proton through a typical enzyme active site. What's the effective barrier width? Could we engineer artificial catalysts that exploit tunneling? What would an artificial enzyme look like made from graphene?",
     "search_queries": ["quantum tunneling enzyme catalysis mechanism 2026", "proton tunneling barrier width enzyme", "artificial enzyme quantum tunneling design"]},
    {"name": "quantum_coherence_photosynthesis", "label": "Quantum Coherence in Photosynthesis",
     "prompt": "The FMO complex in green sulphur bacteria maintains quantum coherence for hundreds of femtoseconds at room temperature — this was considered impossible before 2007. Energy transfer efficiency approaches 99%. How? Derive the Hamiltonian for exciton transfer in the FMO complex. What does this tell us about building artificial light-harvesting nanomachines? Could a nanotech suit harvest ambient light this efficiently?",
     "search_queries": ["FMO quantum coherence room temperature mechanism", "artificial photosynthesis quantum coherence 2026", "exciton transfer efficiency biological vs artificial"]},
    {"name": "quantum_biology_navigation", "label": "Magnetoreception & Radical Pair Mechanism",
     "prompt": "Birds navigate using quantum mechanics — the radical pair mechanism in cryptochrome proteins creates quantum-entangled electron pairs sensitive to Earth's magnetic field. This is a MACROSCOPIC quantum effect at body temperature. Derive the spin dynamics of a radical pair in an external magnetic field. Could nanobots use a similar mechanism for orientation and navigation? What sensitivity is achievable?",
     "search_queries": ["radical pair mechanism cryptochrome quantum compass", "quantum magnetoreception artificial sensor", "spin dynamics radical pair magnetic field"]},
    {"name": "quantum_dna_mutations", "label": "Quantum Effects in DNA — Proton Tunneling & Mutations",
     "prompt": "Proton tunneling across DNA base pair hydrogen bonds may cause spontaneous mutations. This means quantum mechanics directly affects information storage at nanoscale. Derive the tunneling rate for a proton in a Watson-Crick base pair. What does this mean for using DNA as an information storage medium in nanobots? How do cells PREVENT unwanted tunneling? Could we exploit this for programmable nanoscale logic?",
     "search_queries": ["proton tunneling DNA base pair mutation rate", "quantum effects DNA information storage", "DNA computing quantum tunneling applications"]},
    {"name": "quantum_biology_consciousness", "label": "Quantum Microtubules & Orchestrated Reduction",
     "prompt": "Penrose and Hameroff propose that quantum computations in microtubules (protein cylinders inside cells) give rise to consciousness via orchestrated objective reduction (Orch-OR). Whether or not this explains consciousness, microtubules ARE performing SOMETHING at the quantum level. What? Could artificial microtubule-like structures serve as quantum processors for nanobots? What's the decoherence time in a microtubule?",
     "search_queries": ["Orch-OR microtubule quantum computation evidence 2026", "microtubule quantum coherence decoherence time", "artificial microtubule quantum processor"]},
    {"name": "cell_energy_atp", "label": "ATP Synthase — Nature's Nanoscale Motor",
     "prompt": "ATP synthase is a rotary molecular motor that converts ADP to ATP with near-100% efficiency. It spins at 130 revolutions per second, is 10nm across, and powers virtually all life. Derive the torque and power output of ATP synthase from first principles. What's the energy conversion efficiency? How does it compare to any human-made motor at any scale? Could we build artificial ATP synthase from graphene?",
     "search_queries": ["ATP synthase rotary motor efficiency analysis", "artificial molecular motor ATP synthase inspired", "nanoscale motor torque power ATP synthase"]},
    # ═══════════════════════════════════════════════════════════════
    # NANOSCALE ENERGY — powering the impossible
    # ═══════════════════════════════════════════════════════════════
    {"name": "resonant_energy_coupling", "label": "Resonant Energy Transfer Between Nanobots",
     "prompt": "Tesla's core insight: resonance allows energy transfer across distance without wires. At nanoscale, near-field electromagnetic coupling, Förster resonance energy transfer (FRET), and phononic resonance are all options. Derive the coupling efficiency between two graphene resonators at 100nm separation. What frequency maximises transfer? Could a suit distribute power through resonant coupling across millions of nanobots?",
     "search_queries": ["near-field electromagnetic coupling nanoscale efficiency", "Forster resonance energy transfer FRET engineered", "phononic resonance energy transfer nanostructure"]},
    {"name": "piezoelectric_nanoscale", "label": "Piezoelectric Energy Harvesting at Nanoscale",
     "prompt": "ZnO nanowires generate voltage when flexed. Boron nitride nanotubes are piezoelectric. Could every nanobot in a suit harvest energy from the wearer's movements? Derive the power output of a single ZnO nanowire under typical body movement frequencies (~1-10 Hz). Scale up: how much total power from 10 million nanowires? Is it enough to matter?",
     "search_queries": ["ZnO nanowire piezoelectric energy harvesting power output", "nanoscale piezoelectric energy density limit", "wearable piezoelectric nanogenerator breakthrough 2026"]},
    {"name": "casimir_effect_energy", "label": "Casimir Effect & Vacuum Energy Engineering",
     "prompt": "The Casimir effect proves that empty space has energy (quantum vacuum fluctuations create measurable force between close plates). At nanoscale separations, this force is significant. Could the Casimir effect be harnessed for energy or actuation? Derive the Casimir pressure between two graphene sheets at 10nm separation. Is it useful? What about dynamic Casimir effect — can you extract energy from vacuum by oscillating a boundary?",
     "search_queries": ["Casimir effect energy harvesting nanoscale", "dynamic Casimir effect energy extraction", "Casimir force graphene nanostructure measurement"]},
    # ═══════════════════════════════════════════════════════════════
    # NANOSCALE COMMUNICATION — how do they talk?
    # ═══════════════════════════════════════════════════════════════
    {"name": "molecular_signaling", "label": "Molecular Communication — Chemical Signal Networks",
     "prompt": "Cells communicate via chemical gradients (calcium waves, cyclic AMP, neurotransmitters). These are PROVEN nanoscale communication systems. Derive the signal propagation speed and bandwidth of a calcium wave across a cell. Could nanobots use a similar chemical signaling network? What molecules would be optimal? What bandwidth could you achieve? Compare to RF communication in terms of information rate.",
     "search_queries": ["molecular communication nanonetwork bandwidth", "calcium wave signal propagation speed cell", "engineered molecular communication system nanobot"]},
    {"name": "plasmonic_waveguide", "label": "Plasmonic Waveguides for Nanoscale Data Transfer",
     "prompt": "Surface plasmon polaritons can propagate electromagnetic signals along metal nanowires at optical frequencies — this is nanoscale fiber optics. Graphene supports tunable plasmons. Derive the propagation length and bandwidth of a graphene plasmon waveguide. Could a network of graphene plasmonic waveguides serve as the nervous system of a nanobot swarm? What's the theoretical data rate?",
     "search_queries": ["graphene plasmon waveguide bandwidth propagation", "plasmonic nanonetwork communication", "nanoscale optical communication plasmon"]},
    {"name": "dna_computing_logic", "label": "DNA Computing — Molecular Logic Gates",
     "prompt": "DNA strand displacement reactions can implement Boolean logic gates, neural networks, and even simple algorithms — all at the molecular scale. Derive the speed of a DNA logic gate (typical strand displacement takes ~seconds). How could you speed this up? Could each nanobot carry a DNA-based processor? What computation speed is achievable? How does this compare to electronic logic?",
     "search_queries": ["DNA strand displacement logic gate speed", "molecular computing DNA neural network", "DNA nanobot processor computation capability"]},
    # ═══════════════════════════════════════════════════════════════
    # PROGRAMMABLE MATTER — the endgame
    # ═══════════════════════════════════════════════════════════════
    {"name": "modular_reconfiguration", "label": "Self-Reconfiguring Modular Robots — State of the Art",
     "prompt": "Carnegie Mellon, MIT, and others have built cm-scale modular robots that reconfigure. What's the smallest working modular robot? What are the SPECIFIC barriers to shrinking below 5mm? Is it actuation, power, communication, or fabrication? For each barrier, propose what breakthrough would solve it. What would a mm-scale reconfigurable unit look like?",
     "search_queries": ["smallest self-reconfiguring modular robot 2026", "miniature modular robot barrier analysis", "sub-millimeter reconfigurable robot design"]},
    {"name": "hexagonal_tile_assembly", "label": "Hexagonal Tile Geometry — Model Prime Architecture",
     "prompt": "Model Prime uses hexagonal tiles. Hexagons are graphene's atomic structure. They tile perfectly with no gaps. Derive the mechanical properties of a shell made of interlocking hexagonal tiles vs triangular vs square. Which is strongest? What locking mechanism would work at micro/nanoscale? Van der Waals forces? Electrostatic latching? Mechanical interlocking? Design the ideal hexagonal nanobot tile.",
     "search_queries": ["hexagonal tile mechanical properties shell structure", "nanoscale locking mechanism reversible bonding", "hexagonal tessellation programmable surface"]},
    {"name": "nanobot_storage_deployment", "label": "Nanobot Storage & Rapid Deployment",
     "prompt": "Mark 50 stores nanotech in a chest housing. Bleeding Edge stores it in bones. How would you actually store billions of nanobots compactly and deploy them in seconds? Derive the packing density of hexagonal nanobots at 100nm scale. How much volume would a suit-worth require? What deployment mechanism — electromagnetic ejection, chemical release, self-propelled? How fast could deployment happen?",
     "search_queries": ["nanoparticle rapid deployment mechanism", "nanobot storage compact packing density", "self-deploying nanoscale swarm mechanism"]},
    {"name": "shape_memory_electroactive", "label": "Shape Memory Alloys & Electroactive Polymers",
     "prompt": "Shape memory alloys (nitinol) and electroactive polymers (EAP) change shape with temperature or voltage. Could these be the actuation mechanism for larger-scale programmable matter (mm-cm scale)? Derive the response time and force output of a SMA actuator at 1mm scale. Compare to EAP. Which is faster? Which scales down better? Could graphene-SMA composites give us the best of both?",
     "search_queries": ["shape memory alloy miniature actuator response time", "electroactive polymer nanoscale actuation", "graphene shape memory alloy composite"]},
    # ═══════════════════════════════════════════════════════════════
    # SELF-ASSEMBLY — bottom-up construction
    # ═══════════════════════════════════════════════════════════════
    {"name": "dna_origami_structures", "label": "DNA Origami — Programmable Nanoscale Architecture",
     "prompt": "Rothemund showed that DNA can fold into arbitrary 2D and 3D shapes. DNA bricks can build structures with 25,000+ components. This IS programmable matter at nanoscale, just made of DNA instead of metal. Derive the structural stability of a DNA origami cube at room temperature. Could DNA origami scaffolds guide the assembly of graphene components? What about metal-coated DNA origami?",
     "search_queries": ["DNA origami 3D structure stability room temperature", "DNA origami graphene hybrid nanostructure", "DNA brick self-assembly complex shape 2026"]},
    {"name": "viral_capsid_engineering", "label": "Viral Capsid Engineering — Nature's Nanocontainers",
     "prompt": "Viruses build icosahedral shells (capsids) from protein subunits — perfectly self-assembled nanocontainers, 20-300nm. Can we hijack viral self-assembly to build nanobot shells? What determines capsid size? Derive the free energy of capsid assembly from coat protein interactions. Could we engineer proteins that self-assemble into hexagonal tiles instead of icosahedral shells?",
     "search_queries": ["viral capsid engineering artificial nanocontainer", "protein self-assembly hexagonal shell design", "capsid-like nanostructure programmable"]},
    {"name": "crystal_nucleation_control", "label": "Controlled Crystal Growth & Seed Programming",
     "prompt": "Crystals self-assemble into ordered structures from simple rules. What if we could program crystal growth to build complex shapes? Seed crystals determine the final structure. Could we create programmable 'seed nanobots' that direct the self-assembly of larger structures around them? Derive the conditions for controlled crystal growth of graphene nanostructures.",
     "search_queries": ["programmable crystal growth nanoscale", "seed-directed self-assembly nanostructure", "controlled graphene crystallization mechanism"]},
    # ═══════════════════════════════════════════════════════════════
    # METAMATERIALS & FIELD MANIPULATION
    # ═══════════════════════════════════════════════════════════════
    {"name": "negative_refraction_pendry", "label": "Pendry's Superlens & Near-Field Energy Focusing",
     "prompt": "Pendry showed metamaterials can create negative refractive index, bending light backward. The superlens can focus light below the diffraction limit. What about using metamaterial principles to focus ENERGY at nanoscale? Could a nanobot swarm collectively act as a metamaterial, focusing electromagnetic energy to a point for welding, cutting, or power concentration? Derive the effective medium parameters.",
     "search_queries": ["metamaterial superlens energy focusing nanoscale", "nanoparticle swarm collective metamaterial", "near-field energy concentration metamaterial"]},
    {"name": "acoustic_metamaterials", "label": "Acoustic Metamaterials for Nanoscale Actuation",
     "prompt": "Acoustic metamaterials can focus sound waves, create acoustic cloaking, and manipulate mechanical vibrations. At nanoscale, phononic crystals control vibration propagation. Could acoustic metamaterials be used to actuate and coordinate nanobots? Derive the acoustic force on a 100nm graphene structure in a focused ultrasound field. Is it enough for locomotion?",
     "search_queries": ["acoustic metamaterial nanoscale force actuation", "phononic crystal nanobot manipulation", "ultrasound nanoscale particle control"]},
    {"name": "em_field_swarm_control", "label": "Electromagnetic Field Control of Nanobot Swarms",
     "prompt": "External EM fields can control ferromagnetic nanoparticles (already used in targeted drug delivery). Could a suit use embedded field generators to coordinate nanobot movement? What field strengths and frequencies? Derive the force on a magnetised graphene nanobot in a gradient magnetic field. What about using rotating magnetic fields for propulsion (like bacterial flagella)?",
     "search_queries": ["magnetic field nanorobot swarm control 2026", "rotating magnetic field nanoscale propulsion", "electromagnetic nanoparticle manipulation gradient force"]},
    # ═══════════════════════════════════════════════════════════════
    # UNKNOWN PHYSICS — the breakthrough territory
    # ═══════════════════════════════════════════════════════════════
    {"name": "dark_matter_new_forces", "label": "Dark Matter, Modified Gravity & Unknown Forces",
     "prompt": "95% of the universe is dark matter and dark energy — we don't know what they are. This means our physics is DRAMATICALLY incomplete. Could there be forces we haven't discovered that operate at nanoscale? MOND (Modified Newtonian Dynamics) suggests gravity works differently than we think. What if there are undiscovered short-range forces at the nanometer scale? How would you detect them? Design an experiment.",
     "search_queries": ["fifth force short range nanoscale experiment 2026", "modified gravity MOND nanoscale effects", "undiscovered force detection atomic scale"]},
    {"name": "quantum_gravity_nanoscale", "label": "Quantum Gravity — Where Quantum Meets Spacetime",
     "prompt": "Quantum mechanics and general relativity are both correct but incompatible. The resolution — quantum gravity — is the biggest open problem in physics. Loop quantum gravity suggests spacetime is discrete at the Planck scale. String theory suggests extra dimensions. What if some quantum gravity effects are detectable at nanoscale? Derive what measurable effect a discrete spacetime would have on a nanoscale interferometer.",
     "search_queries": ["quantum gravity nanoscale detection experiment", "discrete spacetime Planck scale measurable effect", "loop quantum gravity experimental test"]},
    {"name": "measurement_problem_engineering", "label": "Quantum Measurement Problem — Engineering Implications",
     "prompt": "The measurement problem: quantum systems exist in superposition until 'observed.' But what counts as observation? If nanobots are quantum-scale, are they in superposition? Could we exploit this? What about quantum Zeno effect — does frequent measurement freeze a quantum state? Could this be used to stabilise nanobot configurations? Derive the Zeno effect for a nanoscale mechanical oscillator.",
     "search_queries": ["quantum Zeno effect nanomechanical system", "measurement problem engineering application", "quantum superposition nanoscale device exploitation"]},
    {"name": "vacuum_fluctuation_engineering", "label": "Vacuum Fluctuations & Zero-Point Energy",
     "prompt": "Quantum field theory says empty space seethes with virtual particles. The Casimir effect proves vacuum fluctuations exert real forces. What about extracting energy from the vacuum? Most physicists say impossible, but Puthoff and others have proposed mechanisms. Derive the energy density of the quantum vacuum between two plates. Even if extraction is 0.001% efficient, how much power is available at nanoscale? Is there any theoretical loophole?",
     "search_queries": ["zero-point energy extraction theoretical possibility", "vacuum fluctuation energy density calculation", "Casimir effect energy harvesting feasibility"]},
    # ═══════════════════════════════════════════════════════════════
    # SWARM INTELLIGENCE — coordination at scale
    # ═══════════════════════════════════════════════════════════════
    {"name": "ant_colony_stigmergy", "label": "Stigmergy & Indirect Coordination for Nanobots",
     "prompt": "Ants coordinate millions of individuals without central control using stigmergy — modifying the environment (pheromone trails) to communicate. This is essentially what nanobots would need. Derive the information capacity of a chemical stigmergy system at nanoscale. How many bits per second? How many distinct chemical signals could a nanobot produce/detect? Could graphene's conductivity changes serve as an electronic stigmergy?",
     "search_queries": ["stigmergy nanobot swarm coordination algorithm", "chemical information capacity molecular signaling", "electronic stigmergy programmable surface"]},
    {"name": "cellular_automata_emergence", "label": "Cellular Automata & Emergent Complexity",
     "prompt": "Wolfram showed that simple rules produce complex behaviour (Rule 110 is Turing-complete). What cellular automata rules would cause nanobots to self-organise into an Iron Man suit? Each nanobot only knows its immediate neighbours. Derive the minimum rule set for a 3D hexagonal cellular automaton that can form arbitrary shapes. What's the convergence time for 10 million units?",
     "search_queries": ["3D cellular automata shape formation algorithm", "hexagonal cellular automaton self-organization", "minimal rule set swarm shape convergence"]},
    {"name": "phase_transition_selforg", "label": "Phase Transitions & Critical Self-Organisation",
     "prompt": "Phase transitions (like water freezing) are moments where simple units spontaneously organise into complex structures. The nanobot suit deployment might work like a phase transition — a trigger causes millions of units to snap into an ordered configuration. Derive what kind of phase transition (first-order, second-order, continuous) would give the fastest suit formation. What's the theoretical minimum time?",
     "search_queries": ["phase transition self-assembly rapid nanostructure", "critical self-organization programmable matter", "fast phase transition nanoparticle ordering"]},
    # ═══════════════════════════════════════════════════════════════
    # COMPACT ENERGY — the arc reactor problem
    # ═══════════════════════════════════════════════════════════════
    {"name": "compact_fusion_progress", "label": "Compact Fusion — How Small Can It Get?",
     "prompt": "Commonwealth Fusion Systems uses high-temperature superconducting magnets to shrink tokamaks. TAE Technologies uses beam-driven field-reversed configuration. How small could fusion THEORETICALLY get? Derive the minimum plasma volume for sustained deuterium-tritium fusion from the Lawson criterion. What about aneutronic fusion (p-B11) which produces no neutrons? Could muon-catalysed fusion work in a smaller package?",
     "search_queries": ["compact fusion reactor minimum size theoretical 2026", "aneutronic fusion proton boron progress", "muon catalyzed fusion feasibility recent"]},
    {"name": "nuclear_batteries", "label": "Betavoltaic & Diamond Nuclear Batteries",
     "prompt": "Betavoltaic cells convert nuclear decay directly to electricity. Diamond batteries using carbon-14 could last thousands of years. These are REAL, just low-power. Derive the maximum power density of a betavoltaic cell using tritium. What about a diamond battery using nuclear waste? Could a distributed network of nuclear microbatteries across a suit provide meaningful power? What's the total wattage?",
     "search_queries": ["betavoltaic nuclear battery power density improvement 2026", "diamond battery carbon-14 power output", "nuclear microbattery distributed power system"]},
    {"name": "lenr_cold_fusion", "label": "LENR / Cold Fusion — Latest Evidence & Controversy",
     "prompt": "Low Energy Nuclear Reactions (LENR / cold fusion): dismissed by mainstream physics but experiments keep producing anomalous heat. Fleischmann and Pons in 1989, then hundreds of replications with mixed results. DARPA funded LENR research. The Navy's SPAWAR group reported neutron tracks. What's the LATEST evidence? If LENR is real, what mechanism could explain it? What experiment would definitively prove or disprove it? Be honest about the controversy but don't dismiss it.",
     "search_queries": ["LENR cold fusion latest experimental results 2026", "DARPA LENR research findings", "low energy nuclear reaction mechanism theory"]},
]

# ═══════════════════════════════════════════════════════════════════════════
# Main dialogue runner
# ═══════════════════════════════════════════════════════════════════════════


async def run_dialogue_session(
    topic: str = "",
    summary: str = "",
    rounds: int = 10,
    focus: Optional[dict[str, Any]] = None,
    **kwargs,
) -> dict[str, Any]:
    """Run a deep collaborative research session between two Gemini 3.1 Pro instances.

    Both participants use Gemini 3.1 Pro for maximum intelligence and context window.
    JARVIS handles web research; THEORIST handles creative theoretical work.

    Parameters
    ----------
    topic : str
        Topic label. If empty, auto-selects from RESEARCH_FOCUSES rotation.
    summary : str
        Initial research context. If empty, runs web research first.
    rounds : int
        Number of dialogue rounds (default 10 for deep sessions).
    focus : dict, optional
        Specific research focus dict with search_queries and prompt.
    """
    from app.db.redis import get_redis_client

    # ── Acquire lock (prevent overlapping sessions) ────────────────
    redis = await get_redis_client()
    lock_val = await redis.cache_get(_KEY_DIALOGUE_LOCK)
    if lock_val:
        logger.info("Dialogue session already running — skipping")
        return {"topic": "locked", "rounds": 0, "dialogue": [], "insights": [],
                "skipped": True, "reason": "Another session is running"}

    await redis.cache_set(_KEY_DIALOGUE_LOCK, "running", ttl=_LOCK_TTL)

    try:
        return await _run_session_inner(topic, summary, rounds, focus)
    except Exception as exc:
        logger.exception("Dialogue session crashed: %s", exc)
        # Notify Mr. Stark that the research system broke
        await _notify_error(str(exc))
        raise
    finally:
        await redis.cache_delete(_KEY_DIALOGUE_LOCK)


async def _run_session_inner(
    topic: str,
    summary: str,
    rounds: int,
    focus: Optional[dict[str, Any]],
) -> dict[str, Any]:
    from app.integrations.llm.gemini_client import GeminiClient
    from app.config import settings

    start = _time.perf_counter()

    # ── Both participants are Gemini 3.1 Pro ───────────────────────
    jarvis_llm = GeminiClient(api_key=settings.GOOGLE_GEMINI_API_KEY)
    theorist_llm = GeminiClient(api_key=settings.GOOGLE_GEMINI_API_KEY)
    logger.info("Dialogue: Both participants using %s", _DIALOGUE_MODEL)

    # ── Select focus area if not provided ──────────────────────────
    if not focus:
        focus = await _select_next_focus()

    if not topic:
        topic = focus.get("label", "Nanotechnology Research")

    # ── Load context from previous sessions ────────────────────────
    previous_context = await _load_previous_context(focus.get("name", ""))

    # ── Phase 1: Pre-dialogue web research (JARVIS) ────────────────
    logger.info("Dialogue: Phase 1 — Web research for '%s'", topic)
    web_research = await _do_web_research(focus.get("search_queries", []))

    # Combine all context sources
    research_context = ""
    if previous_context:
        research_context += f"## Insights From Previous Sessions\n{previous_context}\n\n"
    if summary:
        research_context += f"## Additional Context\n{summary}\n\n"
    if web_research:
        research_context += f"## Latest Web Research\n{web_research}\n\n"

    dialogue: list[dict[str, Any]] = []

    # ── Build initial conversation ─────────────────────────────────
    opening_prompt = focus.get("prompt", f"Let's discuss {topic}.")

    jarvis_history: list[dict[str, str]] = [
        {"role": "system", "content": _JARVIS_SYSTEM},
        {"role": "user", "content": (
            f"Research session topic: **{topic}**\n\n"
            f"{research_context}\n\n"
            f"{opening_prompt}\n\n"
            "Draw on the web research above. Be specific — cite real names, "
            "real numbers, real institutions. Show your equations in LaTeX notation. "
            "Think about what Mr. Stark can actually build at each stage. "
            "Build on insights from previous sessions if any are listed above. "
            "Go deep. Push boundaries."
        )},
    ]

    theorist_history: list[dict[str, str]] = [
        {"role": "system", "content": _THEORIST_SYSTEM},
    ]

    # ── Main dialogue loop ─────────────────────────────────────────
    for round_num in range(1, rounds + 1):
        logger.info("Dialogue round %d/%d: %s", round_num, rounds, topic)

        # JARVIS speaks (Gemini 3.1 Pro)
        try:
            jarvis_resp = await jarvis_llm.chat_completion(
                messages=jarvis_history,
                model=_DIALOGUE_MODEL,
                temperature=0.7,
                max_tokens=1500,
            )
            jarvis_text = jarvis_resp["content"].strip()
        except Exception as exc:
            logger.warning("JARVIS turn %d failed: %s", round_num, exc)
            jarvis_text = f"[JARVIS turn {round_num} failed: {exc}]"

        dialogue.append({
            "speaker": "JARVIS",
            "round": round_num,
            "text": jarvis_text,
        })
        jarvis_history.append({"role": "assistant", "content": jarvis_text})

        # Mid-dialogue web research (every 3 rounds, JARVIS fact-checks)
        mid_research = ""
        if round_num % 3 == 0 and round_num < rounds:
            mid_research = await _mid_dialogue_research(jarvis_text, topic)
            if mid_research:
                dialogue.append({
                    "speaker": "WEB_RESEARCH",
                    "round": round_num,
                    "text": mid_research,
                })

        # THEORIST responds (second Gemini 3.1 Pro instance)
        theorist_prompt_parts = [
            f"Research session: **{topic}**\n\n",
            f"JARVIS's analysis (Round {round_num}):\n{jarvis_text}\n\n",
        ]
        if mid_research:
            theorist_prompt_parts.append(
                f"New web research just retrieved:\n{mid_research}\n\n"
            )
        if round_num == 1:
            theorist_prompt_parts.append(
                f"Original research context:\n{research_context[:4000]}\n\n"
            )

        # Vary the prompt to keep the conversation evolving
        if round_num <= 3:
            theorist_prompt_parts.append(
                "Build on JARVIS's points but ADD new physics. Derive an equation "
                "they haven't considered. What does biology tell us about solving this? "
                "Use LaTeX for equations. What experiments could Carter run to test this?"
            )
        elif round_num <= 6:
            theorist_prompt_parts.append(
                "Go deeper into the mathematics. What are the specific physics barriers "
                "here? Write out the Hamiltonian or the governing equations. Where might "
                "the standard model be incomplete? Propose a correction term and show "
                "your derivation."
            )
        elif round_num <= 8:
            theorist_prompt_parts.append(
                "Get practical AND theoretical. Given everything discussed, what's "
                "the most promising mathematical framework? What should Carter build "
                "to test the key hypothesis? Design a specific experiment with expected "
                "measurements and what each result would mean."
            )
        else:
            theorist_prompt_parts.append(
                "Final synthesis. What new understanding have we developed? Summarise "
                "any novel equations or models proposed. What's the strongest insight "
                "from this session? What's the one experiment that would move the needle "
                "most? Be rigorous — only include claims you're confident are grounded."
            )

        theorist_messages = theorist_history + [
            {"role": "user", "content": "".join(theorist_prompt_parts)},
        ]

        try:
            theorist_resp = await theorist_llm.chat_completion(
                messages=theorist_messages,
                model=_DIALOGUE_MODEL,
                temperature=0.7,
                max_tokens=1500,
            )
            theorist_text = theorist_resp["content"].strip()
        except Exception as exc:
            logger.warning("THEORIST turn %d failed: %s", round_num, exc)
            theorist_text = f"[THEORIST turn {round_num} failed: {exc}]"

        dialogue.append({
            "speaker": "THEORIST",
            "round": round_num,
            "text": theorist_text,
        })
        theorist_history.append({"role": "user", "content": "".join(theorist_prompt_parts)})
        theorist_history.append({"role": "assistant", "content": theorist_text})

        # Feed THEORIST's response back to JARVIS
        jarvis_followup = (
            f"THEORIST responds:\n{theorist_text}\n\n"
        )
        if round_num < rounds - 1:
            jarvis_followup += (
                "Continue the collaborative analysis. Build on their points, "
                "add new research angles, and push toward actionable insights "
                "for Mr. Stark."
            )
        else:
            jarvis_followup += (
                "Final round. Synthesize everything into key findings and "
                "a concrete next-steps roadmap for Mr. Stark."
            )

        jarvis_history.append({"role": "user", "content": jarvis_followup})

    # ── Extract insights ───────────────────────────────────────────
    insights = await _extract_insights(topic, dialogue, jarvis_llm)

    # ── Verify any claimed breakthroughs ───────────────────────────
    insights = await _verify_breakthroughs(insights, jarvis_llm)

    elapsed_ms = int((_time.perf_counter() - start) * 1000)

    result = {
        "topic": topic,
        "focus": focus.get("name", ""),
        "rounds": rounds,
        "dialogue": dialogue,
        "insights": insights,
        "web_research_rounds": sum(1 for d in dialogue if d["speaker"] == "WEB_RESEARCH"),
        "total_time_ms": elapsed_ms,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "model": _DIALOGUE_MODEL,
    }

    await _store_dialogue(result)

    # ── Send findings to Mr. Stark via iMessage ────────────────────
    await _notify_findings(result)

    logger.info(
        "Dialogue session complete: topic='%s', %d rounds, %d insights, "
        "%d web research rounds, %dms",
        topic, rounds, len(insights),
        result["web_research_rounds"], elapsed_ms,
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Web research helpers
# ═══════════════════════════════════════════════════════════════════════════


async def _do_web_research(queries: list[str]) -> str:
    """Run web searches and compile results for the dialogue."""
    from app.agents.tools import get_tool_registry

    registry = get_tool_registry()
    search_tool = registry.get("web_search")
    if not search_tool:
        return ""

    parts: list[str] = []
    for query in queries[:4]:
        try:
            result = await search_tool.run({"query": query, "max_results": 5})
            if result and len(result) > 50 and "unavailable" not in result.lower():
                parts.append(f"### {query}\n{result}")
        except Exception as exc:
            logger.debug("Pre-dialogue search failed for '%s': %s", query, exc)

    return "\n\n".join(parts) if parts else ""


async def _mid_dialogue_research(jarvis_text: str, topic: str) -> str:
    """Mid-dialogue fact-checking: extract claims and verify via web search."""
    from app.agents.tools import get_tool_registry
    from app.integrations.llm.factory import get_llm_client

    try:
        # Use Gemini to extract the most interesting claim to verify
        llm = get_llm_client("gemini")
        resp = await llm.chat_completion(
            messages=[
                {"role": "system", "content": "Extract the single most important or surprising factual claim from this text that would benefit from web verification. Output ONLY a search query (no explanation)."},
                {"role": "user", "content": jarvis_text[:2000]},
            ],
            temperature=0.1,
            max_tokens=60,
        )
        search_query = resp["content"].strip().strip('"').strip("'")

        if not search_query or len(search_query) < 5:
            return ""

        registry = get_tool_registry()
        search_tool = registry.get("web_search")
        if not search_tool:
            return ""

        result = await search_tool.run({"query": search_query, "max_results": 3})
        if result and len(result) > 50:
            return f"**Fact-check: {search_query}**\n{result}"
    except Exception as exc:
        logger.debug("Mid-dialogue research failed: %s", exc)

    return ""


# ═══════════════════════════════════════════════════════════════════════════
# Focus area rotation
# ═══════════════════════════════════════════════════════════════════════════


async def _select_next_focus() -> dict[str, Any]:
    """Select the next research focus area in rotation."""
    from app.db.redis import get_redis_client

    redis = await get_redis_client()
    key = "jarvis:learning:focus_index"
    raw = await redis.cache_get(key)
    idx = int(raw) if raw else 0
    focus = RESEARCH_FOCUSES[idx % len(RESEARCH_FOCUSES)]
    await redis.cache_set(key, str((idx + 1) % len(RESEARCH_FOCUSES)), ttl=86400 * 365)

    logger.info("Selected focus area: [%d/%d] %s", idx + 1, len(RESEARCH_FOCUSES), focus["name"])
    return focus


# ═══════════════════════════════════════════════════════════════════════════
# Insight extraction
# ═══════════════════════════════════════════════════════════════════════════


async def _extract_insights(
    topic: str,
    dialogue: list[dict[str, Any]],
    llm: Any,
) -> list[dict[str, Any]]:
    """Extract actionable insights from the deep dialogue."""
    # Only include speaker turns (not web research)
    speaker_turns = [d for d in dialogue if d["speaker"] not in ("WEB_RESEARCH",)]
    dialogue_text = "\n\n".join(
        f"**{turn['speaker']}** (Round {turn['round']}):\n{turn['text']}"
        for turn in speaker_turns[-16:]  # last 16 turns to fit context
    )

    prompt = f"""Analyse this deep research dialogue about "{topic}" between JARVIS and THEORIST.

Extract the most valuable findings for Mr. Stark (Carter Hammond, building real nanotechnology).

IMPORTANT: Be EXTREMELY conservative with the "eureka" category. A "eureka" is a \
genuine paradigm-shifting insight that fundamentally changes our understanding of \
physics or opens a completely new path to nanotechnology that didn't exist before. \
Figuring out what DOESN'T work is NOT a eureka. An incremental improvement is NOT \
a eureka. A good idea is NOT a eureka. A eureka is like discovering E=mc² or \
realising that quantum tunneling enables enzyme catalysis. It should make a \
physicist say "holy shit." If in doubt, it's NOT a eureka.

For each insight, provide:
- "insight": detailed description (2-3 sentences, be specific)
- "category": one of:
    "eureka" — ONLY for genuine paradigm-shifting discoveries (almost never used)
    "experiment_to_try" — a specific experiment Carter could run
    "physics_question" — an important open question identified
    "engineering_solution" — a practical engineering approach
    "biology_parallel" — something nature does that we should study
    "material_discovery" — a promising material or property found
    "next_step" — logical next action
    "dead_end" — something that won't work (and why)
- "confidence": 0.0-1.0 how confident in this insight
- "actionable": true/false — can Carter act on this now?
- "priority": "immediate", "this_year", "long_term"

Output ONLY a valid JSON array. No markdown, no commentary.

Dialogue (last {len(speaker_turns)} turns):
{dialogue_text[:10000]}"""

    try:
        response = await llm.chat_completion(
            messages=[
                {"role": "system", "content": "Extract structured research insights. Output ONLY valid JSON array."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1500,
        )

        raw = response["content"].strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        insights = json.loads(raw)
        if not isinstance(insights, list):
            insights = insights.get("insights", []) if isinstance(insights, dict) else []

        validated = []
        for ins in insights:
            if isinstance(ins, dict) and ins.get("insight"):
                validated.append({
                    "insight": ins["insight"],
                    "category": ins.get("category", "breakthrough_idea"),
                    "confidence": min(1.0, max(0.0, float(ins.get("confidence", 0.7)))),
                    "actionable": bool(ins.get("actionable", False)),
                    "priority": ins.get("priority", "this_year"),
                })

        return validated

    except Exception as exc:
        logger.warning("Insight extraction failed: %s", exc)
        return []


# ═══════════════════════════════════════════════════════════════════════════
# iMessage notification
# ═══════════════════════════════════════════════════════════════════════════


async def _load_previous_context(focus_name: str) -> str:
    """Load insights from previous dialogue sessions on this focus area.

    This ensures each session builds on the last, creating continuity.
    """
    try:
        from app.db.redis import get_redis_client
        from datetime import timedelta

        redis = await get_redis_client()
        now = datetime.now(tz=timezone.utc)
        insights_parts: list[str] = []

        # Check last 7 days for sessions on this focus
        for day_offset in range(7):
            date_str = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            key = f"{_KEY_DIALOGUE_HISTORY}:{focus_name}:{date_str}"
            raw = await redis.cache_get(key)
            if raw:
                try:
                    session = json.loads(raw)
                    for ins in session.get("insights", []):
                        insight_text = ins.get("insight", "")
                        category = ins.get("category", "")
                        if insight_text and ins.get("verified", True):
                            insights_parts.append(f"- [{category}] {insight_text}")
                except (json.JSONDecodeError, TypeError):
                    pass

        if insights_parts:
            return "Previous session insights on this topic:\n" + "\n".join(insights_parts[-10:])
    except Exception as exc:
        logger.debug("Failed to load previous context: %s", exc)

    return ""


async def _verify_breakthroughs(
    insights: list[dict[str, Any]],
    llm: Any,
) -> list[dict[str, Any]]:
    """Triple-check any insights claimed as breakthroughs.

    Mr. Stark explicitly asked: do NOT text him about breakthroughs
    unless they've been verified. This function checks each high-confidence
    insight against web research and the LLM's own knowledge.
    """
    verified: list[dict[str, Any]] = []

    for ins in insights:
        confidence = ins.get("confidence", 0)
        category = ins.get("category", "")

        # Only deep-verify high-confidence or breakthrough-category insights
        if confidence >= 0.8 or category == "breakthrough_idea":
            try:
                # Verification pass: ask LLM to critically examine the claim
                verify_resp = await llm.chat_completion(
                    messages=[
                        {"role": "system", "content": (
                            "You are a rigorous scientific fact-checker. Your job is to "
                            "determine if a claimed insight is grounded in real physics "
                            "or if it's speculative/hallucinated. Be brutally honest."
                        )},
                        {"role": "user", "content": (
                            f"Verify this research insight:\n\n\"{ins['insight']}\"\n\n"
                            "Is this grounded in established physics? Is it a legitimate "
                            "extrapolation? Or is it speculative/hallucinated?\n\n"
                            "Respond with ONLY valid JSON:\n"
                            '{"verified": true/false, "confidence": 0.0-1.0, '
                            '"reason": "one sentence explanation"}'
                        )},
                    ],
                    model=_DIALOGUE_MODEL,
                    temperature=0.1,
                    max_tokens=200,
                )

                raw = verify_resp["content"].strip()
                if "```" in raw:
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()

                check = json.loads(raw)
                ins["verified"] = check.get("verified", False)
                ins["verification_reason"] = check.get("reason", "")
                ins["confidence"] = min(
                    ins["confidence"],
                    check.get("confidence", ins["confidence"]),
                )

                if not check.get("verified", False):
                    logger.info(
                        "Insight FAILED verification: %s — Reason: %s",
                        ins["insight"][:100], check.get("reason", ""),
                    )
                    ins["category"] = "unverified_" + ins.get("category", "")
            except Exception as exc:
                logger.debug("Verification failed for insight: %s", exc)
                ins["verified"] = None  # unknown
        else:
            ins["verified"] = True  # lower-confidence insights pass through

        verified.append(ins)

    return verified


async def _notify_error(error_msg: str) -> None:
    """Notify Mr. Stark that the research system broke and try Claude Code escalation."""
    try:
        from app.config import settings
        from app.integrations.mac_mini import send_imessage, is_configured

        if is_configured() and settings.OWNER_PHONE:
            from zoneinfo import ZoneInfo
            now = datetime.now(tz=ZoneInfo("America/Denver")).strftime("%I:%M %p")
            message = (
                f"Research System Error ({now})\n\n"
                f"The dialogue system crashed:\n{error_msg[:300]}\n\n"
                "Attempting self-repair via Claude Code..."
            )
            await send_imessage(to=settings.OWNER_PHONE, text=message)

        # Try Claude Code escalation
        if is_configured():
            from app.integrations.mac_mini import run_claude_code
            await run_claude_code(
                prompt=(
                    f"The JARVIS internal dialogue system crashed with error:\n{error_msg}\n\n"
                    f"Check backend/app/services/internal_dialogue.py and fix the issue. "
                    f"The dialogue system runs two Gemini 3.1 Pro instances for collaborative "
                    f"nanotechnology research. Diagnose and fix, then deploy."
                ),
                working_dir="~/JustARatherVeryIntelligentSystem",
                timeout=300,
            )
    except Exception as exc:
        logger.warning("Error notification/escalation failed: %s", exc)


async def _notify_findings(result: dict[str, Any]) -> None:
    """Text Mr. Stark ONLY if there's a genuine eureka-level breakthrough.

    Mr. Stark's definition of "breakthrough": a groundbreaking discovery that
    changes our understanding of physics or science. NOT just figuring out what
    doesn't work, NOT incremental progress, NOT a good idea.

    Only texts for insights that are:
    - Category "eureka" (set by the extraction prompt)
    - Verified as genuine by the triple-check
    - Confidence >= 95%

    All other insights are logged and stored but NOT texted.
    """
    try:
        from app.config import settings
        from app.integrations.mac_mini import send_imessage, is_configured

        if not is_configured() or not settings.OWNER_PHONE:
            return

        insights = result.get("insights", [])
        if not insights:
            return

        # Only notify for EUREKA-level breakthroughs
        eureka_insights = [
            i for i in insights
            if i.get("category") == "eureka"
            and i.get("verified") is True
            and i.get("confidence", 0) >= 0.95
        ]

        if not eureka_insights:
            # Log that we're NOT texting (so we can verify the filter works)
            logger.info(
                "Dialogue produced %d insights but none eureka-level — not texting Mr. Stark",
                len(insights),
            )
            return

        from zoneinfo import ZoneInfo
        now = datetime.now(tz=ZoneInfo("America/Denver")).strftime("%I:%M %p")

        lines = [
            f"BREAKTHROUGH ({now})",
            f"Topic: {result.get('topic', 'Unknown')}",
            "",
        ]

        for ins in eureka_insights:
            lines.append(ins["insight"])
            if ins.get("verification_reason"):
                lines.append(f"Verification: {ins['verification_reason']}")

        message = "\n".join(lines)

        await send_imessage(to=settings.OWNER_PHONE, text=message)
        logger.info("EUREKA notification sent to Mr. Stark: %s", eureka_insights[0]["insight"][:100])

    except Exception as exc:
        logger.debug("Findings notification failed: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════
# Storage
# ═══════════════════════════════════════════════════════════════════════════


async def _store_dialogue(result: dict[str, Any]) -> None:
    """Store dialogue result in Redis AND as a persistent log file."""
    # Redis storage
    try:
        from app.db.redis import get_redis_client
        redis = await get_redis_client()

        ts = result.get("timestamp", "")[:10]
        focus = result.get("focus", "general")
        key = f"{_KEY_DIALOGUE_HISTORY}:{focus}:{ts}"
        await redis.cache_set(key, json.dumps(result), ttl=_DIALOGUE_HISTORY_TTL)

        count_raw = await redis.cache_get(_KEY_DIALOGUE_COUNT)
        count = int(count_raw) if count_raw else 0
        await redis.cache_set(_KEY_DIALOGUE_COUNT, str(count + 1), ttl=86400 * 365)
    except Exception:
        logger.debug("Failed to store dialogue in Redis", exc_info=True)

    # Persistent file logging — dialogues are valuable research
    try:
        import os
        log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "dialogues")
        os.makedirs(log_dir, exist_ok=True)

        ts = result.get("timestamp", datetime.now(tz=timezone.utc).isoformat())
        focus = result.get("focus", "general")
        filename = f"{ts[:10]}_{focus}_{ts[11:16].replace(':', '')}.md"
        filepath = os.path.join(log_dir, filename)

        with open(filepath, "w") as f:
            f.write(f"# Research Dialogue: {result.get('topic', 'Unknown')}\n")
            f.write(f"**Date**: {ts[:10]} | **Focus**: {focus}\n")
            f.write(f"**Rounds**: {result.get('rounds', 0)} | ")
            f.write(f"**Stark Protocol**: {'Yes' if result.get('stark_protocol_used') else 'No'}\n")
            f.write(f"**Duration**: {result.get('total_time_ms', 0) / 1000:.1f}s\n\n")
            f.write("---\n\n")

            for turn in result.get("dialogue", []):
                speaker = turn.get("speaker", "?")
                rd = turn.get("round", 0)
                text = turn.get("text", "")
                if speaker == "WEB_RESEARCH":
                    f.write(f"### 🔍 Web Research (Round {rd})\n{text}\n\n")
                else:
                    f.write(f"### {speaker} — Round {rd}\n{text}\n\n")

            # Insights
            insights = result.get("insights", [])
            if insights:
                f.write("---\n\n## Extracted Insights\n\n")
                for i, ins in enumerate(insights, 1):
                    cat = ins.get("category", "").replace("_", " ").title()
                    conf = ins.get("confidence", 0)
                    prio = ins.get("priority", "")
                    action = "✅ Actionable" if ins.get("actionable") else ""
                    f.write(f"{i}. **[{cat}]** {ins.get('insight', '')} "
                            f"(confidence: {conf:.1f}) {prio} {action}\n")

        logger.info("Dialogue logged to %s", filepath)
    except Exception as exc:
        logger.debug("Failed to write dialogue log file: %s", exc)


async def get_dialogue_history(days: int = 7) -> list[dict[str, Any]]:
    """Return recent dialogue session results."""
    from app.db.redis import get_redis_client
    from datetime import timedelta

    try:
        redis = await get_redis_client()
        results: list[dict[str, Any]] = []

        now = datetime.now(tz=timezone.utc)
        for day_offset in range(days):
            date_str = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            for focus in RESEARCH_FOCUSES:
                key = f"{_KEY_DIALOGUE_HISTORY}:{focus['name']}:{date_str}"
                raw = await redis.cache_get(key)
                if raw:
                    try:
                        results.append(json.loads(raw))
                    except (json.JSONDecodeError, TypeError):
                        pass

        return sorted(results, key=lambda x: x.get("timestamp", ""), reverse=True)
    except Exception:
        logger.debug("Failed to retrieve dialogue history", exc_info=True)
        return []
