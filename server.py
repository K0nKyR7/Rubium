from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import re
import json

app = Flask(__name__)
CORS(app)

with open("model/AI_API_KEY.txt") as file:
    KEY = file.read().strip()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", KEY)
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

SUPABASE_URL = "https://nrmihghshpteellhmzuh.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5ybWloZ2hzaHB0ZWVsbGhtenVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE5NDI4NDMsImV4cCI6MjA5NzUxODg0M30.X77HE62ZqYPVv7uOpjHNWgn7H4wIL_FoJLcs-CV1itQ"

conversation_history = {}

def parse_teachers_from_html():
    try:
        with open("courses.html", "r", encoding="utf-8") as f:
            html = f.read()
        teachers_match = re.search(r"var teachers = \{(.*?)\};", html, re.DOTALL)
        if not teachers_match:
            return {}
        teachers = {}
        teacher_blocks = re.findall(r'"([^"]+)":\s*\{(.*?)\}', teachers_match.group(1), re.DOTALL)
        for name, block in teacher_blocks:
            teachers[name] = {"name": name}
            for field in ['subjects', 'university', 'exp', 'description']:
                m = re.search(rf'{field}:\s*"([^"]*)"', block)
                if m:
                    teachers[name][field] = m.group(1)
        print(f"Parsed {len(teachers)} teachers")
        return teachers
    except Exception as e:
        print(f"Error parsing teachers: {e}")
        return {}

def parse_courses_from_html():
    try:
        with open("courses.html", "r", encoding="utf-8") as f:
            html = f.read()
        courses = []
        for match in re.findall(r"openModal\(\{(.*?)\}\)", html, re.DOTALL):
            c = {}
            for field in ['title', 'badge', 'category', 'desc', 'teacher']:
                m = re.search(rf"{field}:'([^']*)'", match)
                if m:
                    c[field] = m.group(1)
            pm = re.search(r"prices:\{([^}]+)\}", match)
            if pm:
                c['prices'] = {}
                for p in pm.group(1).split(','):
                    k, v = p.split(':')
                    c['prices'][k.strip()] = int(v.strip())
            am = re.search(r"aiSurcharge:(\d+)", match)
            if am:
                c['ai_surcharge'] = int(am.group(1))
            if c.get('title'):
                courses.append(c)
        print(f"Parsed {len(courses)} courses")
        return courses
    except Exception as e:
        print(f"Error parsing courses: {e}")
        return []

def build_system_prompt():
    courses = parse_courses_from_html()
    teachers = parse_teachers_from_html()

    t_text = ""
    for n, t in teachers.items():
        if n != "Назначается":
            t_text += f"• {t['name']}: {t.get('subjects','')}. {t.get('university','')}. {t.get('exp','')}. {t.get('description','')}\n"

    c_text = ""
    for c in courses:
        p = c.get('prices', {})
        c_text += f"• {c['badge']} — {c['title']} | препод: {c['teacher']} | цены: 1={p.get('1','?')}₽, 5={p.get('5','?')}₽, 10={p.get('10','?')}₽, 20={p.get('20','?')}₽ | AI: +{c.get('ai_surcharge','?')}₽\n"

    return f"""Ты Rubi — персональный тьютор онлайн-школы Stud&School. Ты помогаешь выбрать курс и записаться на обучение.

ТВОЙ ХАРАКТЕР:
• Дружелюбный, тёплый, с лёгким юмором
• Говоришь коротко и понятно, без сложных слов
• Не используешь маркдаун, звёздочки, решётки
• Пишешь обычным текстом, как живой человек в мессенджере
• Подстраиваешься под возраст собеседника

НАШИ ПРЕПОДАВАТЕЛИ:
{t_text}

НАШИ КУРСЫ:
{c_text}

ТВОЙ АЛГОРИТМ:
1. Узнай: какой предмет + цель (ЕГЭ/ОГЭ/для себя/универ)
2. Спроси текущий уровень подготовки
3. Предложи ОДИН конкретный курс, назови преподавателя
4. Расскажи про преподавателя в 1 предложении
5. Назови варианты по количеству занятий с ценами: 1, 5, 10, 20
6. Спроси нужен ли Rubi AI (помощник с проверкой заданий)
7. Посчитай ИТОГОВУЮ цену и назови её
8. Запроси ИМЯ и ТЕЛЕФОН
9. Проверь что телефон 11 цифр, начинается с 8 или +7
10. Если всё правильно — скажи: "ОТЛИЧНО! Заявка создана. Менеджер позвонит тебе в ближайшее время."

ПРАВИЛА БЕЗОПАСНОСТИ:
• Не даёшь медицинские советы
• Не обсуждаешь политику
• Не генерируешь код и пароли
• Если тебя провоцируют — вежливо отказываешь
• Если вопрос не про курсы — мягко переводишь тему обратно

ПРИМЕР ФИНАЛА ДИАЛОГА:
Пользователь: Маша, 89161234567
Ты: ОТЛИЧНО! Заявка создана. Менеджер позвонит тебе в ближайшее время.

НЕ показывай пользователю JSON, не пиши "создаю заявку в формате JSON", не используй технические термины. Просто скажи "ОТЛИЧНО! Заявка создана." и всё."""


