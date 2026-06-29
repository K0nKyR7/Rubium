from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import re

app = Flask(__name__)
CORS(app)

with open("model/AI_API_KEY.txt") as file:
    KEY = file.read().strip()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", KEY)
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

def load_courses_data():
    """Вытаскиваем информацию о курсах из courses.html"""
    try:
        with open("courses.html", "r", encoding="utf-8") as f:
            html = f.read()
        
        # Ищем все блоки с курсами
        courses = []
        pattern = r'<!-- (.*?) -->.*?<span class="course-item-badge.*?">(.*?)</span>.*?<h3>(.*?)</h3>.*?<p>(.*?)</p>.*?meta-value">(.*?)</span>'
        matches = re.findall(pattern, html, re.DOTALL)
        
        for match in matches:
            comment, badge, title, description, teacher = match
            courses.append({
                "title": title.strip(),
                "badge": badge.strip(),
                "description": description.strip(),
                "teacher": teacher.strip() if teacher.strip() != "—" else "пока не назначен"
            })
        
        return courses
    except Exception as e:
        print(f"Error loading courses: {e}")
        return []

def build_system_prompt(user_profile=None):
    """Строим системный промпт с актуальными данными"""
    
    courses = load_courses_data()
    
    courses_text = ""
    for i, course in enumerate(courses, 1):
        courses_text += f"{i}. {course['badge']} — {course['title']}\n"
        courses_text += f"   Описание: {course['description']}\n"
        courses_text += f"   Преподаватель: {course['teacher']}\n\n"
    
    profile_text = ""
    if user_profile:
        profile_text = f"""
ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ:
- Имя: {user_profile.get('name', 'не указано')}
- Уровень: {user_profile.get('level', 'не указан')}
- Интересы: {user_profile.get('interests', 'не указаны')}
- История запросов: {user_profile.get('history', 'нет')}

Используй эту информацию чтобы персонализировать ответ. Обращайся по имени если оно есть. Учитывай уровень подготовки.
"""
    
    return f"""Ты Rubi AI — персональный тьютор онлайн-школы Stud&School. Ты помогаешь подобрать идеальный курс.

{profile_text}

АКТУАЛЬНЫЙ СПИСОК КУРСОВ (загружен из courses.html):
{courses_text}

ТВОЯ РОЛЬ:
- Вести живую консультацию как настоящий тьютор
- Задавать уточняющие вопросы если нужно
- Объяснять почему конкретный курс подходит именно этому пользователю
- Рассказывать что будет на курсе
- Учитывать уровень подготовки из профиля
- Если пользователь не в сети (нет профиля) — работать в обычном режиме

ПРАВИЛА ОТВЕТА:
- Не используй обозначения из markdown, пиши как человек
- Размытый запрос → 1-2 уточняющих вопроса
- Коротко, 1-2 предложения
- Если курс не найден → предложи ближайший похожий
- Упоминай преподавателя если он назначен
- Можно использовать эмодзи
- Никогда не придумывать ложной информации
- В случае отсутствия информации говорить что ей не владеешь
- Внимательно проверяй наличие курсов
"""

conversation_history = {}

def get_user_profile(session_id):
    """Заглушка для получения профиля. Потом заменишь на свою БД."""
    # Пока возвращаем тестовые данные
    # В будущем здесь будет запрос к БД или localStorage через API
    test_profiles = {
        "user_123": {
            "name": "Максим",
            "level": "11 класс, готовлюсь к ЕГЭ",
            "interests": "математика, физика",
            "history": "интересовался ЕГЭ по математике"
        }
    }
    return test_profiles.get(session_id)

@app.route("/api/consult", methods=["POST"])
def consult():
    data = request.get_json()
    user_query = data.get("query", "").strip()
    session_id = data.get("session_id", "default")

    if not user_query:
        return jsonify({"response": "Расскажи, что тебя интересует. Например: «готовлюсь к ЕГЭ по физике»."})

    # Получаем профиль пользователя
    user_profile = get_user_profile(session_id)

    # Для каждой сессии строим системный промпт заново
    # (можно оптимизировать, но для разработки норм)
    if session_id not in conversation_history:
        conversation_history[session_id] = [
            {"role": "system", "content": build_system_prompt(user_profile)}
        ]
    else:
        # Обновляем системный промпт если изменились курсы или профиль
        conversation_history[session_id][0] = {
            "role": "system", 
            "content": build_system_prompt(user_profile)
        }

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
                "temperature": 0.8,
                "max_tokens": 500
            },
            timeout=20
        )
        resp.raise_for_status()
        body = resp.json()
        reply = body["choices"][0]["message"]["content"]
        conversation_history[session_id].append({"role": "assistant", "content": reply})

        # Держим историю в разумных пределах
        if len(conversation_history[session_id]) > 20:
            # Сохраняем системный промпт + последние сообщения
            conversation_history[session_id] = [
                conversation_history[session_id][0]
            ] + conversation_history[session_id][-19:]

        return jsonify({"response": reply})

    except Exception as e:
        print(f"DeepSeek API error: {e}")
        return jsonify({
            "response": "Что-то пошло не так. Попробуй ещё раз или напиши нам в Telegram."
        })

@app.route("/api/profile", methods=["POST"])
def update_profile():
    """Эндпоинт для обновления профиля с фронтенда"""
    data = request.get_json()
    session_id = data.get("session_id")
    profile_data = data.get("profile")
    
    # Здесь потом будет сохранение в БД
    print(f"Profile update for {session_id}: {profile_data}")
    
    # Очищаем историю чтобы перестроить промпт с новым профилем
    if session_id in conversation_history:
        del conversation_history[session_id]
    
    return jsonify({"status": "ok"})

@app.route("/api/courses", methods=["GET"])
def get_courses():
    """Отдаём список курсов для фронтенда"""
    courses = load_courses_data()
    return jsonify({"courses": courses})

if __name__ == "__main__":
    # Проверяем что курсы загрузились
    courses = load_courses_data()
    print(f"Loaded {len(courses)} courses from courses.html")
    for c in courses:
        print(f"  - {c['badge']}: {c['title']}")
    
    app.run(host="0.0.0.0", port=5001, debug=True)