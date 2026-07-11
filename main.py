# -*- coding: utf-8 -*-
# ================================================================
# remote_admin_bot.py  —  Легальный инструмент удалённого администрирования
# (c) 2025  —  Только для собственных машин с явного согласия
# ================================================================

import os
import sys
import subprocess
import platform
import psutil
import ctypes
import time
import threading
import io
import json
import sqlite3
import shutil
import asyncio
from datetime import datetime
from PIL import ImageGrab
import pyautogui
from pyaudio import PyAudio, paInt16
import comtypes
from comtypes import CLSCTX_ALL
from ctypes import cast, POINTER
from comtypes.gen import IID_IMMDeviceEnumerator, IID_IAudioEndpointVolume
from comtypes.gen import MMDeviceAPI

# ---------- Telegram API ----------
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = "ВАШ_НОВЫЙ_ТОКЕН_ОТ_BOTFATHER"  # ← СЮДА ВСТАВЬТЕ НОВЫЙ ТОКЕН!
AUTHORIZED_USERS = []      # список Telegram ID (числа) — оставьте пустым для открытого доступа
DB_FILE = "clients.db"
BUILD_DIR = "build_output"

# ========== БАЗА ДАННЫХ ДЛЯ КЛИЕНТОВ ==========
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
              (client_id, machine_name, datetime.now().isoformat(), ip, os_ver))
    conn.commit()
    conn.close()

def get_clients():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT client_id, machine_name, last_seen, ip, os FROM clients')
    rows = c.fetchall()
    conn.close()
    return rows

# ========== ФУНКЦИИ УПРАВЛЕНИЯ КОМПЬЮТЕРОМ ==========
def get_screenshot():
    img = ImageGrab.grab()
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf.read()

def set_volume(level):
    if platform.system() != 'Windows':
        return "Только Windows"
    try:
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
        return "Только Windows"
    try:
        dev = comtypes.client.CreateObject(MMDeviceAPI.MMDeviceEnumerator, interface=MMDeviceAPI.IMMDeviceEnumerator)
        dev.GetDefaultAudioEndpoint(0, 1, ctypes.byref(dev))
        endpoint = cast(dev, POINTER(MMDeviceAPI.IMMDevice))
        endpoint.Activate(IID_IAudioEndpointVolume, CLSCTX_ALL, None, ctypes.byref(endpoint))
        volume = cast(endpoint, POINTER(MMDeviceAPI.IAudioEndpointVolume))
        volume.SetMute(enable, None)
        return "Звук выключен" if enable else "Звук включён"
    except Exception as e:
        return f"Ошибка: {e}"

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
        "cpu": platform.processor(),
        "cores": os.cpu_count(),
        "ram": f"{round(psutil.virtual_memory().total / (1024**3), 2)} GB"
    }

def get_volume():
    if platform.system() != 'Windows':
        return None, None
    try:
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

# ========== ФУНКЦИЯ ГЕНЕРАЦИИ EXE ==========
async def build_exe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if AUTHORIZED_USERS and user.id not in AUTHORIZED_USERS:
        await update.message.reply_text("Доступ запрещён.")
        return

    await update.message.reply_text("🔨 Начинаю сборку EXE... Это может занять 2-5 минут.")

    script_path = os.path.abspath(__file__)
    script_dir = os.path.dirname(script_path)
    build_path = os.path.join(script_dir, BUILD_DIR)

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
                caption="✅ Готовый EXE-файл. Используйте только на своих машинах с согласия владельца."
            )

        shutil.rmtree(build_path)
        await update.message.reply_text("🗑 Временные файлы удалены.")

    except FileNotFoundError:
        await update.message.reply_text("❌ PyInstaller не найден. Установите: pip install pyinstaller")
    except Exception as e:
        await update.message.reply_text(f"❌ Непредвиденная ошибка: {e}")

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if AUTHORIZED_USERS and user.id not in AUTHORIZED_USERS:
        await update.message.reply_text("Доступ запрещён.")
        return

    client_id = str(user.id)
    machine_name = platform.node()
    ip = str(update.effective_message.chat.id)
    os_ver = platform.system() + " " + platform.release()
    register_client(client_id, machine_name, f"chat_{ip}", os_ver)

    keyboard = [
        [InlineKeyboardButton("🖥 Скриншот", callback_data='screenshot')],
        [InlineKeyboardButton("🔊 Громкость +", callback_data='vol_up'),
         InlineKeyboardButton("🔇 Mute", callback_data='mute'),
         InlineKeyboardButton("🔊 Громкость -", callback_data='vol_down')],
        [InlineKeyboardButton("📋 Процессы", callback_data='list_procs')],
        [InlineKeyboardButton("❌ Завершить процесс", callback_data='kill_proc')],
        [InlineKeyboardButton("🚀 Запустить программу", callback_data='run_prog')],
        [InlineKeyboardButton("ℹ️ Инфо о системе", callback_data='sysinfo')],
        [InlineKeyboardButton("📋 Список клиентов", callback_data='list_clients')],
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

    user = update.effective_user
    if AUTHORIZED_USERS and user.id not in AUTHORIZED_USERS:
        await query.edit_message_text("Доступ запрещён.")
        return

    if data == 'screenshot':
        img_bytes = get_screenshot()
        await query.edit_message_text("📸 Делаю скриншот...")
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=img_bytes)
        await query.delete_message()

    elif data == 'vol_up':
        level, muted = get_volume()
        if level is None:
            await query.edit_message_text("Не удалось определить громкость (только Windows).")
            return
        new_level = min(level + 0.1, 1.0)
        res = set_volume(new_level)
        await query.edit_message_text(res)

    elif data == 'vol_down':
        level, muted = get_volume()
        if level is None:
            await query.edit_message_text("Не удалось определить громкость (только Windows).")
            return
        new_level = max(level - 0.1, 0.0)
        res = set_volume(new_level)
        await query.edit_message_text(res)

    elif data == 'mute':
        level, muted = get_volume()
        if muted is None:
            await query.edit_message_text("Не удалось определить состояние (только Windows).")
            return
        res = mute(not muted)
        await query.edit_message_text(res)

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

    elif data == 'build_exe':
        await build_exe(update, context)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if AUTHORIZED_USERS and user.id not in AUTHORIZED_USERS:
        await update.message.reply_text("Доступ запрещён.")
        return

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

    await start(update, context)

# ========== ЗАПУСК ==========
def main():
    init_db()
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("build_exe", build_exe))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Бот запущен. Нажмите Ctrl+C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
