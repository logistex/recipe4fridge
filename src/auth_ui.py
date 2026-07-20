import streamlit as st

import auth
import db

db.init_db()

# app.py의 1~2단계 진행 상태 키. 로그아웃 시 이전 화면(재료 목록/레시피 등)이
# 남아있지 않도록 함께 지운다. app.py에서 새 session_state 키를 추가하면 여기도 갱신해야 한다.
APP_FLOW_STATE_KEYS = [
    "ingredients",
    "recognition_error",
    "recognition_error_detail",
    "used_vision_model",
    "confirmed_ingredients",
    "recipes",
    "selected_recipe",
    "last_recipe_request_time",
    "auto_generate_recipes",
    "recipe_cuisine",
    "recipe_difficulty",
    "recipe_time",
    "recipe_servings",
]


def current_user():
    return st.session_state.get("current_user")


def render_sidebar_auth():
    """사이드바에 로그인 상태/로그인·회원가입 폼을 그린다. 모든 페이지에서 공통으로 호출한다."""
    with st.sidebar:
        user = current_user()
        if user:
            st.markdown(f"👋 **{user['nickname']}**님")
            st.caption(user["email"])
            if st.button("로그아웃", key="logout_button"):
                st.session_state.pop("current_user", None)
                for key in APP_FLOW_STATE_KEYS:
                    st.session_state.pop(key, None)
                st.rerun()
        else:
            st.subheader("로그인 / 회원가입")
            tab_login, tab_signup = st.tabs(["로그인", "회원가입"])

            with tab_login:
                with st.form("login_form"):
                    login_email = st.text_input("이메일", key="login_email")
                    login_password = st.text_input("비밀번호", type="password", key="login_password")
                    submitted = st.form_submit_button("로그인")
                    if submitted:
                        ok, result = auth.login(login_email, login_password)
                        if ok:
                            st.session_state.current_user = result
                            st.rerun()
                        else:
                            st.error(result)

            with tab_signup:
                with st.form("signup_form"):
                    signup_email = st.text_input("이메일", key="signup_email")
                    signup_nickname = st.text_input("닉네임", key="signup_nickname")
                    signup_password = st.text_input(
                        "비밀번호 (8자 이상)", type="password", key="signup_password"
                    )
                    submitted = st.form_submit_button("회원가입")
                    if submitted:
                        ok, result = auth.signup(signup_email, signup_password, signup_nickname)
                        if ok:
                            st.session_state.current_user = result
                            st.success("회원가입이 완료되었습니다.")
                            st.rerun()
                        else:
                            st.error(result)
