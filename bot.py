#!/usr/bin/env python3
import os
import json
import logging
import time
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHAT_ID')

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if not TOKEN or not CHANNEL_ID:
    logger.error("Ошибка: переменные не заданы!")
    os._exit(1)

SETTINGS_FILE = 'bot_settings.json'

DEFAULT_SETTINGS = {
    "messages": [],
    "hourly_enabled": True,
    "hourly_start": 9,
    "hourly_end": 21,
    "hourly_default_text": "⏰ ЕЖЕЧАСНОЕ НАПОМИНАНИЕ!\n\nНе забывай о важном!",
    "hourly_exceptions": []
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

bot = None
scheduler = None
settings = load_settings()

def send_message(text):
    global bot
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=text)
        logger.info(f"✅ Отправлено в {datetime.now().strftime('%H:%M')}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")

def setup_scheduler():
    global scheduler, settings
    if scheduler:
        try:
            scheduler.shutdown()
        except:
            pass
    
    scheduler = BackgroundScheduler(timezone="Europe/Moscow")
    jobs = 0
    
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
            logger.info(f"✅ Запланировано: {msg['time']}")
        except Exception as e:
            logger.error(f"Ошибка: {e}")
    
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

def get_main_keyboard():
    return [
        [InlineKeyboardButton("📊 СТАТУС", callback_data="status")],
        [InlineKeyboardButton("➕ ДОБАВИТЬ СООБЩЕНИЕ", callback_data="add")],
        [InlineKeyboardButton("📋 МОИ СООБЩЕНИЯ", callback_data="list")],
        [InlineKeyboardButton("⏰ ПОЧАСОВАЯ", callback_data="hourly")],
        [InlineKeyboardButton("🧪 ТЕСТ", callback_data="test")],
        [InlineKeyboardButton("🗑 ОЧИСТИТЬ", callback_data="clear")]
    ]

def start(update, context):
    msgs_count = len(settings.get("messages", []))
    hourly_status = "ВКЛ" if settings.get("hourly_enabled", False) else "ВЫКЛ"
    
    text = f"🤖 *БОТ ДЛЯ КАНАЛА*\n\n"
    text += f"📨 Сообщений: *{msgs_count}*\n"
    text += f"⏰ Почасовой: *{hourly_status}*\n"
    text += f"📢 Канал: `{CHANNEL_ID}`\n\n"
    text += "⚡ *ИНСТРУКЦИЯ:*\n"
    text += "1️⃣ Добавь бота в канал как АДМИНА\n"
    text += "2️⃣ Нажми 'ДОБАВИТЬ СООБЩЕНИЕ' для конкретного времени\n"
    text += "3️⃣ Или настрой 'ПОЧАСОВУЮ РАССЫЛКУ'\n"
    text += "4️⃣ Бот сам отправит в канал!"
    
    update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(get_main_keyboard()), parse_mode='Markdown')

def status_callback(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    msgs = settings.get("messages", [])
    hourly_enabled = settings.get("hourly_enabled", False)
    
    text = f"*📊 СТАТУС БОТА*\n\n"
    text += f"📢 Канал: `{CHANNEL_ID}`\n"
    text += f"📨 Обычных: *{len(msgs)}*\n\n"
    
    if msgs:
        text += "*⏰ ОБЫЧНОЕ РАСПИСАНИЕ:*\n"
        for msg in msgs:
            text += f"• *{msg['time']}* → {msg['text'][:40]}\n"
        text += "\n"
    
    text += f"*⏰ ПОЧАСОВОЙ РЕЖИМ:* { '✅ ВКЛ' if hourly_enabled else '❌ ВЫКЛ'}\n"
    if hourly_enabled:
        text += f"• Интервал: *{settings['hourly_start']}:00 - {settings['hourly_end']}:00*\n"
        exceptions = settings.get("hourly_exceptions", [])
        if exceptions:
            text += "\n*🌟 ОСОБЫЕ ЧАСЫ:*\n"
            for exc in exceptions:
                text += f"• *{exc['hour']}:00* → {exc['text'][:40]}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]]
    try:
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except:
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

def add_start(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    try:
        query.edit_message_text(
            "✏️ *ДОБАВЛЕНИЕ СООБЩЕНИЯ*\n\n"
            "⚡ Введи ВРЕМЯ в формате *ЧЧ:ММ*\n"
            "Пример: `14:30` или `09:00`\n\n"
            "Часы: 00-23, минуты: 00-59",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]]),
            parse_mode='Markdown'
        )
    except:
        pass
    
    context.user_data['step'] = 'waiting_time'

