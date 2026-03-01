"""Edamam Nutrition and Recipe API client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.integrations.edamam")

_RECIPE_URL = "https://api.edamam.com/api/recipes/v2"
_NUTRITION_URL = "https://api.edamam.com/api/nutrition-data"


class EdamamClient:
    """Async client for the Edamam Recipe and Nutrition APIs."""

    def __init__(
        self,
        app_id: str | None = None,
        app_key: str | None = None,
    ) -> None:
        self._app_id = app_id or settings.EDAMAM_APP_ID
        self._app_key = app_key or settings.EDAMAM_APP_KEY

    async def search_recipes(
        self,
        query: str,
        diet: str | None = None,
        health: str | None = None,
        cuisine_type: str | None = None,
        max_results: int = 5,
    ) -> dict[str, Any]:
        """Search for recipes by query."""
        if not self._app_id or not self._app_key:
            return {"error": "Edamam API is not configured (EDAMAM_APP_ID/KEY missing)."}

        params: dict[str, Any] = {
            "type": "public",
            "q": query,
            "app_id": self._app_id,
            "app_key": self._app_key,
        }
        if diet:
            params["diet"] = diet
        if health:
            params["health"] = health
        if cuisine_type:
            params["cuisineType"] = cuisine_type

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(_RECIPE_URL, params=params)
            response.raise_for_status()
            data = response.json()

        recipes = []
        for hit in data.get("hits", [])[:max_results]:
            recipe = hit.get("recipe", {})
            recipes.append({
                "label": recipe.get("label", ""),
                "source": recipe.get("source", ""),
                "url": recipe.get("url", ""),
                "calories": round(recipe.get("calories", 0)),
                "servings": recipe.get("yield", 0),
                "ingredients": [i.get("text", "") for i in recipe.get("ingredients", [])],
                "diet_labels": recipe.get("dietLabels", []),
                "health_labels": recipe.get("healthLabels", []),
            })

        return {"query": query, "recipes": recipes, "count": data.get("count", 0)}

    async def get_nutrition(self, ingredient: str) -> dict[str, Any]:
        """Get nutrition data for an ingredient string."""
        if not self._app_id or not self._app_key:
            return {"error": "Edamam API is not configured (EDAMAM_APP_ID/KEY missing)."}

        params = {
            "app_id": self._app_id,
            "app_key": self._app_key,
            "ingr": ingredient,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(_NUTRITION_URL, params=params)
            response.raise_for_status()
            data = response.json()

        nutrients = data.get("totalNutrients", {})
        return {
            "ingredient": ingredient,
            "calories": data.get("calories", 0),
            "total_weight": data.get("totalWeight", 0),
            "nutrients": {
                key: {
                    "label": val.get("label", ""),
                    "quantity": round(val.get("quantity", 0), 1),
                    "unit": val.get("unit", ""),
                }
                for key, val in nutrients.items()
            },
        }
