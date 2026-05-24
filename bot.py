#!/usr/bin/env python3
import os
import json
import logging
import sys
import asyncio
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHAT_ID')

if not TOKEN or not CHANNEL_ID:
    logger.error("Ошибка: проверь TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в .env")
    sys.exit(1)

SETTINGS_FILE = 'bot_settings.json'

DEFAULT_SETTINGS = {
    "messages": [],               # Обычные сообщения
    "hourly_enabled": False,      # Включена ли почасовая рассылка
    "hourly_start": 9,            # Начальный час
    "hourly_end": 21,             # Конечный час
    "hourly_default_text": "⏰ ЕЖЕЧАСНОЕ НАПОМИНАНИЕ!\n\n",
    "hourly_exceptions": [],      # Особые часы [{"hour": 12, "text": "Обед!"}]
    "is_configured": False
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

class BotManager:
    def __init__(self, application):
        self.application = application
        self.scheduler = None
        self.settings = load_settings()
        
    def setup_scheduler(self):
        if self.scheduler:
            try:
                self.scheduler.shutdown()
            except:
                pass
        
        self.scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
        jobs_added = 0
        
        # 1. Обычные сообщения (конкретное время)
        for msg in self.settings.get("messages", []):
            try:
                hour, minute = map(int, msg["time"].split(':'))
                trigger = CronTrigger(hour=hour, minute=minute, timezone="Europe/Moscow")
                self.scheduler.add_job(
                    self.send_message,
                    trigger,
                    args=[msg["text"]],
                    id=f"msg_{msg['id']}",
                    replace_existing=True
                )
                logger.info(f"✅ Запланировано обычное: {msg['time']}")
                jobs_added += 1
            except Exception as e:
                logger.error(f"Ошибка планирования {msg['time']}: {e}")
        
        # 2. Почасовые сообщения
        if self.settings.get("hourly_enabled", False):
            hourly_start = self.settings.get("hourly_start", 9)
            hourly_end = self.settings.get("hourly_end", 21)
            default_text = self.settings.get("hourly_default_text", "⏰ Ежечасное напоминание!")
            exceptions = self.settings.get("hourly_exceptions", [])
            
            for hour in range(hourly_start, hourly_end + 1):
                exception = next((e for e in exceptions if e["hour"] == hour), None)
                text = exception["text"] if exception else default_text
                
                trigger = CronTrigger(hour=hour, minute=0, timezone="Europe/Moscow")
                self.scheduler.add_job(
                    self.send_message,
                    trigger,
                    args=[text],
                    id=f"hourly_{hour}",
                    replace_existing=True
                )
                logger.info(f"✅ Запланировано почасовое: {hour}:00")
                jobs_added += 1
        
        if jobs_added > 0:
            self.scheduler.start()
            logger.info(f"Планировщик запущен. Всего задач: {jobs_added}")
        else:
            logger.info("Нет сообщений для отправки")
    
    async def send_message(self, text):
        try:
            await self.application.bot.send_message(chat_id=CHANNEL_ID, text=text)
            logger.info(f"✅ Отправлено в {datetime.now().strftime('%H:%M')}: {text[:50]}")
        except Exception as e:
            logger.error(f"❌ НЕ УДАЛОСЬ ОТПРАВИТЬ: {e}")
    
    async def test_send(self, update: Update):
        try:
            await self.application.bot.send_message(chat_id=CHANNEL_ID, text="🧪 ТЕСТОВОЕ СООБЩЕНИЕ! Бот работает!")
            await update.callback_query.answer("✅ УСПЕШНО! Сообщение отправлено в канал!")
            logger.info(f"✅ Тестовая отправка успешна")
            return True
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Тест не удался: {error_msg}")
            if "chat not found" in error_msg.lower():
                await update.callback_query.answer("❌ ОШИБКА: Канал не найден! Проверь CHAT_ID")
            elif "forbidden" in error_msg.lower():
                await update.callback_query.answer("❌ ОШИБКА: Нет прав! Добавь бота в канал как АДМИНА")
            else:
                await update.callback_query.answer(f"❌ Ошибка: {error_msg[:40]}")
            return False

bot_manager = None

# ============ ГЛАВНОЕ МЕНЮ ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 СТАТУС", callback_data="status")],
        [InlineKeyboardButton("➕ РАССЫЛКА В ОПРЕДЕЛЕННЫЕ ЧАСЫ", callback_data="add")],
        [InlineKeyboardButton("📋 МОИ СООБЩЕНИЯ", callback_data="list")],
        [InlineKeyboardButton("⏰ ПОЧАСОВАЯ РАССЫЛКА", callback_data="hourly_menu")],
        [InlineKeyboardButton("🧪 ТЕСТ КАНАЛА", callback_data="test")],
        [InlineKeyboardButton("🗑 УДАЛИТЬ ВСЁ", callback_data="clear")]
    ]
    
    msgs_count = len(bot_manager.settings.get("messages", []))
    hourly_status = "ВКЛ" if bot_manager.settings.get("hourly_enabled", False) else "ВЫКЛ"
    
    text = f"🤖 *БОТ ДЛЯ КАНАЛА*\n\n"
    text += f"📨 Обычных: *{msgs_count}*\n"
    text += f"⏰ Почасовой: *{hourly_status}*\n"
    text += f"📢 Канал: `{CHANNEL_ID}`\n\n"
    text += "⚡ *ИНСТРУКЦИЯ:*\n"
    text += "1️⃣ Добавь бота в канал как АДМИНА\n"
    text += "2️⃣ Нажми 'РАССЫЛКА В ОПРЕДЕЛЕННЫЕ ЧАСЫ' для конкретного времени\n"
    text += "3️⃣ Или настрой 'ПОЧАСОВУЮ РАССЫЛКУ'\n"
    text += "4️⃣ Бот сам отправит в канал!"
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============ СТАТУС ============
async def status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    msgs = bot_manager.settings.get("messages", [])
    hourly_enabled = bot_manager.settings.get("hourly_enabled", False)
    
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
        text += f"• Интервал: *{bot_manager.settings['hourly_start']}:00 - {bot_manager.settings['hourly_end']}:00*\n"
        exceptions = bot_manager.settings.get("hourly_exceptions", [])
        if exceptions:
            text += "\n*🌟 ОСОБЫЕ ЧАСЫ:*\n"
            for exc in exceptions:
                text += f"• *{exc['hour']}:00* → {exc['text'][:40]}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============ ДОБАВЛЕНИЕ ОБЫЧНОГО СООБЩЕНИЯ ============
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✏️ *ДОБАВЛЕНИЕ СООБЩЕНИЯ*\n\n"
        "⚡ Введи ВРЕМЯ в формате *ЧЧ:ММ*\n"
        "Пример: `14:30` или `09:00`\n\n"
        "Часы: 00-23, минуты: 00-59",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]]),
        parse_mode='Markdown'
    )
    context.user_data['step'] = 'waiting_time'

