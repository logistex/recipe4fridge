import json
import re
import time

import requests

API_URL = "https://openrouter.ai/api/v1/chat/completions"
RECIPE_MODEL = "openai/gpt-oss-20b:free"


def build_prompt(ingredient_names):
    ingredients_text = ", ".join(ingredient_names)
    return (
        f"다음 재료로 만들 수 있는 요리 3가지를 추천해줘: {ingredients_text}. "
        "각 레시피는 아래 JSON 형식으로만 답해줘.\n"
        "{\n"
        '  "recipes": [\n'
        "    {\n"
        '      "name": "요리명",\n'
        '      "used_ingredients": ["보유 재료 중 사용되는 것"],\n'
        '      "missing_ingredients": ["추가로 필요한 재료"],\n'
        '      "steps": ["조리 순서 1", "조리 순서 2"],\n'
        '      "cook_time_minutes": 20\n'
        "    }\n"
        "  ]\n"
        "}"
    )


def call_recipe_model(ingredient_names, api_key):
    return requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": RECIPE_MODEL,
            "messages": [{"role": "user", "content": build_prompt(ingredient_names)}],
        },
        timeout=60,
    )


def generate_recipes(ingredient_names, api_key, on_attempt=None):
    """429가 나면 동일 모델로 한 번 더 재시도한다 (1단계와 동일한 원칙)."""
    response = None
    for i, label in enumerate(["1차 시도", "재시도"]):
        if on_attempt is not None:
            on_attempt(label, RECIPE_MODEL)
        response = call_recipe_model(ingredient_names, api_key)
        if response.status_code != 429:
            break
        if i == 0:
            time.sleep(2)
    return response


def parse_recipes(content):
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    recipes = data.get("recipes")
    if not isinstance(recipes, list):
        return None
    return recipes
