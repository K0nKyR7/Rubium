import json
import os
import re

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS


# ─── Configuration ────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

with open("model/AI_API_KEY.txt") as f:
    KEY = f.read().strip()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", KEY)
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

SUPABASE_URL = "https://nrmihghshpteellhmzuh.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5ybWloZ2hzaHB0ZWVsbGhtenVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE5NDI4NDMsImV4cCI6MjA5NzUxODg0M30."
    "X77HE62ZqYPVv7uOpjHNWgn7H4wIL_FoJLcs-CV1itQ"
)

conversation_history = {}


# ─── HTML Parsers ─────────────────────────────────────────────────────────────

def parse_teachers_from_html():
    """Extract teacher data from courses.html."""
    try:
        with open("courses.html", "r", encoding="utf-8") as f:
            html = f.read()

        teachers_match = re.search(r"var teachers = \{(.*?)\};", html, re.DOTALL)
        if not teachers_match:
            return {}

        teachers = {}
        teacher_blocks = re.findall(
            r'"([^"]+)":\s*\{(.*?)\}', teachers_match.group(1), re.DOTALL
        )

        for name, block in teacher_blocks:
            teachers[name] = {"name": name}
            for field in ["subjects", "university", "exp", "description"]:
                m = re.search(rf'{field}:\s*"([^"]*)"', block)
                if m:
                    teachers[name][field] = m.group(1)

        print(f"Parsed {len(teachers)} teachers")
        return teachers

    except Exception as e:
        print(f"Error parsing teachers: {e}")
        return {}


def parse_courses_from_html():
    """Extract course data from courses.html."""
    try:
        with open("courses.html", "r", encoding="utf-8") as f:
            html = f.read()

        courses = []
        for match in re.findall(r"openModal\(\{(.*?)\}\)", html, re.DOTALL):
            c = {}
            for field in ["title", "badge", "category", "desc", "teacher"]:
                m = re.search(rf"{field}:'([^']*)'", match)
                if m:
                    c[field] = m.group(1)

            pm = re.search(r"prices:\{([^}]+)\}", match)
            if pm:
                c["prices"] = {}
                for p in pm.group(1).split(","):
                    k, v = p.split(":")
                    c["prices"][k.strip()] = int(v.strip())

            am = re.search(r"aiSurcharge:(\d+)", match)
            if am:
                c["ai_surcharge"] = int(am.group(1))

            if c.get("title"):
                courses.append(c)

        print(f"Parsed {len(courses)} courses")
        return courses

    except Exception as e:
        print(f"Error parsing courses: {e}")
        return []


# ─── AI System Prompt ─────────────────────────────────────────────────────────

def build_system_prompt():
    """Build the Rubi AI tutor system prompt with live course/teacher data."""
    courses = parse_courses_from_html()
    teachers = parse_teachers_from_html()

    t_text = ""
    for name, t in teachers.items():
        if name != "Назначается":
            t_text += (
                f"• {t['name']}: {t.get('subjects', '')}. "
                f"{t.get('university', '')}. {t.get('exp', '')}. "
                f"{t.get('description', '')}\n"
            )

    c_text = ""
    for c in courses:
        p = c.get("prices", {})
        c_text += (
            f"• {c['badge']} — {c['title']} | "
            f"препод: {c['teacher']} | "
            f"цены: 1={p.get('1', '?')}₽, 5={p.get('5', '?')}₽, "
            f"10={p.get('10', '?')}₽, 20={p.get('20', '?')}₽ | "
            f"AI: +{c.get('ai_surcharge', '?')}₽\n"
        )

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


# ─── AI Lead Extraction ───────────────────────────────────────────────────────

def extract_lead_via_ai(full_chat):
    """Use DeepSeek to extract lead data from conversation history."""
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
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 200,
            },
            timeout=10,
        )
        resp.raise_for_status()

        text = resp.json()["choices"][0]["message"]["content"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        lead = json.loads(text)

        print(f"📋 AI extracted: {lead}")
        return lead

    except Exception as e:
        print(f"❌ AI extraction failed: {e}")
        return None


# ─── Supabase Helpers ─────────────────────────────────────────────────────────

def supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def save_lead(lead):
    """Save a lead record to Supabase."""
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/leads",
        headers=supabase_headers(),
        json={
            "client_name": lead.get("client_name", ""),
            "phone": lead.get("phone", ""),
            "course_title": lead.get("course_title", ""),
            "teacher_name": lead.get("teacher_name", ""),
            "lessons": lead.get("lessons", 1),
            "with_ai": lead.get("with_ai", False),
            "total_price": lead.get("total_price"),
            "student_message": "",
            "student_id": None,
            "chat_history": lead.get("chat_history", ""),
            "status": "new",
        },
    )
    return r.status_code == 201


# ─── API Routes ───────────────────────────────────────────────────────────────

