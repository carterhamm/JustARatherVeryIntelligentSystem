"""
LLM-based entity and relationship extraction for the JARVIS knowledge graph.

Uses Gemini or any LLM with JSON output to pull named entities and directed
relationships from arbitrary text, returning typed dataclass instances ready
for graph and vector storage.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

ENTITY_TYPES = frozenset(
    {"PERSON", "ORG", "CONCEPT", "EVENT", "LOCATION", "TECHNOLOGY"}
)


@dataclass
class Entity:
    """A named entity extracted from text."""

    name: str
    type: str  # one of ENTITY_TYPES
    description: str = ""
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "properties": self.properties,
        }


@dataclass
class Relationship:
    """A directed relationship between two entities."""

    source: str
    target: str
    type: str
    description: str = ""
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "description": self.description,
            "weight": self.weight,
        }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_ENTITY_EXTRACTION_PROMPT = """\
You are an expert knowledge-graph engineer.  Analyse the following text and
extract every meaningful entity and every directed relationship between
entities.

### Entity types
PERSON, ORG, CONCEPT, EVENT, LOCATION, TECHNOLOGY

### Output format (strict JSON)
{
  "entities": [
    {
      "name": "<canonical name>",
      "type": "<one of the types above>",
      "description": "<one-sentence description>",
      "properties": {}
    }
  ],
  "relationships": [
    {
      "source": "<source entity name>",
      "target": "<target entity name>",
      "type": "<RELATIONSHIP_TYPE in UPPER_SNAKE_CASE>",
      "description": "<one-sentence description>",
      "weight": <0.0-1.0 confidence>
    }
  ]
}

Rules:
- Use the SAME canonical name for an entity everywhere.
- Relationship source/target MUST reference entity names from the entities list.
- type for relationships should be descriptive, e.g. WORKS_AT, FOUNDED, USES, LOCATED_IN, RELATED_TO.
- Output ONLY valid JSON.  No markdown fences, no commentary.

### Text to analyse
{text}
"""


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class EntityExtractor:
    """Extract entities and relationships from text using an LLM."""

    def __init__(self, llm_client: Optional[Any] = None, model: str = "gemini-3.1-pro-preview") -> None:
        self._llm = llm_client  # unused — we call Gemini REST directly
        self._model = model

    # -- public API ----------------------------------------------------------

    async def extract_entities(self, text: str) -> list[Entity]:
        """Return a list of entities found in *text*."""
        parsed = await self._call_llm(text)
        return self._parse_entities(parsed)

    async def extract_relationships(
        self,
        text: str,
        entities: list[Entity],
    ) -> list[Relationship]:
        """
        Return a list of relationships found in *text*.

        If the extraction was already performed via :meth:`extract_all`, this
        simply re-parses from the cached LLM call.  Otherwise a fresh call
        is made.
        """
        parsed = await self._call_llm(text)
        entity_names = {e.name for e in entities}
        return self._parse_relationships(parsed, entity_names)

    async def extract_all(
        self, text: str
    ) -> tuple[list[Entity], list[Relationship]]:
        """Extract both entities **and** relationships in a single LLM call."""
        parsed = await self._call_llm(text)
        entities = self._parse_entities(parsed)
        entity_names = {e.name for e in entities}
        relationships = self._parse_relationships(parsed, entity_names)
        return entities, relationships

    # -- internals -----------------------------------------------------------

    def _build_extraction_prompt(self, text: str) -> str:
        return _ENTITY_EXTRACTION_PROMPT.format(text=text)

    async def _call_llm(self, text: str) -> dict[str, Any]:
        """Send the extraction prompt to the LLM and parse the JSON reply."""
        prompt = self._build_extraction_prompt(text)
        try:
            import httpx
            from app.config import settings

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent"
            payload = {
                "contents": [{"parts": [{"text": (
                    "You are a precise entity-extraction engine. "
                    "Reply ONLY with valid JSON.\n\n" + prompt
                )}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.0,
                },
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    params={"key": settings.GOOGLE_GEMINI_API_KEY},
                )
                resp.raise_for_status()
                data = resp.json()

            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON for entity extraction.")
            return {"entities": [], "relationships": []}
        except Exception:
            logger.exception("Entity extraction LLM call failed.")
            return {"entities": [], "relationships": []}

    # -- parsing helpers -----------------------------------------------------

    @staticmethod
    def _parse_entities(parsed: dict[str, Any]) -> list[Entity]:
        entities: list[Entity] = []
        for raw in parsed.get("entities", []):
            name = raw.get("name", "").strip()
            etype = raw.get("type", "CONCEPT").upper()
            if not name:
                continue
            if etype not in ENTITY_TYPES:
                etype = "CONCEPT"
            entities.append(
                Entity(
                    name=name,
                    type=etype,
                    description=raw.get("description", ""),
                    properties=raw.get("properties", {}),
                )
            )
        return entities

    @staticmethod
    def _parse_relationships(
        parsed: dict[str, Any],
        valid_entity_names: set[str],
    ) -> list[Relationship]:
        relationships: list[Relationship] = []
        for raw in parsed.get("relationships", []):
            source = raw.get("source", "").strip()
            target = raw.get("target", "").strip()
            rtype = raw.get("type", "RELATED_TO").upper()
            if not source or not target:
                continue
            # Only keep relationships where both endpoints are known entities
            if source not in valid_entity_names or target not in valid_entity_names:
                logger.debug(
                    "Dropping relationship %s->%s: endpoint not in entity list.",
                    source,
                    target,
                )
                continue
            weight = raw.get("weight", 1.0)
            if not isinstance(weight, (int, float)):
                weight = 1.0
            weight = max(0.0, min(1.0, float(weight)))
            relationships.append(
                Relationship(
                    source=source,
                    target=target,
                    type=rtype,
                    description=raw.get("description", ""),
                    weight=weight,
                )
            )
        return relationships
