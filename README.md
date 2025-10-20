# SFKT VPN Node Service

VPN node service с Xray-core для SFKT VPN проекта.

## Описание

Этот сервис представляет собой независимую VPN ноду, которая:
- Работает на базе Xray-core с протоколом VLESS/REALITY
- Маскирует трафик под VK Video для обхода блокировок
- Автоматически регистрируется на главном сервере
- Синхронизирует статистику трафика в реальном времени
- Отправляет health checks для мониторинга

## Требования

- Docker и Docker Compose установлены на сервере
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

### 2. Генерация ключей REALITY

```bash
# Сделайте скрипт исполняемым
chmod +x scripts/generate_reality_keys.sh

# Запустите генерацию ключей
# Скрипт автоматически использует Docker для запуска Xray
./scripts/generate_reality_keys.sh
```

Скрипт выведет три значения:
- **Private Key** - приватный ключ для конфигурации Xray на ноде
- **Public Key** - публичный ключ для базы данных главного сервера и клиентов
- **Short ID** - короткий идентификатор для REALITY протокола

**ВАЖНО**: Сохраните эти значения в безопасном месте! Они понадобятся на следующих шагах.

### 3. Настройка Docker Compose

```bash
# Создайте docker-compose.yml из примера
cp docker-compose.example.yml docker-compose.yml

# Отредактируйте конфигурацию
nano docker-compose.yml
```

Заполните все переменные окружения в `docker-compose.yml`:

```yaml
environment:
  # Информация о ноде
  NODE_NAME: "Moscow-1"                    # Название ноды (отображается в админке)
  NODE_HOSTNAME: "moscow1.yourdomain.com"  # Домен ноды (или IP)
  NODE_IP: "1.2.3.4"                       # Публичный IP сервера
  NODE_PORT: "443"                         # Порт для VPN (обычно 443)

  # Геолокация
  NODE_COUNTRY: "Russia"
  NODE_COUNTRY_CODE: "RU"
  NODE_CITY: "Moscow"

  # REALITY ключи (из шага 2)
  REALITY_PRIVATE_KEY: "your-private-key-from-step-2"
  REALITY_PUBLIC_KEY: "your-public-key-from-step-2"
  REALITY_SHORT_ID: "your-short-id-from-step-2"

  # SNI для маскировки (оставьте по умолчанию или измените)
  NODE_SNI: "vk.com"

  # Подключение к главному серверу
  MAIN_SERVER_URL: "https://sfkt.mxl.wtf"  # URL главного сервера
  NODE_API_KEY: "same-as-NODE_API_SECRET-on-main-server"  # API ключ из .env главного сервера
```

**ВАЖНО**: `NODE_API_KEY` на ноде должен совпадать с `NODE_API_SECRET` в `.env` файле главного сервера!

### 4. Создание Docker сети

Нода использует сеть `sfkt_network` для изоляции:

```bash
docker network create sfkt_network
```

### 5. Запуск ноды

```bash
# Запустите контейнер в фоновом режиме
docker compose up -d --build

# Дождитесь загрузки (может занять 1-2 минуты)
sleep 30
```

### 6. Проверка работоспособности

```bash
# Проверьте статус контейнера
docker compose ps

# Должно быть:
# NAME                   STATUS
# sfkt_xray_node        Up (healthy)

# Просмотрите логи
docker compose logs -f

# В логах должны быть:
# - "Xray started successfully"
# - "Node registered successfully" или "Node updated successfully"
# - "Traffic synced successfully" (каждые 30 секунд)
# - "Health check sent successfully" (каждые 60 секунд)
```

Если вы видите сообщение "Node registered successfully", нода успешно подключилась к главному серверу!

## Компоненты

### Xray-core
- **Протокол**: VLESS с REALITY
- **Маскировка**: SNI под vk.com, vkvideo.ru
- **Порт**: 443 (HTTPS)
- **Stats API**: localhost:10085

### Node Agent (Python)
- Регистрация на главном сервере при старте
- Синхронизация трафика каждые 30 секунд
- Health checks каждые 60 секунд
- Отправка метрик (CPU, Memory, Connections)

### Supervisor
Управляет двумя процессами:
- Xray (VPN сервер)
- Node Agent (синхронизация)

## Управление

### Просмотр логов

```bash
# Все логи
docker-compose logs -f

# Только Xray
docker-compose logs -f | grep xray

# Только Agent
docker-compose logs -f | grep node_agent
```

### Перезапуск

```bash
docker-compose restart
```

### Обновление

```bash
git pull
docker-compose down
docker-compose up -d --build
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

### Нода не регистрируется

Если в логах ошибка "Failed to register node" или "401 Unauthorized":

```bash
# 1. Проверьте доступность главного сервера
curl https://sfkt.mxl.wtf/api/health

# Должен вернуть: {"status":"ok"}

# 2. Проверьте правильность NODE_API_KEY
# Он должен совпадать с NODE_API_SECRET на главном сервере
docker compose exec xray-node env | grep NODE_API_KEY

# 3. Посмотрите детальные логи агента
docker compose logs -f
```

### Xray не запускается

Если контейнер постоянно перезапускается:

```bash
# 1. Проверьте логи
docker compose logs xray-node

# 2. Убедитесь, что все REALITY ключи заполнены
docker compose config | grep REALITY

# 3. Проверьте конфигурацию Xray
docker compose exec xray-node cat /etc/xray/config.json
```

### Ошибка "network sfkt_network not found"

```bash
# Создайте сеть вручную
docker network create sfkt_network

# Перезапустите контейнер
docker compose up -d
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

1. Остановите конфликтующий сервис
2. Или измените порт ноды в docker-compose.yml:
   ```yaml
   ports:
     - "8443:443"  # Используйте другой внешний порт
   ```
   И обновите `NODE_PORT: "8443"` в переменных окружения

## Связанные репозитории

- Главный проект: https://github.com/mixelka75/sfkt
- Документация: см. README.md в основном репозитории

## Лицензия

См. LICENSE в основном репозитории
