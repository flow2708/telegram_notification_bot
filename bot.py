#!/usr/bin/env python3
import os
import json
import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHAT_ID')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if not TOKEN or not CHANNEL_ID:
    logger.error("Ошибка: переменные не заданы!")
    os._exit(1)

SETTINGS_FILE = 'bot_settings.json'
DEFAULT_SETTINGS = {
    "messages": [],
    "hourly_enabled": False,
    "hourly_start": 9,
    "hourly_end": 21,
    "hourly_24h": False,  # НОВЫЙ ФЛАГ ДЛЯ 24 ЧАСОВ
    "hourly_default_text": "⏰ ЕЖЕЧАСНОЕ НАПОМИНАНИЕ!",
    "hourly_exceptions": []
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            saved = json.load(f)
            # Добавляем новый флаг в старые настройки
            if "hourly_24h" not in saved:
                saved["hourly_24h"] = False
            return saved
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
    try:
        if scheduler:
            try:
                scheduler.shutdown(wait=False)
            except:
                pass
        scheduler = BackgroundScheduler(timezone="Europe/Moscow")
        jobs = 0
        for msg in settings.get("messages", []):
            h, m = map(int, msg['time'].split(':'))
            scheduler.add_job(send_message, CronTrigger(hour=h, minute=m), args=[msg['text']])
            jobs += 1
        if settings.get('hourly_enabled'):
            # Если включен режим 24 часа
            if settings.get('hourly_24h', False):
                for h in range(0, 24):  # 0:00 до 23:00
                    exc = next((e for e in settings.get('hourly_exceptions', []) if e['hour'] == h), None)
                    text = exc['text'] if exc else settings['hourly_default_text']
                    scheduler.add_job(send_message, CronTrigger(hour=h, minute=0), args=[text])
                    jobs += 1
            else:
                # Обычный интервал
                for h in range(settings['hourly_start'], settings['hourly_end'] + 1):
                    exc = next((e for e in settings.get('hourly_exceptions', []) if e['hour'] == h), None)
                    text = exc['text'] if exc else settings['hourly_default_text']
                    scheduler.add_job(send_message, CronTrigger(hour=h, minute=0), args=[text])
                    jobs += 1
        if jobs > 0:
            scheduler.start()
            logger.info(f"✅ Планировщик: {jobs} задач")
    except Exception as e:
        logger.error(f"Ошибка: {e}")

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
    try: q.answer()
    except: pass
    msgs = settings.get('messages', [])
    text = f"📊 СТАТУС\n\nКанал: {CHANNEL_ID}\nСообщений: {len(msgs)}\n\n"
    if msgs:
        text += "РАСПИСАНИЕ:\n"
        for m in msgs:
            text += f"• {m['time']} - {m['text'][:30]}\n"
        text += "\n"
    text += f"Почасовой: {'ВКЛ' if settings.get('hourly_enabled') else 'ВЫКЛ'}"
    if settings.get('hourly_enabled'):
        if settings.get('hourly_24h', False):
            text += f"\nИнтервал: 24 ЧАСА (каждый час)"
        else:
            text += f"\nИнтервал: {settings['hourly_start']}:00 - {settings['hourly_end']}:00"
    try:
        q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]]))
    except: pass

def add_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    try:
        q.edit_message_text(
            "✏️ Введи ВРЕМЯ в формате ЧЧ:ММ\nПример: 14:30",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]])
        )
    except: pass
    context.user_data['step'] = 'wait_time'

def list_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    msgs = settings.get('messages', [])
    if not msgs:
        try:
            q.edit_message_text("📭 НЕТ СООБЩЕНИЙ", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]]))
        except: pass
        return
    text = "📋 МОИ СООБЩЕНИЯ\n\n"
    kb = []
    for m in msgs:
        text += f"🕐 {m['time']}\n📝 {m['text'][:50]}\n───────────\n"
        kb.append([InlineKeyboardButton(f"✏️ {m['time']}", callback_data=f"edit_{m['id']}")])
    kb.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")])
    try:
        q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    except: pass

def hourly_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    enabled = settings.get('hourly_enabled', False)
    is_24h = settings.get('hourly_24h', False)
    
    kb = [
        [InlineKeyboardButton(f"{'✅' if enabled else '❌'} ВКЛ/ВЫКЛ", callback_data="toggle_h")],
    ]
    
    # Добавляем кнопку 24 ЧАСА только если включена почасовая рассылка
    if enabled:
        kb.append([InlineKeyboardButton(f"{'✅' if is_24h else '❌'} 24 ЧАСА", callback_data="toggle_24h")])
    
    kb.extend([
        [InlineKeyboardButton("⏰ ИНТЕРВАЛ", callback_data="interval")],
        [InlineKeyboardButton("📝 ТЕКСТ", callback_data="def_text")],
        [InlineKeyboardButton("🌟 ОСОБЫЙ ЧАС", callback_data="add_exc")],
        [InlineKeyboardButton("📋 ИСКЛЮЧЕНИЯ", callback_data="list_exc")],
        [InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]
    ])
    
    text = f"⏰ ПОЧАСОВАЯ\nСтатус: {'ВКЛ' if enabled else 'ВЫКЛ'}"
    if enabled:
        if is_24h:
            text += f"\nРежим: 24 ЧАСА (каждый час)"
        else:
            text += f"\nИнтервал: {settings['hourly_start']}:00 - {settings['hourly_end']}:00"
    try:
        q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    except: pass

