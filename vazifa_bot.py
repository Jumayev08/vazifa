from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from datetime import datetime, timedelta
import sqlite3
import pytz
import pandas as pd
import os

ADMIN_IDS = [615865532]
ADMIN_ID = 615865532
TOKEN = "7801763591:AAGpBgKZfRA2P82J6cA2gcPpYh6IwIIQJYQ"

user_states = {}
user_files = {}

def setup_database():
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            telegram_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            student_id TEXT,
            is_approved BOOLEAN DEFAULT FALSE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS homework_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            submission_date TEXT,
            homework_date TEXT,
            status TEXT,
            submission_time TIMESTAMP,
            file_ids TEXT,
            FOREIGN KEY (telegram_id) REFERENCES students (telegram_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT,
            homework_date TEXT,
            deadline TEXT,
            created_at TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()


def get_date_keyboard():
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT homework_date 
        FROM notifications 
        WHERE datetime(deadline) > datetime('now') 
        ORDER BY homework_date
    ''')
    
    dates = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for date in dates:
        keyboard.append([
            InlineKeyboardButton(
                date[0], 
                callback_data=f"date_{date[0]}"
            )
        ])
    
    return InlineKeyboardMarkup(keyboard)

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Admin panel - Hisobotlar bo'limi:",
        reply_markup=get_admin_reports_keyboard()
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM students WHERE telegram_id = ?', (user.id,))
    existing_user = cursor.fetchone()
    
    if not existing_user:
        user_states[user.id] = {
            "state": "awaiting_first_name"
        }
        await update.message.reply_text(
            "Assalomu alaykum! Iltimos, ismingizni kiriting:"
        )
    else:
        if is_admin(user.id):
            await show_admin_panel(update, context)
            conn.close()
            return
        
        if not is_user_approved(user.id):
            await update.message.reply_text(
                "Sizning ma'lumotlaringiz admin tomonidan tekshirilmoqda. "
                "Iltimos, tasdiqlash jarayoni tugashini kuting."
            )
            return
        
        
        await show_main_menu(update, context)
    
    conn.close()

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📚 Vazifalar ro'yxati", callback_data="show_homework_list")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            "✅ Sizning profilingiz tasdiqlangan!\n\n"
            "Vazifalarni ko'rish uchun quyidagi tugmani bosing:",
            reply_markup=reply_markup
        )
    else:
        await update.callback_query.message.edit_text(
            "✅ Sizning profilingiz tasdiqlangan!\n\n"
            "Vazifalarni ko'rish uchun quyidagi tugmani bosing:",
            reply_markup=reply_markup
        )

        

def get_available_dates():
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    try:
        today = datetime.now()
        dates = []
        
        cursor.execute('''
            SELECT homework_date, deadline 
            FROM notifications 
            WHERE datetime(deadline) > datetime('now', '-2 days')
            ORDER BY homework_date DESC
        ''')
        
        existing_dates = cursor.fetchall()
        dates.extend(existing_dates)
        
        if not dates:  
            for i in range(3, -1, -1):
                date = today - timedelta(days=i)
                formatted_date = date.strftime('%d.%m.%Y')
                deadline = (date + timedelta(days=2)).replace(hour=23, minute=59)
                deadline_str = deadline.strftime('%d.%m.%Y %H:%M')
                
                cursor.execute('''
                    INSERT INTO notifications (message, homework_date, deadline, created_at)
                    VALUES (?, ?, ?, ?)
                ''', ("Kunlik vazifa", formatted_date, deadline_str, datetime.now()))
                
                dates.append((formatted_date, deadline_str))
            
            conn.commit()
        
        return dates
    
    except Exception as e:
        print(f"Error in get_available_dates: {e}")
        return []
    finally:
        conn.close()



def check_submission_exists(user_id: int, homework_date: str) -> bool:

    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id 
        FROM homework_submissions 
        WHERE telegram_id = ? AND homework_date = ?
    ''', (user_id, homework_date))
    
    result = cursor.fetchone()
    conn.close()
    
    return bool(result)


