import base64
import io
import json
import random
import re
import time
import uuid

import requests
from PIL import Image

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
MAX_IMAGE_DIMENSION = 1024
UNIT_OPTIONS = ["개", "병", "봉지", "팩", "단", "g", "kg", "ml", "L", "기타"]
RECOGNITION_PROMPT = (
    '이 냉장고 사진에서 보이는 식재료를 한국어로 인식해서 JSON 배열 형식으로만 답해줘. '
    '각 항목은 name(이름), quantity(수량, 숫자), unit(단위: 개/병/봉지/팩/단/g/kg/ml/L 중 하나)을 포함해줘. '
    '사진만으로 정확한 수량을 알기 어려우면 quantity는 1, unit은 "개"로 추정해줘.\n'
    '예: [{"name": "계란", "quantity": 6, "unit": "개"}, {"name": "우유", "quantity": 1, "unit": "개"}]'
)

# 오픈라우터 무료 모델 목록 조회 자체가 실패할 경우를 위한 최소 안전망 (과거에 정상 동작 확인된 모델).
SAFETY_NET_VISION_MODELS = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
]
_EXCLUDE_KEYWORDS = ["safety", "rerank", "guard"]


def list_free_vision_models():
    """오픈라우터에서 현재 사용 가능한 무료 비전(이미지 입력) 모델 목록을 실시간으로 조회한다.

    무료 모델 라인업은 시간에 따라 계속 바뀌므로 매번 새로 조회한다.
    조회 자체가 실패하면 최소한의 고정 안전망 목록을 반환한다.
    """
    try:
        response = requests.get(MODELS_URL, timeout=10)
        response.raise_for_status()
        data = response.json().get("data", [])
    except (requests.exceptions.RequestException, ValueError):
        return list(SAFETY_NET_VISION_MODELS)

    models = []
    for m in data:
        model_id = m.get("id", "")
        if not model_id.endswith(":free"):
            continue
        if any(keyword in model_id.lower() for keyword in _EXCLUDE_KEYWORDS):
            continue
        modality = m.get("architecture", {}).get("input_modalities", [])
        if "image" in modality:
            models.append(model_id)
    return models or list(SAFETY_NET_VISION_MODELS)


def to_resized_data_uri(file_like):
    """이미지를 긴 변 기준 MAX_IMAGE_DIMENSION 이하로 축소해 base64 data URI로 변환한다."""
    image = Image.open(file_like).convert("RGB")
    image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    resized_bytes = buffer.getvalue()
    b64 = base64.b64encode(resized_bytes).decode()
    return f"data:image/jpeg;base64,{b64}", len(resized_bytes)


def call_vision_model(model, data_uri, api_key):
    return requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": RECOGNITION_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        },
        timeout=60,
    )


def recognize_ingredients(data_uri, api_key, on_attempt=None, attempts=3):
    """매 시도마다 오픈라우터의 현재 무료 비전 모델 중 서로 다른 모델을 무작위로 골라 시도한다.

    429(요청 폭주)든 JSON 파싱 실패든 실패로 간주하고, 성공(재료 목록을 얻을 때)할 때까지
    또는 attempts 횟수만큼 매번 다른 모델로 재시도한다. 고정된 "폴백 모델" 개념 대신,
    매 시도 자체가 서로 다른 모델이라 폴백 역할을 겸한다.

    on_attempt: 선택적 콜백. (label, model) 을 인자로 호출되어 진행 상황을 UI에 전달할 수 있다.
    """
    pool = list_free_vision_models()
    random.shuffle(pool)
    models = pool[:attempts]
    while len(models) < attempts:
        models.append(random.choice(SAFETY_NET_VISION_MODELS))

    response = None
    used_model = models[0]
    for i, model in enumerate(models):
        label = f"{i + 1}차 시도"
        if on_attempt is not None:
            on_attempt(label, model)
        response = call_vision_model(model, data_uri, api_key)
        used_model = model
        if response.status_code == 200:
            try:
                body = response.json()
                choices = body.get("choices")
                if choices and parse_ingredients(choices[0]["message"]["content"]) is not None:
                    break
            except ValueError:
                pass
        if i < len(models) - 1:
            time.sleep(1)
    return response, used_model


def merge_duplicate_ingredients(ingredients):
    """이름이 같은(공백 제거, 대소문자 무시) 재료는 수량을 합쳐 하나로 합친다."""
    merged = {}
    order = []
    for item in ingredients:
        key = item["name"].strip().lower()
        if key not in merged:
            merged[key] = dict(item)
            order.append(key)
        else:
            try:
                merged[key]["quantity"] = str(int(merged[key]["quantity"]) + int(item["quantity"]))
            except (TypeError, ValueError):
                pass
    return [merged[key] for key in order]


def parse_ingredients(content):
    """모델 응답을 [{"name", "quantity", "unit"}, ...] 형태로 파싱한다.

    모델이 예전 방식대로 문자열 배열(["계란", "우유"])로 답한 경우도
    수량 1, 단위 "개"로 채워 동일한 형태로 반환한다 (하위 호환).
    동일한 이름의 재료가 중복 인식된 경우 수량을 합쳐 하나로 정리한다.
    """
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None

    ingredients = []
    for item in data:
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            try:
                quantity = int(float(item.get("quantity", 1)))
            except (TypeError, ValueError):
                quantity = 1
            unit = str(item.get("unit") or "개").strip() or "개"
        else:
            name = str(item).strip()
            if not name:
                continue
            quantity = 1
            unit = "개"
        ingredients.append({"_id": uuid.uuid4().hex, "name": name, "quantity": str(quantity), "unit": unit})
    if not ingredients:
        return None
    return merge_duplicate_ingredients(ingredients)