def hourly_menu(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    hourly_enabled = settings.get("hourly_enabled", False)
    
    keyboard = [
        [InlineKeyboardButton(f"{'✅' if hourly_enabled else '❌'} ВКЛ/ВЫКЛ", callback_data="toggle_hourly")],
        [InlineKeyboardButton("⏰ ИНТЕРВАЛ", callback_data="set_interval")],
        [InlineKeyboardButton("📝 ТЕКСТ ПО УМОЛЧАНИЮ", callback_data="set_default_text")],
        [InlineKeyboardButton("🌟 ОСОБЫЙ ЧАС", callback_data="add_exception")],
        [InlineKeyboardButton("📋 ОСОБЫЕ ЧАСЫ", callback_data="list_exceptions")],
        [InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]
    ]
    
    text = f"*⏰ ПОЧАСОВАЯ РАССЫЛКА*\n\n"
    text += f"Статус: *{'ВКЛ' if hourly_enabled else 'ВЫКЛ'}*\n"
    if hourly_enabled:
        text += f"Интервал: *{settings['hourly_start']}:00 - {settings['hourly_end']}:00*\n"
        text += f"Особых часов: *{len(settings.get('hourly_exceptions', []))}*\n"
    
    try:
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except:
        pass

def toggle_hourly(update, context):
    global settings
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    settings["hourly_enabled"] = not settings.get("hourly_enabled", False)
    save_settings(settings)
    setup_scheduler()
    
    try:
        query.edit_message_text(f"✅ Почасовая {'ВКЛЮЧЕНА' if settings['hourly_enabled'] else 'ВЫКЛЮЧЕНА'}")
    except:
        pass
    
    time.sleep(1)
    hourly_menu(update, context)

def set_interval(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    try:
        query.edit_message_text(
            "⏰ *НАСТРОЙКА ИНТЕРВАЛА*\n\n"
            "Введи начальный и конечный час\n"
            "Пример: `9 21`\n\n"
            "Часы от 0 до 23",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly_menu")]]),
            parse_mode='Markdown'
        )
    except:
        pass
    
    context.user_data['step'] = 'waiting_interval'

def set_default_text(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    current = settings.get("hourly_default_text", "")
    try:
        query.edit_message_text(
            f"📝 *ТЕКСТ ПО УМОЛЧАНИЮ*\n\n"
            f"Текущий текст:\n{current}\n\n"
            f"Введи новый текст:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly_menu")]]),
            parse_mode='Markdown'
        )
    except:
        pass
    
    context.user_data['step'] = 'waiting_default_text'

