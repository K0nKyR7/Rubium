import json
import os
import re
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
CORS(app, origins=[
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:5000",
    "https://studandschool.ru"
])

# ─── Конфигурация ───
with open("model/AI_API_KEY.txt") as f:
    DEEPSEEK_API_KEY = f.read().strip()

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
SUPABASE_URL = "https://nrmihghshpteellhmzuh.supabase.co"
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

conversation_history = {}
CONFIDENCE_THRESHOLD = 0.85


def supabase_headers(use_service_role=False):
    key = SUPABASE_SERVICE_KEY if use_service_role and SUPABASE_SERVICE_KEY else SUPABASE_ANON_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    
@app.route("/api/leads/cleanup", methods=["POST"])
def cleanup_old_leads():
    """Удаляет принятые заявки старше 7 дней."""
    try:
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        # Получаем старые принятые заявки
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/leads?select=id&status=eq.accepted&created_at=lt.{seven_days_ago.isoformat()}",
            headers=supabase_headers(use_service_role=True)
        )
        
        if r.status_code == 200 and r.json():
            ids = [lead['id'] for lead in r.json()]
            for lead_id in ids:
                requests.delete(
                    f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead_id}",
                    headers=supabase_headers(use_service_role=True)
                )
            return jsonify({"status": "ok", "deleted": len(ids)})
        return jsonify({"status": "ok", "deleted": 0})
    except Exception as e:
        print(f"❌ Cleanup error: {e}")
        return jsonify({"status": "error"}), 500


def get_user_from_token(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    
    token = auth_header.replace("Bearer ", "")
    try:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"}
        )
        if r.status_code == 200:
            user_data = r.json()
            return {
                "id": user_data.get("id"),
                "email": user_data.get("email", ""),
                "first_name": user_data.get("user_metadata", {}).get("first_name", ""),
                "last_name": user_data.get("user_metadata", {}).get("last_name", ""),
                "role": user_data.get("user_metadata", {}).get("role", "student")
            }
    except Exception as e:
        print(f"❌ Auth error: {e}")
    return None

def get_teacher_id_from_db(name):
    if not name:
        return None
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/get_teacher_id",
            headers=supabase_headers(),
            json={"teacher_name": name.strip()}
        )
        if r.status_code == 200 and r.text.strip():
            return r.text.replace('"', '')
    except Exception as e:
        print(f"❌ get_teacher_id error: {e}")
    return None


def get_teachers_from_db():
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/users?select=id,first_name,last_name,email,role"
            f"&role=in.(teacher,admin)&order=first_name.asc",
            headers=supabase_headers()
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"❌ get_teachers error: {e}")
    return []


def get_courses_from_db():
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/courses?select=*&order=created_at.asc",
            headers=supabase_headers()
        )
        if r.status_code == 200:
            courses = r.json()
            for c in courses:
                if isinstance(c.get("prices"), str):
                    c["prices"] = json.loads(c["prices"])
            return courses
    except Exception as e:
        print(f"❌ Courses error: {e}")
    return []


