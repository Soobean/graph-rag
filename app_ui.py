"""Graph RAG Chat UI - Streamlit"""
import streamlit as st
import requests

st.title("Graph RAG")

API_URL = "http://localhost:8000/api/v1/query"

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("질문을 입력하세요"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    with st.spinner("검색 중..."):
        try:
            res = requests.post(API_URL, json={"question": prompt}, timeout=30)
            data = res.json()
            answer = data.get("response", "응답 없음")

            # 메타데이터 표시 (옵션)
            meta = data.get("metadata", {})
            if meta.get("cypher_query"):
                with st.expander("🔍 실행된 Cypher 쿼리"):
                    st.code(meta["cypher_query"], language="cypher")
        except Exception as e:
            answer = f"오류: {e}"

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.chat_message("assistant").write(answer)
