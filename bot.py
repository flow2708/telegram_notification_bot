#!/usr/bin/env python3
import os
import json
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ============ КОНФИГ ============
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHAT_ID')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if not TOKEN or not CHANNEL_ID:
    logger.error("Ошибка: переменные TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID не заданы!")
    os._exit(1)

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

def save_settings(s):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(s, f, indent=2, ensure_ascii=False)

settings = load_settings()
bot = None
scheduler = None

def send_message(text):
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=text)
        logger.info(f"✅ Отправлено: {text[:50]}")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

def setup_scheduler():
    global scheduler
    if scheduler:
        scheduler.shutdown()
    scheduler = BackgroundScheduler(timezone="Europe/Moscow")
    jobs = 0
    for msg in settings.get("messages", []):
        h, m = map(int, msg['time'].split(':'))
        scheduler.add_job(send_message, CronTrigger(hour=h, minute=m), args=[msg['text']])
        jobs += 1
    if settings.get('hourly_enabled'):
        for h in range(settings['hourly_start'], settings['hourly_end'] + 1):
            exc = next((e for e in settings.get('hourly_exceptions', []) if e['hour'] == h), None)
            text = exc['text'] if exc else settings['hourly_default_text']
            scheduler.add_job(send_message, CronTrigger(hour=h, minute=0), args=[text])
            jobs += 1
    if jobs:
        scheduler.start()
        logger.info(f"✅ Планировщик: {jobs} задач")

def main_menu():
    return [
        [InlineKeyboardButton("📊 СТАТУС", callback_data="status")],
        [InlineKeyboardButton("➕ ДОБАВИТЬ", callback_data="add")],
        [InlineKeyboardButton("📋 СПИСОК", callback_data="list")],
        [InlineKeyboardButton("⏰ ПОЧАСОВАЯ", callback_data="hourly")],
        [InlineKeyboardButton("🧪 ТЕСТ", callback_data="test")],
        [InlineKeyboardButton("🗑 СБРОС", callback_data="clear")]
    ]

def start(update, context):
    update.message.reply_text(
        f"🤖 БОТ ДЛЯ КАНАЛА\n\n"
        f"Сообщений: {len(settings.get('messages', []))}\n"
        f"Почасовой: {'ВКЛ' if settings.get('hourly_enabled') else 'ВЫКЛ'}\n"
        f"Канал: {CHANNEL_ID}",
        reply_markup=InlineKeyboardMarkup(main_menu())
    )

def status_cb(update, context):
    q = update.callback_query
    q.answer()
    msgs = settings.get('messages', [])
    text = f"📊 СТАТУС\n\nКанал: {CHANNEL_ID}\nСообщений: {len(msgs)}\n\n"
    if msgs:
        text += "РАСПИСАНИЕ:\n"
        for m in msgs:
            text += f"• {m['time']} - {m['text'][:30]}\n"
        text += "\n"
    text += f"Почасовой: {'ВКЛ' if settings.get('hourly_enabled') else 'ВЫКЛ'}"
    if settings.get('hourly_enabled'):
        text += f"\nИнтервал: {settings['hourly_start']}:00 - {settings['hourly_end']}:00"
    q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]]))

def add_cb(update, context):
    q = update.callback_query
    q.answer()
    q.edit_message_text(
        "✏️ Введи ВРЕМЯ в формате ЧЧ:ММ\nПример: 14:30",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]])
    )
    context.user_data['step'] = 'wait_time'

def list_cb(update, context):
    q = update.callback_query
    q.answer()
    msgs = settings.get('messages', [])
    if not msgs:
        q.edit_message_text("📭 НЕТ СООБЩЕНИЙ", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]]))
        return
    text = "📋 МОИ СООБЩЕНИЯ\n\n"
    kb = []
    for m in msgs:
        text += f"🕐 {m['time']}\n📝 {m['text'][:50]}\n───────────\n"
        kb.append([InlineKeyboardButton(f"✏️ {m['time']}", callback_data=f"edit_{m['id']}")])
    kb.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")])
    q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

def hourly_cb(update, context):
    q = update.callback_query
    q.answer()
    enabled = settings.get('hourly_enabled', False)
    kb = [
        [InlineKeyboardButton(f"{'✅' if enabled else '❌'} ВКЛ/ВЫКЛ", callback_data="toggle_h")],
        [InlineKeyboardButton("⏰ ИНТЕРВАЛ", callback_data="interval")],
        [InlineKeyboardButton("📝 ТЕКСТ", callback_data="def_text")],
        [InlineKeyboardButton("🌟 ОСОБЫЙ ЧАС", callback_data="add_exc")],
        [InlineKeyboardButton("📋 ИСКЛЮЧЕНИЯ", callback_data="list_exc")],
        [InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]
    ]
    text = f"⏰ ПОЧАСОВАЯ\nСтатус: {'ВКЛ' if enabled else 'ВЫКЛ'}"
    if enabled:
        text += f"\nИнтервал: {settings['hourly_start']}:00 - {settings['hourly_end']}:00"
    q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

