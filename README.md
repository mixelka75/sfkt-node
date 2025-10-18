# SFKT VPN Node Service

VPN node service с Xray-core для SFKT VPN проекта.

## Описание

Этот сервис представляет собой независимую VPN ноду, которая:
- Работает на базе Xray-core с протоколом VLESS/REALITY
- Маскирует трафик под VK Video для обхода блокировок
- Автоматически регистрируется на главном сервере
- Синхронизирует статистику трафика в реальном времени
- Отправляет health checks для мониторинга

## Быстрый старт

### 1. Генерация ключей REALITY

```bash
./scripts/generate_reality_keys.sh
```

Сохраните выведенные ключи:
- **Private Key** - для конфигурации Xray
- **Public Key** - для базы данных главного сервера и клиентов
- **Short ID** - для конфигурации

### 2. Настройка

```bash
cp docker-compose.example.yml docker-compose.yml
nano docker-compose.yml
```

Заполните все переменные окружения:

```yaml
environment:
  # Node Info
  NODE_NAME=Moscow-1
  NODE_HOSTNAME=moscow1.yourdomain.com
  NODE_IP=1.2.3.4
  NODE_PORT=443

  # Location
  NODE_COUNTRY=Russia
  NODE_COUNTRY_CODE=RU
  NODE_CITY=Moscow

  # REALITY Keys
  REALITY_PRIVATE_KEY=<your-private-key>
  REALITY_PUBLIC_KEY=<your-public-key>
  REALITY_SHORT_ID=<your-short-id>

  # Main Server
  MAIN_SERVER_URL=https://api.yourdomain.com
  NODE_API_KEY=<same-as-NODE_API_SECRET-in-main-server>
```

### 3. Запуск

```bash
docker-compose up -d
```

### 4. Проверка

```bash
# Логи
docker-compose logs -f

# Статус
docker-compose ps
```

Нода автоматически зарегистрируется на главном сервере.

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

Проверьте:
- Доступность главного сервера: `curl $MAIN_SERVER_URL/health`
- Правильность NODE_API_KEY
- Логи агента: `docker-compose logs node_agent`

### Xray не запускается

Проверьте:
- Валидность конфигурации
- Наличие всех REALITY ключей
- Логи: `docker-compose logs xray`

## Связанные репозитории

- Главный проект: https://github.com/mixelka75/sfkt
- Документация: см. README.md в основном репозитории

## Лицензия

См. LICENSE в основном репозитории
