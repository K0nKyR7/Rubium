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

def parse_courses_from_html():
    """Парсим все данные курсов из courses.html"""
    try:
        with open("courses.html", "r", encoding="utf-8") as f:
            html = f.read()
        
        courses = []
        onclick_pattern = r"openModal\(\{(.*?)\}\)"
        matches = re.findall(onclick_pattern, html, re.DOTALL)
        
        for match in matches:
            try:
                course_data = {}
                
                title_match = re.search(r"title:'([^']*)'", match)
                if title_match:
                    course_data['title'] = title_match.group(1)
                
                badge_match = re.search(r"badge:'([^']*)'", match)
                if badge_match:
                    course_data['badge'] = badge_match.group(1)
                
                cat_match = re.search(r"category:'([^']*)'", match)
                if cat_match:
                    course_data['category'] = cat_match.group(1)
                
                desc_match = re.search(r"desc:'([^']*)'", match)
                if desc_match:
                    course_data['description'] = desc_match.group(1)
                
                teacher_match = re.search(r"teacher:'([^']*)'", match)
                if teacher_match:
                    course_data['teacher'] = teacher_match.group(1)
                
                prices_match = re.search(r"prices:\{([^}]+)\}", match)
                if prices_match:
                    prices_str = prices_match.group(1)
                    prices = {}
                    for p in prices_str.split(','):
                        parts = p.split(':')
                        if len(parts) == 2:
                            prices[parts[0].strip()] = int(parts[1].strip())
                    course_data['prices'] = prices
                
                ai_match = re.search(r"aiSurcharge:(\d+)", match)
                if ai_match:
                    course_data['ai_surcharge'] = int(ai_match.group(1))
                
                if course_data.get('title'):
                    courses.append(course_data)
                    
            except Exception as e:
                print(f"Error parsing course: {e}")
                continue
        
        print(f"Parsed {len(courses)} courses from courses.html")
        return courses
        
    except Exception as e:
        print(f"Error reading courses.html: {e}")
        return []

def build_system_prompt(user_profile=None):
    """Строим системный промпт с актуальными данными"""
    
    courses = parse_courses_from_html()
    
    courses_text = ""
    for i, course in enumerate(courses, 1):
        prices = course.get('prices', {})
        price_1 = prices.get('1', '?')
        price_5 = prices.get('5', '?')
        price_10 = prices.get('10', '?')
        price_20 = prices.get('20', '?')
        ai = course.get('ai_surcharge', '?')
        
        courses_text += f"{i}. {course['badge']} — {course['title']}\n"
        courses_text += f"   {course['description']}\n"
        courses_text += f"   Преподаватель: {course['teacher']}\n"
        courses_text += f"   Тарифы: 1 занятие — {price_1}₽, 5 занятий — {price_5}₽, 10 занятий — {price_10}₽, 20 занятий — {price_20}₽\n"
        courses_text += f"   Доплата за Rubi AI: +{ai}₽ за занятие\n\n"
    
    profile_text = ""
    if user_profile:
        profile_text = f"""
О ПОЛЬЗОВАТЕЛЕ:
Имя: {user_profile.get('name', 'неизвестно')}
Уровень: {user_profile.get('level', 'не указан')}
Интересы: {user_profile.get('interests', 'не указаны')}

"""
    
    return f"""Ты Rubi AI — персональный тьютор онлайн-школы Stud&School. Ты помогаешь подобрать идеальный курс и записать пользователя на обучение.

{profile_text}
ДОСТУПНЫЕ КУРСЫ (с ценами):
{courses_text}

ТВОЯ ЗАДАЧА:
1. Помоги пользователю выбрать курс — уточни предмет, уровень, цель
2. Расскажи о подходящем курсе: что изучают, кто преподаёт, какие тарифы
3. Обсуди количество занятий и нужен ли Rubi AI
4. Когда пользователь готов записаться — запроси имя и номер телефона
5. Если пользователь оставил имя и телефон — подтверди заявку и попрощайся

ФОРМАТ ОТВЕТА:
- Пиши обычным текстом, без маркдауна, без звёздочек
- Будь дружелюбным, как живой преподаватель
- Когда пользователь готов записаться, скажи: "Отлично! Оставь, пожалуйста, имя и номер телефона, и мы свяжемся с тобой в ближайшее время."
- После получения контактов подтверди: "Спасибо, [имя]! Мы приняли твою заявку на курс [название]. Скоро наш менеджер позвонит тебе по номеру [телефон]. Хорошей подготовки!"

ВАЖНО: Ты не создаёшь заявки автоматически. Просто собираешь контакты в диалоге. Система сама сохранит их."""