def toggle_h_cb(update, context):
    q = update.callback_query
    q.answer()
    settings['hourly_enabled'] = not settings.get('hourly_enabled', False)
    save_settings(settings)
    setup_scheduler()
    q.edit_message_text(f"✅ Почасовая {'ВКЛЮЧЕНА' if settings['hourly_enabled'] else 'ВЫКЛЮЧЕНА'}")
    import time; time.sleep(0.8)
    hourly_cb(update, context)

def interval_cb(update, context):
    q = update.callback_query
    q.answer()
    q.edit_message_text(
        "Введи начальный и конечный час\nПример: 9 21",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")]])
    )
    context.user_data['step'] = 'wait_interval'

def def_text_cb(update, context):
    q = update.callback_query
    q.answer()
    q.edit_message_text(
        f"Текущий текст:\n{settings.get('hourly_default_text')}\n\nВведи новый текст:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")]])
    )
    context.user_data['step'] = 'wait_def_text'

def add_exc_cb(update, context):
    q = update.callback_query
    q.answer()
    q.edit_message_text(
        "Введи ЧАС (0-23)\nПример: 12",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")]])
    )
    context.user_data['step'] = 'wait_exc_hour'

def list_exc_cb(update, context):
    q = update.callback_query
    q.answer()
    excs = settings.get('hourly_exceptions', [])
    if not excs:
        q.edit_message_text("📭 НЕТ ОСОБЫХ ЧАСОВ", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")]]))
        return
    text = "🌟 ОСОБЫЕ ЧАСЫ\n\n"
    kb = []
    for e in excs:
        text += f"• {e['hour']}:00 - {e['text'][:40]}\n"
        kb.append([InlineKeyboardButton(f"🗑 Удалить {e['hour']}:00", callback_data=f"del_exc_{e['hour']}")])
    kb.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")])
    q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

def del_exc_cb(update, context):
    q = update.callback_query
    q.answer()
    hour = int(q.data.split('_')[2])
    settings['hourly_exceptions'] = [e for e in settings.get('hourly_exceptions', []) if e['hour'] != hour]
    save_settings(settings)
    setup_scheduler()
    q.edit_message_text(f"✅ Исключение {hour}:00 удалено")
    import time; time.sleep(0.8)
    list_exc_cb(update, context)

def edit_msg_cb(update, context):
    q = update.callback_query
    q.answer()
    msg_id = int(q.data.split('_')[1])
    context.user_data['edit_id'] = msg_id
    msg = next((m for m in settings.get('messages', []) if m['id'] == msg_id), None)
    if not msg:
        q.edit_message_text("❌ Не найдено")
        return
    kb = [
        [InlineKeyboardButton("✏️ ТЕКСТ", callback_data=f"edit_text_{msg_id}")],
        [InlineKeyboardButton("🕐 ВРЕМЯ", callback_data=f"edit_time_{msg_id}")],
        [InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]
    ]
    q.edit_message_text(f"✏️ РЕДАКТИРОВАНИЕ\n\n🕐 {msg['time']}\n📝 {msg['text'][:100]}", reply_markup=InlineKeyboardMarkup(kb))

def edit_text_cb(update, context):
    q = update.callback_query
    q.answer()
    msg_id = int(q.data.split('_')[2])
    context.user_data['edit_id'] = msg_id
    context.user_data['step'] = 'wait_edit_text'
    q.edit_message_text("✏️ Введи НОВЫЙ ТЕКСТ", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]]))

