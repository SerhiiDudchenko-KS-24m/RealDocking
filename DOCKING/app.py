# -*- coding: utf-8 -*-
# ВАЖЛИВО: Gevent patch - має бути на самому початку!
from gevent import monkey
monkey.patch_all()

# Решта імпортів
import os
import pika
import threading # Gevent патчить це
import time
import json
import logging
from flask import Flask, render_template, Response
from flask_sse import sse

# Налаштування логування
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Налаштування Flask ---
app = Flask(__name__)
# ВАЖЛИВО: Встановлюємо URL для Redis
app.config["REDIS_URL"] = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
# app.config["SSE_CHANNEL_NAME"] = "messages" # Можна видалити або залишити для довідки
# app.config["SSE_DEFAULT_CHANNEL"] = ... # Видаляємо, бо не спрацювало

# Використовуємо канал 'sse', який Flask-SSE використовує для підписки за замовчуванням
ACTUAL_SSE_CHANNEL = 'sse' # Визначаємо фактичний канал

app.register_blueprint(sse, url_prefix='/stream') # Реєстрація SSE ендпоінту

# --- Налаштування RabbitMQ ---
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT', 5672))
RABBITMQ_USER = os.environ.get('RABBITMQ_USER', 'guest')
RABBITMQ_PASS = os.environ.get('RABBITMQ_PASS', 'guest')
RABBITMQ_QUEUE = os.environ.get('RABBITMQ_QUEUE', 'my_message_queue')

# --- Глобальна змінна для зберігання статусу підключення ---
rabbitmq_connected = False

# --- Логіка RabbitMQ Listener ---
def rabbitmq_listener():
    """Функція, що слухає чергу RabbitMQ у окремому потоці."""
    global rabbitmq_connected
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        connection_attempts=5,
        retry_delay=5
    )

    while True:
        try:
            logging.info(f"Спроба підключення до RabbitMQ: {RABBITMQ_HOST}:{RABBITMQ_PORT}...")
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
            logging.info(f"Підключено до RabbitMQ, слухаю чергу '{RABBITMQ_QUEUE}'")
            rabbitmq_connected = True

            def callback(ch, method, properties, body):
                """Обробник отриманих повідомлень."""
                try:
                    message = body.decode('utf-8')
                    logging.info(f"Отримано повідомлення: {message}")
                    # *** ЗМІНЕНО ТУТ: Публікуємо в канал 'sse' ***
                    with app.app_context():
                        sse.publish({"message": message}, type='new_message', channel=ACTUAL_SSE_CHANNEL) # Явно вказуємо 'sse'
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    logging.exception("Помилка обробки повідомлення або публікації SSE:")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=callback)
            logging.info(" [*] Очікування повідомлень. Для виходу натисніть CTRL+C")
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            logging.error(f"Не вдалося підключитися до RabbitMQ: {e}. Повторна спроба через {parameters.retry_delay} сек.")
            rabbitmq_connected = False
            time.sleep(parameters.retry_delay)
        except Exception as e:
            logging.error(f"Неочікувана помилка RabbitMQ: {e}. Спроба перепідключення...")
            rabbitmq_connected = False
            if 'connection' in locals() and connection.is_open:
                try: connection.close()
                except Exception: pass # Ігноруємо помилки при закритті в стані помилки
            time.sleep(5)

# Запускаємо слухача RabbitMQ у окремому потоці (gevent пропатчить threading)
listener_thread = threading.Thread(target=rabbitmq_listener, daemon=True)
listener_thread.start()

# --- Маршрути Flask ---
@app.route('/')
def index():
    """Головна сторінка, що відображає HTML."""
    # Передаємо реальний канал, який використовується ('sse')
    return render_template(
        'index.html',
        queue_name=RABBITMQ_QUEUE,
        rabbitmq_host=RABBITMQ_HOST,
        sse_channel_name=ACTUAL_SSE_CHANNEL # Передаємо 'sse' в шаблон
    )

# Цей блок більше не потрібен, оскільки Gunicorn запускає додаток
# if __name__ == '__main__':
#     pass