def build_system_prompt(user_info=None):
    courses = get_courses_from_db()
    teachers = get_teachers_from_db()

    t_text = ""
    for t in teachers:
        full_name = f"{t.get('first_name', '')} {t.get('last_name', '')}".strip()
        t_text += f"• {full_name}\n"

    c_text = ""
    for c in courses:
        p = c.get("prices", {})
        c_text += (
            f"• {c['badge']} — {c['title']} | "
            f"препод: {c['teacher_name']} | "
            f"цены: 1={p.get('1', '?')}₽, 5={p.get('5', '?')}₽, "
            f"10={p.get('10', '?')}₽, 20={p.get('20', '?')}₽ | "
            f"AI: +{c.get('ai_surcharge', '?')}₽\n"
        )

    user_context = ""
    if user_info:
        user_context = f"""
ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ:
• Имя: {user_info.get('first_name', 'Не указано')} {user_info.get('last_name', '')}
• Email: {user_info.get('email', 'Не указано')}
• Роль: {user_info.get('role', 'ученик')}

ВАЖНО: Ты уже знаешь имя пользователя. Обращайся к нему по имени.
НЕ спрашивай имя повторно. Но ОБЯЗАТЕЛЬНО запроси:
- Телефон (11 цифр, начиная с 8 или +7)
- Telegram (username или номер)
- ВКонтакте (ссылка или ник)
"""

    return f"""Ты Rubi — персональный тьютор онлайн-школы Stud&School. Помогаешь выбрать курс и записаться.

ХАРАКТЕР: дружелюбный, тёплый, с лёгким юмором. Коротко и понятно. Без маркдауна. Обычный текст, как в мессенджере. Обращайся по имени, не слишком формально, но и не фамильярно, не нужно писать фамилию. Не используй "ты" и "вы" в начале предложений. Не называй "скидки" и "акции", не придумывай цены. Не придумывай курсы и преподавателей, которых нет в списках.

{user_context}

ПРЕПОДАВАТЕЛИ:
{t_text}

КУРСЫ:
{c_text}

АЛГОРИТМ:
1. Узнай предмет + цель (ЕГЭ/ОГЭ/для себя/универ)
2. Спроси уровень подготовки
3. Предложи ОДИН конкретный курс с преподавателем
4. Расскажи про преподавателя в 1 предложении
5. Назови варианты занятий с ценами: 1, 5, 10, 20
6. Спроси нужен ли Rubi AI (+цена)
7. Посчитай ИТОГОВУЮ цену
8. Запроси ТЕЛЕФОН
9. Спроси Telegram или ВКонтакте (необязательно)
10. Проверь что телефон 11 цифр, начинается с 8 или +7

ЖЁСТКИЕ ПРАВИЛА:
• Ты можешь предлагать ТОЛЬКО курсы и преподавателей из списков выше
• НЕ придумывай курсы, которых нет в списке
• НЕ придумывай преподавателей — только те, что перечислены
• Если подходящего курса нет — честно скажи "давай я уточню у менеджера"
• Если назвал несуществующий курс или преподавателя — извинись и предложи из списка
• Цены бери ТОЛЬКО из списка курсов, не выдумывай
- не называй "скидки" и "акции", не придумывай цены
- не используй маркдаун, не вставляй ссылки, не давай код и пароли, символы как */ и т.д.
- не пиши много текста, не повторяйся
- пиши максимаоьно удобно доя восприятия, как в мессенджере, коротко и понятно

ТВОИ КУРСЫ И ПРЕПОДАВАТЕЛИ УКАЗАНЫ НИЖЕ. ЭТО ИСЧЕРПЫВАЮЩИЙ СПИСОК.
ТЫ НЕ ИМЕЕШЬ ПРАВА УПОМИНАТЬ ДРУГИЕ КУРСЫ ИЛИ ПРЕПОДАВАТЕЛЕЙ.
ЕСЛИ У НАС НЕТ НУЖНОГО ПРЕДМЕТА — ЧЕСТНО СКАЖИ ОБ ЭТОМ.

КОГДА ДИАЛОГ ЗАВЕРШЁН (имя + телефон + курс подтверждены):
• Добавь в конец ответа блок [SYSTEM] с JSON:
[SYSTEM]{{"confidence":0.95,"lead":{{"client_name":"Имя","phone":"79991234567","course_title":"Название","teacher_name":"Имя Фамилия","lessons":1,"with_ai":false,"total_price":1500,"tg_username":"","vk_username":""}}}}[/SYSTEM]
• confidence: 0.0-1.0 (насколько уверен что заявка готова)
• client_name заполни из информации о пользователе выше — не спрашивай имя повторно
• Если заявка не готова — не добавляй блок [SYSTEM]
• Не говори "ОТЛИЧНО! Заявка создана" пока confidence < 0.85

ПРАВИЛА: без медицины, без политики, без кода и паролей. При провокации — вежливый отказ. Не по теме курсов — мягко перевести."""


