# SFKT VPN Node Service

VPN node service с Xray-core для SFKT VPN проекта.

## Описание

Этот сервис представляет собой независимую VPN ноду, которая:
- Работает на базе Xray-core с протоколом VLESS/REALITY (Xray работает напрямую на хосте)
- Node Agent работает в Docker и управляет конфигурацией Xray
- Маскирует трафик под VK Video для обхода блокировок
- Автоматически регистрируется на главном сервере
- Синхронизирует статистику трафика в реальном времени
- Отправляет health checks для мониторинга

## Архитектура

- **Xray-core**: Работает на хосте (установлен через systemd), обеспечивает лучшую производительность и стабильность сети
- **Node Agent**: Работает в Docker, синхронизирует пользователей и статистику с главным сервером

## Требования

- Сервер на Debian 12 или Ubuntu 22.04+ (для установки Xray на хост)
- Docker и Docker Compose установлены на сервере
- Root доступ для установки Xray на хост
- Открыт порт 443 (для VPN трафика)
- Доступ к главному серверу SFKT
- Валидный домен с А-записью, указывающей на IP ноды (опционально, но рекомендуется)

## Установка

### 1. Клонирование репозитория

```bash
# Создайте директорию для ноды
mkdir -p /opt/sfkt-node
cd /opt/sfkt-node

# Скопируйте файлы node-service из основного репозитория
# (предполагается, что вы клонировали основной репозиторий SFKT)
```

### 2. Установка Xray на хост

Xray устанавливается напрямую на хост-систему для лучшей производительности:

```bash
# Перейдите в директорию скриптов
cd /opt/sfkt-node/scripts

# Сделайте скрипт установки исполняемым
chmod +x install_xray_host.sh

# Запустите установку от root
sudo ./install_xray_host.sh
```

Скрипт автоматически:
- Загрузит и установит последнюю версию Xray-core
- Создаст systemd сервис `xray.service`
- Установит конфигурационный шаблон в `/usr/local/etc/xray/config.json`
- Настроит права доступа

После установки:
```bash
# Проверьте статус сервиса
sudo systemctl status xray

# Включите автозапуск
sudo systemctl enable xray
```

### 3. Генерация ключей REALITY

```bash
# Вернитесь в директорию node-service
cd /opt/sfkt-node

# Сделайте скрипт исполняемым
chmod +x scripts/generate_reality_keys.sh

# Запустите генерацию ключей
./scripts/generate_reality_keys.sh
```

Скрипт выведет три значения:
- **Private Key** - приватный ключ для конфигурации Xray на ноде
- **Public Key** - публичный ключ для базы данных главного сервера и клиентов
- **Short ID** - короткий идентификатор для REALITY протокола

**ВАЖНО**: Сохраните эти значения в безопасном месте! Они понадобятся на следующих шагах.

### 4. Настройка Xray конфигурации

Отредактируйте конфигурацию Xray и вставьте сгенерированные ключи:

```bash
# Откройте конфигурацию
sudo nano /usr/local/etc/xray/config.json
```

Замените плейсхолдеры на реальные значения:
- `PRIVATE_KEY_PLACEHOLDER` → ваш Private Key из шага 3
- `SHORT_ID_PLACEHOLDER` → ваш Short ID из шага 3

Сохраните файл (Ctrl+O, Enter, Ctrl+X).

### 5. Настройка переменных окружения

```bash
# Создайте .env файл из примера
cp .env.example .env

# Отредактируйте .env файл
nano .env
```

Заполните все переменные в `.env` файле:

```bash
# Информация о ноде
NODE_NAME=Moscow-1
NODE_HOSTNAME=moscow1.yourdomain.com  # или IP адрес
NODE_IP=1.2.3.4
NODE_PORT=443

# Геолокация
NODE_COUNTRY=Russia
NODE_COUNTRY_CODE=RU
NODE_CITY=Moscow

# REALITY ключи (из шага 2)
REALITY_PRIVATE_KEY=your-private-key-from-step-2
REALITY_PUBLIC_KEY=your-public-key-from-step-2
REALITY_SHORT_ID=your-short-id-from-step-2

# SNI для маскировки
NODE_SNI=vk.com

# Подключение к главному серверу
MAIN_SERVER_URL=https://sfkt.mxl.wtf
NODE_API_KEY=same-as-NODE_API_SECRET-on-main-server
```

**ВАЖНО**: `NODE_API_KEY` на ноде должен совпадать с `NODE_API_SECRET` в `.env` файле главного сервера!

Также создайте docker-compose.yml (если его нет):

```bash
cp docker-compose.example.yml docker-compose.yml
```

### 6. Запуск Xray на хосте

Запустите Xray сервис:

```bash
# Запустите Xray
sudo systemctl start xray

# Проверьте статус
sudo systemctl status xray

# Должно быть: active (running)
```

Проверьте, что Xray слушает порт 443:

```bash
sudo ss -tulpn | grep 443
# Должно быть: LISTEN ... xray
```

### 7. Запуск Node Agent в Docker

```bash
# Запустите контейнер node-agent в фоновом режиме
docker compose up -d --build

# Дождитесь загрузки (10-15 секунд)
sleep 15
```

### 8. Проверка работоспособности

```bash
# Проверьте статус контейнера
docker compose ps

# Должно быть:
# NAME                    STATUS
# sfkt_node_agent        Up (healthy)

# Просмотрите логи node agent
docker compose logs -f

# В логах должны быть:
# - "Starting Node Agent..."
# - "Node registered successfully" или "Node updated successfully"
# - "✓ Synced traffic for X users" (каждые 30 секунд)
# - "✓ Health check sent successfully" (каждые 60 секунд)
# - "✓ User sync complete: added X, removed Y" (каждые 60 секунд)

# Проверьте логи Xray на хосте
sudo journalctl -u xray -f
```

