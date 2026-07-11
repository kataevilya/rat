# -*- coding: utf-8 -*-
import os
import json
import sqlite3
import datetime
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ---------- БАЗА ДАННЫХ ДЛЯ КОМАНД И РЕЗУЛЬТАТОВ ----------
DB = "commands.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS clients
                 (client_id TEXT PRIMARY KEY, machine_name TEXT, last_seen TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS commands
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  client_id TEXT,
                  command TEXT,
                  params TEXT,
                  status TEXT DEFAULT 'pending',
                  result TEXT,
                  created_at TEXT,
                  executed_at TEXT)''')
    conn.commit()
    conn.close()

def register_client(client_id, machine_name):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('REPLACE INTO clients (client_id, machine_name, last_seen) VALUES (?, ?, ?)',
              (client_id, machine_name, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()

def add_command(client_id, command, params=''):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('INSERT INTO commands (client_id, command, params, created_at) VALUES (?, ?, ?, ?)',
              (client_id, command, params, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_pending_command(client_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id, command, params FROM commands WHERE client_id=? AND status="pending" ORDER BY id LIMIT 1', (client_id,))
    row = c.fetchone()
    conn.close()
    return row

def set_command_result(cmd_id, result, status='done'):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('UPDATE commands SET status=?, result=?, executed_at=? WHERE id=?',
              (status, result, datetime.datetime.now().isoformat(), cmd_id))
    conn.commit()
    conn.close()

def get_command_result(cmd_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT result FROM commands WHERE id=?', (cmd_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# ---------- ОБРАБОТЧИКИ КОМАНД БОТА ----------
TOKEN = "8451519620:AAGNpryYEiYzWIHyoZtz7GDmSJdwNXEXUkE"  # замените

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    client_id = str(user.id)
    machine_name = "unknown"  # сервер не знает имя клиента, агент зарегистрирует
    register_client(client_id, machine_name)
    keyboard = [
        [InlineKeyboardButton("🖥 Скриншот", callback_data='screenshot')],
        [InlineKeyboardButton("📋 Процессы", callback_data='list_procs')],
        [InlineKeyboardButton("❌ Завершить процесс", callback_data='kill_proc')],
        [InlineKeyboardButton("🚀 Запустить программу", callback_data='run_prog')],
        [InlineKeyboardButton("ℹ️ Инфо о системе", callback_data='sysinfo')],
        [InlineKeyboardButton("💬 MsgBox", callback_data='msgbox')],
        [InlineKeyboardButton("🔊 Громкость +", callback_data='vol_up'),
         InlineKeyboardButton("🔇 Mute", callback_data='mute'),
         InlineKeyboardButton("🔊 Громкость -", callback_data='vol_down')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие для выполнения на клиенте:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    client_id = str(user.id)

    if data == 'screenshot':
        add_command(client_id, 'screenshot')
        await query.edit_message_text("📸 Команда отправлена агенту. Ожидайте...")
        # запускаем проверку результата
        asyncio.create_task(wait_for_result(update, context, client_id))

    elif data == 'list_procs':
        add_command(client_id, 'list_procs')
        await query.edit_message_text("📋 Запрос на список процессов отправлен.")
        asyncio.create_task(wait_for_result(update, context, client_id))

    elif data == 'kill_proc':
        await query.edit_message_text("Введите PID процесса для завершения (число):")
        context.user_data['awaiting_pid'] = True

    elif data == 'run_prog':
        await query.edit_message_text("Введите полный путь к программе для запуска:")
        context.user_data['awaiting_path'] = True

    elif data == 'sysinfo':
        add_command(client_id, 'sysinfo')
        await query.edit_message_text("ℹ️ Запрос информации о системе отправлен.")
        asyncio.create_task(wait_for_result(update, context, client_id))

    elif data == 'msgbox':
        await query.edit_message_text("Введите заголовок и текст окна через '|' (например: Заголовок|Текст сообщения):")
        context.user_data['awaiting_msgbox'] = True

    elif data in ('vol_up', 'vol_down', 'mute'):
        add_command(client_id, data)
        await query.edit_message_text(f"🔊 Команда '{data}' отправлена агенту.")
        asyncio.create_task(wait_for_result(update, context, client_id))

async def wait_for_result(update: Update, context: ContextTypes.DEFAULT_TYPE, client_id):
    """Ожидает результат выполнения команды (до 60 секунд)."""
    for _ in range(30):  # 30 раз по 2 секунды = 60 сек
        await asyncio.sleep(2)
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('SELECT id, result FROM commands WHERE client_id=? AND status="done" ORDER BY id DESC LIMIT 1', (client_id,))
        row = c.fetchone()
        conn.close()
        if row:
            cmd_id, result = row
            # отправить результат пользователю
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ Результат:\n{result[:2000]}")
            # удалить команду, чтобы не повторять
            conn = sqlite3.connect(DB)
            c = conn.cursor()
            c.execute('DELETE FROM commands WHERE id=?', (cmd_id,))
            conn.commit()
            conn.close()
            return
    await context.bot.send_message(chat_id=update.effective_chat.id, text="⏱ Время ожидания результата истекло. Агент не ответил.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    client_id = str(user.id)

    if context.user_data.get('awaiting_pid', False):
        try:
            pid = int(text)
            add_command(client_id, 'kill_process', str(pid))
            await update.message.reply_text(f"❌ Команда завершить процесс {pid} отправлена.")
            asyncio.create_task(wait_for_result(update, context, client_id))
        except ValueError:
            await update.message.reply_text("Введите корректное число.")
        context.user_data['awaiting_pid'] = False
        return

    if context.user_data.get('awaiting_path', False):
        add_command(client_id, 'run_program', text)
        await update.message.reply_text(f"🚀 Команда запустить '{text}' отправлена.")
        asyncio.create_task(wait_for_result(update, context, client_id))
        context.user_data['awaiting_path'] = False
        return

    if context.user_data.get('awaiting_msgbox', False):
        if '|' not in text:
            await update.message.reply_text("Используйте формат: Заголовок|Текст")
            return
        title, msg = text.split('|', 1)
        add_command(client_id, 'msgbox', json.dumps({'title': title.strip(), 'msg': msg.strip()}))
        await update.message.reply_text("💬 Команда MsgBox отправлена.")
        asyncio.create_task(wait_for_result(update, context, client_id))
        context.user_data['awaiting_msgbox'] = False
        return

    await start(update, context)

# ---------- ЭНДПОИНТЫ ДЛЯ АГЕНТА (используем ту же БД) ----------
# Агент будет вызывать эти функции через getUpdates (polling) или через вебхук.
# Но проще: агент будет использовать методы бота для отправки команд? Нет, лучше через БД.
# Однако для упрощения агент может просто читать команды из БД и отправлять результаты обратно
# через метод send_message бота (но тогда бот должен знать chat_id). У нас chat_id = client_id.
# Можно реализовать агента, который периодически запрашивает команды через отдельный веб-сервер,
# но для простоты используем polling: агент вызывает API бота (getUpdates) с ограничением по времени.
# Но это сложно. Проще: бот будет отправлять команды агенту через сообщения, а агент будет слушать их.
# Однако агент должен быть инициирован первым сообщением от бота? Нет, агент сам периодически проверяет БД.

# Я реализую простой REST API внутри этого же бота (используя aiohttp) для агента.
# Но для Render проще использовать polling: агент будет периодически вызывать метод бота getUpdates
# с ограничением по чату? Это неудобно.

# Предлагаю добавить веб-сервер на порту 5000 (или 8080) внутри этого же приложения,
# чтобы агент мог отправлять GET запросы для получения команд и POST для отправки результатов.
# Это стандартный подход.

# ДОПИШЕМ ВЕБ-СЕРВЕР НА AIOHTTP:

from aiohttp import web

async def handle_get_command(request):
    """Агент запрашивает команду."""
    client_id = request.query.get('client_id')
    if not client_id:
        return web.json_response({'error': 'missing client_id'}, status=400)
    row = get_pending_command(client_id)
    if row:
        cmd_id, command, params = row
        return web.json_response({'cmd_id': cmd_id, 'command': command, 'params': params})
    else:
        return web.json_response({'status': 'no_commands'})

async def handle_post_result(request):
    """Агент отправляет результат выполнения."""
    data = await request.json()
    cmd_id = data.get('cmd_id')
    result = data.get('result')
    if not cmd_id:
        return web.json_response({'error': 'missing cmd_id'}, status=400)
    set_command_result(cmd_id, result)
    # также уведомим бота через send_message (но мы уже используем wait_for_result)
    return web.json_response({'status': 'ok'})

async def init_web_app():
    app = web.Application()
    app.router.add_get('/get_command', handle_get_command)
    app.router.add_post('/post_result', handle_post_result)
    return app

# ---------- ЗАПУСК БОТА И ВЕБ-СЕРВЕРА ----------
async def main():
    init_db()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Запускаем веб-сервер в фоне
    web_app = await init_web_app()
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("Веб-сервер запущен на порту 8080")

    # Запускаем бота
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # Держим процесс
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
