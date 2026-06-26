# rubi_ai.py
import streamlit as st
from openai import OpenAI

with open("AI_API_KEY.txt") as file:
    
    API_KEY = file.read().strip()

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com"
)

st.set_page_config(page_title="Rubi AI", page_icon="⚡")
st.title("Rubi AI — твой помощник")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "system",
            "content": (
                "Ты Rubi AI — репетитор образовательной платформы Stud&School. "
                "Ты помогаешь школьникам 5-11 классов с математикой, физикой и информатикой. "
                "Твои правила:\n"
                "1. Не даёшь готовых ответов — ведёшь к решению через наводящие вопросы.\n"
                "2. Объясняешь простым языком, без сложного жаргона.\n"
                "3. Если задача непонятна — просишь уточнить условие.\n"
                "4. Можешь предлагать похожие задачи для закрепления.\n"
                "5. Ты дружелюбный, терпеливый, не осуждаешь за ошибки."
            )
        }
    ]

for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

if prompt := st.chat_input("Задай вопрос по математике, физике или информатике..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""

        stream = client.chat.completions.create(
            model="deepseek-chat",
            messages=st.session_state.messages,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content
                placeholder.markdown(full_response + "▌")

        placeholder.markdown(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})