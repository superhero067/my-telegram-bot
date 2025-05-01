import telebot
import random
from telebot import types
from datetime import datetime, timedelta
import threading
import time
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')

bot = telebot.TeleBot(TOKEN)

# База данных
tasks_data = {
    "Логика": {
        "name": "Логические уравнения",
        "theory": "https://i.imgur.com/EXAMPLE1.jpg",
        "tasks": [
            {"question": "Сколько решений имеет уравнение (A ∨ ¬B) ∧ C?", "answer": "4"},
            {"question": "Какое выражение эквивалентно ¬(A ∧ B)?", "answer": "¬A ∨ ¬B"}
        ]
    }
}

# Хранение данных
user_data = {}
notification_time = "09:00"  # Время уведомлений (HH:MM)

# Меню (как в предыдущих версиях)
main_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
main_markup.row("📝 Задача", "📚 Теория", "📊 Статистика", "⏰ Настройки")


# Функция для ежедневных уведомлений
def daily_notifications():
    while True:
        now = datetime.now().strftime("%H:%M")
        if now == notification_time:
            for user_id, data in user_data.items():
                stats = data.get("stats", {})
                if stats.get("streak_days", 0) > 0:
                    last_active = datetime.strptime(stats["last_active_date"], "%Y-%m-%d")
                    if (datetime.now() - last_active).days >= 1:
                        try:
                            if stats["streak_days"] >= 3:
                                bot.send_message(
                                    user_id,
                                    f"⏳ Не забудьте решить задачу сегодня!\n"
                                    f"Ваша серия: {stats['streak_days']} дней\n"
                                    f"Решите задачу до завтра, чтобы продолжить!",
                                    reply_markup=main_markup
                                )
                            else:
                                bot.send_message(
                                    user_id,
                                    "📌 Не забудьте потренироваться сегодня!",
                                    reply_markup=main_markup
                                )
                        except Exception as e:
                            print(f"Ошибка отправки уведомления: {e}")
            time.sleep(60)  # Задержка перед следующей проверкой
        time.sleep(30)  # Проверяем время каждые 30 секунд


# Запуск фонового потока
notification_thread = threading.Thread(target=daily_notifications)
notification_thread.daemon = True
notification_thread.start()


# Обработчик для настройки времени уведомлений
@bot.message_handler(func=lambda message: message.text == "⏰ Настройки")
def settings(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🕘 Установить время", "🔕 Отключить уведомления", "🔙 Назад")
    bot.send_message(
        message.chat.id,
        "Настройки уведомлений:",
        reply_markup=markup
    )


@bot.message_handler(func=lambda message: message.text == "🕘 Установить время")
def set_notification_time(message):
    msg = bot.send_message(
        message.chat.id,
        "Введите время для уведомлений в формате HH:MM (например, 09:00):",
        reply_markup=types.ForceReply(selective=True)
    )
    bot.register_next_step_handler(msg, process_time_input)


def process_time_input(message):
    global notification_time
    try:
        datetime.strptime(message.text, "%H:%M")
        notification_time = message.text
        bot.send_message(
            message.chat.id,
            f"⏰ Время уведомлений установлено на {notification_time}",
            reply_markup=main_markup
        )
    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ Неверный формат времени. Используйте HH:MM",
            reply_markup=main_markup
        )


# Меню выбора теории
theory_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
for topic in tasks_data.keys():
    theory_markup.add(f"📖 {topic}")
theory_markup.add("🔙 Назад")


def init_user(user_id):
    """Инициализирует данные нового пользователя"""
    if user_id not in user_data:
        user_data[user_id] = {
            "current_task": None,
            "stats": {
                "correct": 0,
                "wrong": 0,
                "by_topic": {topic: {"correct": 0, "wrong": 0} for topic in tasks_data},
                "last_active_date": None,
                "streak_days": 0,
                "notified_about_streak_loss": False  # Флаг для уведомлений
            }
        }


def update_streak(user_id):
    """Обновляет счетчик дней подряд с уведомлениями"""
    today = datetime.now().strftime("%Y-%m-%d")
    stats = user_data[user_id]["stats"]
    message = None

    if stats["last_active_date"] != today:
        if stats["last_active_date"]:
            last_date = datetime.strptime(stats["last_active_date"], "%Y-%m-%d")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            if yesterday == stats["last_active_date"]:
                stats["streak_days"] += 1
            else:
                # Пропустили день - проверяем, нужно ли уведомлять
                if stats["streak_days"] >= 3 and not stats["notified_about_streak_loss"]:
                    days_lost = (datetime.now() - last_date).days - 1
                    message = f"⚠️ Вы потеряли серию из {stats['streak_days']} дней!\nНе решали задачи {days_lost} день(дня)."
                stats["streak_days"] = 1
                stats["notified_about_streak_loss"] = True
        else:
            # Первое использование
            stats["streak_days"] = 1

        stats["last_active_date"] = today
        stats["notified_about_streak_loss"] = False

    return message


