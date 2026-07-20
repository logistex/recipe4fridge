import os
import time

import requests
import streamlit as st
from dotenv import load_dotenv

import db
from auth_ui import current_user, render_sidebar_auth
from recipe import (
    CUISINE_OPTIONS,
    DIFFICULTY_OPTIONS,
    SERVINGS_OPTIONS,
    TIME_OPTIONS,
    generate_recipes,
    parse_recipes,
)
from vision import (
    MAX_IMAGE_DIMENSION,
    UNIT_OPTIONS,
    parse_ingredients,
    recognize_ingredients,
    to_resized_data_uri,
)

load_dotenv()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
RECIPE_REQUEST_COOLDOWN_SECONDS = 5
WIZARD_STEP_LABELS = ["① 사진 업로드", "② 식재료 확인", "③ 레시피 추천"]


def get_api_key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    try:
        return st.secrets["OPENROUTER_API_KEY"]
    except (FileNotFoundError, KeyError):
        st.error("OPENROUTER_API_KEY가 설정되지 않았습니다. .env 또는 Streamlit secrets를 확인해주세요.")
        st.stop()


st.set_page_config(page_title="냉장고 식재료 인식", page_icon="🥬")
render_sidebar_auth()

# '자세히 보기' 버튼이 카드마다 다른 높이에 걸리지 않도록, 카드 안 마지막 요소(버튼)를 바닥에 붙인다.
st.markdown(
    """
    <style>
    div[data-testid="column"] > div[data-testid="stVerticalBlockBorderWrapper"] > div {
        display: flex;
        flex-direction: column;
        height: 100%;
    }
    div[data-testid="column"] > div[data-testid="stVerticalBlockBorderWrapper"] > div > div:last-child {
        margin-top: auto;
    }
    .ingredient-chip {
        display: inline-block;
        background: #e8e8e8;
        color: #333;
        border-radius: 14px;
        padding: 4px 12px;
        margin: 2px 4px 2px 0;
        font-size: 0.9em;
        white-space: nowrap;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🥬 냉장고 레시피 추천")

api_key = get_api_key()

wizard_step = st.session_state.get("wizard_step", 1)

step_cols = st.columns(3)
for i, col in enumerate(step_cols, start=1):
    label = WIZARD_STEP_LABELS[i - 1]
    if i == wizard_step:
        col.markdown(f"**:red[{label}]**")
    elif i < wizard_step:
        col.markdown(f"✅ {label}")
    else:
        col.markdown(label)
st.divider()

# ==================== 1단계: 사진 업로드 ====================
if wizard_step == 1:
    uploaded_file = st.file_uploader(
        "냉장고 사진을 업로드하거나, 이 영역으로 파일을 끌어다 놓으세요", type=["jpg", "jpeg", "png"]
    )

    if uploaded_file is not None:
        if uploaded_file.size > MAX_UPLOAD_BYTES:
            st.error("이미지 용량이 10MB를 초과합니다. 더 작은 이미지를 업로드해주세요.")
            st.stop()

        st.image(uploaded_file, caption="업로드한 사진", use_container_width=True)

        if st.button("식재료 인식하기", type="primary"):
            st.session_state.pop("recognition_error", None)
            st.session_state.pop("recognition_error_detail", None)
            st.session_state.pop("ingredients", None)

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
                    st.session_state.recognition_error = "❌ 식재료 인식 실패: 요청이 시간 초과되었습니다. 잠시 후 다시 시도해주세요."
                    st.rerun()
                except requests.exceptions.RequestException as e:
                    st.session_state.recognition_error = f"❌ 식재료 인식 실패: 네트워크 오류가 발생했습니다: {e}"
                    st.rerun()
                status.update(label="분석 완료", state="complete")

            st.session_state.used_vision_model = used_model

            if response.status_code == 429:
                st.session_state.recognition_error = (
                    "❌ 식재료 인식 실패: 서로 다른 무료 비전 모델로 3차 시도까지 모두 요청이 제한되었습니다 (429). "
                    "잠시 후 다시 시도해주세요."
                )
            elif response.status_code >= 500:
                st.session_state.recognition_error = "❌ 식재료 인식 실패: 모델 제공자 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            elif response.status_code != 200:
                st.session_state.recognition_error = f"❌ 식재료 인식 실패: 요청이 실패했습니다 (status {response.status_code})."
                st.session_state.recognition_error_detail = response.text
            else:
                body = response.json()
                choices = body.get("choices")
                if not choices:
                    st.session_state.recognition_error = "❌ 식재료 인식 실패: 모델 응답 형식이 올바르지 않습니다 (choices 없음). 잠시 후 다시 시도해주세요."
                    st.session_state.recognition_error_detail = response.text
                else:
                    content = choices[0]["message"]["content"]
                    ingredients = parse_ingredients(content)
                    if ingredients is None:
                        st.session_state.recognition_error = "❌ 식재료 인식 실패: 서로 다른 모델 3차 시도 모두 응답을 재료 목록으로 변환하지 못했습니다."
                        st.session_state.recognition_error_detail = content
                    else:
                        st.session_state.ingredients = ingredients
                        st.session_state.wizard_step = 2
            st.rerun()

    if st.session_state.get("used_vision_model"):
        st.caption(f"실제 응답 모델: `{st.session_state.used_vision_model}`")

    if st.session_state.get("recognition_error"):
        st.error(st.session_state.recognition_error)
        if st.session_state.get("recognition_error_detail"):
            st.code(st.session_state.recognition_error_detail)
        if st.button("재료를 직접 입력할게요"):
            st.session_state.ingredients = []
            st.session_state.pop("recognition_error", None)
            st.session_state.pop("recognition_error_detail", None)
            st.session_state.wizard_step = 2
            st.rerun()

# ==================== 2단계: 식재료 확인/편집 ====================
elif wizard_step == 2:
    st.subheader("인식된 식재료 목록")
    st.caption("⚠️ AI 인식 결과는 부정확할 수 있습니다. 이름/수량/단위를 확인하고 필요하면 직접 수정해주세요.")

    ingredients = st.session_state.get("ingredients", [])
    if not ingredients:
        st.info("아직 목록이 비어 있습니다. 아래에서 직접 추가해주세요.")

    delete_index = None
    for i, item in enumerate(ingredients):
        item.setdefault("unit", "개")
        col_name, col_qty, col_unit, col_delete = st.columns([3, 2, 1, 1])
        item["name"] = col_name.text_input(
            "이름", value=item["name"], key=f"ingredient_name_{i}", label_visibility="collapsed"
        )
        try:
            qty_value = int(item["quantity"])
        except (TypeError, ValueError):
            qty_value = 1
        item["quantity"] = str(
            col_qty.number_input(
                "수량",
                min_value=0,
                step=1,
                value=qty_value,
                key=f"ingredient_qty_{i}",
                label_visibility="collapsed",
            )
        )
        unit_index = UNIT_OPTIONS.index(item["unit"]) if item["unit"] in UNIT_OPTIONS else 0
        item["unit"] = col_unit.selectbox(
            "단위", UNIT_OPTIONS, index=unit_index, key=f"ingredient_unit_{i}", label_visibility="collapsed"
        )
        if col_delete.button("삭제", key=f"delete_{i}"):
            delete_index = i
    if delete_index is not None:
        ingredients.pop(delete_index)
        st.rerun()

    with st.form("add_ingredient_form", clear_on_submit=True):
        col_name, col_qty, col_unit, col_add = st.columns([3, 2, 1, 1])
        new_name = col_name.text_input("재료 이름", label_visibility="collapsed", placeholder="재료 이름")
        new_qty = col_qty.number_input("수량", min_value=0, step=1, value=1, label_visibility="collapsed")
        new_unit = col_unit.selectbox("단위", UNIT_OPTIONS, label_visibility="collapsed")
        submitted = col_add.form_submit_button("추가")
        if submitted and new_name.strip():
            ingredients.append({"name": new_name.strip(), "quantity": str(new_qty), "unit": new_unit})
            st.rerun()

    st.session_state.ingredients = ingredients

    st.divider()
    nav_cols = st.columns(2)
    if nav_cols[0].button("← 이전 (사진 다시 업로드)"):
        st.session_state.wizard_step = 1
        st.rerun()
    if nav_cols[1].button("다음: 레시피 추천 →", type="primary", disabled=not ingredients):
        st.session_state.confirmed_ingredients = {
            "ingredients": [item["name"] for item in ingredients]
        }
        st.session_state.pop("recipes", None)
        st.session_state.pop("selected_recipe", None)
        st.session_state.auto_generate_recipes = True
        st.session_state.wizard_step = 3
        st.rerun()

# ==================== 3단계: 레시피 추천 ====================
elif wizard_step == 3:
    if not st.session_state.get("confirmed_ingredients"):
        st.warning("먼저 2단계에서 재료를 확인해주세요.")
        if st.button("← 2단계로 돌아가기"):
            st.session_state.wizard_step = 2
            st.rerun()
        st.stop()

    header_col, back_col = st.columns([4, 1])
    header_col.subheader("🍳 레시피 추천")
    if back_col.button("← 이전"):
        st.session_state.wizard_step = 2
        st.rerun()

    ingredient_names = st.session_state.confirmed_ingredients["ingredients"]
    chips_html = "".join(f'<span class="ingredient-chip">{name}</span>' for name in ingredient_names)
    st.markdown(chips_html, unsafe_allow_html=True)

    opt_cols = st.columns(4)
    cuisine = opt_cols[0].selectbox("요리 종류", CUISINE_OPTIONS, key="recipe_cuisine")
    difficulty = opt_cols[1].selectbox("난이도", DIFFICULTY_OPTIONS, key="recipe_difficulty")
    time_pref = opt_cols[2].selectbox("조리 시간", TIME_OPTIONS, key="recipe_time")
    servings = opt_cols[3].selectbox("인원", SERVINGS_OPTIONS, key="recipe_servings")
    recipe_options = {
        "cuisine": cuisine,
        "difficulty": difficulty,
        "time_pref": time_pref,
        "servings": servings,
    }

    now = time.time()
    last_request = st.session_state.get("last_recipe_request_time", 0)
    elapsed = now - last_request
    can_request = elapsed >= RECIPE_REQUEST_COOLDOWN_SECONDS

    button_label = "다시 추천받기" if "recipes" in st.session_state else "레시피 생성하기"
    if not can_request:
        st.caption(f"{RECIPE_REQUEST_COOLDOWN_SECONDS - elapsed:.0f}초 후 다시 시도할 수 있습니다.")

    manual_click = st.button(button_label, type="primary", disabled=not can_request)
    auto_trigger = st.session_state.pop("auto_generate_recipes", False) and can_request

    if manual_click or auto_trigger:
        st.session_state.last_recipe_request_time = time.time()
        with st.status("레시피를 생성하는 중입니다...", expanded=True) as status:
            try:
                response, used_recipe_model = generate_recipes(
                    ingredient_names,
                    api_key,
                    on_attempt=lambda label, model: status.write(f"{label}: `{model}` 호출 중..."),
                    **recipe_options,
                )
            except requests.exceptions.Timeout:
                st.session_state.pop("recipes", None)
                st.session_state.pop("selected_recipe", None)
                st.error("❌ 레시피 생성 실패: 요청이 시간 초과되었습니다. 잠시 후 다시 시도해주세요.")
                st.stop()
            except requests.exceptions.RequestException as e:
                st.session_state.pop("recipes", None)
                st.session_state.pop("selected_recipe", None)
                st.error(f"❌ 레시피 생성 실패: 네트워크 오류가 발생했습니다: {e}")
                st.stop()
            status.update(label="생성 완료", state="complete")

        st.caption(f"실제 응답 모델: `{used_recipe_model}`")

        if response.status_code == 429:
            st.session_state.pop("recipes", None)
            st.session_state.pop("selected_recipe", None)
            st.error(
                "❌ 레시피 생성 실패: 서로 다른 무료 텍스트 모델로 3차 시도까지 모두 요청이 제한되었습니다 (429). "
                "잠시 후 다시 시도해주세요."
            )
        elif response.status_code >= 500:
            st.session_state.pop("recipes", None)
            st.session_state.pop("selected_recipe", None)
            st.error("❌ 레시피 생성 실패: 모델 제공자 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
        elif response.status_code != 200:
            st.session_state.pop("recipes", None)
            st.session_state.pop("selected_recipe", None)
            st.error(f"❌ 레시피 생성 실패: 요청이 실패했습니다 (status {response.status_code}).")
            st.code(response.text)
        else:
            body = response.json()
            choices = body.get("choices")
            if not choices:
                st.session_state.pop("recipes", None)
                st.session_state.pop("selected_recipe", None)
                st.error("❌ 레시피 생성 실패: 모델 응답 형식이 올바르지 않습니다 (choices 없음). 잠시 후 다시 시도해주세요.")
                st.code(response.text)
            else:
                content = choices[0]["message"]["content"]
                recipes = parse_recipes(content)
                if not recipes:
                    st.session_state.pop("recipes", None)
                    st.session_state.pop("selected_recipe", None)
                    st.error("❌ 레시피 생성 실패: 서로 다른 모델 3차 시도 모두 응답을 레시피로 변환하지 못했습니다.")
                    st.code(content)
                else:
                    st.session_state.recipes = recipes
                    st.session_state.selected_recipe = 0

    if st.session_state.get("recipes"):
        st.caption("💡 매 요청마다 다른 레시피가 나올 수 있어요. 마음에 안 들면 다시 추천받아보세요.")
        cols = st.columns(len(st.session_state.recipes))
        for idx, (col, r) in enumerate(zip(cols, st.session_state.recipes)):
            with col:
                with st.container(border=True, height=260):
                    st.markdown(f"**{r.get('name', '이름 없음')}**")
                    st.write(f"⏱ 약 {r.get('cook_time_minutes', '?')}분")
                    missing = r.get("missing_ingredients") or []
                    if missing:
                        st.warning("부족: " + ", ".join(missing))
                    else:
                        st.success("모든 재료 보유!")
                    if st.button("자세히 보기", key=f"select_recipe_{idx}"):
                        st.session_state.selected_recipe = idx

        selected_idx = st.session_state.get("selected_recipe")
        if selected_idx is not None and 0 <= selected_idx < len(st.session_state.recipes):
            recipe = st.session_state.recipes[selected_idx]
            st.divider()
            detail_header_col, detail_back_col = st.columns([4, 1])
            detail_header_col.markdown(f"### 📖 {recipe.get('name', '이름 없음')}")
            if detail_back_col.button("← 목록으로"):
                st.session_state.pop("selected_recipe", None)
                st.rerun()

            st.write("**사용 재료**: " + ", ".join(recipe.get("used_ingredients") or []))
            missing = recipe.get("missing_ingredients") or []
            if missing:
                st.warning("**부족한 재료**: " + ", ".join(missing))
            else:
                st.success("모든 재료를 보유하고 있습니다!")
            st.write("**조리 순서**")
            for step_idx, step in enumerate(recipe.get("steps") or [], start=1):
                st.write(f"{step_idx}. {step}")

            if st.button("레시피 저장", key="save_recipe"):
                user = current_user()
                if not user:
                    st.warning("로그인 후 저장할 수 있습니다. 왼쪽 사이드바에서 로그인/회원가입해주세요.")
                else:
                    db.save_recipe(user["id"], recipe)
                    st.success(f"'{recipe.get('name')}' 레시피를 저장했습니다. 사이드바의 '내 레시피'에서 확인하세요.")
