import json
import random
import re
import time

import requests

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"

CUISINE_OPTIONS = ["상관없음", "한식", "양식", "중식", "일식"]
DIFFICULTY_OPTIONS = ["상관없음", "초급", "중급", "고급"]
TIME_OPTIONS = ["상관없음", "15분 이내", "30분 이내", "30분 이상"]
SERVINGS_OPTIONS = ["상관없음", "1인분", "2인분", "3인분", "4인분"]

# 오픈라우터 무료 모델 목록 조회 자체가 실패할 경우를 위한 최소 안전망.
SAFETY_NET_RECIPE_MODELS = [
    "openai/gpt-oss-20b:free",
    "nvidia/nemotron-nano-9b-v2:free",
]
_EXCLUDE_KEYWORDS = ["safety", "rerank", "guard"]


def list_free_text_models():
    """오픈라우터에서 현재 사용 가능한 무료 텍스트 전용 모델 목록을 실시간으로 조회한다."""
    try:
        response = requests.get(MODELS_URL, timeout=10)
        response.raise_for_status()
        data = response.json().get("data", [])
    except (requests.exceptions.RequestException, ValueError):
        return list(SAFETY_NET_RECIPE_MODELS)

    models = []
    for m in data:
        model_id = m.get("id", "")
        if not model_id.endswith(":free"):
            continue
        if any(keyword in model_id.lower() for keyword in _EXCLUDE_KEYWORDS):
            continue
        modality = m.get("architecture", {}).get("input_modalities", [])
        if "image" in modality:
            continue  # 레시피 생성은 텍스트 전용 모델만 사용
        models.append(model_id)
    return models or list(SAFETY_NET_RECIPE_MODELS)


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
        "요리명, 조리 순서 등 모든 텍스트는 반드시 한국어로만 작성해줘. 영어를 섞지 마.\n"
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


def generate_recipes(ingredient_names, api_key, on_attempt=None, attempts=3, **options):
    """매 시도마다 오픈라우터의 현재 무료 텍스트 모델 중 서로 다른 모델을 무작위로 골라 시도한다.

    429든 JSON 파싱 실패든 한국어가 아닌 응답이든 실패로 간주하고, 성공할 때까지 또는
    attempts 횟수만큼 매번 다른 모델로 재시도한다 (별도의 고정 폴백 모델 없이, 매 시도
    자체가 폴백 역할을 겸함).
    """
    pool = list_free_text_models()
    random.shuffle(pool)
    models = pool[:attempts]
    while len(models) < attempts:
        models.append(random.choice(SAFETY_NET_RECIPE_MODELS))

    response = None
    used_model = models[0]
    for i, model in enumerate(models):
        label = f"{i + 1}차 시도"
        if on_attempt is not None:
            on_attempt(label, model)
        response = call_recipe_model(model, ingredient_names, api_key, **options)
        used_model = model
        if response.status_code == 200:
            try:
                body = response.json()
                choices = body.get("choices")
                if choices:
                    recipes = parse_recipes(choices[0]["message"]["content"])
                    if recipes and _is_korean_enough(recipes):
                        break
            except ValueError:
                pass
        if i < len(models) - 1:
            time.sleep(1)
    return response, used_model


_HANGUL_RE = re.compile(r"[가-힣]")


def _is_korean_enough(recipes):
    """레시피명/조리 순서에 한글이 전혀 없으면(영어로만 응답한 경우) 실패로 간주한다."""
    combined = " ".join(
        (r.get("name") or "") + " " + " ".join(r.get("steps") or []) for r in recipes
    )
    return bool(_HANGUL_RE.search(combined))


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