# ============ ПОЧАСОВАЯ РАССЫЛКА ============
async def hourly_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    hourly_enabled = bot_manager.settings.get("hourly_enabled", False)
    
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
        text += f"Интервал: *{bot_manager.settings['hourly_start']}:00 - {bot_manager.settings['hourly_end']}:00*\n"
        text += f"Особых часов: *{len(bot_manager.settings.get('hourly_exceptions', []))}*\n"
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def toggle_hourly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    current = bot_manager.settings.get("hourly_enabled", False)
    bot_manager.settings["hourly_enabled"] = not current
    save_settings(bot_manager.settings)
    bot_manager.setup_scheduler()
    
    status = "ВКЛЮЧЕН" if bot_manager.settings["hourly_enabled"] else "ВЫКЛЮЧЕН"
    await query.edit_message_text(f"✅ ПОЧАСОВАЯ РАССЫЛКА {status}!")
    await asyncio.sleep(1)
    await hourly_menu(update, context)

async def set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "⏰ *НАСТРОЙКА ИНТЕРВАЛА*\n\n"
        "Введи начальный и конечный час\n"
        "Пример: `9 21` (с 9 до 21 часа)\n\n"
        "Часы от 0 до 23",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly_menu")]]),
        parse_mode='Markdown'
    )
    context.user_data['step'] = 'waiting_interval'

async def set_default_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    current = bot_manager.settings.get("hourly_default_text", "")
    await query.edit_message_text(
        f"📝 *ТЕКСТ ПО УМОЛЧАНИЮ*\n\n"
        f"Текущий текст:\n{current}\n\n"
        f"Введи новый текст:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly_menu")]]),
        parse_mode='Markdown'
    )
    context.user_data['step'] = 'waiting_default_text'

