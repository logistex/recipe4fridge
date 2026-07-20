import streamlit as st

import db
from auth_ui import current_user, render_sidebar_auth

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