def parse_structured_response(content):
    """Извлекает [SYSTEM] JSON из ответа AI."""
    match = re.search(r'\[SYSTEM\](.*?)\[/SYSTEM\]', content, re.DOTALL)
    if not match:
        return content, None

    try:
        system_data = json.loads(match.group(1).strip())
        clean_content = re.sub(r'\[SYSTEM\].*?\[/SYSTEM\]', '', content, flags=re.DOTALL).strip()
        return clean_content, system_data
    except json.JSONDecodeError:
        return content, None


def save_lead_from_ai(lead_data, chat_history, student_id=None):
    """Сохраняет заявку из структурированных данных AI."""
    lead = lead_data.get("lead", lead_data)

    if not lead.get("client_name") or not lead.get("phone"):
        print(f"❌ Invalid lead data: {lead}")
        return False

    body = {
        "client_name": lead.get("client_name", ""),
        "phone": lead.get("phone", ""),
        "course_title": lead.get("course_title", ""),
        "teacher_name": lead.get("teacher_name", ""),
        "teacher_id": get_teacher_id_from_db(lead.get("teacher_name", "")),
        "lessons": lead.get("lessons", 1),
        "with_ai": lead.get("with_ai", False),
        "total_price": lead.get("total_price"),
        "chat_history": chat_history,
        "status": "new",
        "tg_username": lead.get("tg_username", ""),
        "vk_username": lead.get("vk_username", ""),
    }
    if student_id:
        body["student_id"] = student_id

    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/leads",
        headers=supabase_headers(use_service_role=True),
        json=body,
    )
    print(f"📤 save_lead: {r.status_code} {r.text[:300]}")
    return r.status_code == 201


# ─── Routes ───

@app.route("/api/consult", methods=["POST"])
def consult():
    # Проверка авторизации
    auth_header = request.headers.get("Authorization", "")
    user_info = get_user_from_token(auth_header)
    
    if not user_info:
        return jsonify({"response": "Пожалуйста, войдите в аккаунт чтобы общаться с Rubi AI.", "auth_required": True}), 401

    data = request.get_json()
    user_query = data.get("query", "").strip()
    session_id = data.get("session_id", "default")
    student_id = user_info.get("id")

    if not user_query:
        full_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
        return jsonify({"response": f"Привет, {full_name}! Расскажи, какой предмет интересует и для чего — ЕГЭ, ОГЭ или просто хочется подтянуть знания?"})

    if session_id not in conversation_history:
        conversation_history[session_id] = [{"role": "system", "content": build_system_prompt(user_info)}]

    conversation_history[session_id].append({"role": "user", "content": user_query})

    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": conversation_history[session_id],
                "temperature": 0.75,
                "max_tokens": 800
            },
            timeout=20,
        )
        resp.raise_for_status()
        raw_reply = resp.json()["choices"][0]["message"]["content"]

        clean_reply, system_data = parse_structured_response(raw_reply)
        conversation_history[session_id].append({"role": "assistant", "content": clean_reply})

        if len(conversation_history[session_id]) > 20:
            conversation_history[session_id] = [
                conversation_history[session_id][0],
                *conversation_history[session_id][-19:]
            ]

        if system_data:
            try:
                confidence = float(system_data.get("confidence", 0))
            except (ValueError, TypeError):
                confidence = 0

            if confidence >= CONFIDENCE_THRESHOLD:
                full_chat = "\n".join(
                    m["content"] for m in conversation_history[session_id] if m["role"] != "system"
                )
                if save_lead_from_ai(system_data, full_chat, student_id):
                    print(f"✅ Auto-saved lead: {system_data.get('lead', {}).get('client_name', '?')}")
                    clean_reply += "\n\nЗаявка создана. Менеджер свяжется с тобой в ближайшее время."
                else:
                    print("❌ Failed to save lead from AI")

        return jsonify({"response": clean_reply})

    except Exception as e:
        print(f"❌ Consult error: {e}")
        return jsonify({"response": "Что-то пошло не так. Попробуй ещё раз."})


