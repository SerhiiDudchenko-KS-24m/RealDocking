# Використовуємо офіційний образ Python
FROM python:3.9-slim

# Встановлюємо робочу директорію в контейнері
WORKDIR /app

# Копіюємо файл залежностей
COPY requirements.txt .

# Встановлюємо залежності
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо решту коду програми в робочу директорію
COPY . .

# Вказуємо порт, який слухає Gunicorn
EXPOSE 5000

# *** ЗМІНЕНО ТУТ: Команда для запуску через Gunicorn + Gevent ***
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--worker-class", "gevent", "app:app"]