async def show_homework_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_user_approved(user_id):
        await query.answer("Kechirasiz, sizning ma'lumotlaringiz hali tasdiqlanmagan.")
        return
    
    try:
        available_dates = get_available_dates()
        
        if not available_dates:
            await query.message.edit_text(
                "Hozircha faol vazifalar mavjud emas.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_main")
                ]])
            )
            return
        
        keyboard = []
        for date, deadline in available_dates:
            if check_submission_exists(user_id, date):
                button_text = f"✅ {date} (Topshirilgan)"
            else:
                deadline_dt = datetime.strptime(deadline, '%d.%m.%Y %H:%M')
                if deadline_dt < datetime.now():
                    button_text = f"❌ {date} (Muddat tugagan)"
                else:
                    button_text = f"📝 {date}"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"date_{date}")])
        
        # Add back button
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(
            "📚 Mavjud vazifalar ro'yxati:\n"
            "Vazifa topshirish uchun sanani tanlang:\n\n"
            "✅ - Topshirilgan\n"
            "❌ - Muddat tugagan\n"
            "📝 - Topshirish mumkin",
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Error in show_homework_list: {e}")
        await query.answer(f"Xatolik yuz berdi: {str(e)}")

def is_valid_student_id(student_id: str) -> bool:
    return student_id.isdigit() and len(student_id) == 9

def is_user_approved(user_id: int) -> bool:
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT is_approved FROM students WHERE telegram_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return bool(result and result[0])

async def _message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_states:
        await update.message.reply_text(
            "Iltimos, /start buyrug'ini bosing."
        )
        return
    
    state = user_states[user_id]["state"]
    
    if state == "awaiting_first_name":
        user_states[user_id].update({
            "state": "awaiting_last_name",
            "first_name": update.message.text
        })
        await update.message.reply_text("Endi familiyangizni kiriting:")
        
    elif state == "awaiting_last_name":
        user_states[user_id].update({
            "state": "awaiting_student_id",
            "last_name": update.message.text
        })
        await update.message.reply_text(
            "Iltimos, 9 xonali talaba ID raqamingizni kiriting:"
        )
        
    elif state == "awaiting_student_id":
        student_id = update.message.text
        if not is_valid_student_id(student_id):
            await update.message.reply_text(
                "Noto'g'ri ID format. ID raqam 9 ta raqamdan iborat bo'lishi kerak. "
                "Iltimos, qaytadan kiriting:"
            )
            return
            
        conn = sqlite3.connect('homework_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO students (telegram_id, first_name, last_name, student_id, is_approved)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, user_states[user_id]["first_name"], 
              user_states[user_id]["last_name"], student_id, False))
        
        conn.commit()
        conn.close()
        
        admin_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{user_id}")
            ]
        ])
        
        admin_message = (
            "Yangi foydalanuvchi ro'yxatdan o'tdi!\n\n"
            f"👤 {user_states[user_id]['first_name']}\n"
            f"📝 {user_states[user_id]['last_name']}\n"
            f"🆔 {student_id}"
        )
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_message,
            reply_markup=admin_keyboard
        )
        
        await update.message.reply_text(
            "Sizning ma'lumotlaringiz admin tomonidan tekshirilgandan keyin "
            "botdan foydalanishingiz mumkin bo'ladi. Iltimos, kuting."
        )
        
        user_states[user_id]["state"] = "waiting_approval"

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Send reminders to users who haven't submitted homework"""
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT homework_date, deadline 
        FROM notifications 
        WHERE datetime(deadline) > datetime('now')
    ''')
    active_assignments = cursor.fetchall()
    
    for homework_date, deadline in active_assignments:
        cursor.execute('''
            SELECT s.telegram_id, s.first_name 
            FROM students s 
            LEFT JOIN homework_submissions h 
            ON s.telegram_id = h.telegram_id AND h.homework_date = ?
            WHERE h.id IS NULL AND s.is_approved = TRUE
        ''', (homework_date,))
        
        users_to_remind = cursor.fetchall()
        
        for user_id, first_name in users_to_remind:
            reminder_message = (
                f"⚠️ Eslatma!\n\n"
                f"Hurmatli {first_name}, {homework_date} sanasi uchun vazifani topshirish muddati "
                f"{deadline} gacha.\n"
                f"Iltimos, vazifani o'z vaqtida topshiring!"
            )
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=reminder_message
                )
            except Exception as e:
                print(f"Error sending reminder to {user_id}: {e}")
    
    conn.close()

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        if query.data == "show_homework_list":
            await show_homework_list(update, context)
        elif query.data.startswith("date_"):
            homework_date = query.data.split("_")[1]
            await handle_homework_date_selection(update, context, homework_date)
        elif query.data.startswith("approve_"):
            if not is_admin(user_id):
                await query.answer("Bu funksiya faqat adminlar uchun!")
                return
            student_id = int(query.data.split("_")[1])
            await approve_student(update, context, student_id)
        elif query.data.startswith("reject_"):
            if not is_admin(user_id):
                await query.answer("Bu funksiya faqat adminlar uchun!")
                return
            student_id = int(query.data.split("_")[1])
            await reject_student(update, context, student_id)
        elif query.data == "homework_done":
            await submit_homework(update, context)
        elif query.data == "back_to_main":
            await show_main_menu(update, context)
        elif query.data == "back_to_homework_list":
            await show_homework_list(update, context)
    except Exception as e:
        print(f"Error in handle_callback: {e}")
        await query.answer("Xatolik yuz berdi. Iltimos, /start buyrug'ini qaytadan bosing.")


def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("✅ Tasdiqlash", callback_data="approve_students")],
        [InlineKeyboardButton("📢 Vazifa e'lon qilish", callback_data="announce_homework")],
        [InlineKeyboardButton("📊 Hisobotlar", callback_data="show_reports_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def register_admin_report_handlers(application: Application):
    application.add_handler(CallbackQueryHandler(show_reports_menu, pattern="^show_reports_menu$"))
    application.add_handler(CallbackQueryHandler(report_by_student, pattern="^report_by_student$"))
    application.add_handler(CallbackQueryHandler(show_student_report, pattern="^student_report_"))
    application.add_handler(CallbackQueryHandler(report_submitted_by_date, pattern="^report_submitted_by_date$"))
    application.add_handler(CallbackQueryHandler(show_submitted_by_date, pattern="^submitted_date_"))
    application.add_handler(CallbackQueryHandler(report_not_submitted_by_date, pattern="^report_not_submitted_by_date$"))
    application.add_handler(CallbackQueryHandler(show_not_submitted_by_date, pattern="^not_submitted_date_"))
    application.add_handler(CallbackQueryHandler(report_students_list, pattern="^report_students_list$"))



def get_admin_reports_keyboard():
    keyboard = [
        [InlineKeyboardButton("👨‍🎓 Talabalar bo'yicha hisobot", callback_data="report_by_student")],
        [InlineKeyboardButton("📅 Topshirganlar (sana bo'yicha)", callback_data="report_submitted_by_date")],
        [InlineKeyboardButton("❌ Topshirmaganlar (sana bo'yicha)", callback_data="report_not_submitted_by_date")],
        [InlineKeyboardButton("📋 Talabalar ro'yxati", callback_data="generate_student_list")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_admin_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def show_reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        await update.message.reply_text(
            "📊 Hisobotlar menyusi",
            reply_markup=get_admin_reports_keyboard()
        )
    else:
        await query.edit_message_text(
            "📊 Hisobotlar menyusi",
            reply_markup=get_admin_reports_keyboard()
        )

async def report_by_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    # Get all approved students
    cursor.execute('''
        SELECT telegram_id, first_name, last_name, student_id
        FROM students
        WHERE is_approved = TRUE
        ORDER BY last_name, first_name
    ''')
    students = cursor.fetchall()
    
    # Create keyboard with student list
    keyboard = []
    for student in students:
        student_name = f"{student[2]} {student[1]} ({student[3]})"  # Added student ID for better identification
        keyboard.append([InlineKeyboardButton(
            student_name,
            callback_data=f"student_report_{student[0]}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="show_reports_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            "👨‍🎓 Talaba tanlang:",
            reply_markup=reply_markup
        )
    except TelegramError as e:
        if "Message is not modified" not in str(e):
            raise e
    
    conn.close()



async def show_student_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    student_id = query.data.split('_')[2]
    
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    # Get student info
    cursor.execute('''
        SELECT first_name, last_name, student_id
        FROM students
        WHERE telegram_id = ?
    ''', (student_id,))
    student = cursor.fetchone()
    
    # Get all homework submissions for the student
    cursor.execute('''
        SELECT homework_date, submission_date, submission_time, status
        FROM homework_submissions
        WHERE telegram_id = ?
        ORDER BY homework_date
    ''', (student_id,))
    submissions = cursor.fetchall()
    
    # Get all homework dates
    cursor.execute('''
        SELECT DISTINCT homework_date, deadline
        FROM notifications
        ORDER BY homework_date
    ''')
    all_assignments = cursor.fetchall()
    
    # Generate report
    report = f"📊 *{student[1]} {student[0]}* hisoboti\n"
    report += f"🆔 Talaba ID: {student[2]}\n\n"
    report += "📅 Vazifalar holati:\n\n"
    
    submitted_dates = {sub[0]: sub for sub in submissions}
    
    for homework_date, deadline in all_assignments:
        if homework_date in submitted_dates:
            submission = submitted_dates[homework_date]
            status_emoji = "✅" if submission[3] == "accepted" else "⏳"
            report += f"{status_emoji} {homework_date}:\n"
            report += f"⏰ Topshirilgan vaqt: {submission[2]}\n"
            if submission[3] == "accepted":
                report += "📝 Status: Qabul qilingan\n\n"
            else:
                report += "📝 Status: Ko'rib chiqilmoqda\n\n"
        else:
            deadline_date = datetime.strptime(deadline, '%d.%m.%Y %H:%M')
            if deadline_date < datetime.now():
                report += f"❌ {homework_date}: Topshirilmagan (Muddat tugagan)\n\n"
            else:
                report += f"⚠️ {homework_date}: Topshirilmagan (Muddat: {deadline})\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="report_by_student")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            report,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except TelegramError as e:
        if "Message is not modified" not in str(e):
            raise e
    
    conn.close()

async def report_submitted_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    # Get all homework dates
    cursor.execute('''
        SELECT DISTINCT homework_date
        FROM notifications
        ORDER BY homework_date DESC
    ''')
    dates = cursor.fetchall()
    
    keyboard = []
    for date in dates:
        keyboard.append([InlineKeyboardButton(
            date[0],
            callback_data=f"submitted_date_{date[0]}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="show_reports_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            "📅 Hisobot uchun sanani tanlang:",
            reply_markup=reply_markup
        )
    except TelegramError as e:
        if "Message is not modified" not in str(e):
            raise e
    
    conn.close()

async def show_submitted_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    homework_date = query.data.split('_')[2]
    
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    # Get all submissions for the selected date
    cursor.execute('''
        SELECT s.first_name, s.last_name, s.student_id, 
               h.submission_time, h.status
        FROM homework_submissions h
        JOIN students s ON h.telegram_id = s.telegram_id
        WHERE h.homework_date = ?
        ORDER BY s.last_name, s.first_name
    ''', (homework_date,))
    submissions = cursor.fetchall()
    
    report = f"📊 *{homework_date}* sanasi uchun topshirilgan vazifalar:\n\n"
    
    if submissions:
        for sub in submissions:
            status_emoji = "✅" if sub[4] == "accepted" else "⏳"
            report += f"{status_emoji} *{sub[1]} {sub[0]}*\n"
            report += f"🆔 ID: {sub[2]}\n"
            report += f"⏰ Vaqt: {sub[3]}\n"
            report += f"📝 Status: {'Qabul qilingan' if sub[4] == 'accepted' else 'Ko\'rib chiqilmoqda'}\n\n"
    else:
        report += "❌ Bu sana uchun topshirilgan vazifalar yo'q"
    
    keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="report_submitted_by_date")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            report,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except TelegramError as e:
        if "Message is not modified" not in str(e):
            raise e
    
    conn.close()

async def show_not_submitted_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    homework_date = query.data.split('_')[3]
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    # Tanlangan sanada vazifa topshirmagan talabalar
    cursor.execute('''
        SELECT s.last_name, s.first_name, s.student_id
        FROM students s
        WHERE s.is_approved = TRUE
        AND s.telegram_id NOT IN (
            SELECT telegram_id 
            FROM homework_submissions 
            WHERE homework_date = ?
        )
        ORDER BY s.last_name, s.first_name
    ''', (homework_date,))
    not_submitted = cursor.fetchall()
    
    cursor.execute('SELECT deadline FROM notifications WHERE homework_date = ?', (homework_date,))
    deadline = cursor.fetchone()[0]
    
    report = f"📊 *{homework_date}* sanasida vazifa topshirmaganlar\n"
    report += f"⏰ Muddat: {deadline}\n\n"
    
    for student in not_submitted:
        report += f"❌ {student[0]} {student[1]} ({student[2]})\n"
    
    if not not_submitted:
        report += "✅ Barcha talabalar vazifani topshirgan"
    
    keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="report_not_submitted_by_date")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            report,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except telegram.error.BadRequest:
        await query.edit_message_text(
            report.replace('*', ''),
            reply_markup=reply_markup
        )
    conn.close()

async def report_students_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT last_name, first_name, student_id, is_approved
        FROM students
        ORDER BY last_name, first_name
    ''')
    students = cursor.fetchall()
    
    report = "📋 *Talabalar ro'yxati*\n\n"
    
    for student in students:
        status = "✅" if student[3] else "⏳"
        report += f"{status} {student[0]} {student[1]}\n"
        report += f"🆔 {student[2]}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="show_reports_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            report,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except telegram.error.BadRequest:
        await query.edit_message_text(
            report.replace('*', ''),
            reply_markup=reply_markup
        )
    conn.close()


