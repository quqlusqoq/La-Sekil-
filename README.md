# La Sekilé Music Bot 🎵

Telegram бот для скачивания музыки с YouTube и Spotify

## Команды
- Отправь ссылку на YouTube видео
- Отправь ссылку на Spotify трек
- Отправь название песни (поиск по YouTube)

## Деплой на Render
1. Создай аккаунт на render.com
2. Нажми "New +" → "Web Service"
3. Подключи GitHub репозиторий
4. Настрой:
   - Environment: Docker
   - Branch: main
   - Plan: Free
5. Добавь переменную BOT_TOKEN
6. В Advanced добавь Health Check Path: /health
7. Нажми "Create Web Service"