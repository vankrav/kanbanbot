from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
from datetime import datetime, timedelta
from config import TOKEN

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('kanban.db')
    c = conn.cursor()
    
    # Удаляем старую таблицу, если она существует
    c.execute('DROP TABLE IF EXISTS tasks')
    
    # Создаем таблицу с новой структурой
    c.execute('''CREATE TABLE IF NOT EXISTS tasks
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  task_text TEXT,
                  status TEXT,
                  created_at TIMESTAMP)''')
    conn.commit()
    conn.close()

# Статусы задач для канбан-доски
STATUSES = ['To Do', 'In Progress', 'Done']

# В начале файла добавим константу с кнопками меню
MAIN_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("📋 Показать доску"), KeyboardButton("➕ Добавить задачу")],
    [KeyboardButton("❓ Помощь")]
], resize_keyboard=True)

# В начале файла добавим константу для максимального количества сообщений
MAX_MESSAGES = 3

async def cleanup_messages(context: ContextTypes.DEFAULT_TYPE):
    """Удаляет старые сообщения, оставляя только последние MAX_MESSAGES"""
    if 'message_history' not in context.user_data:
        context.user_data['message_history'] = []
    
    messages = context.user_data['message_history']
    while len(messages) > MAX_MESSAGES:
        old_message = messages.pop(0)  # Удаляем самое старое сообщение
        try:
            await old_message.delete()
        except:
            pass

async def add_message_to_history(message, context: ContextTypes.DEFAULT_TYPE):
    """Добавляет сообщение в историю и удаляет старые"""
    if 'message_history' not in context.user_data:
        context.user_data['message_history'] = []
    
    context.user_data['message_history'].append(message)
    await cleanup_messages(context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Добро пожаловать в Канбан-бот!\n'
        'Используйте следующие команды:\n'
        '/add <задача> - добавить новую задачу\n'
        '/board - показать канбан-доску\n'
        '/help - показать справку',
        reply_markup=MAIN_KEYBOARD
    )

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Если нет аргументов, запрашиваем текст задачи
    if not context.args:
        context.user_data['waiting_for_task'] = True
        await update.message.reply_text('Введите текст задачи:')
        return

    # Если есть аргументы, создаем задачу сразу
    task_text = ' '.join(context.args)
    await create_task(update, context, task_text)

async def create_task(update: Update, context: ContextTypes.DEFAULT_TYPE, task_text: str):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('kanban.db')
    c = conn.cursor()
    c.execute('INSERT INTO tasks (user_id, task_text, status, created_at) VALUES (?, ?, ?, ?)',
              (user_id, task_text, 'To Do', datetime.now()))
    conn.commit()
    conn.close()
    
    message = await update.message.reply_text(f'✅ Задача "{task_text}" добавлена в колонку "To Do"')
    await add_message_to_history(message, context)
    await show_board(update, context)

async def show_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'last_board_message' in context.user_data:
        try:
            await context.user_data['last_board_message'].delete()
        except:
            pass
    
    user_id = update.effective_user.id
    conn = sqlite3.connect('kanban.db')
    c = conn.cursor()
    
    keyboard = []
    
    for status in STATUSES:
        c.execute('SELECT id, task_text FROM tasks WHERE user_id = ? AND status = ?',
                 (user_id, status))
        tasks = c.fetchall()
        
        keyboard.append([InlineKeyboardButton(f"📌 {status}", callback_data="header")])
        
        if tasks:
            for task_id, task_text in tasks:
                keyboard.append([InlineKeyboardButton(
                    f"• {task_text}", 
                    callback_data=f"task_{task_id}"
                )])
        else:
            keyboard.append([InlineKeyboardButton("Нет задач", callback_data="empty")])
        
        if status != STATUSES[-1]:
            keyboard.append([InlineKeyboardButton("⎯⎯⎯⎯⎯", callback_data="divider")])

    conn.close()
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = await update.message.reply_text(
        "🎯 Ваша Канбан-доска\nНажмите на задачу для действий:",
        reply_markup=reply_markup
    )
    await add_message_to_history(message, context)
    context.user_data['last_board_message'] = message