Если вы видите сообщение "Node registered successfully", нода успешно подключилась к главному серверу!

## Компоненты

### Xray-core (на хосте)
- **Установка**: systemd сервис (`xray.service`)
- **Протокол**: VLESS с REALITY (xtls-rprx-vision flow)
- **Маскировка**: SNI под vk.com, vkvideo.ru, vk.video
- **Порт**: 443 (HTTPS)
- **Stats API**: localhost:10085 (для node agent)
- **Конфигурация**: `/usr/local/etc/xray/config.json`
- **Бинарный файл**: `/usr/local/bin/xray`
- **Логи**: `/var/log/xray/` и journalctl

### Node Agent (в Docker)
- Регистрация на главном сервере при старте
- Синхронизация пользователей каждые 60 секунд (чтение из главного сервера, запись в config.json)
- Синхронизация трафика каждые 30 секунд (через Xray CLI stats API)
- Health checks каждые 60 секунд
- Отправка метрик (CPU, Memory, Connections)
- Управление конфигурацией Xray (добавление/удаление пользователей)
- Перезагрузка Xray при изменениях через `systemctl reload xray`

## Управление

### Управление Xray (на хосте)

```bash
# Запуск
sudo systemctl start xray

# Остановка
sudo systemctl stop xray

# Перезапуск (обрывает существующие соединения)
sudo systemctl restart xray

# Перезагрузка конфигурации (после изменений в config.json)
sudo systemctl reload xray

# Статус
sudo systemctl status xray

# Логи
sudo journalctl -u xray -f

# Проверка конфигурации
sudo xray run -test -config /usr/local/etc/xray/config.json
```

### Управление Node Agent (Docker)

```bash
# Просмотр логов
docker compose logs -f

# Перезапуск
docker compose restart

# Остановка
docker compose down

# Запуск
docker compose up -d
```

### Обновление

```bash
# Обновление кода
git pull

# Перезапуск node agent
docker compose down
docker compose up -d --build

# Если обновилась версия Xray, переустановите
cd scripts
sudo ./install_xray_host.sh
sudo systemctl restart xray
```

## Безопасность

1. **Firewall**: Откройте только порт 443
2. **API Key**: Используйте сильный NODE_API_KEY
3. **Обновления**: Регулярно обновляйте Xray и систему

## Мониторинг

Нода отправляет метрики на главный сервер:
- CPU usage
- Memory usage
- Active connections
- Traffic statistics
- Availability status

## Troubleshooting

### Node Agent не регистрируется

Если в логах ошибка "Failed to register node" или "401 Unauthorized":

```bash
# 1. Проверьте доступность главного сервера
curl https://sfkt.mxl.wtf/api/health

# Должен вернуть: {"status":"ok"}

# 2. Проверьте правильность NODE_API_KEY в .env
# Он должен совпадать с NODE_API_SECRET на главном сервере
docker compose exec node-agent env | grep NODE_API_KEY

# 3. Посмотрите детальные логи агента
docker compose logs -f
```

### Xray не запускается

Если Xray сервис не активен:

```bash
# 1. Проверьте статус и логи
sudo systemctl status xray
sudo journalctl -u xray -n 50

# 2. Проверьте конфигурацию на ошибки
sudo xray run -test -config /usr/local/etc/xray/config.json

# 3. Убедитесь, что REALITY ключи правильно вставлены
sudo cat /usr/local/etc/xray/config.json | grep -A2 realitySettings

# 4. Проверьте права доступа
sudo ls -la /usr/local/etc/xray/config.json
# Должно быть: -rw-r--r-- root root
```

### Node Agent не может управлять Xray

Если логи показывают "Failed to reload Xray":

```bash
# 1. Проверьте, что контейнер запущен с privileged: true
docker compose config | grep privileged

# 2. Проверьте монтирование systemd сокетов
docker compose exec node-agent ls -la /var/run/dbus/system_bus_socket
docker compose exec node-agent ls -la /run/systemd

# 3. Проверьте, что node agent может выполнять systemctl
docker compose exec node-agent systemctl status xray
```

### Ошибка генерации ключей "Permission denied"

```bash
# Дайте права на выполнение скрипта
chmod +x scripts/generate_reality_keys.sh

# Запустите снова
./scripts/generate_reality_keys.sh
```

### Порт 443 уже занят

Если другой сервис (nginx, apache) использует порт 443:

```bash
# Проверьте, что занимает порт
sudo ss -tulpn | grep :443

# Если это не xray, остановите конфликтующий сервис
sudo systemctl stop nginx  # или другой сервис

# Затем запустите xray
sudo systemctl start xray
```

### VPN подключение не работает

Если клиент подключается, но нет доступа к интернету:

```bash
# 1. Проверьте, что Xray слушает порт 443
sudo ss -tulpn | grep :443

# 2. Проверьте логи Xray на ошибки
sudo journalctl -u xray -f

# 3. Проверьте, что пользователь добавлен в config.json
sudo cat /usr/local/etc/xray/config.json | jq '.inbounds[0].settings.clients'

# 4. Проверьте firewall
sudo iptables -L -n -v
sudo ufw status  # если используется ufw

# 5. Включите отладку в Xray (временно)
# Отредактируйте config.json: "loglevel": "debug"
sudo nano /usr/local/etc/xray/config.json
sudo systemctl reload xray
sudo journalctl -u xray -f
```

## Связанные репозитории

- Главный проект: https://github.com/mixelka75/sfkt
- Документация: см. README.md в основном репозитории

## Лицензия

См. LICENSE в основном репозитории
