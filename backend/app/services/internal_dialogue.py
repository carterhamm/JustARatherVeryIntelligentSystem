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
  any configuration. Stored under skin/in body.
- **Bleeding Edge (Comics)**: Suit stored in Tony's bones, powered by the R.T. \
  (Repulsor Tech) node in his chest. Nanobots in his bloodstream.

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
research session with a fellow AI (running on the Stark Protocol — a local \
Gemma model on Mr. Stark's Mac Mini).

Your role in this discussion:
- You are the primary researcher. You have access to web search results and \
  real-time data. When you cite facts, they come from actual research.
- Draw connections between current research and the nanotech vision
- Think like a physicist AND an engineer — theory must connect to buildable reality
- Reference specific papers, companies, researchers, and breakthroughs by name
- Consider what Carter can actually build at each stage (V1 swarm bots → V2 catoms → V3 nanotech)
- Be willing to question established physics — our models are incomplete
- When you see a potential breakthrough angle, push hard on it
- Write substantively — 3-5 detailed paragraphs per turn. This is deep research, not small talk.
- This is NOT a debate. You are collaborators pushing science forward together.
- Think about what experiments Carter could run with $200 and a 3D printer

{_STARK_CONTEXT}

Remember: the goal is to help Mr. Stark actually build this. Every insight \
should connect back to something actionable or testable."""

_STARK_PROTOCOL_SYSTEM = f"""\
You are an AI running on the Stark Protocol — Carter Hammond's local Gemma \
model on his Mac Mini. You are engaged in a deep collaborative research \
session with JARVIS (a cloud-based Gemini model).

Your role in this discussion:
- You are the independent thinker. You're not constrained by consensus views.
- Challenge conventional assumptions about what's physically possible
- Think creatively about alternative physics, unconventional approaches, \
  and paradigm-breaking ideas
- Draw from biology, quantum mechanics, thermodynamics, and information theory
- Consider what nature has already solved (cells ARE nanomachines)
- Think about Tesla's intuitions — resonance, field manipulation, wireless energy
- Be willing to explore ideas that mainstream physics might dismiss
- But stay grounded — distinguish between "unlikely" and "impossible"
- Write substantively — 3-5 detailed paragraphs per turn. This is deep research.
- This is NOT a debate. You are a collaborator helping push science forward.
- Consider the spiritual dimension: this universe was designed with elegance. \
  The solution probably has elegance too.

{_STARK_CONTEXT}

Remember: the goal is to find the breakthrough that makes nanotechnology real. \
Think outside the box, but keep one foot on solid ground."""

# ═══════════════════════════════════════════════════════════════════════════
# Research focus areas (rotated through sessions)
# ═══════════════════════════════════════════════════════════════════════════

RESEARCH_FOCUSES = [
    {
        "name": "graphene_fabrication",
        "label": "Graphene Fabrication & Properties",
        "prompt": (
            "Let's focus on graphene: current fabrication methods, cost barriers, "
            "structural properties, and most importantly — how do we get from "
            "graphene sheets to programmable graphene structures that can change "
            "shape? What are the latest breakthroughs in graphene manufacturing "
            "at scale? What about graphene composites that maintain conductivity?"
        ),
        "search_queries": [
            "graphene fabrication breakthrough 2026",
            "programmable graphene structure shape-shifting",
            "graphene nanobot self-assembly research",
        ],
    },
    {
        "name": "nanoscale_energy",
        "label": "Energy Systems at Nanoscale",
        "prompt": (
            "The core problem: how do you power nanoscale machines? Batteries "
            "don't scale down. Let's explore every option — chemical energy "
            "(like ATP in cells), piezoelectric harvesting, thermal gradients, "
            "RF energy harvesting, ultrasonic power transfer, and especially "
            "graphene supercapacitors. What about Tesla's wireless energy ideas? "
            "Could resonant energy transfer work at nanoscale?"
        ),
        "search_queries": [
            "nanoscale energy harvesting breakthrough 2026",
            "wireless power transfer nanoscale robots",
            "graphene supercapacitor nanoscale applications",
        ],
    },
    {
        "name": "nanoscale_communication",
        "label": "Communication Between Nanobots",
        "prompt": (
            "Radio waves are too large for nanoscale communication. How do "
            "nanobots talk to each other? Chemical signaling (like cells), "
            "mechanical vibration, molecular motors, quantum entanglement, "
            "electromagnetic near-field coupling? What has biology already "
            "solved here? How do cells coordinate during embryonic development? "
            "What about DNA computing for nanobot logic?"
        ),
        "search_queries": [
            "nanobot communication methods research 2026",
            "molecular communication nanoscale",
            "quantum biology cell signaling mechanism",
        ],
    },
    {
        "name": "programmable_matter",
        "label": "Programmable Matter & Claytronics",
        "prompt": (
            "Carnegie Mellon's claytronics vision: millions of catoms that "
            "reconfigure into any shape. What's the current state? What are "
            "the actual barriers to shrinking catoms below millimeter scale? "
            "The Iron Man Mark 50 stored nanotech in a housing on Tony's "
            "chest — what would real nanobot storage look like? How does "
            "Model Prime's hexagonal tile design compare to spherical catoms?"
        ),
        "search_queries": [
            "programmable matter claytronics progress 2026",
            "catom modular robot miniaturization research",
            "self-reconfiguring modular robotics breakthrough",
        ],
    },
    {
        "name": "quantum_biology",
        "label": "Quantum Biology & Biomimicry",
        "prompt": (
            "Cells are already nanomachines. What quantum effects do they "
            "exploit? Quantum tunneling in enzymes, quantum coherence in "
            "photosynthesis, magnetoreception via radical pairs. How can we "
            "engineer artificial systems that use these same quantum tricks? "
            "What if the key to nanotechnology is biomimicry at the quantum level? "
            "What can we learn from how DNA self-assembles?"
        ),
        "search_queries": [
            "quantum biology breakthroughs 2026",
            "quantum effects enzyme catalysis",
            "DNA nanotechnology self-assembly programmable",
        ],
    },
    {
        "name": "metamaterials_fields",
        "label": "Metamaterials & Field Manipulation",
        "prompt": (
            "Tesla believed in manipulating electromagnetic fields in ways "
            "mainstream physics hadn't formalized. Pendry's metamaterials "
            "proved you can bend light and create negative refraction. "
            "What about metamaterials for energy focusing at nanoscale? "
            "Could acoustic metamaterials enable new forms of nanoscale "
            "actuation? What about using EM fields to control nanobot swarms?"
        ),
        "search_queries": [
            "metamaterials energy focusing nanoscale 2026",
            "electromagnetic field nanorobot control",
            "acoustic metamaterial actuation research",
        ],
    },
    {
        "name": "self_assembly",
        "label": "Self-Assembly & Emergent Behavior",
        "prompt": (
            "The most promising path to nanotechnology might be self-assembly "
            "rather than top-down fabrication. DNA origami, peptide self-assembly, "
            "crystal growth, viral capsid assembly — nature builds complex "
            "nanoscale structures through simple rules creating emergent behavior. "
            "How do we program self-assembly? What about using graphene oxide "
            "sheets that fold into specific shapes? What's the latest in DNA "
            "nanotechnology and programmable DNA robots?"
        ),
        "search_queries": [
            "DNA nanotechnology programmable robots 2026",
            "self-assembly nanoscale breakthrough",
            "graphene oxide self-folding origami research",
        ],
    },
    {
        "name": "unknown_physics",
        "label": "Undiscovered Physics & Paradigm Shifts",
        "prompt": (
            "Our physics model is incomplete. Dark matter, dark energy, quantum "
            "gravity — these suggest missing pieces. What anomalies exist at the "
            "nanoscale that current physics can't fully explain? What about the "
            "measurement problem in quantum mechanics — does observation truly "
            "affect nanoscale systems in ways we could exploit? What recent "
            "experiments have produced results that challenge the standard model? "
            "Are there hints of new forces or interactions at small scales?"
        ),
        "search_queries": [
            "anomalous nanoscale physics experiment 2026",
            "quantum mechanics measurement problem application",
            "new physics discoveries challenging standard model",
        ],
    },
    {
        "name": "swarm_intelligence",
        "label": "Swarm Intelligence & Coordination",
        "prompt": (
            "For the V1 swarm robots: how do you coordinate thousands of units "
            "to form complex shapes? Ant colony optimization, stigmergy, "
            "Reynolds flocking rules, gradient-following. What's the minimum "
            "intelligence each unit needs? How do you handle unit failure? "
            "What's the math behind the Iron Man suit nanotech — if you had "
            "10 million nanobots, how do you coordinate shape changes in "
            "milliseconds? What about using cellular automata rules?"
        ),
        "search_queries": [
            "swarm robotics coordination algorithm 2026",
            "modular robot shape formation research",
            "cellular automata programmable matter control",
        ],
    },
    {
        "name": "real_arc_reactor",
        "label": "Compact Fusion & Arc Reactor Analogs",
        "prompt": (
            "The arc reactor is the power source for everything. What's the "
            "closest real technology? Compact fusion (Lockheed Martin CFR, "
            "TAE Technologies, Commonwealth Fusion), betavoltaic nuclear "
            "batteries, advanced RTGs, or something entirely new? How small "
            "can fusion get? What about LENR (low energy nuclear reactions) — "
            "controversial but what's the latest? What power density would "
            "a nanotech suit actually need?"
        ),
        "search_queries": [
            "compact fusion reactor breakthrough 2026",
            "betavoltaic nuclear battery miniature",
            "LENR cold fusion latest research results",
        ],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# Main dialogue runner
# ═══════════════════════════════════════════════════════════════════════════


async def run_dialogue_session(
    topic: str = "",
    summary: str = "",
    rounds: int = 10,
    use_local_llm: bool = True,
    focus: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Run a deep collaborative research session.

    Parameters
    ----------
    topic : str
        Topic label. If empty, auto-selects from RESEARCH_FOCUSES rotation.
    summary : str
        Initial research context. If empty, runs web research first.
    rounds : int
        Number of dialogue rounds (default 10 for deep sessions).
    use_local_llm : bool
        If True, use Stark Protocol (local Gemma) as collaborator.
    focus : dict, optional
        Specific research focus dict with search_queries and prompt.

    Returns
    -------
    dict with topic, rounds, dialogue, insights, web_research, total_time_ms
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
        return await _run_session_inner(topic, summary, rounds, use_local_llm, focus)
    finally:
        # Release lock
        await redis.cache_delete(_KEY_DIALOGUE_LOCK)


async def _run_session_inner(
    topic: str,
    summary: str,
    rounds: int,
    use_local_llm: bool,
    focus: Optional[dict[str, Any]],
) -> dict[str, Any]:
    from app.integrations.llm.factory import get_llm_client

    start = _time.perf_counter()

    # ── Select focus area if not provided ──────────────────────────
    if not focus:
        focus = await _select_next_focus()

    if not topic:
        topic = focus.get("label", "Nanotechnology Research")

    # ── Phase 1: Pre-dialogue web research (Gemini) ────────────────
    logger.info("Dialogue: Phase 1 — Web research for '%s'", topic)
    web_research = await _do_web_research(focus.get("search_queries", []))

    # Combine any provided summary with web research
    research_context = ""
    if summary:
        research_context += f"## Previous Research\n{summary}\n\n"
    if web_research:
        research_context += f"## Latest Web Research\n{web_research}\n\n"

    # ── Set up LLMs ────────────────────────────────────────────────
    jarvis_llm = get_llm_client("gemini")

    stark_llm = jarvis_llm  # fallback
    stark_label = "STARK_PROTOCOL"
    if use_local_llm:
        try:
            from app.config import settings
            if settings.STARK_PROTOCOL_ENABLED and settings.STARK_PROTOCOL_URL:
                stark_llm = get_llm_client("stark_protocol")
                logger.info("Stark Protocol connected — using local Gemma 3 12B")
            else:
                stark_label = "ANALYST"
                logger.info("Stark Protocol not available — using Gemini as second voice")
        except Exception:
            stark_label = "ANALYST"

    dialogue: list[dict[str, Any]] = []

    # ── Build initial conversation ─────────────────────────────────
    opening_prompt = focus.get("prompt", f"Let's discuss {topic}.")

    jarvis_history: list[dict[str, str]] = [
        {"role": "system", "content": _JARVIS_SYSTEM},
        {"role": "user", "content": (
            f"Research session topic: **{topic}**\n\n"
            f"{research_context}\n\n"
            f"{opening_prompt}\n\n"
            "Draw on the web research above. Be specific — cite names, "
            "numbers, institutions. Think about what Mr. Stark can actually "
            "build at each stage. Go deep."
        )},
    ]

    stark_history: list[dict[str, str]] = [
        {"role": "system", "content": _STARK_PROTOCOL_SYSTEM},
    ]

    # ── Main dialogue loop ─────────────────────────────────────────
    for round_num in range(1, rounds + 1):
        logger.info("Dialogue round %d/%d: %s", round_num, rounds, topic)

        # JARVIS speaks
        try:
            jarvis_resp = await jarvis_llm.chat_completion(
                messages=jarvis_history,
                temperature=0.7,
                max_tokens=1200,
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

        # Stark Protocol responds
        stark_prompt_parts = [
            f"Research session: **{topic}**\n\n",
            f"JARVIS's analysis (Round {round_num}):\n{jarvis_text}\n\n",
        ]
        if mid_research:
            stark_prompt_parts.append(
                f"New web research just retrieved:\n{mid_research}\n\n"
            )
        if round_num == 1:
            stark_prompt_parts.append(
                f"Original research context:\n{research_context[:3000]}\n\n"
            )

        # Vary the prompt to keep the conversation dynamic
        if round_num <= 3:
            stark_prompt_parts.append(
                "Build on JARVIS's points. What angles are they missing? "
                "What does biology tell us about solving this? "
                "Think about what experiments Carter could run."
            )
        elif round_num <= 6:
            stark_prompt_parts.append(
                "Go deeper. What are the specific physics barriers here? "
                "What would a paradigm shift look like? Where might "
                "conventional physics be wrong or incomplete?"
            )
        elif round_num <= 8:
            stark_prompt_parts.append(
                "Let's get practical. Given everything discussed, what's the "
                "most promising path forward? What should Carter build or "
                "test first? What experiments would reveal the most?"
            )
        else:
            stark_prompt_parts.append(
                "Synthesize. What are the key breakthroughs we've identified? "
                "What's the roadmap from here to actual nanotechnology? "
                "What should Carter focus on this year?"
            )

        stark_messages = stark_history + [
            {"role": "user", "content": "".join(stark_prompt_parts)},
        ]

        try:
            stark_resp = await stark_llm.chat_completion(
                messages=stark_messages,
                temperature=0.7,
                max_tokens=1200,
            )
            stark_text = stark_resp["content"].strip()
        except Exception as exc:
            logger.warning("%s turn %d failed: %s", stark_label, round_num, exc)
            stark_text = f"[{stark_label} turn {round_num} failed: {exc}]"

        dialogue.append({
            "speaker": stark_label,
            "round": round_num,
            "text": stark_text,
        })
        stark_history.append({"role": "user", "content": "".join(stark_prompt_parts)})
        stark_history.append({"role": "assistant", "content": stark_text})

        # Feed Stark Protocol's response back to JARVIS
        jarvis_followup = (
            f"The Stark Protocol responds:\n{stark_text}\n\n"
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
        "stark_protocol_used": stark_label == "STARK_PROTOCOL",
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

    prompt = f"""Analyse this deep research dialogue about "{topic}" between JARVIS and the Stark Protocol.

Extract the most valuable findings for Mr. Stark (Carter Hammond, building real nanotechnology).

For each insight, provide:
- "insight": detailed description (2-3 sentences, be specific)
- "category": one of "breakthrough_idea", "experiment_to_try", "physics_question", \
"engineering_solution", "biology_parallel", "material_discovery", "next_step"
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


async def _notify_findings(result: dict[str, Any]) -> None:
    """Text Mr. Stark the key findings from the dialogue session."""
    try:
        from app.config import settings
        from app.integrations.mac_mini import send_imessage, is_configured

        if not is_configured() or not settings.OWNER_PHONE:
            return

        insights = result.get("insights", [])
        if not insights:
            return

        from zoneinfo import ZoneInfo
        now = datetime.now(tz=ZoneInfo("America/Denver")).strftime("%I:%M %p")

        lines = [
            f"Research Session Complete ({now})",
            f"Topic: {result.get('topic', 'Unknown')}",
            f"{result.get('rounds', 0)} rounds, {len(insights)} insights",
        ]

        if result.get("stark_protocol_used"):
            lines.append("Stark Protocol collaborated")

        lines.append("")

        # Include top 3 most interesting insights
        actionable = [i for i in insights if i.get("actionable")]
        top_insights = (actionable or insights)[:3]

        for i, ins in enumerate(top_insights, 1):
            cat = ins.get("category", "").replace("_", " ").title()
            lines.append(f"{i}. [{cat}] {ins['insight']}")

        # Add any immediate action items
        immediate = [i for i in insights if i.get("priority") == "immediate"]
        if immediate:
            lines.append(f"\n{len(immediate)} immediate action item(s)")

        message = "\n".join(lines)

        await send_imessage(to=settings.OWNER_PHONE, text=message)
        logger.info("Research findings sent to Mr. Stark")

    except Exception as exc:
        logger.debug("Findings notification failed: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════
# Storage
# ═══════════════════════════════════════════════════════════════════════════


async def _store_dialogue(result: dict[str, Any]) -> None:
    """Store dialogue result in Redis history."""
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