def create_task_actions_keyboard(task_id):
    keyboard = [
        [
            InlineKeyboardButton("⬅️ To Do", callback_data=f"move_{task_id}_To Do"),
            InlineKeyboardButton("▶️ In Progress", callback_data=f"move_{task_id}_In Progress"),
            InlineKeyboardButton("✅ Done", callback_data=f"move_{task_id}_Done")
        ],
        [
            InlineKeyboardButton("✏️ Изменить", callback_data=f"edit_{task_id}"),
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{task_id}")
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_board")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.data == "header" or query.data == "empty" or query.data == "divider":
        await query.answer()
        return
    
    if query.data == "back_to_board":
        await show_board(update, context)
        return
    
    action = query.data.split('_')[0]
    
    conn = sqlite3.connect('kanban.db')
    c = conn.cursor()
    
    if action == "task":
        task_id = query.data.split('_')[1]
        task_text, status = c.execute(
            'SELECT task_text, status FROM tasks WHERE id = ?', 
            (task_id,)
        ).fetchone()
        conn.close()
        
        keyboard = create_task_actions_keyboard(task_id)
        message = await query.message.edit_text(
            f"📝 Задача: {task_text}\n"
            f"📌 Статус: {status}\n\n"
            "Выберите действие:",
            reply_markup=keyboard
        )
        await add_message_to_history(message, context)
        await query.answer()
        return
    
    elif action == "move":
        _, task_id, new_status = query.data.split('_')
        c.execute('UPDATE tasks SET status = ? WHERE id = ?', (new_status, task_id))
        conn.commit()
        conn.close()
        message = await update.effective_message.reply_text(f'✅ Задача перемещена в {new_status}')
        await add_message_to_history(message, context)
        await show_board(update, context)
    
    elif action == "delete":
        task_id = query.data.split('_')[1]
        c.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
        conn.close()
        message = await update.effective_message.reply_text('🗑️ Задача удалена')
        await add_message_to_history(message, context)
        await show_board(update, context)
    
    elif action == "edit":
        task_id = query.data.split('_')[1]
        context.user_data['editing_task'] = task_id
        message = await update.effective_message.reply_text('Отправьте новый текст для задачи:')
        await add_message_to_history(message, context)
        conn.close()
        await query.answer()

# Добавляем обработчик для редактирования задачи
async def handle_edit_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Удаляем сообщение с новым текстом
    try:
        await update.message.delete()
    except:
        pass

    if 'editing_task' not in context.user_data:
        return
    
    task_id = context.user_data['editing_task']
    new_text = update.message.text
    
    conn = sqlite3.connect('kanban.db')
    c = conn.cursor()
    c.execute('UPDATE tasks SET task_text = ? WHERE id = ?', (new_text, task_id))
    conn.commit()
    conn.close()
    
    del context.user_data['editing_task']
    await update.message.reply_text('Задача обновлена!')
    await show_board(update, context)

# Добавим новую функцию для обработки текстовых команд с кнопок
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # Проверяем, ожидаем ли мы текст задачи
    if context.user_data.get('waiting_for_task'):
        del context.user_data['waiting_for_task']
        await create_task(update, context, text)
        return
    
    if text == "📋 Показать доску":
        await show_board(update, context)
    elif text == "➕ Добавить задачу":
        context.user_data['waiting_for_task'] = True
        await update.message.reply_text('Введите текст задачи:')
    elif text == "❓ Помощь":
        await start(update, context)
    elif 'editing_task' in context.user_data:
        await handle_edit_message(update, context)

def main():
    init_db()
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("add", add_task))
    application.add_handler(CommandHandler("board", show_board))
    application.add_handler(CallbackQueryHandler(handle_button))
    # Обновляем обработчик сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == '__main__':
    main() 