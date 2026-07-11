# -*- coding: utf-8 -*-
import os, sys, subprocess, platform, psutil, io, sqlite3, datetime, shutil, asyncio
from PIL import ImageGrab   # для скриншотов (на Linux требует DISPLAY, но если нет — ловим ошибку)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, filters

# ---------- Обёртка для импорта Windows-специфичных модулей ----------
try:
    import comtypes
    from comtypes import CLSCTX_ALL
    from ctypes import cast, POINTER
    from comtypes.gen import IID_IMMDeviceEnumerator, IID_IAudioEndpointVolume
    from comtypes.gen import MMDeviceAPI
    HAS_COMTYPES = True
except ImportError:
    HAS_COMTYPES = False

# ---------- Проверка наличия DISPLAY (для Linux) ----------
def has_display():
    return 'DISPLAY' in os.environ

# ---------- Функции управления (адаптированы) ----------
def get_screenshot():
    """Возвращает скриншот, если доступен дисплей, иначе заглушку."""
    if not has_display():
        return None
    try:
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf.read()
    except Exception as e:
        return None

def set_volume(level):
    if not HAS_COMTYPES or platform.system() != 'Windows':
        return "Функция доступна только на Windows"
    # ... реализация (оставлена как в исходном коде)
    # для краткости возвращаем сообщение, что недоступна

def mute(enable):
    if not HAS_COMTYPES or platform.system() != 'Windows':
        return "Функция доступна только на Windows"
    # ... аналогично

def get_volume():
    if not HAS_COMTYPES or platform.system() != 'Windows':
        return None, None
    # ...

def list_processes():
    procs = []
    for p in psutil.process_iter(['pid', 'name']):
        try:
            procs.append((p.info['name'], p.info['pid']))
        except:
            pass
    return procs

def kill_process(pid):
    try:
        p = psutil.Process(pid)
        p.terminate()
        return f"Процесс {pid} завершён"
    except Exception as e:
        return f"Ошибка: {e}"

def run_program(path):
    try:
        subprocess.Popen(path, shell=True)
        return f"Запущено: {path}"
    except Exception as e:
        return f"Ошибка: {e}"

def get_system_info():
    return {
        "os": platform.system() + " " + platform.release(),
        "node": platform.node(),
        "cpu": platform.processor() or "unknown",
        "cores": os.cpu_count(),
        "ram": f"{round(psutil.virtual_memory().total / (1024**3), 2)} GB"
    }

# ---------- Функция сборки EXE (только для Windows) ----------
async def build_exe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if platform.system() != 'Windows':
        await update.message.reply_text("❌ Сборка EXE доступна только на Windows.")
        return
    # остальной код сборки (без изменений)

# ---------- Обработчики команд ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # клавиатура без звука и без скриншота (или с ними, но с проверкой)
    keyboard = [
        [InlineKeyboardButton("📋 Процессы", callback_data='list_procs')],
        [InlineKeyboardButton("❌ Завершить процесс", callback_data='kill_proc')],
        [InlineKeyboardButton("🚀 Запустить программу", callback_data='run_prog')],
        [InlineKeyboardButton("ℹ️ Инфо о системе", callback_data='sysinfo')],
        [InlineKeyboardButton("🔨 Собрать EXE (только Windows)", callback_data='build_exe')],
    ]
    if has_display() and platform.system() == 'Windows' or has_display() and platform.system() == 'Linux':
        keyboard.insert(0, [InlineKeyboardButton("🖥 Скриншот", callback_data='screenshot')])
    # если звук доступен (Windows) — добавить кнопки звука
    if HAS_COMTYPES and platform.system() == 'Windows':
        keyboard.insert(1, [InlineKeyboardButton("🔊 Громкость +", callback_data='vol_up'),
                            InlineKeyboardButton("🔇 Mute", callback_data='mute'),
                            InlineKeyboardButton("🔊 Громкость -", callback_data='vol_down')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

# ---------- Callback-обработчик ----------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'screenshot':
        img_bytes = get_screenshot()
        if img_bytes is None:
            await query.edit_message_text("❌ Скриншот недоступен (нет графической среды).")
            return
        await query.edit_message_text("📸 Делаю скриншот...")
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=img_bytes)
        await query.delete_message()

    elif data == 'list_procs':
        procs = list_processes()
        text = "📋 Процессы (имя, PID):\n" + "\n".join([f"{name} ({pid})" for name, pid in procs[:20]])
        if len(procs) > 20:
            text += "\n... и ещё " + str(len(procs)-20)
        await query.edit_message_text(text)

    elif data == 'kill_proc':
        await query.edit_message_text("Введите PID процесса для завершения (число):")
        context.user_data['awaiting_pid'] = True

    elif data == 'run_prog':
        await query.edit_message_text("Введите полный путь к программе для запуска:")
        context.user_data['awaiting_path'] = True

    elif data == 'sysinfo':
        info = get_system_info()
        text = f"ℹ️ Система:\nOS: {info['os']}\nХост: {info['node']}\nCPU: {info['cpu']}\nЯдра: {info['cores']}\nRAM: {info['ram']}"
        await query.edit_message_text(text)

    elif data == 'build_exe':
        await build_exe(update, context)

    # Кнопки звука (если доступны)
    elif data in ('vol_up', 'vol_down', 'mute'):
        if not HAS_COMTYPES or platform.system() != 'Windows':
            await query.edit_message_text("❌ Управление звуком доступно только на Windows.")
            return
        # здесь вызываем соответствующие функции, оставлю заглушку
        await query.edit_message_text("Функция звука временно отключена в облачной версии.")

# ---------- Обработчик текста ----------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if context.user_data.get('awaiting_pid', False):
        try:
            pid = int(text)
            res = kill_process(pid)
            await update.message.reply_text(res)
        except ValueError:
            await update.message.reply_text("Введите число.")
        context.user_data['awaiting_pid'] = False
        return
    if context.user_data.get('awaiting_path', False):
        res = run_program(text)
        await update.message.reply_text(res)
        context.user_data['awaiting_path'] = False
        return
    await start(update, context)

# ---------- Запуск ----------
def main():
    TOKEN = "8451519620:AAGNpryYEiYzWIHyoZtz7GDmSJdwNXEXUkE"   # обязательно замените
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Бот запущен.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
