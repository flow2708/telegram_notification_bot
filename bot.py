#!/usr/bin/env python3
import os
import json
import logging
import time
from datetime import datetime

import telegram
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ============ КОНФИГУРАЦИЯ ============
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHAT_ID')
# =====================================

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if not TOKEN or not CHANNEL_ID:
    logger.error("Ошибка: переменные не заданы!")
    sys.exit(1)

SETTINGS_FILE = 'bot_settings.json'

DEFAULT_SETTINGS = {
    "messages": [],
    "hourly_enabled": False,
    "hourly_start": 9,
    "hourly_end": 21,
    "hourly_default_text": "⏰ ЕЖЕЧАСНОЕ НАПОМИНАНИЕ!",
    "hourly_exceptions": []
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

# Глобальные переменные
bot = None
scheduler = None
settings = load_settings()

# ============ ОТПРАВКА СООБЩЕНИЙ ============
def send_message(text):
    global bot
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=text)
        logger.info(f"✅ Отправлено: {text[:50]}")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

def setup_scheduler():
    global scheduler, settings
    if scheduler:
        try:
            scheduler.shutdown()
        except:
            pass
    
    scheduler = BackgroundScheduler(timezone="Europe/Moscow")
    jobs = 0
    
    # Обычные сообщения
    for msg in settings.get("messages", []):
        try:
            h, m = map(int, msg["time"].split(':'))
            scheduler.add_job(
                send_message,
                CronTrigger(hour=h, minute=m, timezone="Europe/Moscow"),
                args=[msg["text"]],
                id=f"msg_{msg['id']}"
            )
            jobs += 1
        except:
            pass
    
    # Почасовая рассылка
    if settings.get("hourly_enabled", False):
        for h in range(settings["hourly_start"], settings["hourly_end"] + 1):
            exc = next((e for e in settings.get("hourly_exceptions", []) if e["hour"] == h), None)
            text = exc["text"] if exc else settings["hourly_default_text"]
            scheduler.add_job(
                send_message,
                CronTrigger(hour=h, minute=0, timezone="Europe/Moscow"),
                args=[text],
                id=f"hourly_{h}"
            )
            jobs += 1
    
    if jobs > 0:
        scheduler.start()
        logger.info(f"✅ Планировщик запущен. Задач: {jobs}")

# ============ КНОПКИ ============
def get_main_keyboard():
    return [
        [telegram.InlineKeyboardButton("📊 СТАТУС", callback_data="status")],
        [telegram.InlineKeyboardButton("➕ ДОБАВИТЬ СООБЩЕНИЕ", callback_data="add")],
        [telegram.InlineKeyboardButton("📋 МОИ СООБЩЕНИЯ", callback_data="list")],
        [telegram.InlineKeyboardButton("⏰ ПОЧАСОВАЯ", callback_data="hourly")],
        [telegram.InlineKeyboardButton("🧪 ТЕСТ", callback_data="test")],
        [telegram.InlineKeyboardButton("🗑 ОЧИСТИТЬ", callback_data="clear")]
    ]

# ============ КОМАНДЫ ============
def start(update, context):
    text = f"🤖 БОТ ДЛЯ КАНАЛА\n\n"
    text += f"📨 Сообщений: {len(settings.get('messages', []))}\n"
    text += f"⏰ Почасовой: {'ВКЛ' if settings.get('hourly_enabled') else 'ВЫКЛ'}\n"
    text += f"📢 Канал: {CHANNEL_ID}"
    
    update.message.reply_text(
        text,
        reply_markup=telegram.InlineKeyboardMarkup(get_main_keyboard())
    )

def status_callback(update, context):
    query = update.callback_query
    query.answer()
    
    msgs = settings.get("messages", [])
    text = f"📊 СТАТУС\n\n"
    text += f"Канал: {CHANNEL_ID}\n"
    text += f"Обычных: {len(msgs)}\n"
    
    if msgs:
        text += "\nРАСПИСАНИЕ:\n"
        for m in msgs:
            text += f"• {m['time']} - {m['text'][:30]}\n"
    
    text += f"\nПочасовой: {'ВКЛ' if settings.get('hourly_enabled') else 'ВЫКЛ'}"
    if settings.get('hourly_enabled'):
        text += f"\nИнтервал: {settings['hourly_start']}:00 - {settings['hourly_end']}:00"
    
    keyboard = [[telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]]
    query.edit_message_text(text, reply_markup=telegram.InlineKeyboardMarkup(keyboard))

def add_start(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "✏️ Введи ВРЕМЯ в формате ЧЧ:ММ\nПример: 14:30",
        reply_markup=telegram.InlineKeyboardMarkup([[telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]])
    )
    context.user_data['step'] = 'waiting_time'