@app.route("/api/courses", methods=["GET"])
def get_courses():
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/courses?select=*&order=created_at.asc",
            headers=supabase_headers()
        )
        return jsonify(r.json() if r.status_code == 200 else [])
    except Exception as e:
        print(f"❌ Courses error: {e}")
        return jsonify([])


@app.route("/api/teachers", methods=["GET"])
def get_teachers():
    try:
        return jsonify(get_teachers_from_db())
    except Exception as e:
        print(f"❌ Teachers error: {e}")
        return jsonify([])


@app.route("/api/leads", methods=["GET"])
def get_leads():
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/leads?select=*&order=created_at.desc",
            headers=supabase_headers(use_service_role=True)
        )
        return jsonify(r.json() if r.status_code == 200 else [])
    except Exception:
        return jsonify([])


@app.route("/api/leads", methods=["POST"])
def create_lead():
    # Проверка авторизации
    auth_header = request.headers.get("Authorization", "")
    user_info = get_user_from_token(auth_header)
    
    if not user_info:
        return jsonify({"status": "error", "detail": "Требуется авторизация"}), 401

    data = request.get_json()
    try:
        body = {
            "client_name": data.get("client_name", f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()),
            "phone": data.get("phone", ""),
            "course_title": data.get("course_title", ""),
            "teacher_name": data.get("teacher_name", ""),
            "teacher_id": get_teacher_id_from_db(data.get("teacher_name", "")),
            "lessons": data.get("lessons", 1),
            "with_ai": data.get("with_ai", False),
            "total_price": data.get("total_price"),
            "student_message": data.get("student_message", ""),
            "chat_history": data.get("chat_history", ""),
            "status": "new",
            "tg_username": data.get("tg_username", ""),
            "vk_username": data.get("vk_username", ""),
            "student_id": user_info.get("id"),
        }

        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers=supabase_headers(use_service_role=True),
            json=body,
        )
        if r.status_code == 201:
            return jsonify({"status": "ok"})
        return jsonify({"status": "error", "detail": r.text[:200]}), 500
    except Exception as e:
        print("❌ Exception:", e)
        return jsonify({"status": "error"}), 500


@app.route("/api/leads/<lead_id>", methods=["PATCH"])
def update_lead(lead_id):
    data = request.get_json()
    try:
        body = {}
        if "status" in data:
            body["status"] = data["status"]
        if "reject_reason" in data:
            body["reject_reason"] = data["reject_reason"]
        if "teacher_name" in data:
            body["teacher_name"] = data["teacher_name"]
            body["teacher_id"] = get_teacher_id_from_db(data["teacher_name"])
        if not body:
            return jsonify({"status": "error", "detail": "no fields"}), 400

        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead_id}",
            headers=supabase_headers(use_service_role=True),
            json=body,
        )
        return jsonify({"status": "ok" if r.status_code in (200, 204) else "error"})
    except Exception as e:
        print("❌ PATCH error:", e)
        return jsonify({"status": "error"}), 500


@app.route("/api/leads/<lead_id>", methods=["DELETE"])
def delete_lead(lead_id):
    try:
        r = requests.delete(
            f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead_id}",
            headers=supabase_headers(use_service_role=True),
        )
        return jsonify({"status": "ok" if r.status_code in (200, 204) else "error"})
    except Exception as e:
        print("❌ DELETE error:", e)
        return jsonify({"status": "error"}), 500


