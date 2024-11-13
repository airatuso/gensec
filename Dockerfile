# Используем базовый образ Python 3.10 или новее
FROM python:3.10-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл зависимостей и устанавливаем их
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта в рабочую директорию контейнера
COPY . .

# Устанавливаем переменную окружения для Flask
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_ENV=production
# Устанавливаем в production для безопасности

# Открываем порт 5000 для внешнего доступа
EXPOSE 5000

# Запускаем Flask сервер
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