def toggle_h_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    settings['hourly_enabled'] = not settings.get('hourly_enabled', False)
    # Если выключаем - сбрасываем флаг 24h
    if not settings['hourly_enabled']:
        settings['hourly_24h'] = False
    save_settings(settings)
    setup_scheduler()
    try:
        q.edit_message_text(f"✅ Почасовая {'ВКЛЮЧЕНА' if settings['hourly_enabled'] else 'ВЫКЛЮЧЕНА'}")
    except: pass
    import time
    time.sleep(0.8)
    hourly_cb(update, context)

def toggle_24h_cb(update, context):
    """НОВАЯ ФУНКЦИЯ: Включение/выключение режима 24 часа"""
    q = update.callback_query
    try: q.answer()
    except: pass
    settings['hourly_24h'] = not settings.get('hourly_24h', False)
    save_settings(settings)
    setup_scheduler()
    try:
        q.edit_message_text(f"✅ Режим 24 ЧАСА {'ВКЛЮЧЕН' if settings['hourly_24h'] else 'ВЫКЛЮЧЕН'}")
    except: pass
    import time
    time.sleep(0.8)
    hourly_cb(update, context)

def interval_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    try:
        q.edit_message_text(
            "Введи начальный и конечный час\nПример: 9 21\n\n(Режим 24 часа будет отключён)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")]])
        )
    except: pass
    context.user_data['step'] = 'wait_interval'

def def_text_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    try:
        q.edit_message_text(
            f"Текущий текст:\n{settings.get('hourly_default_text')}\n\nВведи новый текст:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")]])
        )
    except: pass
    context.user_data['step'] = 'wait_def_text'

def add_exc_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    try:
        q.edit_message_text(
            "Введи ЧАС (0-23)\nПример: 12",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")]])
        )
    except: pass
    context.user_data['step'] = 'wait_exc_hour'

def list_exc_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    excs = settings.get('hourly_exceptions', [])
    if not excs:
        try:
            q.edit_message_text("📭 НЕТ ОСОБЫХ ЧАСОВ", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")]]))
        except: pass
        return
    text = "🌟 ОСОБЫЕ ЧАСЫ\n\n"
    kb = []
    for e in excs:
        text += f"• {e['hour']}:00 - {e['text'][:40]}\n"
        kb.append([InlineKeyboardButton(f"🗑 Удалить {e['hour']}:00", callback_data=f"del_exc_{e['hour']}")])
    kb.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly")])
    try:
        q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    except: pass

def del_exc_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    hour = int(q.data.split('_')[2])
    settings['hourly_exceptions'] = [e for e in settings.get('hourly_exceptions', []) if e['hour'] != hour]
    save_settings(settings)
    setup_scheduler()
    try:
        q.edit_message_text(f"✅ Исключение {hour}:00 удалено")
    except: pass
    import time
    time.sleep(0.8)
    list_exc_cb(update, context)

def edit_msg_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    parts = q.data.split('_')
    if len(parts) < 2:
        return
    msg_id = int(parts[1])
    context.user_data['edit_id'] = msg_id
    msg = next((m for m in settings.get('messages', []) if m['id'] == msg_id), None)
    if not msg:
        try:
            q.edit_message_text("❌ Не найдено")
        except: pass
        return
    kb = [
        [InlineKeyboardButton("✏️ ТЕКСТ", callback_data=f"edit_text_{msg_id}")],
        [InlineKeyboardButton("🕐 ВРЕМЯ", callback_data=f"edit_time_{msg_id}")],
        [InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]
    ]
    try:
        q.edit_message_text(f"✏️ РЕДАКТИРОВАНИЕ\n\n🕐 {msg['time']}\n📝 {msg['text'][:100]}", reply_markup=InlineKeyboardMarkup(kb))
    except: pass

def edit_text_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    parts = q.data.split('_')
    if len(parts) < 3:
        return
    msg_id = int(parts[2])
    context.user_data['edit_id'] = msg_id
    context.user_data['step'] = 'wait_edit_text'
    try:
        q.edit_message_text("✏️ Введи НОВЫЙ ТЕКСТ", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]]))
    except: pass