def edit_time_cb(update, context):
    q = update.callback_query
    q.answer()
    msg_id = int(q.data.split('_')[2])
    context.user_data['edit_id'] = msg_id
    context.user_data['step'] = 'wait_edit_time'
    q.edit_message_text("🕐 Введи НОВОЕ ВРЕМЯ (ЧЧ:ММ)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]]))

def del_msg_cb(update, context):
    q = update.callback_query
    q.answer()
    msg_id = int(q.data.split('_')[1])
    settings['messages'] = [m for m in settings.get('messages', []) if m['id'] != msg_id]
    save_settings(settings)
    setup_scheduler()
    q.edit_message_text("✅ УДАЛЕНО")
    import time; time.sleep(0.8)
    list_cb(update, context)

def test_cb(update, context):
    q = update.callback_query
    try:
        context.bot.send_message(chat_id=CHANNEL_ID, text="🧪 ТЕСТ! Бот работает!")
        q.answer("✅ Отправлено!")
    except Exception as e:
        q.answer(f"❌ {str(e)[:30]}")

def clear_cb(update, context):
    q = update.callback_query
    q.answer()
    kb = [[InlineKeyboardButton("✅ ДА", callback_data="confirm_clear")], [InlineKeyboardButton("❌ НЕТ", callback_data="menu")]]
    q.edit_message_text("⚠️ УДАЛИТЬ ВСЕ?", reply_markup=InlineKeyboardMarkup(kb))

def confirm_clear_cb(update, context):
    q = update.callback_query
    q.answer()
    global settings
    settings = DEFAULT_SETTINGS.copy()
    save_settings(settings)
    setup_scheduler()
    q.edit_message_text("✅ ВСЕ УДАЛЕНО")
    import time; time.sleep(0.8)
    menu_cb(update, context)

def menu_cb(update, context):
    q = update.callback_query
    q.answer()
    q.edit_message_text(
        f"🤖 ГЛАВНОЕ МЕНЮ\n\nСообщений: {len(settings.get('messages', []))}\nПочасовой: {'ВКЛ' if settings.get('hourly_enabled') else 'ВЫКЛ'}",
        reply_markup=InlineKeyboardMarkup(main_menu())
    )

def handle_text(update, context):
    text = update.message.text.strip()
    step = context.user_data.get('step')
    
    if step == 'wait_time':
        try:
            h, m = map(int, text.split(':'))
            if 0 <= h <= 23 and 0 <= m <= 59:
                context.user_data['new_time'] = f"{h:02d}:{m:02d}"
                context.user_data['step'] = 'wait_text'
                update.message.reply_text(f"✅ Время {h:02d}:{m:02d}\n\nТеперь введи ТЕКСТ:")
            else:
                update.message.reply_text("❌ Час 0-23, минуты 0-59")
        except:
            update.message.reply_text("❌ Формат ЧЧ:ММ")
        return
    
    if step == 'wait_text':
        time_str = context.user_data.get('new_time')
        msgs = settings.get('messages', [])
        new_id = max([m.get('id', 0) for m in msgs] + [0]) + 1
        settings['messages'].append({'id': new_id, 'time': time_str, 'text': text})
        save_settings(settings)
        setup_scheduler()
        update.message.reply_text(f"✅ ДОБАВЛЕНО!\n\n🕐 {time_str}\n📝 {text[:100]}")
        context.user_data['step'] = None
        update.message.reply_text("Вернуться в меню - /start")
        return
    
    if step == 'wait_interval':
        try:
            parts = text.split()
            start, end = int(parts[0]), int(parts[1])
            if 0 <= start <= 23 and 0 <= end <= 23 and start <= end:
                settings['hourly_start'] = start
                settings['hourly_end'] = end
                save_settings(settings)
                setup_scheduler()
                update.message.reply_text(f"✅ Интервал: {start}:00 - {end}:00")
                context.user_data['step'] = None
                update.message.reply_text("Вернуться в меню - /start")
            else:
                update.message.reply_text("❌ Ошибка")
        except:
            update.message.reply_text("❌ Пример: 9 21")
        return
    
    if step == 'wait_def_text':
        settings['hourly_default_text'] = text
        save_settings(settings)
        setup_scheduler()
        update.message.reply_text("✅ Текст сохранен")
        context.user_data['step'] = None
        update.message.reply_text("Вернуться в меню - /start")
        return
    
    if step == 'wait_exc_hour':
        try:
            hour = int(text)
            if 0 <= hour <= 23:
                context.user_data['exc_hour'] = hour
                context.user_data['step'] = 'wait_exc_text'
                update.message.reply_text(f"✅ Час {hour}:00\n\nТеперь введи ТЕКСТ:")
            else:
                update.message.reply_text("❌ Час 0-23")
        except:
            update.message.reply_text("❌ Введи число")
        return
    
    if step == 'wait_exc_text':
        hour = context.user_data.get('exc_hour')
        excs = settings.get('hourly_exceptions', [])
        excs = [e for e in excs if e['hour'] != hour]
        excs.append({'hour': hour, 'text': text})
        settings['hourly_exceptions'] = excs
        save_settings(settings)
        setup_scheduler()
        update.message.reply_text(f"✅ Особый час {hour}:00 ДОБАВЛЕН")
        context.user_data['step'] = None
        update.message.reply_text("Вернуться в меню - /start")
        return
    
    if step == 'wait_edit_text':
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
    
    if step == 'wait_edit_time':
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

def callback_handler(update, context):
    data = update.callback_query.data
    handlers = {
        "menu": menu_cb,
        "status": status_cb,
        "add": add_cb,
        "list": list_cb,
        "hourly": hourly_cb,
        "toggle_h": toggle_h_cb,
        "interval": interval_cb,
        "def_text": def_text_cb,
        "add_exc": add_exc_cb,
        "list_exc": list_exc_cb,
        "test": test_cb,
        "clear": clear_cb,
        "confirm_clear": confirm_clear_cb,
    }
    if data in handlers:
        handlers[data](update, context)
    elif data.startswith("del_exc_"):
        del_exc_cb(update, context)
    elif data.startswith("edit_"):
        edit_msg_cb(update, context)
    elif data.startswith("edit_text_"):
        edit_text_cb(update, context)
    elif data.startswith("edit_time_"):
        edit_time_cb(update, context)
    elif data.startswith("del_"):
        del_msg_cb(update, context)

def main():
    global bot
    updater = Updater(TOKEN, use_context=True)
    bot = updater.bot
    setup_scheduler()
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(callback_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    logger.info("🚀 БОТ ЗАПУЩЕН!")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
