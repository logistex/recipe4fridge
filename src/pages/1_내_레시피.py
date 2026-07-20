import streamlit as st

import db
from auth_ui import current_user, render_sidebar_auth

st.set_page_config(page_title="내 레시피", page_icon="📖")
render_sidebar_auth()

st.title("📖 내 레시피")

user = current_user()
if not user:
    st.info("로그인 후 저장한 레시피를 볼 수 있습니다. 왼쪽 사이드바에서 로그인/회원가입해주세요.")
    st.stop()

recipes = db.list_recipes(user["id"])

if not recipes:
    st.info("아직 저장한 레시피가 없습니다. 2단계 레시피 상세 화면에서 '레시피 저장'을 눌러보세요.")
else:
    delete_target = None
    for recipe in recipes:
        with st.container(border=True):
            col_main, col_delete = st.columns([5, 1])
            with col_main:
                st.markdown(f"### {recipe['name']}")
                st.caption(f"저장 시각: {recipe['saved_at']}")
                st.write(f"⏱ 약 {recipe.get('cook_time_minutes', '?')}분")
                st.write("**사용 재료**: " + ", ".join(recipe["used_ingredients"]))
                if recipe["missing_ingredients"]:
                    st.write("**추가로 필요한 재료**: " + ", ".join(recipe["missing_ingredients"]))
                with st.expander("조리 순서 보기"):
                    for i, step in enumerate(recipe["steps"], start=1):
                        st.write(f"{i}. {step}")
            with col_delete:
                if st.button("삭제", key=f"delete_saved_{recipe['id']}"):
                    delete_target = recipe["id"]

    if delete_target is not None:
        db.delete_recipe(user["id"], delete_target)
        st.rerun()
