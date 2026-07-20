import base64
import io
import json
import re
import time

import requests
from PIL import Image

API_URL = "https://openrouter.ai/api/v1/chat/completions"
VISION_MODEL = "google/gemma-4-31b-it:free"
# 기본 모델이 429(일시적 요청 제한)로 실패할 경우 시도할, 다른 제공사의 인기가 낮은 무료 비전 모델.
# 같은 제공사(Google AI Studio)의 혼잡을 그대로 물려받지 않도록 다른 제공사 모델을 선택했다.
FALLBACK_VISION_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"
MAX_IMAGE_DIMENSION = 1024
UNIT_OPTIONS = ["개", "병", "봉지", "팩", "단", "g", "kg", "ml", "L", "기타"]
RECOGNITION_PROMPT = (
    '이 냉장고 사진에서 보이는 식재료를 한국어로 인식해서 JSON 배열 형식으로만 답해줘. '
    '각 항목은 name(이름), quantity(수량, 숫자), unit(단위: 개/병/봉지/팩/단/g/kg/ml/L 중 하나)을 포함해줘. '
    '사진만으로 정확한 수량을 알기 어려우면 quantity는 1, unit은 "개"로 추정해줘.\n'
    '예: [{"name": "계란", "quantity": 6, "unit": "개"}, {"name": "우유", "quantity": 1, "unit": "개"}]'
)


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


def recognize_ingredients(data_uri, api_key, on_attempt=None):
    """429가 나면 같은 모델로 최대 3차 시도까지 재시도하고, 그래도 안 되면 폴백 모델로 전환한다.

    on_attempt: 선택적 콜백. (label, model) 을 인자로 호출되어 진행 상황을 UI에 전달할 수 있다.
    """
    plan = [
        (VISION_MODEL, "1차 시도"),
        (VISION_MODEL, "2차 시도"),
        (VISION_MODEL, "3차 시도"),
        (FALLBACK_VISION_MODEL, "폴백 모델로 전환"),
    ]
    response = None
    used_model = VISION_MODEL
    for i, (model, label) in enumerate(plan):
        if on_attempt is not None:
            on_attempt(label, model)
        response = call_vision_model(model, data_uri, api_key)
        used_model = model
        if response.status_code != 429:
            break
        if i < len(plan) - 1:
            time.sleep(2)
    return response, used_model


def parse_ingredients(content):
    """모델 응답을 [{"name", "quantity", "unit"}, ...] 형태로 파싱한다.

    모델이 예전 방식대로 문자열 배열(["계란", "우유"])로 답한 경우도
    수량 1, 단위 "개"로 채워 동일한 형태로 반환한다 (하위 호환).
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
        ingredients.append({"name": name, "quantity": str(quantity), "unit": unit})
    return ingredients if ingredients else None