async def submit_homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in user_states or "homework_date" not in user_states[user_id]:
        await query.answer("Xatolik! Iltimos qaytadan urinib ko'ring")
        return
    homework_date = user_states[user_id]["homework_date"]
    if user_id not in user_files or not user_files[user_id]:
        await query.answer("Iltimos, avval fayllarni yuklang")
        return
    
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    try:
        file_ids = ",".join(user_files[user_id])
        submission_time = datetime.now()
        cursor.execute('''
            INSERT INTO homework_submissions
            (telegram_id, homework_date, submission_date, status, submission_time, file_ids)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            homework_date,
            submission_time.strftime('%Y-%m-%d'),
            'submitted',
            submission_time,
            file_ids
        ))
        conn.commit()
        
        files_to_send = user_files[user_id].copy()
        
        await query.message.edit_text(
            "✅ Vazifa muvaffaqiyatli yuklandi!\n"
            "Bosh menyuga qaytish uchun /start buyrug'ini bosing."
        )

        for admin_id in ADMIN_IDS:
            student_info = get_student_info(user_id)
            if student_info:
                admin_message = (
                    f"📥 Yangi vazifa yuklandi!\n\n"
                    f"👤 Talaba: {student_info['first_name']} {student_info['last_name']}\n"
                    f"🆔 Talaba ID: {student_info['student_id']}\n"
                    f"📅 Sana: {homework_date}\n"
                )
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=admin_message
                    )
                    
                    for file_id in files_to_send:
                        try:
                            file = await context.bot.get_file(file_id)
                            file_path = file.file_path.lower()
                            
                            if any(file_path.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                                await context.bot.send_photo(
                                    chat_id=admin_id,
                                    photo=file_id,
                                    caption=f"Talaba {student_info['first_name']} {student_info['last_name']} ning fayli"
                                )
                            else:
                                await context.bot.send_document(
                                    chat_id=admin_id,
                                    document=file_id,
                                    caption=f"Talaba {student_info['first_name']} {student_info['last_name']} ning fayli"
                                )
                        except Exception as e:
                            print(f"Error sending file to admin {admin_id}: {e}")
                            continue
                            
                except Exception as e:
                    print(f"Error notifying admin {admin_id}: {e}")
        
        user_files.pop(user_id, None)
        user_states[user_id].pop("homework_date", None)
        user_states[user_id].pop("last_message_id", None)
                    
    except Exception as e:
        print(f"Error submitting homework: {e}")
        await query.answer("Xatolik yuz berdi")
    finally:
        conn.close()


        
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Send reminders to users who haven't submitted homework"""
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT homework_date, deadline 
        FROM notifications 
        WHERE datetime(deadline) > datetime('now')
    ''')
    active_assignments = cursor.fetchall()
    
    for homework_date, deadline in active_assignments:
        try:
            deadline_dt = datetime.strptime(deadline, '%d.%m.%Y %H:%M')
            current_time = datetime.now()
            time_left = deadline_dt - current_time
            
            cursor.execute('''
                SELECT s.telegram_id, s.first_name 
                FROM students s 
                LEFT JOIN homework_submissions h 
                ON s.telegram_id = h.telegram_id AND h.homework_date = ?
                WHERE h.id IS NULL AND s.is_approved = TRUE
            ''', (homework_date,))
            
            users_to_remind = cursor.fetchall()
            
            for user_id, first_name in users_to_remind:
                reminder_message = ""
                
                if timedelta(hours=23) <= time_left <= timedelta(hours=24):
                    reminder_message = (
                        f"⚠️ Muhim eslatma!\n\n"
                        f"Hurmatli {first_name}, {homework_date} sanasi uchun vazifani topshirishga:\n"
                        f"⏰ 24 soat qoldi!\n"
                        f"Oxirgi muddat: {deadline}\n\n"
                        f"Iltimos, vazifani o'z vaqtida topshiring!"
                    )
                
                elif timedelta(hours=11) <= time_left <= timedelta(hours=12):
                    reminder_message = (
                        f"⚠️ Juda muhim eslatma!\n\n"
                        f"Hurmatli {first_name}, {homework_date} sanasi uchun vazifani topshirishga:\n"
                        f"⏰ 12 soat qoldi!\n"
                        f"Oxirgi muddat: {deadline}\n\n"
                        f"Iltimos, vazifani tezroq topshiring!"
                    )
                
                elif timedelta(hours=2) <= time_left <= timedelta(hours=3):
                    reminder_message = (
                        f"🚨 JUDA MUHIM ESLATMA!\n\n"
                        f"Hurmatli {first_name}, {homework_date} sanasi uchun vazifani topshirishga:\n"
                        f"⏰ ATIGI 3 SOAT QOLDI!\n"
                        f"Oxirgi muddat: {deadline}\n\n"
                        f"Iltimos, vazifani DARHOL topshiring!"
                    )
                
                if reminder_message:
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=reminder_message
                        )
                    except Exception as e:
                        print(f"Error sending reminder to {user_id}: {e}")
                        
        except Exception as e:
            print(f"Error processing deadline {deadline}: {e}")
            continue
    
    conn.close()