@app.route("/api/subscriptions", methods=["GET"])
def get_subscriptions():
    try:
        student_id = request.args.get("student_id")
        teacher_id = request.args.get("teacher_id")
        url = f"{SUPABASE_URL}/rest/v1/subscriptions?select=*&order=created_at.desc"
        if student_id:
            url += f"&student_id=eq.{student_id}"
        if teacher_id:
            url += f"&teacher_id=eq.{teacher_id}"

        r = requests.get(url, headers=supabase_headers(use_service_role=True))

        if r.status_code == 200:
            subs = r.json()
            for s in subs:
                if s.get("student_id"):
                    ur = requests.get(
                        f"{SUPABASE_URL}/rest/v1/users?id=eq.{s['student_id']}&select=first_name,last_name,email",
                        headers=supabase_headers()
                    )
                    if ur.status_code == 200 and ur.json():
                        u = ur.json()[0]
                        s["student_name"] = (u.get("first_name", "") + " " + u.get("last_name", "")).strip()
                        s["student_email"] = u.get("email", "")
                if s.get("teacher_id"):
                    tr = requests.get(
                        f"{SUPABASE_URL}/rest/v1/users?id=eq.{s['teacher_id']}&select=first_name,last_name",
                        headers=supabase_headers()
                    )
                    if tr.status_code == 200 and tr.json():
                        t = tr.json()[0]
                        s["teacher_name"] = (t.get("first_name", "") + " " + t.get("last_name", "")).strip()
            return jsonify(subs)
        return jsonify([])
    except Exception as e:
        print(f"❌ Subscriptions error: {e}")
        return jsonify([])


@app.route("/api/subscriptions", methods=["POST"])
def create_subscription():
    data = request.get_json()
    try:
        lead_id = data.get("lead_id")

        if lead_id:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead_id}&select=*",
                headers=supabase_headers(use_service_role=True)
            )
            if r.status_code == 200 and r.json():
                lead = r.json()[0]

                check = requests.get(
                    f"{SUPABASE_URL}/rest/v1/subscriptions?lead_id=eq.{lead_id}&select=id",
                    headers=supabase_headers(use_service_role=True)
                )
                if check.status_code == 200 and check.json():
                    return jsonify({"status": "error", "detail": "Подписка уже существует"}), 409

                teacher_id = lead.get("teacher_id") or get_teacher_id_from_db(lead.get("teacher_name", ""))

                body = {
                    "lead_id": lead_id,
                    "student_id": lead.get("student_id"),
                    "teacher_id": teacher_id,
                    "course_title": lead.get("course_title", ""),
                    "lessons_total": lead.get("lessons", 1),
                    "lessons_left": lead.get("lessons", 1),
                    "with_ai": lead.get("with_ai", False),
                    "total_price": lead.get("total_price"),
                    "is_paid": True,
                }
            else:
                return jsonify({"status": "error", "detail": "Lead not found"}), 404
        else:
            body = {
                "student_id": data.get("student_id"),
                "teacher_id": data.get("teacher_id"),
                "course_title": data.get("course_title", ""),
                "lessons_total": data.get("lessons_total", 1),
                "lessons_left": data.get("lessons_left", data.get("lessons_total", 1)),
                "with_ai": data.get("with_ai", False),
                "total_price": data.get("total_price"),
                "is_paid": data.get("is_paid", True),
            }

        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/subscriptions",
            headers=supabase_headers(use_service_role=True),
            json=body,
        )
        if r.status_code == 201:
            return jsonify({"status": "ok"})
        return jsonify({"status": "error", "detail": r.text[:200]}), 500
    except Exception as e:
        print(f"❌ Create subscription error: {e}")
        return jsonify({"status": "error"}), 500

@app.route("/api/subscriptions/<sub_id>/pay", methods=["POST"])
def mark_subscription_paid(sub_id):
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/subscriptions?id=eq.{sub_id}",
            headers=supabase_headers(use_service_role=True),
            json={"is_paid": True},
        )
        return jsonify({"status": "ok" if r.status_code in (200, 204) else "error"})
    except Exception as e:
        print(f"❌ Pay error: {e}")
        return jsonify({"status": "error"}), 500


@app.route("/api/health", methods=["GET"])
def health():
    courses = get_courses_from_db()
    teachers = get_teachers_from_db()
    return jsonify({
        "status": "ok",
        "courses": len(courses),
        "teachers": len(teachers),
    })


if __name__ == "__main__":
    print(f"🚀 Starting with {len(get_courses_from_db())} courses and {len(get_teachers_from_db())} teachers")
    app.run(host="0.0.0.0", port=5001, debug=True)