def hourly_menu(update, context):
    query = update.callback_query
    query.answer()
    
    enabled = settings.get('hourly_enabled', False)
    keyboard = [
        [telegram.InlineKeyboardButton(f"{'✅' if enabled else '❌'} ВКЛ/ВЫКЛ", callback_data="toggle")],
        [telegram.InlineKeyboardButton("⏰ ИНТЕРВАЛ", callback_data="interval")],
        [telegram.InlineKeyboardButton("📝 ТЕКСТ", callback_data="text")],
        [telegram.InlineKeyboardButton("🌟 ОСОБЫЙ ЧАС", callback_data="exception")],
        [telegram.InlineKeyboardButton("📋 ИСКЛЮЧЕНИЯ", callback_data="exceptions")],
        [telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]
    ]
    
    text = f"⏰ ПОЧАСОВАЯ\nСтатус: {'ВКЛ' if enabled else 'ВЫКЛ'}"
    if enabled:
        text += f"\nИнтервал: {settings['hourly_start']}:00 - {settings['hourly_end']}:00"
    
    query.edit_message_text(text, reply_markup=telegram.InlineKeyboardMarkup(keyboard))

def toggle_hourly(update, context):
    global settings
    query = update.callback_query
    query.answer()
    
    settings['hourly_enabled'] = not settings.get('hourly_enabled', False)
    save_settings(settings)
    setup_scheduler()
    
    query.edit_message_text(f"✅ Почасовая {'ВКЛЮЧЕНА' if settings['hourly_enabled'] else 'ВЫКЛЮЧЕНА'}")
    time.sleep(1)
    hourly_menu(update, context)