def add_exception(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    try:
        query.edit_message_text(
            "🌟 *ДОБАВЛЕНИЕ ОСОБОГО ЧАСА*\n\n"
            "Введи ЧАС (0-23)\n"
            "Пример: `12` для 12:00",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly_menu")]]),
            parse_mode='Markdown'
        )
    except:
        pass
    
    context.user_data['step'] = 'waiting_exception_hour'

def list_exceptions(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    exceptions = settings.get("hourly_exceptions", [])
    
    if not exceptions:
        text = "📭 *НЕТ ОСОБЫХ ЧАСОВ*"
        keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly_menu")]]
    else:
        text = "*🌟 ОСОБЫЕ ЧАСЫ*\n\n"
        keyboard = []
        for exc in exceptions:
            text += f"• *{exc['hour']}:00* → {exc['text'][:50]}\n"
            keyboard.append([InlineKeyboardButton(f"🗑 Удалить {exc['hour']}:00", callback_data=f"del_exc_{exc['hour']}")])
        keyboard.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly_menu")])
    
    try:
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except:
        pass

def delete_exception(update, context):
    global settings
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    hour = int(query.data.split('_')[2])
    settings["hourly_exceptions"] = [e for e in settings.get("hourly_exceptions", []) if e["hour"] != hour]
    save_settings(settings)
    setup_scheduler()
    
    try:
        query.edit_message_text(f"✅ Исключение для {hour}:00 удалено!")
    except:
        pass
    
    time.sleep(0.8)
    list_exceptions(update, context)

def list_messages(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    msgs = settings.get("messages", [])
    
    if not msgs:
        text = "📭 *НЕТ СООБЩЕНИЙ*"
        keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]]
    else:
        text = "*📋 МОИ СООБЩЕНИЯ*\n\n"
        keyboard = []
        for msg in msgs:
            text += f"🕐 *{msg['time']}*\n📝 {msg['text'][:50]}\n───────────\n"
            keyboard.append([
                InlineKeyboardButton(f"✏️ {msg['time']}", callback_data=f"edit_{msg['id']}"),
                InlineKeyboardButton(f"🗑 Удалить", callback_data=f"del_{msg['id']}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")])
    
    try:
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except:
        pass

def edit_message(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    msg_id = int(query.data.split('_')[1])
    context.user_data['edit_id'] = msg_id
    
    msg = next((m for m in settings.get("messages", []) if m["id"] == msg_id), None)
    if not msg:
        try:
            query.edit_message_text("❌ Сообщение не найдено")
        except:
            pass
        return
    
    keyboard = [
        [InlineKeyboardButton("✏️ ТЕКСТ", callback_data=f"edit_text_{msg_id}")],
        [InlineKeyboardButton("🕐 ВРЕМЯ", callback_data=f"edit_time_{msg_id}")],
        [InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]
    ]
    
    try:
        query.edit_message_text(
            f"*✏️ РЕДАКТИРОВАНИЕ*\n\n🕐 *{msg['time']}*\n📝 `{msg['text'][:100]}`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except:
        pass

def edit_text_prompt(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    msg_id = int(query.data.split('_')[2])
    context.user_data['edit_id'] = msg_id
    context.user_data['step'] = 'waiting_new_text'
    
    try:
        query.edit_message_text(
            "✏️ *ВВЕДИ НОВЫЙ ТЕКСТ*",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]]),
            parse_mode='Markdown'
        )
    except:
        pass

def edit_time_prompt(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    msg_id = int(query.data.split('_')[2])
    context.user_data['edit_id'] = msg_id
    context.user_data['step'] = 'waiting_new_time'
    
    try:
        query.edit_message_text(
            "🕐 *ВВЕДИ НОВОЕ ВРЕМЯ* (ЧЧ:ММ)\nПример: 15:30",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]]),
            parse_mode='Markdown'
        )
    except:
        pass

def delete_message(update, context):
    global settings
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    msg_id = int(query.data.split('_')[1])
    settings["messages"] = [m for m in settings.get("messages", []) if m["id"] != msg_id]
    save_settings(settings)
    setup_scheduler()
    
    try:
        query.edit_message_text("✅ СООБЩЕНИЕ УДАЛЕНО!")
    except:
        pass
    
    time.sleep(0.8)
    list_messages(update, context)

def test_callback(update, context):
    query = update.callback_query
    try:
        context.bot.send_message(chat_id=CHANNEL_ID, text="🧪 ТЕСТ! Бот работает!")
        try:
            query.answer("✅ Отправлено в канал!")
        except:
            pass
        logger.info("✅ Тест отправлен")
    except Exception as e:
        error_msg = str(e)
        try:
            if "chat not found" in error_msg.lower():
                query.answer("❌ Канал не найден!")
            elif "forbidden" in error_msg.lower():
                query.answer("❌ Нет прав! Добавь бота в канал как АДМИНА")
            else:
                query.answer(f"❌ {error_msg[:30]}")
        except:
            pass
        logger.error(f"❌ Тест не удался: {error_msg}")

def clear_callback(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    keyboard = [
        [InlineKeyboardButton("✅ ДА", callback_data="confirm_clear")],
        [InlineKeyboardButton("❌ НЕТ", callback_data="menu")]
    ]
    
    try:
        query.edit_message_text(
            "⚠️ *УДАЛИТЬ ВСЕ СООБЩЕНИЯ?*\nЭто нельзя отменить!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except:
        pass

def confirm_clear(update, context):
    global settings
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    settings = DEFAULT_SETTINGS.copy()
    save_settings(settings)
    setup_scheduler()
    
    try:
        query.edit_message_text("✅ ВСЕ УДАЛЕНО!")
    except:
        pass
    
    time.sleep(0.8)
    menu_callback(update, context)

def menu_callback(update, context):
    query = update.callback_query
    try:
        query.answer()
    except:
        pass
    
    msgs_count = len(settings.get("messages", []))
    hourly_status = "ВКЛ" if settings.get("hourly_enabled", False) else "ВЫКЛ"
    
    text = f"🤖 *ГЛАВНОЕ МЕНЮ*\n\n📨 Сообщений: {msgs_count}\n⏰ Почасовой: {hourly_status}\n📢 Канал: `{CHANNEL_ID}`"
    
    try:
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(get_main_keyboard()), parse_mode='Markdown')
    except:
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(get_main_keyboard()), parse_mode='Markdown')

