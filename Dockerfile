FROM python:3.12-slim

# Установить рабочую директорию
WORKDIR /app

# Скопировать файлы проекта
COPY . /app

# Создать папку instance для базы данных
RUN mkdir -p /app/instance

# Установить зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Открыть порт
EXPOSE 8000

# Команда для запуска приложения
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--log-level", "warning"]