def interval_start(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "⏰ Введи начальный и конечный час\nПример: 9 21",
        reply_markup=telegram.InlineKeyboardMarkup([[telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")]])
    )
    context.user_data['step'] = 'waiting_interval'

def text_start(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        f"📝 Текущий текст:\n{settings.get('hourly_default_text')}\n\nВведи новый текст:",
        reply_markup=telegram.InlineKeyboardMarkup([[telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")]])
    )
    context.user_data['step'] = 'waiting_default_text'

def exception_start(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "🌟 Введи ЧАС (0-23)\nПример: 12",
        reply_markup=telegram.InlineKeyboardMarkup([[telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")]])
    )
    context.user_data['step'] = 'waiting_exception_hour'

def list_exceptions(update, context):
    query = update.callback_query
    query.answer()
    
    excs = settings.get('hourly_exceptions', [])
    if not excs:
        text = "📭 НЕТ ОСОБЫХ ЧАСОВ"
        keyboard = [[telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")]]
    else:
        text = "🌟 ОСОБЫЕ ЧАСЫ\n\n"
        keyboard = []
        for e in excs:
            text += f"• {e['hour']}:00 - {e['text'][:40]}\n"
            keyboard.append([telegram.InlineKeyboardButton(f"🗑 Удалить {e['hour']}:00", callback_data=f"del_exc_{e['hour']}")])
        keyboard.append([telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")])
    
    query.edit_message_text(text, reply_markup=telegram.InlineKeyboardMarkup(keyboard))

def delete_exception(update, context):
    global settings
    query = update.callback_query
    query.answer()
    
    hour = int(query.data.split('_')[2])
    settings['hourly_exceptions'] = [e for e in settings.get('hourly_exceptions', []) if e['hour'] != hour]
    save_settings(settings)
    setup_scheduler()
    
    query.edit_message_text(f"✅ Исключение для {hour}:00 удалено")
    time.sleep(1)
    list_exceptions(update, context)

def list_messages(update, context):
    query = update.callback_query
    query.answer()
    
    msgs = settings.get("messages", [])
    if not msgs:
        text = "📭 НЕТ СООБЩЕНИЙ"
        keyboard = [[telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]]
    else:
        text = "📋 МОИ СООБЩЕНИЯ\n\n"
        keyboard = []
        for m in msgs:
            text += f"🕐 {m['time']}\n📝 {m['text'][:50]}\n───────────\n"
            keyboard.append([
                telegram.InlineKeyboardButton(f"✏️ {m['time']}", callback_data=f"edit_{m['id']}"),
                telegram.InlineKeyboardButton(f"🗑", callback_data=f"del_{m['id']}")
            ])
        keyboard.append([telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")])
    
    query.edit_message_text(text, reply_markup=telegram.InlineKeyboardMarkup(keyboard))

def edit_message(update, context):
    query = update.callback_query
    query.answer()
    
    msg_id = int(query.data.split('_')[1])
    context.user_data['edit_id'] = msg_id
    
    msg = next((m for m in settings.get("messages", []) if m["id"] == msg_id), None)
    if not msg:
        query.edit_message_text("❌ Не найдено")
        return
    
    keyboard = [
        [telegram.InlineKeyboardButton("✏️ ТЕКСТ", callback_data=f"edit_text_{msg_id}")],
        [telegram.InlineKeyboardButton("🕐 ВРЕМЯ", callback_data=f"edit_time_{msg_id}")],
        [telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]
    ]
    
    query.edit_message_text(
        f"✏️ РЕДАКТИРОВАНИЕ\n\n🕐 {msg['time']}\n📝 {msg['text'][:100]}",
        reply_markup=telegram.InlineKeyboardMarkup(keyboard)
    )

def edit_text_prompt(update, context):
    query = update.callback_query
    query.answer()
    
    msg_id = int(query.data.split('_')[2])
    context.user_data['edit_id'] = msg_id
    context.user_data['step'] = 'waiting_new_text'
    
    query.edit_message_text(
        "✏️ Введи НОВЫЙ ТЕКСТ",
        reply_markup=telegram.InlineKeyboardMarkup([[telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]])
    )

def edit_time_prompt(update, context):
    query = update.callback_query
    query.answer()
    
    msg_id = int(query.data.split('_')[2])
    context.user_data['edit_id'] = msg_id
    context.user_data['step'] = 'waiting_new_time'
    
    query.edit_message_text(
        "🕐 Введи НОВОЕ ВРЕМЯ (ЧЧ:ММ)",
        reply_markup=telegram.InlineKeyboardMarkup([[telegram.InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]])
    )

def delete_message(update, context):
    global settings
    query = update.callback_query
    query.answer()
    
    msg_id = int(query.data.split('_')[1])
    settings['messages'] = [m for m in settings.get('messages', []) if m['id'] != msg_id]
    save_settings(settings)
    setup_scheduler()
    
    query.edit_message_text("✅ УДАЛЕНО")
    time.sleep(1)
    list_messages(update, context)

def test_callback(update, context):
    query = update.callback_query
    try:
        context.bot.send_message(chat_id=CHANNEL_ID, text="🧪 ТЕСТ! Бот работает!")
        query.answer("✅ Отправлено!")
    except Exception as e:
        query.answer(f"❌ Ошибка: {str(e)[:30]}")

def clear_callback(update, context):
    query = update.callback_query
    query.answer()
    
    keyboard = [
        [telegram.InlineKeyboardButton("✅ ДА", callback_data="confirm")],
        [telegram.InlineKeyboardButton("❌ НЕТ", callback_data="menu")]
    ]
    query.edit_message_text("⚠️ УДАЛИТЬ ВСЕ?", reply_markup=telegram.InlineKeyboardMarkup(keyboard))

def confirm_clear(update, context):
    global settings
    query = update.callback_query
    query.answer()
    
    settings = DEFAULT_SETTINGS.copy()
    save_settings(settings)
    setup_scheduler()
    
    query.edit_message_text("✅ ВСЕ УДАЛЕНО")
    time.sleep(1)
    menu_callback(update, context)

def menu_callback(update, context):
    query = update.callback_query
    query.answer()
    
    text = f"🤖 ГЛАВНОЕ МЕНЮ\n\n📨 Сообщений: {len(settings.get('messages', []))}\n⏰ Почасовой: {'ВКЛ' if settings.get('hourly_enabled') else 'ВЫКЛ'}"
    query.edit_message_text(text, reply_markup=telegram.InlineKeyboardMarkup(get_main_keyboard()))

# ============ ОБРАБОТКА ТЕКСТА ============
def handle_text(update, context):
    global settings
    text = update.message.text.strip()
    step = context.user_data.get('step')
    
    if step == 'waiting_time':
        try:
            h, m = map(int, text.split(':'))
            if 0 <= h <= 23 and 0 <= m <= 59:
                context.user_data['new_time'] = f"{h:02d}:{m:02d}"
                context.user_data['step'] = 'waiting_text'
                update.message.reply_text(f"✅ Время {h:02d}:{m:02d}\n\nТеперь введи ТЕКСТ:")
            else:
                update.message.reply_text("❌ Час 0-23, минуты 0-59")
        except:
            update.message.reply_text("❌ Формат ЧЧ:ММ, например 14:30")
        return
    
    if step == 'waiting_text':
        time_str = context.user_data.get('new_time')
        msgs = settings.get('messages', [])
        new_id = max([m.get('id', 0) for m in msgs] + [0]) + 1
        
        settings['messages'].append({
            'id': new_id,
            'time': time_str,
            'text': text
        })
        save_settings(settings)
        setup_scheduler()
        
        update.message.reply_text(f"✅ ДОБАВЛЕНО!\n\n🕐 {time_str}\n📝 {text[:100]}")
        context.user_data['step'] = None
        return
    
    if step == 'waiting_interval':
        try:
            parts = text.split()
            start = int(parts[0])
            end = int(parts[1])
            if 0 <= start <= 23 and 0 <= end <= 23 and start <= end:
                settings['hourly_start'] = start
                settings['hourly_end'] = end
                save_settings(settings)
                setup_scheduler()
                update.message.reply_text(f"✅ Интервал: {start}:00 - {end}:00")
                context.user_data['step'] = None
            else:
                update.message.reply_text("❌ Ошибка")
        except:
            update.message.reply_text("❌ Пример: 9 21")
        return
    
    if step == 'waiting_default_text':
        settings['hourly_default_text'] = text
        save_settings(settings)
        setup_scheduler()
        update.message.reply_text("✅ Текст сохранен")
        context.user_data['step'] = None
        return
    
    if step == 'waiting_exception_hour':
        try:
            hour = int(text)
            if 0 <= hour <= 23:
                context.user_data['exception_hour'] = hour
                context.user_data['step'] = 'waiting_exception_text'
                update.message.reply_text(f"✅ Час {hour}:00\n\nТеперь введи ТЕКСТ:")
            else:
                update.message.reply_text("❌ Час 0-23")
        except:
            update.message.reply_text("❌ Введи число")
        return
    
    if step == 'waiting_exception_text':
        hour = context.user_data.get('exception_hour')
        exceptions = settings.get('hourly_exceptions', [])
        exceptions = [e for e in exceptions if e['hour'] != hour]
        exceptions.append({'hour': hour, 'text': text})
        settings['hourly_exceptions'] = exceptions
        save_settings(settings)
        setup_scheduler()
        update.message.reply_text(f"✅ Особый час {hour}:00 ДОБАВЛЕН")
        context.user_data['step'] = None
        return
    
    if step == 'waiting_new_text':
        msg_id = context.user_data.get('edit_id')
        for msg in settings.get('messages', []):
            if msg['id'] == msg_id:
                msg['text'] = text
                break
        save_settings(settings)
        setup_scheduler()
        update.message.reply_text("✅ ТЕКСТ ОБНОВЛЕН")
        context.user_data['step'] = None
        return
    
    if step == 'waiting_new_time':
        try:
            h, m = map(int, text.split(':'))
            if 0 <= h <= 23 and 0 <= m <= 59:
                new_time = f"{h:02d}:{m:02d}"
                msg_id = context.user_data.get('edit_id')
                for msg in settings.get('messages', []):
                    if msg['id'] == msg_id:
                        msg['time'] = new_time
                        break
                save_settings(settings)
                setup_scheduler()
                update.message.reply_text(f"✅ ВРЕМЯ ИЗМЕНЕНО НА {new_time}")
                context.user_data['step'] = None
            else:
                update.message.reply_text("❌ Час 0-23, минуты 0-59")
        except:
            update.message.reply_text("❌ Формат ЧЧ:ММ")
        return

# ============ ОБРАБОТЧИК КНОПОК ============
def callback_handler(update, context):
    data = update.callback_query.data
    
    if data == "menu":
        menu_callback(update, context)
    elif data == "status":
        status_callback(update, context)
    elif data == "add":
        add_start(update, context)
    elif data == "list":
        list_messages(update, context)
    elif data == "hourly":
        hourly_menu(update, context)
    elif data == "toggle":
        toggle_hourly(update, context)
    elif data == "interval":
        interval_start(update, context)
    elif data == "text":
        text_start(update, context)
    elif data == "exception":
        exception_start(update, context)
    elif data == "exceptions":
        list_exceptions(update, context)
    elif data.startswith("del_exc_"):
        delete_exception(update, context)
    elif data == "test":
        test_callback(update, context)
    elif data == "clear":
        clear_callback(update, context)
    elif data == "confirm":
        confirm_clear(update, context)
    elif data.startswith("edit_"):
        edit_message(update, context)
    elif data.startswith("edit_text_"):
        edit_text_prompt(update, context)
    elif data.startswith("edit_time_"):
        edit_time_prompt(update, context)
    elif data.startswith("del_"):
        delete_message(update, context)

# ============ ЗАПУСК ============
def main():
    global bot
    
    updater = Updater(TOKEN)
    bot = updater.bot
    
    setup_scheduler()
    
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(callback_handler))
    dp.add_handler(MessageHandler(None, handle_text))
    
    logger.info("🚀 БОТ ЗАПУЩЕН!")
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
