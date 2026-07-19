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
RECOGNITION_PROMPT = (
    '이 냉장고 사진에서 보이는 식재료 이름만 한국어로, JSON 배열 형식으로 답해줘. '
    '예: ["계란", "우유", "당근"]'
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
    """429가 나면 같은 모델로 한 번 더 재시도하고, 그래도 안 되면 폴백 모델로 전환한다.

    on_attempt: 선택적 콜백. (label, model) 을 인자로 호출되어 진행 상황을 UI에 전달할 수 있다.
    """
    plan = [
        (VISION_MODEL, "1차 시도"),
        (VISION_MODEL, "재시도"),
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
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return [str(item).strip() for item in data if str(item).strip()]
    return None
