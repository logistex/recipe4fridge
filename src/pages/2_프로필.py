import streamlit as st

import db
from auth_ui import current_user, render_sidebar_auth
from recipe import CUISINE_OPTIONS, DIFFICULTY_OPTIONS, SERVINGS_OPTIONS, TIME_OPTIONS

st.set_page_config(page_title="프로필", page_icon="👤")
render_sidebar_auth()

st.title("👤 프로필")

user = current_user()
if not user:
    st.info("로그인 후 프로필을 확인할 수 있습니다. 왼쪽 사이드바에서 로그인/회원가입해주세요.")
    st.stop()

st.write(f"**이메일**: {user['email']}")

with st.form("profile_form"):
    new_nickname = st.text_input("닉네임", value=user["nickname"])
    submitted = st.form_submit_button("저장")
    if submitted:
        new_nickname = new_nickname.strip()
        if not new_nickname:
            st.error("닉네임을 입력해주세요.")
        else:
            db.update_nickname(user["id"], new_nickname)
            st.session_state.current_user["nickname"] = new_nickname
            st.success("닉네임이 변경되었습니다.")
            st.rerun()

st.divider()
st.subheader("🍳 레시피 추천 기본값")
st.caption("여기서 설정한 값이 레시피 추천 화면(3단계)의 기본 선택값으로 채워집니다. 그 화면에서 매번 다시 바꿀 수 있습니다.")

saved = db.get_user_by_id(user["id"])


def _index(saved_value, options):
    return options.index(saved_value) if saved_value in options else 0


with st.form("recipe_preference_form"):
    pref_cols = st.columns(4)
    pref_cuisine = pref_cols[0].selectbox(
        "요리 종류", CUISINE_OPTIONS, index=_index(saved.get("default_cuisine"), CUISINE_OPTIONS)
    )
    pref_difficulty = pref_cols[1].selectbox(
        "난이도", DIFFICULTY_OPTIONS, index=_index(saved.get("default_difficulty"), DIFFICULTY_OPTIONS)
    )
    pref_time = pref_cols[2].selectbox(
        "조리 시간", TIME_OPTIONS, index=_index(saved.get("default_time"), TIME_OPTIONS)
    )
    pref_servings = pref_cols[3].selectbox(
        "인원", SERVINGS_OPTIONS, index=_index(saved.get("default_servings"), SERVINGS_OPTIONS)
    )
    pref_submitted = st.form_submit_button("기본값 저장")
    if pref_submitted:
        db.update_recipe_preferences(user["id"], pref_cuisine, pref_difficulty, pref_time, pref_servings)
        st.success("레시피 추천 기본값이 저장되었습니다.")
