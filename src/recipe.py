import json
import re
import time

import requests

API_URL = "https://openrouter.ai/api/v1/chat/completions"
RECIPE_MODEL = "openai/gpt-oss-20b:free"
# 기본 모델이 429로 실패할 경우 시도할, 다른 제공사의 인기가 낮은 무료 텍스트 모델.
FALLBACK_RECIPE_MODEL = "nvidia/nemotron-nano-9b-v2:free"

CUISINE_OPTIONS = ["상관없음", "한식", "양식", "중식", "일식"]
DIFFICULTY_OPTIONS = ["상관없음", "초급", "중급", "고급"]
TIME_OPTIONS = ["상관없음", "15분 이내", "30분 이내", "30분 이상"]
SERVINGS_OPTIONS = ["상관없음", "1인분", "2인분", "3인분", "4인분"]


def build_prompt(ingredient_names, cuisine=None, difficulty=None, time_pref=None, servings=None):
    ingredients_text = ", ".join(ingredient_names)
    conditions = []
    if cuisine and cuisine != "상관없음":
        conditions.append(f"요리 종류: {cuisine}")
    if difficulty and difficulty != "상관없음":
        conditions.append(f"난이도: {difficulty}")
    if time_pref and time_pref != "상관없음":
        conditions.append(f"조리 시간: {time_pref}")
    if servings and servings != "상관없음":
        conditions.append(f"인원: {servings}")
    condition_text = ""
    if conditions:
        condition_text = "다음 조건에 맞춰줘: " + ", ".join(conditions) + ".\n"

    return (
        f"다음 재료로 만들 수 있는 요리 3가지를 추천해줘: {ingredients_text}.\n"
        f"{condition_text}"
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


def call_recipe_model(model, ingredient_names, api_key, **options):
    return requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": build_prompt(ingredient_names, **options)}],
        },
        timeout=60,
    )


def generate_recipes(ingredient_names, api_key, on_attempt=None, **options):
    """429가 나면 같은 모델로 최대 3차 시도까지 재시도하고, 그래도 안 되면 폴백 모델로 전환한다."""
    plan = [
        (RECIPE_MODEL, "1차 시도"),
        (RECIPE_MODEL, "2차 시도"),
        (RECIPE_MODEL, "3차 시도"),
        (FALLBACK_RECIPE_MODEL, "폴백 모델로 전환"),
    ]
    response = None
    used_model = RECIPE_MODEL
    for i, (model, label) in enumerate(plan):
        if on_attempt is not None:
            on_attempt(label, model)
        response = call_recipe_model(model, ingredient_names, api_key, **options)
        used_model = model
        if response.status_code != 429:
            break
        if i < len(plan) - 1:
            time.sleep(2)
    return response, used_model


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