def get_student_info(user_id: int) -> dict:
    """Get student information from database"""
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT first_name, last_name, student_id 
        FROM students 
        WHERE telegram_id = ?
    ''', (user_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'first_name': result[0],
            'last_name': result[1],
            'student_id': result[2]
        }
    return None


async def approve_student(update: Update, context: ContextTypes.DEFAULT_TYPE, student_id: int):
    """Approve student registration"""
    query = update.callback_query
    
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE students 
            SET is_approved = TRUE 
            WHERE telegram_id = ?
        ''', (student_id,))
        
        cursor.execute('''
            SELECT first_name, last_name 
            FROM students 
            WHERE telegram_id = ?
        ''', (student_id,))
        
        student = cursor.fetchone()
        conn.commit()
        
        if student:
            await query.edit_message_text(
                f"✅ Talaba {student[0]} {student[1]} tasdiqlandi!"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=student_id,
                    text="✅ Sizning profilingiz tasdiqlandi! Botdan foydalanishingiz mumkin."
                )
                await show_main_menu_message(context, student_id)
            except Exception as e:
                print(f"Error notifying student {student_id}: {e}")
        
    except Exception as e:
        print(f"Error approving student: {e}")
        await query.answer("Xatolik yuz berdi")
    finally:
        conn.close()