async def add_exception(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🌟 *ДОБАВЛЕНИЕ ОСОБОГО ЧАСА*\n\n"
        "Введи ЧАС (0-23)\n"
        "Пример: `12` для 12:00",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly_menu")]]),
        parse_mode='Markdown'
    )
    context.user_data['step'] = 'waiting_exception_hour'

async def list_exceptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    exceptions = bot_manager.settings.get("hourly_exceptions", [])
    
    if not exceptions:
        text = "📭 *НЕТ ОСОБЫХ ЧАСОВ*"
        keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return
    
    text = "*🌟 ОСОБЫЕ ЧАСЫ*\n\n"
    keyboard = []
    for exc in exceptions:
        text += f"• *{exc['hour']}:00* → {exc['text'][:50]}\n"
        keyboard.append([InlineKeyboardButton(f"🗑 Удалить {exc['hour']}:00", callback_data=f"del_exc_{exc['hour']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="hourly_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def delete_exception(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    hour = int(query.data.split('_')[2])
    exceptions = bot_manager.settings.get("hourly_exceptions", [])
    bot_manager.settings["hourly_exceptions"] = [e for e in exceptions if e["hour"] != hour]
    save_settings(bot_manager.settings)
    bot_manager.setup_scheduler()
    
    await query.edit_message_text(f"✅ Исключение для {hour}:00 удалено!")
    await asyncio.sleep(0.8)
    await list_exceptions(update, context)

# ============ СПИСОК ОБЫЧНЫХ СООБЩЕНИЙ ============
async def list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    msgs = bot_manager.settings.get("messages", [])
    
    if not msgs:
        text = "📭 *НЕТ СООБЩЕНИЙ*"
        keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return
    
    text = "*📋 МОИ СООБЩЕНИЯ*\n\n"
    keyboard = []
    
    for msg in msgs:
        text += f"🕐 *{msg['time']}*\n📝 {msg['text'][:50]}\n───────────\n"
        keyboard.append([
            InlineKeyboardButton(f"✏️ {msg['time']}", callback_data=f"edit_{msg['id']}"),
            InlineKeyboardButton(f"🗑 Удалить", callback_data=f"del_{msg['id']}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============ РЕДАКТИРОВАНИЕ ============
async def edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    msg_id = int(query.data.split('_')[1])
    context.user_data['edit_id'] = msg_id
    
    msg = next((m for m in bot_manager.settings["messages"] if m["id"] == msg_id), None)
    if not msg:
        await query.edit_message_text("❌ Сообщение не найдено")
        return
    
    keyboard = [
        [InlineKeyboardButton("✏️ ТЕКСТ", callback_data=f"edit_text_{msg_id}")],
        [InlineKeyboardButton("🕐 ВРЕМЯ", callback_data=f"edit_time_{msg_id}")],
        [InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]
    ]
    
    await query.edit_message_text(
        f"*✏️ РЕДАКТИРОВАНИЕ*\n\n🕐 *{msg['time']}*\n📝 `{msg['text'][:100]}`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def edit_text_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    msg_id = int(query.data.split('_')[2])
    context.user_data['edit_id'] = msg_id
    context.user_data['step'] = 'waiting_new_text'
    
    await query.edit_message_text(
        "✏️ *ВВЕДИ НОВЫЙ ТЕКСТ*",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]]),
        parse_mode='Markdown'
    )

async def edit_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    msg_id = int(query.data.split('_')[2])
    context.user_data['edit_id'] = msg_id
    context.user_data['step'] = 'waiting_new_time'
    
    await query.edit_message_text(
        "🕐 *ВВЕДИ НОВОЕ ВРЕМЯ* (ЧЧ:ММ)\nПример: 15:30",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 НАЗАД", callback_data="list")]]),
        parse_mode='Markdown'
    )

async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    msg_id = int(query.data.split('_')[1])
    bot_manager.settings["messages"] = [m for m in bot_manager.settings["messages"] if m["id"] != msg_id]
    save_settings(bot_manager.settings)
    bot_manager.setup_scheduler()
    
    await query.edit_message_text("✅ СООБЩЕНИЕ УДАЛЕНО!")
    await asyncio.sleep(0.8)
    await list_callback(update, context)

# ============ ТЕСТ ============
async def test_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await bot_manager.test_send(update)

# ============ ОЧИСТКА ============
async def clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("✅ ДА", callback_data="confirm_clear")],
        [InlineKeyboardButton("❌ НЕТ", callback_data="menu")]
    ]
    
    await query.edit_message_text(
        "⚠️ *УДАЛИТЬ ВСЕ СООБЩЕНИЯ?*\nЭто нельзя отменить!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def confirm_clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bot_manager.settings = DEFAULT_SETTINGS.copy()
    save_settings(bot_manager.settings)
    bot_manager.setup_scheduler()
    
    await query.edit_message_text("✅ ВСЕ УДАЛЕНО!")
    await asyncio.sleep(0.8)
    await menu_callback(update, context)

# ============ МЕНЮ ============
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📊 СТАТУС", callback_data="status")],
        [InlineKeyboardButton("➕ ДОБАВИТЬ СООБЩЕНИЕ", callback_data="add")],
        [InlineKeyboardButton("📋 МОИ СООБЩЕНИЯ", callback_data="list")],
        [InlineKeyboardButton("⏰ ПОЧАСОВАЯ РАССЫЛКА", callback_data="hourly_menu")],
        [InlineKeyboardButton("🧪 ТЕСТ КАНАЛА", callback_data="test")],
        [InlineKeyboardButton("🗑 УДАЛИТЬ ВСЁ", callback_data="clear")]
    ]
    
    msgs_count = len(bot_manager.settings.get("messages", []))
    hourly_status = "ВКЛ" if bot_manager.settings.get("hourly_enabled", False) else "ВЫКЛ"
    
    text = f"🤖 *ГЛАВНОЕ МЕНЮ*\n\n📨 Обычных: {msgs_count}\n⏰ Почасовой: {hourly_status}\n📢 Канал: `{CHANNEL_ID}`"
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============ ОБРАБОТКА ТЕКСТА ============
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    step = context.user_data.get('step')
    
    # Обычное сообщение - время
    if step == 'waiting_time':
        try:
            hour, minute = map(int, text.split(':'))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                time_str = f"{hour:02d}:{minute:02d}"
                context.user_data['new_time'] = time_str
                context.user_data['step'] = 'waiting_text'
                await update.message.reply_text(f"✅ Время {time_str}\n\nТеперь введи ТЕКСТ:")
            else:
                await update.message.reply_text("❌ Час 0-23, минуты 0-59")
        except:
            await update.message.reply_text("❌ Формат ЧЧ:ММ, например 14:30")
        return
    
    # Обычное сообщение - текст
    if step == 'waiting_text':
        time_str = context.user_data.get('new_time')
        msgs = bot_manager.settings.get("messages", [])
        new_id = max([m.get("id", 0) for m in msgs] + [0]) + 1
        
        bot_manager.settings["messages"].append({
            "id": new_id,
            "time": time_str,
            "text": text
        })
        save_settings(bot_manager.settings)
        bot_manager.setup_scheduler()
        
        await update.message.reply_text(f"✅ ДОБАВЛЕНО!\n\n🕐 {time_str}\n📝 {text[:100]}")
        context.user_data['step'] = None
        
        keyboard = [[InlineKeyboardButton("🔙 В МЕНЮ", callback_data="menu")]]
        await update.message.reply_text("Нажми кнопку:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Интервал почасовой
    if step == 'waiting_interval':
        try:
            parts = text.split()
            start_hour = int(parts[0])
            end_hour = int(parts[1])
            if 0 <= start_hour <= 23 and 0 <= end_hour <= 23 and start_hour <= end_hour:
                bot_manager.settings["hourly_start"] = start_hour
                bot_manager.settings["hourly_end"] = end_hour
                save_settings(bot_manager.settings)
                bot_manager.setup_scheduler()
                
                await update.message.reply_text(f"✅ Интервал: {start_hour}:00 - {end_hour}:00")
                context.user_data['step'] = None
                
                keyboard = [[InlineKeyboardButton("🔙 К ПОЧАСОВОЙ", callback_data="hourly_menu")]]
                await update.message.reply_text("Продолжить:", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.message.reply_text("❌ Ошибка")
        except:
            await update.message.reply_text("❌ Пример: 9 21")
        return
    
    # Текст по умолчанию
    if step == 'waiting_default_text':
        bot_manager.settings["hourly_default_text"] = text
        save_settings(bot_manager.settings)
        bot_manager.setup_scheduler()
        
        await update.message.reply_text(f"✅ Текст сохранен!")
        context.user_data['step'] = None
        
        keyboard = [[InlineKeyboardButton("🔙 К ПОЧАСОВОЙ", callback_data="hourly_menu")]]
        await update.message.reply_text("Продолжить:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Исключение - час
    if step == 'waiting_exception_hour':
        try:
            hour = int(text)
            if 0 <= hour <= 23:
                context.user_data['exception_hour'] = hour
                context.user_data['step'] = 'waiting_exception_text'
                await update.message.reply_text(f"✅ Час {hour}:00\n\nТеперь введи ТЕКСТ для этого часа:")
            else:
                await update.message.reply_text("❌ Час 0-23")
        except:
            await update.message.reply_text("❌ Введи число")
        return
    
    # Исключение - текст
    if step == 'waiting_exception_text':
        hour = context.user_data.get('exception_hour')
        exceptions = bot_manager.settings.get("hourly_exceptions", [])
        exceptions = [e for e in exceptions if e["hour"] != hour]
        exceptions.append({"hour": hour, "text": text})
        bot_manager.settings["hourly_exceptions"] = exceptions
        save_settings(bot_manager.settings)
        bot_manager.setup_scheduler()
        
        await update.message.reply_text(f"✅ Особый час {hour}:00 ДОБАВЛЕН!")
        context.user_data['step'] = None
        
        keyboard = [[InlineKeyboardButton("🔙 К ПОЧАСОВОЙ", callback_data="hourly_menu")]]
        await update.message.reply_text("Продолжить:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Редактирование текста обычного
    if step == 'waiting_new_text':
        msg_id = context.user_data.get('edit_id')
        for msg in bot_manager.settings["messages"]:
            if msg["id"] == msg_id:
                msg["text"] = text
                break
        save_settings(bot_manager.settings)
        bot_manager.setup_scheduler()
        
        await update.message.reply_text("✅ ТЕКСТ ОБНОВЛЕН!")
        context.user_data['step'] = None
        
        keyboard = [[InlineKeyboardButton("🔙 К СПИСКУ", callback_data="list")]]
        await update.message.reply_text("Продолжить:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Редактирование времени обычного
    if step == 'waiting_new_time':
        try:
            hour, minute = map(int, text.split(':'))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                new_time = f"{hour:02d}:{minute:02d}"
                msg_id = context.user_data.get('edit_id')
                
                for msg in bot_manager.settings["messages"]:
                    if msg["id"] == msg_id:
                        msg["time"] = new_time
                        break
                
                save_settings(bot_manager.settings)
                bot_manager.setup_scheduler()
                
                await update.message.reply_text(f"✅ ВРЕМЯ ИЗМЕНЕНО НА {new_time}")
                context.user_data['step'] = None
                
                keyboard = [[InlineKeyboardButton("🔙 К СПИСКУ", callback_data="list")]]
                await update.message.reply_text("Продолжить:", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.message.reply_text("❌ Час 0-23, минуты 0-59")
        except:
            await update.message.reply_text("❌ Формат ЧЧ:ММ")
        return

# ============ ОСНОВНОЙ ОБРАБОТЧИК ============
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == "menu":
        await menu_callback(update, context)
    elif data == "status":
        await status_callback(update, context)
    elif data == "add":
        await add_start(update, context)
    elif data == "list":
        await list_callback(update, context)
    elif data == "hourly_menu":
        await hourly_menu(update, context)
    elif data == "toggle_hourly":
        await toggle_hourly(update, context)
    elif data == "set_interval":
        await set_interval(update, context)
    elif data == "set_default_text":
        await set_default_text(update, context)
    elif data == "add_exception":
        await add_exception(update, context)
    elif data == "list_exceptions":
        await list_exceptions(update, context)
    elif data.startswith("del_exc_"):
        await delete_exception(update, context)
    elif data == "test":
        await test_callback(update, context)
    elif data == "clear":
        await clear_callback(update, context)
    elif data == "confirm_clear":
        await confirm_clear_callback(update, context)
    elif data.startswith("edit_"):
        await edit_callback(update, context)
    elif data.startswith("edit_text_"):
        await edit_text_callback(update, context)
    elif data.startswith("edit_time_"):
        await edit_time_callback(update, context)
    elif data.startswith("del_"):
        await delete_callback(update, context)

# ============ ЗАПУСК ============
async def run_bot():
    global bot_manager
    
    application = Application.builder().token(TOKEN).build()
    bot_manager = BotManager(application)
    bot_manager.setup_scheduler()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("🚀 БОТ ЗАПУЩЕН!")
    logger.info(f"📢 Канал: {CHANNEL_ID}")
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Остановка...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

def main():
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка: {e}")

if __name__ == '__main__':
    main()
