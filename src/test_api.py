import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["OPENROUTER_API_KEY"]
URL = "https://openrouter.ai/api/v1/chat/completions"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

TEXT_MODEL = "openai/gpt-oss-20b:free"
IMAGE_MODEL = "google/gemma-4-31b-it:free"

IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/3/3a/Cat03.jpg"


def call(model, messages):
    response = requests.post(
        URL,
        headers=HEADERS,
        json={"model": model, "messages": messages},
        timeout=60,
    )
    return response


def test_text():
    print(f"--- Text model: {TEXT_MODEL} ---")
    response = call(
        TEXT_MODEL,
        [{"role": "user", "content": "1부터 5까지 더하면 얼마야? 숫자만 답해줘."}],
    )
    print("status:", response.status_code)
    print(response.text)


def test_image():
    print(f"--- Image model: {IMAGE_MODEL} ---")
    response = call(
        IMAGE_MODEL,
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "이 이미지에 무엇이 보이는지 한 문장으로 설명해줘."},
                    {"type": "image_url", "image_url": {"url": IMAGE_URL}},
                ],
            }
        ],
    )
    print("status:", response.status_code)
    print(response.text)


if __name__ == "__main__":
    test_text()
    print()
    test_image()