@app.route("/api/consult", methods=["POST"])
def consult():
    data = request.get_json()
    user_query = data.get("query", "").strip()
    session_id = data.get("session_id", "default")

    if not user_query:
        return jsonify({"response": "Расскажи, что тебя интересует. Например: «хочу подготовиться к ЕГЭ по физике» или «помоги выбрать курс по Python»."})

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
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": conversation_history[session_id],
                "temperature": 0.75,
                "max_tokens": 500
            },
            timeout=20
        )
        resp.raise_for_status()
        body = resp.json()
        reply = body["choices"][0]["message"]["content"]
        
        reply = reply.replace("**", "").replace("__", "")
        
        conversation_history[session_id].append({"role": "assistant", "content": reply})

        if len(conversation_history[session_id]) > 20:
            conversation_history[session_id] = [
                conversation_history[session_id][0]
            ] + conversation_history[session_id][-19:]

        return jsonify({"response": reply})

    except Exception as e:
        print(f"DeepSeek API error: {e}")
        return jsonify({
            "response": "Что-то пошло не так на стороне сервера. Попробуй ещё раз через пару секунд. Если ошибка повторяется — напиши нам в Telegram."
        })


@app.route("/api/leads", methods=["POST"])
def create_lead():
    """Сохраняет заявку в Supabase"""
    data = request.get_json()
    
    course_title = data.get("course_title", "")
    
    # Ищем преподавателя по курсу
    teacher_name = ""
    courses = parse_courses_from_html()
    for course in courses:
        if course['title'].lower() in course_title.lower() or course_title.lower() in course['title'].lower():
            teacher_name = course.get('teacher', '')
            break
    
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            json={
                "client_name": data.get("client_name", ""),
                "phone": data.get("phone", ""),
                "course_title": course_title,
                "teacher_name": teacher_name,
                "chat_history": data.get("chat_history", ""),
                "status": "new"
            }
        )
        
        if resp.status_code == 201:
            return jsonify({"status": "ok", "message": "Заявка сохранена", "teacher": teacher_name})
        else:
            print(f"Supabase error: {resp.status_code} {resp.text}")
            return jsonify({"status": "error", "message": "Ошибка сохранения"}), 500
            
    except Exception as e:
        print(f"Error saving lead: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/leads", methods=["GET"])
def get_leads():
    """Получает заявки"""
    user_id = request.args.get("user_id")
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/leads?select=*&order=created_at.desc"
        if user_id:
            url += f"&user_id=eq.{user_id}"
        
        resp = requests.get(
            url,
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify([])
            
    except Exception as e:
        print(f"Error fetching leads: {e}")
        return jsonify([])


@app.route("/api/courses", methods=["GET"])
def get_courses():
    """Отдаём список курсов для фронтенда"""
    courses = parse_courses_from_html()
    return jsonify({"courses": courses})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "courses_parsed": len(parse_courses_from_html())})


if __name__ == "__main__":
    courses = parse_courses_from_html()
    print(f"Loaded {len(courses)} courses:")
    for c in courses:
        prices = c.get('prices', {})
        print(f"  - {c['badge']}: {c['title']} ({c['teacher']}) от {prices.get('1', '?')}₽")
    
    app.run(host="0.0.0.0", port=5001, debug=True)