@app.route("/api/consult", methods=["POST"])
def consult():
    data = request.get_json()
    user_query = data.get("query", "").strip()
    session_id = data.get("session_id", "default")

    if not user_query:
        return jsonify({
            "response": "Привет! Расскажи, какой предмет интересует и для чего — ЕГЭ, ОГЭ или просто хочется подтянуть знания?"
        })

    if session_id not in conversation_history:
        conversation_history[session_id] = [
            {"role": "system", "content": build_system_prompt()}
        ]

    conversation_history[session_id].append({"role": "user", "content": user_query})

    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": conversation_history[session_id],
                "temperature": 0.75,
                "max_tokens": 600,
            },
            timeout=15,
        )
        resp.raise_for_status()

        reply = resp.json()["choices"][0]["message"]["content"]
        reply = reply.replace("**", "").replace("*", "").replace("__", "").replace("##", "")
        conversation_history[session_id].append({"role": "assistant", "content": reply})

        # Trim history to last 20 messages (keeping system prompt)
        if len(conversation_history[session_id]) > 20:
            conversation_history[session_id] = [
                conversation_history[session_id][0],
                *conversation_history[session_id][-19:],
            ]

        # Auto-extract lead when AI confirms registration
        if "ОТЛИЧНО" in reply.upper() and "заявка создана" in reply.lower():
            print("🔍 Lead confirmation!")
            full_chat = "\n".join(
                m["content"]
                for m in conversation_history[session_id]
                if m["role"] != "system"
            )
            lead = extract_lead_via_ai(full_chat)

            if lead and lead.get("client_name") and lead.get("phone"):
                lead["chat_history"] = full_chat
                if save_lead(lead):
                    print(
                        f"✅ Saved: {lead.get('client_name')}, "
                        f"{lead.get('phone')}, {lead.get('course_title')}"
                    )
                else:
                    print("❌ DB error")
            else:
                print("❌ Invalid lead data from AI")

        return jsonify({"response": reply})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"response": "Что-то пошло не так. Попробуй ещё раз."})


@app.route("/api/leads", methods=["POST"])
def create_lead():
    data = request.get_json()
    try:
        body = {
            "client_name": data.get("client_name", ""),
            "phone": data.get("phone", ""),
            "course_title": data.get("course_title", ""),
            "teacher_name": data.get("teacher_name", ""),
            "lessons": data.get("lessons", 1),
            "with_ai": data.get("with_ai", False),
            "total_price": data.get("total_price"),
            "student_message": data.get("student_message", ""),
            "chat_history": data.get("chat_history", ""),
            "status": "new",
        }
        # student_id добавляем только если он реально есть
        sid = data.get("student_id")
        if sid:
            body["student_id"] = sid

        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        print("📤 Supabase insert:", r.status_code, r.text[:200])
        if r.status_code == 201:
            return jsonify({"status": "ok"})
        return jsonify({"status": "error", "detail": r.text[:200]}), 500
    except Exception as e:
        print("❌ Exception:", e)
        return jsonify({"status": "error"}), 500
    
def save_lead(lead):
    body = {
        "client_name": lead.get("client_name", ""),
        "phone": lead.get("phone", ""),
        "course_title": lead.get("course_title", ""),
        "teacher_name": lead.get("teacher_name", ""),
        "lessons": lead.get("lessons", 1),
        "with_ai": lead.get("with_ai", False),
        "total_price": lead.get("total_price"),
        "chat_history": lead.get("chat_history", ""),
        "status": "new",
    }
    # student_id и student_message только если есть
    if lead.get("student_id"):
        body["student_id"] = lead["student_id"]
    if lead.get("student_message"):
        body["student_message"] = lead["student_message"]

    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/leads",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        },
        json=body,
    )
    print(f"📤 save_lead: {r.status_code} {r.text[:200]}")
    return r.status_code == 201


@app.route("/api/leads", methods=["GET"])
def get_leads():
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/leads?select=*&order=created_at.desc",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        )
        return jsonify(r.json() if r.status_code == 200 else [])
    except Exception:
        return jsonify([])


@app.route("/api/leads/<lead_id>", methods=["PATCH"])
def update_lead(lead_id):
    data = request.get_json()
    try:
        body = {}
        if "status" in data:
            body["status"] = data["status"]
        if "reject_reason" in data:
            body["reject_reason"] = data["reject_reason"]
        
        if not body:
            return jsonify({"status": "error", "detail": "no fields"}), 400

        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead_id}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        print(f"📤 PATCH lead {lead_id}: {r.status_code} {r.text[:200]}")
        return jsonify({"status": "ok" if r.status_code in (200, 204) else "error"})
    except Exception as e:
        print("❌ PATCH error:", e)
        return jsonify({"status": "error"}), 500

@app.route("/api/leads/<lead_id>/accept", methods=["POST"])
def accept_lead(lead_id):
    """Принять заявку — назначает учителя и меняет статус"""
    try:
        data = request.get_json() or {}
        teacher_id = data.get("teacher_id")
        
        body = {"status": "accepted"}
        if teacher_id:
            body["teacher_id"] = teacher_id
        
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead_id}",
            headers=supabase_headers(),
            json=body,
        )
        return jsonify({"status": "ok" if r.status_code == 204 else "error"})
    except Exception:
        return jsonify({"status": "error"}), 500

@app.route("/api/teacher/<teacher_id>/leads", methods=["GET"])
def get_teacher_leads(teacher_id):
    """Получить заявки для конкретного учителя"""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/leads"
            f"?teacher_id=eq.{teacher_id}"
            f"&select=*"
            f"&order=created_at.desc",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        )
        return jsonify(r.json() if r.status_code == 200 else [])
    except Exception:
        return jsonify([])

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "courses": len(parse_courses_from_html()),
        "teachers": len(parse_teachers_from_html()),
    })


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(
        f"Loaded {len(parse_courses_from_html())} courses and "
        f"{len(parse_teachers_from_html())} teachers"
    )
    app.run(host="0.0.0.0", port=5001, debug=True)
