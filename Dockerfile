FROM python:3.12-slim

# Установить рабочую директорию
WORKDIR /app

# Скопировать файлы проекта
COPY . /app

# Установить зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Открыть порт
EXPOSE 5000

# Команда для запуска приложения
CMD ["python", "app.py"]