def edit_time_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    parts = q.data.split('_')
    if len(parts) < 3:
        return
    msg_id = int(parts[2])
    context.user_data['edit_id'] = msg_id
    context.user_data['step'] = 'wait_edit_time'
    try:
        q.edit_message_text("🕐 Введи НОВОЕ ВРЕМЯ (ЧЧ:ММ)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]]))
    except: pass

def del_msg_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    parts = q.data.split('_')
    if len(parts) < 2:
        return
    msg_id = int(parts[1])
    settings['messages'] = [m for m in settings.get('messages', []) if m['id'] != msg_id]
    save_settings(settings)
    setup_scheduler()
    try:
        q.edit_message_text("✅ УДАЛЕНО")
    except: pass
    import time
    time.sleep(0.8)
    list_cb(update, context)

def test_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    try:
        context.bot.send_message(chat_id=CHANNEL_ID, text="🧪 ТЕСТ! Бот работает!")
        context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Тестовое сообщение отправлено в канал!")
    except Exception as e:
        context.bot.send_message(chat_id=update.effective_chat.id, text=f"❌ Ошибка: {str(e)[:200]}\n\nПроверь:\n1. Бот добавлен в канал\n2. У бота есть права администратора\n3. Правильный CHANNEL_ID")

def clear_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    kb = [[InlineKeyboardButton("✅ ДА", callback_data="confirm_clear")], [InlineKeyboardButton("❌ НЕТ", callback_data="menu")]]
    try:
        q.edit_message_text("⚠️ УДАЛИТЬ ВСЕ?", reply_markup=InlineKeyboardMarkup(kb))
    except: pass

def confirm_clear_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    global settings
    settings = DEFAULT_SETTINGS.copy()
    save_settings(settings)
    setup_scheduler()
    try:
        q.edit_message_text("✅ ВСЕ УДАЛЕНО")
    except: pass
    import time
    time.sleep(0.8)
    menu_cb(update, context)

def menu_cb(update, context):
    q = update.callback_query
    try: q.answer()
    except: pass
    try:
        q.edit_message_text(
            f"🤖 ГЛАВНОЕ МЕНЮ\n\nСообщений: {len(settings.get('messages', []))}\nПочасовой: {'ВКЛ' if settings.get('hourly_enabled') else 'ВЫКЛ'}",
            reply_markup=InlineKeyboardMarkup(main_menu())
        )
    except: pass

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
        update.message.reply_text(f"✅ ДОБАВЛЕНО!\n\n🕐 {time_str}\n📝 {text[:100]}\n\n/start - вернуться в меню")
        context.user_data['step'] = None
        return
    
    if step == 'wait_interval':
        try:
            parts = text.split()
            start, end = int(parts[0]), int(parts[1])
            if 0 <= start <= 23 and 0 <= end <= 23 and start <= end:
                settings['hourly_start'] = start
                settings['hourly_end'] = end
                settings['hourly_24h'] = False  # При ручном интервале отключаем 24 часа
                save_settings(settings)
                setup_scheduler()
                update.message.reply_text(f"✅ Интервал: {start}:00 - {end}:00\n\n/start - вернуться в меню")
                context.user_data['step'] = None
            else:
                update.message.reply_text("❌ Ошибка")
        except:
            update.message.reply_text("❌ Пример: 9 21")
        return
    
    if step == 'wait_def_text':
        settings['hourly_default_text'] = text
        save_settings(settings)
        setup_scheduler()
        update.message.reply_text(f"✅ Текст сохранен\n\n/start - вернуться в меню")
        context.user_data['step'] = None
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
        update.message.reply_text(f"✅ Особый час {hour}:00 ДОБАВЛЕН\n\n/start - вернуться в меню")
        context.user_data['step'] = None
        return
    
    if step == 'wait_edit_text':
        msg_id = context.user_data.get('edit_id')
        for msg in settings.get('messages', []):
            if msg['id'] == msg_id:
                msg['text'] = text
                break
        save_settings(settings)
        setup_scheduler()
        update.message.reply_text("✅ ТЕКСТ ОБНОВЛЕН\n\n/list - посмотреть список")
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
                update.message.reply_text(f"✅ ВРЕМЯ ИЗМЕНЕНО НА {new_time}\n\n/list - посмотреть список")
                context.user_data['step'] = None
            else:
                update.message.reply_text("❌ Час 0-23, минуты 0-59")
        except:
            update.message.reply_text("❌ Формат ЧЧ:ММ")
        return

def callback_handler(update, context):
    data = update.callback_query.data
    
    if data == "menu":
        menu_cb(update, context)
    elif data == "status":
        status_cb(update, context)
    elif data == "add":
        add_cb(update, context)
    elif data == "list":
        list_cb(update, context)
    elif data == "hourly":
        hourly_cb(update, context)
    elif data == "toggle_h":
        toggle_h_cb(update, context)
    elif data == "toggle_24h":
        toggle_24h_cb(update, context)
    elif data == "interval":
        interval_cb(update, context)
    elif data == "def_text":
        def_text_cb(update, context)
    elif data == "add_exc":
        add_exc_cb(update, context)
    elif data == "list_exc":
        list_exc_cb(update, context)
    elif data.startswith("del_exc_"):
        del_exc_cb(update, context)
    elif data == "test":
        test_cb(update, context)
    elif data == "clear":
        clear_cb(update, context)
    elif data == "confirm_clear":
        confirm_clear_cb(update, context)
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
    dp.add_handler(MessageHandler(Filters.text, handle_text))
    logger.info("🚀 БОТ ЗАПУЩЕН!")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