# Команда /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = str(message.chat.id)
    init_user(user_id)
    bot.send_message(message.chat.id,
                     "Привет! Я помогу подготовиться к ЕГЭ по информатике.",
                     reply_markup=main_markup)


# Отправка задачи + обработка уведомлений
@bot.message_handler(func=lambda message: message.text == "📝 Задача")
def send_task(message):
    user_id = str(message.chat.id)
    init_user(user_id)

    # Проверяем streak и получаем уведомление (если есть)
    streak_notification = update_streak(user_id)
    if streak_notification:
        bot.send_message(message.chat.id, streak_notification)

    topic = random.choice(list(tasks_data.keys()))
    task = random.choice(tasks_data[topic]["tasks"])

    user_data[user_id]["current_task"] = {
        "answer": task["answer"],
        "topic": topic
    }

    bot.send_message(message.chat.id,
                     f"📌 Тема: {tasks_data[topic]['name']}\n\n"
                     f"❓ Задача:\n{task['question']}",
                     reply_markup=main_markup)


# Обновленная функция статистики
@bot.message_handler(func=lambda message: message.text == "📊 Статистика")
def show_stats(message):
    user_id = str(message.chat.id)
    init_user(user_id)
    stats = user_data.get(user_id, {}).get("stats", {})

    total = stats["correct"] + stats["wrong"]
    accuracy = (stats["correct"] / total * 100) if total > 0 else 0

    # Эмодзи для streak
    if stats["streak_days"] >= 7:
        streak_emoji = "🔥🔥🔥"
    elif stats["streak_days"] >= 3:
        streak_emoji = "🔥"
    else:
        streak_emoji = "⚡️" if stats["streak_days"] > 0 else ""

    # Подсказка для streak
    streak_hint = ""
    if stats["streak_days"] > 0:
        next_day = (datetime.strptime(stats["last_active_date"], "%Y-%m-%d") + timedelta(days=1)).strftime("%d.%m")
        streak_hint = f"\n(Решите задачу до {next_day} чтобы продолжить серию)"

    stats_text = (
        f"📊 Ваша статистика:\n\n"
        f"{streak_emoji} Дней подряд: {stats['streak_days']}{streak_hint}\n"
        f"✅ Правильных: {stats['correct']}\n"
        f"❌ Неправильных: {stats['wrong']}\n"
        f"🎯 Точность: {accuracy:.1f}%\n\n"
        f"По темам:\n"
        f"⏰ Следующее уведомление: {notification_time}"
    )

    for topic, topic_stats in stats["by_topic"].items():
        topic_total = topic_stats["correct"] + topic_stats["wrong"]
        if topic_total > 0:
            topic_accuracy = (topic_stats["correct"] / topic_total * 100)
            stats_text += f"📌 {tasks_data[topic]['name']}: {topic_stats['correct']}/{topic_total} ({topic_accuracy:.1f}%)\n"

    stats_text = f"...\n⏰ Следующее уведомление: {notification_time}"
    bot.send_message(message.chat.id, stats_text, reply_markup=main_markup)


# Проверка ответа
@bot.message_handler(
    func=lambda message: str(message.chat.id) in user_data and user_data[str(message.chat.id)]["current_task"])
def check_answer(message):
    user_id = str(message.chat.id)
    task_data = user_data[user_id]["current_task"]
    correct_answer = task_data["answer"]
    topic = task_data["topic"]
    stats = user_data[user_id]["stats"]

    if message.text.strip() == correct_answer:
        response = "✅ Верно!"
        stats["correct"] += 1
        stats["by_topic"][topic]["correct"] += 1
    else:
        response = f"❌ Неверно. Правильный ответ: {correct_answer}"
        stats["wrong"] += 1
        stats["by_topic"][topic]["wrong"] += 1

    user_data[user_id]["current_task"] = None
    bot.send_message(message.chat.id, response, reply_markup=main_markup)


# Остальные обработчики
@bot.message_handler(func=lambda message: message.text == "📚 Теория")
def choose_theory(message):
    bot.send_message(message.chat.id, "Выбери тему:", reply_markup=theory_markup)


@bot.message_handler(func=lambda message: message.text.startswith("📖 "))
def send_theory(message):
    topic = message.text[2:]
    if topic in tasks_data:
        bot.send_photo(message.chat.id,
                       photo=tasks_data[topic]["theory"],
                       caption=f"📚 {tasks_data[topic]['name']}")


@bot.message_handler(func=lambda message: message.text == "🔙 Назад")
def back_to_main(message):
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_markup)


if __name__ == '__main__':
    bot.remove_webhook() 
    bot.polling(none_stop=True)
