from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

app = FastAPI()

#Live Server (5500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

with open("model/AI_API_KEY.txt") as file:
    API_KEY = file.read().strip()

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com"
)

messages = [
    {
        "role": "system",
        "content": (
            "Ты Rubi AI — репетитор платформы Rubium. "
            "Помогаешь с математикой, физикой, информатикой. "
            "Не даёшь готовых ответов, ведёшь к решению. "
            "Объясняешь понятно, дружелюбно."
        )
    }
]

class Message(BaseModel):
    content: str

@app.post("/chat")
async def chat(msg: Message):
    messages.append({"role": "user", "content": msg.content})
    
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages
    )
    
    reply = response.choices[0].message.content
    messages.append({"role": "assistant", "content": reply})
    
    return {"reply": reply}