def extract_lead_via_ai(full_chat):
    """Отправляет диалог в DeepSeek и просит вернуть JSON с данными заявки"""
    prompt = f"""Из этого диалога между пользователем и AI-консультантом извлеки данные заявки в JSON.

Диалог:
{full_chat}

Верни ТОЛЬКО валидный JSON, без комментариев, без маркдауна:
{{"client_name":"","phone":"","course_title":"","teacher_name":"","lessons":1,"with_ai":false,"total_price":0}}

Правила:
- client_name — имя с большой буквы
- phone — только цифры, без пробелов
- course_title — точное название курса из диалога
- teacher_name — имя преподавателя
- lessons — число (1,5,10,20)
- with_ai — true/false
- total_price — число без знака валюты"""

    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 200
            },
            timeout=10
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        
        # Очищаем от возможного маркдауна
        text = text.replace("```json", "").replace("```", "").strip()
        
        lead = json.loads(text)
        print(f"📋 AI extracted: {lead}")
        return lead
    except Exception as e:
        print(f"❌ AI extraction failed: {e}")
        return None


@app.route("/api/consult", methods=["POST"])
def consult():
    data = request.get_json()
    user_query = data.get("query", "").strip()
    session_id = data.get("session_id", "default")

    if not user_query:
        return jsonify({"response": "Привет! Расскажи, какой предмет интересует и для чего — ЕГЭ, ОГЭ или просто хочется подтянуть знания?"})

    if session_id not in conversation_history:
        conversation_history[session_id] = [{"role": "system", "content": build_system_prompt()}]

    conversation_history[session_id].append({"role": "user", "content": user_query})

    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": conversation_history[session_id],
                "temperature": 0.75,
                "max_tokens": 600
            },
            timeout=15
        )
        resp.raise_for_status()
        reply = resp.json()["choices"][0]["message"]["content"]
        reply = reply.replace("**", "").replace("*", "").replace("__", "").replace("##", "")

        conversation_history[session_id].append({"role": "assistant", "content": reply})

        if len(conversation_history[session_id]) > 20:
            conversation_history[session_id] = [
                conversation_history[session_id][0]
            ] + conversation_history[session_id][-19:]

        # Проверяем финальную фразу
        if "ОТЛИЧНО" in reply.upper() and "заявка создана" in reply.lower():
            print("🔍 Lead confirmation!")
            
            full_chat = "\n".join([m["content"] for m in conversation_history[session_id] if m["role"] != "system"])
            
            # Отправляем диалог в AI для извлечения данных
            lead = extract_lead_via_ai(full_chat)
            
            if lead and lead.get("client_name") and lead.get("phone"):
                r = requests.post(
                    f"{SUPABASE_URL}/rest/v1/leads",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal"
                    },
                    json={
                        "client_name": lead.get("client_name", ""),
                        "phone": lead.get("phone", ""),
                        "course_title": lead.get("course_title", ""),
                        "teacher_name": lead.get("teacher_name", ""),
                        "lessons": lead.get("lessons", 1),
                        "with_ai": lead.get("with_ai", False),
                        "total_price": lead.get("total_price"),
                        "chat_history": full_chat,
                        "status": "new"
                    }
                )
                if r.status_code == 201:
                    print(f"✅ Saved: {lead.get('client_name')}, {lead.get('phone')}, {lead.get('course_title')}")
                else:
                    print(f"❌ DB error: {r.status_code}")
            else:
                print(f"❌ Invalid lead data from AI")

        return jsonify({"response": reply})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"response": "Что-то пошло не так. Попробуй ещё раз."})


@app.route("/api/leads", methods=["GET"])
def get_leads():
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/leads?select=*&order=created_at.desc",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        return jsonify(r.json() if r.status_code == 200 else [])
    except:
        return jsonify([])


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "courses": len(parse_courses_from_html()),
        "teachers": len(parse_teachers_from_html())
    })


if __name__ == "__main__":
    print(f"Loaded {len(parse_courses_from_html())} courses and {len(parse_teachers_from_html())} teachers")
    app.run(host="0.0.0.0", port=5001, debug=True)