def handle_text(update, context):
    text = update.message.text.strip()
    step = context.user_data.get('step')
    
    if step == 'waiting_time':
        try:
            hour, minute = map(int, text.split(':'))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                time_str = f"{hour:02d}:{minute:02d}"
                context.user_data['new_time'] = time_str
                context.user_data['step'] = 'waiting_text'
                update.message.reply_text(f"✅ Время {time_str}\n\nТеперь введи ТЕКСТ:")
            else:
                update.message.reply_text("❌ Час 0-23, минуты 0-59")
        except:
            update.message.reply_text("❌ Формат ЧЧ:ММ, например 14:30")
        return
    
    if step == 'waiting_text':
        time_str = context.user_data.get('new_time')
        msgs = settings.get("messages", [])
        new_id = max([m.get("id", 0) for m in msgs] + [0]) + 1
        
        settings["messages"].append({
            "id": new_id,
            "time": time_str,
            "text": text
        })
        save_settings(settings)
        setup_scheduler()
        
        update.message.reply_text(f"✅ ДОБАВЛЕНО!\n\n🕐 {time_str}\n📝 {text[:100]}")
        context.user_data['step'] = None
        return
    
    if step == 'waiting_interval':
        try:
            parts = text.split()
            start_hour = int(parts[0])
            end_hour = int(parts[1])
            if 0 <= start_hour <= 23 and 0 <= end_hour <= 23 and start_hour <= end_hour:
                settings["hourly_start"] = start_hour
                settings["hourly_end"] = end_hour
                save_settings(settings)
                setup_scheduler()
                update.message.reply_text(f"✅ Интервал: {start_hour}:00 - {end_hour}:00")
                context.user_data['step'] = None
            else:
                update.message.reply_text("❌ Ошибка")
        except:
            update.message.reply_text("❌ Пример: 9 21")
        return
    
    if step == 'waiting_default_text':
        settings["hourly_default_text"] = text
        save_settings(settings)
        setup_scheduler()
        update.message.reply_text(f"✅ Текст сохранен!")
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
        exceptions = settings.get("hourly_exceptions", [])
        exceptions = [e for e in exceptions if e["hour"] != hour]
        exceptions.append({"hour": hour, "text": text})
        settings["hourly_exceptions"] = exceptions
        save_settings(settings)
        setup_scheduler()
        update.message.reply_text(f"✅ Особый час {hour}:00 ДОБАВЛЕН!")
        context.user_data['step'] = None
        return
    
    if step == 'waiting_new_text':
        msg_id = context.user_data.get('edit_id')
        for msg in settings.get("messages", []):
            if msg["id"] == msg_id:
                msg["text"] = text
                break
        save_settings(settings)
        setup_scheduler()
        update.message.reply_text("✅ ТЕКСТ ОБНОВЛЕН!")
        context.user_data['step'] = None
        return
    
    if step == 'waiting_new_time':
        try:
            hour, minute = map(int, text.split(':'))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                new_time = f"{hour:02d}:{minute:02d}"
                msg_id = context.user_data.get('edit_id')
                for msg in settings.get("messages", []):
                    if msg["id"] == msg_id:
                        msg["time"] = new_time
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
        "menu": menu_callback,
        "status": status_callback,
        "add": add_start,
        "list": list_messages,
        "hourly": hourly_menu,
        "toggle_hourly": toggle_hourly,
        "set_interval": set_interval,
        "set_default_text": set_default_text,
        "add_exception": add_exception,
        "list_exceptions": list_exceptions,
        "test": test_callback,
        "clear": clear_callback,
        "confirm_clear": confirm_clear,
    }
    
    if data in handlers:
        handlers[data](update, context)
    elif data.startswith("del_exc_"):
        delete_exception(update, context)
    elif data.startswith("edit_"):
        edit_message(update, context)
    elif data.startswith("edit_text_"):
        edit_text_prompt(update, context)
    elif data.startswith("edit_time_"):
        edit_time_prompt(update, context)
    elif data.startswith("del_"):
        delete_message(update, context)

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