async def show_main_menu_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    keyboard = [
        [InlineKeyboardButton("📚 Vazifalar ro'yxati", callback_data="show_homework_list")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="Vazifalarni ko'rish uchun quyidagi tugmani bosing:",
        reply_markup=reply_markup
    )
    

async def reject_student(update: Update, context: ContextTypes.DEFAULT_TYPE, student_id: int):
    query = update.callback_query
    
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT first_name, last_name 
            FROM students 
            WHERE telegram_id = ?
        ''', (student_id,))
        
        student = cursor.fetchone()
        
        cursor.execute('DELETE FROM students WHERE telegram_id = ?', (student_id,))
        conn.commit()
        
        if student:
            await query.edit_message_text(
                f"❌ Talaba {student[0]} {student[1]} rad etildi!"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=student_id,
                    text="❌ Kechirasiz, sizning so'rovingiz rad etildi. Qaytadan ro'yxatdan o'tish uchun /start buyrug'ini bosing."
                )
            except Exception as e:
                print(f"Error notifying student {student_id}: {e}")
        
    except Exception as e:
        print(f"Error rejecting student: {e}")
        await query.answer("Xatolik yuz berdi")
    finally:
        conn.close()

        

async def handle_homework_date_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, homework_date: str):
    query = update.callback_query
    user_id = query.from_user.id
    
    if check_submission_exists(user_id, homework_date):
        await query.answer("Siz bu vazifani allaqachon topshirgansiz!")
        await show_homework_list(update, context)
        return
    
    if not is_submission_allowed(homework_date):
        await query.answer("Bu vazifani topshirish muddati tugagan.")
        await show_homework_list(update, context)
        return
    
    deadline_date = get_deadline_for_date(homework_date)
    if deadline_date:
        user_states[user_id] = {
            "state": "sending_homework",
            "homework_date": homework_date
        }
        
        keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_homework_list")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(
            f"📝 {homework_date} sanasi uchun vazifa:\n\n"
            f"⚠️ Topshirish muddati: {deadline_date.strftime('%d.%m.%Y %H:%M')} gacha\n\n"
            "Vazifa fayllarini yuborishingiz mumkin.",
            reply_markup=reply_markup
        )
    else:
        await query.answer("Bu sana uchun muddat topilmadi.")
        await show_homework_list(update, context)

def adapt_datetime(dt):
    return dt.isoformat()

def convert_datetime(s):
    try:
        return datetime.fromisoformat(s.decode())
    except:
        return datetime.strptime(s.decode(), '%Y-%m-%d %H:%M:%S')

sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("datetime", convert_datetime)



    
async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return
    
    try:
        conn = sqlite3.connect('homework_bot.db')
        
        conn.execute('PRAGMA journal_mode=WAL')
        
        query = '''
            SELECT 
                s.first_name, 
                s.last_name, 
                s.student_id,
                s.is_approved,
                h.homework_date,
                h.submission_date,
                COALESCE(h.submission_time, '') as submission_time,
                COALESCE(h.status, 'not submitted') as status,
                COALESCE(h.file_ids, '') as file_ids
            FROM students s
            LEFT JOIN homework_submissions h ON s.telegram_id = h.telegram_id
        '''
        
        df = pd.read_sql_query(query, conn)
        
        df.columns = [
            'Ism', 
            'Familiya', 
            'Talaba ID',
            'Tasdiqlangan',
            'Vazifa sanasi',
            'Topshirilgan sana',
            'Topshirilgan vaqt',
            'Status',
            'Fayl IDlari'
        ]
        
        df['Tasdiqlangan'] = df['Tasdiqlangan'].map({1: 'Ha', 0: 'Yo\'q'})
        
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        excel_file = f'homework_report_{current_time}.xlsx'
        
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Vazifalar hisoboti')
            
            worksheet = writer.sheets['Vazifalar hisoboti']
            for i, col in enumerate(df.columns):
                max_length = max(df[col].astype(str).apply(len).max(), len(col)) + 2
                worksheet.column_dimensions[chr(65 + i)].width = max_length
        
        with open(excel_file, 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=f,
                filename=excel_file,
                caption="Vazifalar hisoboti"
            )
        
        os.remove(excel_file)
        
    except Exception as e:
        await update.message.reply_text(f"Hisobot yaratishda xatolik yuz berdi: {str(e)}")
    finally:
        conn.close()


async def generate_student_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return
    
    try:
        conn = sqlite3.connect('homework_bot.db')
        conn.execute('PRAGMA journal_mode=WAL')
        
        query = '''
            SELECT DISTINCT
                s.first_name, 
                s.last_name, 
                s.student_id
            FROM students s
            LEFT JOIN homework_submissions h ON s.telegram_id = h.telegram_id
            GROUP BY s.student_id
        '''
        
        df = pd.read_sql_query(query, conn)
        
        df.columns = [
            'Ism', 
            'Familiya', 
            'Talaba ID'
        ]
                
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        excel_file = f'student_report_{current_time}.xlsx'
        
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Talabalar hisoboti')
            
            worksheet = writer.sheets['Talabalar hisoboti']
            for i, col in enumerate(df.columns):
                max_length = max(df[col].astype(str).apply(len).max(), len(col)) + 2
                worksheet.column_dimensions[chr(65 + i)].width = max_length
        
        with open(excel_file, 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=f,
                filename=excel_file,
                caption="Talabalar"
            )
        
        os.remove(excel_file)
        
    except Exception as e:
        await update.message.reply_text(f"Hisobot yaratishda xatolik yuz berdi: {str(e)}")
    finally:
        conn.close()


async def handle_homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return
    
    try:
        parts = update.message.text.split(' ', 1)
        if len(parts) < 2:
            await update.message.reply_text("Formatga rioya qiling: /vazifa DD.MM.YYYY")
            return
        
        homework_date = parts[1].strip()
        
        try:
            input_date = datetime.strptime(homework_date, '%d.%m.%Y')
        except ValueError:
            await update.message.reply_text("Noto'g'ri sana formati. Iltimos, DD.MM.YYYY formatida kiriting.")
            return
        
        deadline = (input_date + timedelta(days=2)).replace(hour=23, minute=59)
        deadline_str = deadline.strftime('%d.%m.%Y %H:%M')
        
        conn = sqlite3.connect('homework_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO notifications (message, homework_date, deadline, created_at)
            VALUES (?, ?, ?, ?)
        ''', ("Kunlik vazifa", homework_date, deadline_str, datetime.now()))
        conn.commit()
        conn.close()
        
        message = (
            f"📢 Yangi vazifa!\n\n"
            f"Sana: {homework_date}\n"
            f"Oxirgi muddat: {deadline_str}\n\n"
            f"vazifani bajarib yuboringlar!"
        )
        
        conn = sqlite3.connect('homework_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT telegram_id FROM students WHERE is_approved = TRUE')
        users = cursor.fetchall()
        conn.close()
        
        success_count = 0
        fail_count = 0
        
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user[0],
                    text=message
                )
                success_count += 1
            except Exception as e:
                print(f"Error sending to {user[0]}: {e}")
                fail_count += 1
        
        result_message = (
            f"✅ Xabar yuborildi:\n"
            f"Muvaffaqiyatli: {success_count}\n"
            f"Yuborilmadi: {fail_count}"
        )
        await update.message.reply_text(result_message)
        
    except Exception as e:
        await update.message.reply_text(f"Xatolik yuz berdi: {str(e)}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_states:
        await update.message.reply_text(
            "Iltimos, /start buyrug'ini bosing."
        )
        return
    
    state = user_states[user_id]["state"]
    
    if state == "awaiting_first_name":
        user_states[user_id].update({
            "state": "awaiting_last_name",
            "first_name": update.message.text
        })
        await update.message.reply_text("Endi familiyangizni kiriting:")
        
    elif state == "awaiting_last_name":
        user_states[user_id].update({
            "state": "awaiting_student_id",
            "last_name": update.message.text
        })
        await update.message.reply_text(
            "Iltimos, 9 xonali talaba ID raqamingizni kiriting:"
        )
        
    elif state == "awaiting_student_id":
        student_id = update.message.text
        if not is_valid_student_id(student_id):
            await update.message.reply_text(
                "Noto'g'ri ID format. ID raqam 9 ta raqamdan iborat bo'lishi kerak. "
                "Iltimos, qaytadan kiriting:"
            )
            return
            
        conn = sqlite3.connect('homework_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO students (telegram_id, first_name, last_name, student_id, is_approved)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, user_states[user_id]["first_name"], 
              user_states[user_id]["last_name"], student_id, False))
        
        conn.commit()
        conn.close()
        
        admin_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{user_id}")
            ]
        ])
        
        admin_message = (
            "Yangi foydalanuvchi ro'yxatdan o'tdi!\n\n"
            f"👤 {user_states[user_id]['first_name']}\n"
            f"📝 {user_states[user_id]['last_name']}\n"
            f"🆔 {student_id}"
        )
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_message,
                    reply_markup=admin_keyboard
                )
            except Exception as e:
                print(f"Error sending to admin {admin_id}: {e}")
        
        await update.message.reply_text(
            "Sizning ma'lumotlaringiz admin tomonidan tekshirilgandan keyin "
            "botdan foydalanishingiz mumkin bo'ladi. Iltimos, kuting."
        )
        
        user_states[user_id]["state"] = "waiting_approval"

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_states or user_states[user_id].get("state") != "sending_homework":
        return
    
    homework_date = user_states[user_id].get("homework_date")
    if not is_submission_allowed(homework_date):
        await update.message.reply_text(
            f"Kechirasiz, {homework_date} sanadagi vazifani topshirish muddati tugagan. "
            "Siz vazifani o'z vaqtida yubormadingiz."
        )
        await update.message.reply_text(
            "Yangi vazifa sanasini tanlang:",
            reply_markup=get_date_keyboard()
        )
        return
    
    if user_id not in user_files:
        user_files[user_id] = []
    
    file_id = None
    if update.message.document:
        file_id = update.message.document.file_id
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id
    
    if file_id:
        user_files[user_id].append(file_id)
        if "last_message_id" in user_states[user_id]:
            try:
                await context.bot.delete_message(
                    chat_id=user_id,
                    message_id=user_states[user_id]["last_message_id"]
                )
            except:
                pass
        
        message = await update.message.reply_text(
            "Tugatganingizda 'Tayyor' tugmasini bosing:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Tayyor", callback_data="homework_done")]])
        )
        user_states[user_id]["last_message_id"] = message.message_id

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS




def is_submission_allowed(homework_date: str) -> bool:
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT deadline 
        FROM notifications 
        WHERE homework_date = ?
    ''', (homework_date,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        try:
            deadline = datetime.strptime(result[0], '%d.%m.%Y %H:%M')
            return deadline > datetime.now()
        except ValueError:
            return False
    
    return False


def get_deadline_for_date(homework_date):
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT deadline 
        FROM notifications 
        WHERE homework_date = ?
    ''', (homework_date,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        try:
            return datetime.strptime(result[0], '%d.%m.%Y %H:%M')
        except ValueError:
            return None
    return None

async def approve_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tasdiqlash kutayotgan talabalar ro'yxatini ko'rsatish"""
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()
    
    # Tasdiqlanmagan talabalarni olish
    cursor.execute('''
        SELECT telegram_id, first_name, last_name, student_id 
        FROM students 
        WHERE is_approved = FALSE
        ORDER BY last_name, first_name
    ''')
    students = cursor.fetchall()
    
    if not students:
        keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_admin_menu")]]
        await query.edit_message_text(
            "📝 Hozirda tasdiqlash kutayotgan talabalar yo'q",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        conn.close()
        return
    
keyboard = []


    

def main():
    setup_database()
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("report", generate_report))
    application.add_handler(CommandHandler("vazifa", handle_homework))
    application.add_handler(CommandHandler("talabalar", generate_student_list))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_file))
    
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    job_queue = application.job_queue
    job_queue.run_repeating(send_reminder, interval=timedelta(hours=12))
    
    print("Bot ish faoliyatini boshladi...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generates a report of students who have submitted and who have not submitted."""
    conn = sqlite3.connect('homework_bot.db')
    cursor = conn.cursor()

    # Get all students
    cursor.execute("SELECT telegram_id, first_name, last_name, student_id FROM students WHERE is_approved = 1")
    students = cursor.fetchall()

    # Get all submissions
    cursor.execute("SELECT DISTINCT telegram_id FROM homework_submissions WHERE homework_date = ?", (datetime.now().strftime('%Y-%m-%d'),))
    submitted_students = set(row[0] for row in cursor.fetchall())

    # Create lists for submitted and not submitted students
    submitted_list = []
    not_submitted_list = []

    for student in students:
        if student[0] in submitted_students:
            submitted_list.append(f"{student[2]} {student[1]} (ID: {student[3]})")
        else:
            not_submitted_list.append(f"{student[2]} {student[1]} (ID: {student[3]})")

    # Prepare the message
    report_message = "*Homework Submission Report*\n\n"
    report_message += "*Submitted:*\n" + "\n".join(submitted_list) + "\n\n" if submitted_list else "*No submissions yet.*\n\n"
    report_message += "*Not Submitted:*\n" + "\n".join(not_submitted_list) if not_submitted_list else "*All students submitted.*"

    # Send the report message to the admin
    context.bot.send_message(chat_id=ADMIN_ID, text=report_message, parse_mode="Markdown")
    conn.close()
    
    # Inform admin that the report was sent
    update.message.reply_text("Report generated and sent to admin.")

application.add_handler(CommandHandler("report", generate_report, filters.User(ADMIN_IDS[0])))
