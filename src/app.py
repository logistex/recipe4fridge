import os

import requests
import streamlit as st
from dotenv import load_dotenv

from vision import (
    MAX_IMAGE_DIMENSION,
    VISION_MODEL,
    parse_ingredients,
    recognize_ingredients,
    to_resized_data_uri,
)

load_dotenv()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def get_api_key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    try:
        return st.secrets["OPENROUTER_API_KEY"]
    except (FileNotFoundError, KeyError):
        st.error("OPENROUTER_API_KEY가 설정되지 않았습니다. .env 또는 Streamlit secrets를 확인해주세요.")
        st.stop()


st.set_page_config(page_title="냉장고 식재료 인식", page_icon="🥬")
st.title("🥬 냉장고 식재료 인식 (1단계)")
st.caption(f"비전 모델: `{VISION_MODEL}`")

api_key = get_api_key()

uploaded_file = st.file_uploader("냉장고 사진을 업로드하세요", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        st.error("이미지 용량이 10MB를 초과합니다. 더 작은 이미지를 업로드해주세요.")
        st.stop()

    st.image(uploaded_file, caption="업로드한 사진", use_container_width=True)

    if st.button("식재료 인식하기", type="primary"):
        with st.status("사진을 분석하는 중입니다...", expanded=True) as status:
            data_uri, resized_bytes = to_resized_data_uri(uploaded_file)
            status.write(
                f"이미지 축소: {uploaded_file.size // 1024}KB → {resized_bytes // 1024}KB "
                f"(긴 변 {MAX_IMAGE_DIMENSION}px 이하)"
            )
            try:
                response, used_model = recognize_ingredients(
                    data_uri,
                    api_key,
                    on_attempt=lambda label, model: status.write(f"{label}: `{model}` 호출 중..."),
                )
            except requests.exceptions.Timeout:
                st.error("요청이 시간 초과되었습니다. 잠시 후 다시 시도해주세요.")
                st.stop()
            except requests.exceptions.RequestException as e:
                st.error(f"네트워크 오류가 발생했습니다: {e}")
                st.stop()
            status.update(label="분석 완료", state="complete")

        st.caption(f"실제 응답 모델: `{used_model}`")

        if response.status_code == 429:
            st.error(
                "무료 비전 모델 요청이 계속 몰려 제한되었습니다 (429). "
                "기본 모델과 폴백 모델 모두 실패했습니다. 잠시 후 다시 시도해주세요."
            )
        elif response.status_code >= 500:
            st.error("모델 제공자 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
        elif response.status_code != 200:
            st.error(f"요청이 실패했습니다 (status {response.status_code}).")
            st.code(response.text)
        else:
            body = response.json()
            choices = body.get("choices")
            if not choices:
                st.error("모델 응답 형식이 올바르지 않습니다 (choices 없음). 잠시 후 다시 시도해주세요.")
                st.code(response.text)
                st.stop()
            content = choices[0]["message"]["content"]
            ingredients = parse_ingredients(content)
            if ingredients is None:
                st.warning("모델 응답을 목록으로 변환하지 못했습니다. 아래 원문을 참고해 직접 목록을 추가해주세요.")
                st.code(content)
                st.session_state.ingredients = []
            else:
                st.session_state.ingredients = ingredients

if "ingredients" in st.session_state:
    st.subheader("인식된 식재료 목록")

    if not st.session_state.ingredients:
        st.info("아직 목록이 비어 있습니다. 아래에서 직접 추가해주세요.")

    delete_index = None
    for i, item in enumerate(st.session_state.ingredients):
        col1, col2 = st.columns([5, 1])
        col1.write(f"- {item}")
        if col2.button("삭제", key=f"delete_{i}"):
            delete_index = i
    if delete_index is not None:
        st.session_state.ingredients.pop(delete_index)
        st.rerun()

    with st.form("add_ingredient_form", clear_on_submit=True):
        new_item = st.text_input("재료 직접 추가")
        submitted = st.form_submit_button("추가")
        if submitted and new_item.strip():
            st.session_state.ingredients.append(new_item.strip())
            st.rerun()

    st.divider()
    if st.button("레시피 추천받기 →", disabled=not st.session_state.ingredients):
        st.session_state.confirmed_ingredients = {"ingredients": st.session_state.ingredients}
        st.success("식재료 목록이 확정되었습니다. (2단계 레시피 생성은 다음 작업에서 이어집니다)")
        st.json(st.session_state.confirmed_ingredients)
