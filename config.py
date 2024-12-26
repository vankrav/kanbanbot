import os
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# Получаем токен из переменных окружения
TOKEN = os.getenv('BOT_TOKEN')

# Проверка наличия токена
if not TOKEN:
    raise ValueError("Не указан токен бота. Добавьте BOT_TOKEN в файл .env") 