# Развертывание VPN ноды SFKT на Production

Пошаговая инструкция по развертыванию VPN ноды SFKT на production сервере.

## Требования к серверу

- **ОС**: Debian 12 или Ubuntu 22.04+
- **RAM**: Минимум 1GB, рекомендуется 2GB+
- **CPU**: 1 vCPU минимум, рекомендуется 2+ vCPU
- **Диск**: Минимум 10GB свободного места
- **Сеть**: Выделенный IP адрес, порт 443 доступен
- **Домен**: Рекомендуется A-запись, указывающая на IP сервера

## Предварительная подготовка

### 1. Обновление системы

```bash
# Подключитесь к серверу по SSH
ssh root@your-server-ip

# Обновите систему
apt update && apt upgrade -y

# Установите необходимые пакеты
apt install -y curl wget git sudo ufw
```

### 2. Настройка firewall

```bash
# Разрешите SSH (важно сделать до включения firewall!)
ufw allow 22/tcp

# Разрешите порт для VPN
ufw allow 443/tcp

# Включите firewall
ufw --force enable

# Проверьте статус
ufw status
```

### 3. Освобождение порта 443 (Остановка nginx/apache)

**ВАЖНО**: Xray должен слушать на порту 443. Если на сервере уже установлен nginx, apache или другой веб-сервер, его нужно остановить и отключить.

```bash
# Проверьте, что слушает на порту 443
sudo ss -tulpn | grep :443

# Если порт занят nginx:
sudo systemctl stop nginx
sudo systemctl disable nginx

# Если порт занят apache2:
sudo systemctl stop apache2
sudo systemctl disable apache2

# Проверьте, что порт свободен
sudo ss -tulpn | grep :443
# Не должно быть никакого вывода
```

**Примечание**: Если вам нужен веб-сервер на этом сервере, настройте его на другой порт (например, 8080) или используйте отдельный сервер для веб-приложений.

### 4. Установка Docker

```bash
# Установите Docker используя официальный скрипт
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Установите Docker Compose
apt install -y docker-compose-plugin

# Проверьте установку
docker --version
docker compose version
```

## Развертывание ноды

### Шаг 1: Клонирование репозитория

```bash
# Создайте директорию для проекта
mkdir -p /opt/sfkt
cd /opt/sfkt

# Клонируйте репозиторий
git clone https://github.com/yourusername/sfkt.git .

# Перейдите в директорию node-service
cd node-service
```

### Шаг 2: Установка Xray на хост

```bash
# Перейдите в директорию скриптов
cd /opt/sfkt/node-service/scripts

# Дайте права на выполнение
chmod +x install_xray_host.sh

# Запустите установку
./install_xray_host.sh
```

**Вывод скрипта:**
```
==========================================
SFKT Node - Xray Host Installation
==========================================
Installing Xray-core...
...
==========================================
Xray installed successfully!
==========================================
Config file: /usr/local/etc/xray/config.json
Binary: /usr/local/bin/xray
Service: xray.service

Next steps:
1. Edit /usr/local/etc/xray/config.json and set REALITY keys
2. Start Xray: systemctl start xray
3. Enable autostart: systemctl enable xray
4. Check status: systemctl status xray
==========================================
```

**Проверка установки:**
```bash
# Проверьте версию Xray
xray version

# Проверьте статус сервиса
systemctl status xray

# Включите автозапуск
systemctl enable xray
```

### Шаг 3: Генерация REALITY ключей

```bash
# Вернитесь в директорию node-service
cd /opt/sfkt/node-service

# Дайте права на выполнение
chmod +x scripts/generate_reality_keys.sh

# Запустите генерацию
./scripts/generate_reality_keys.sh
```

**Пример вывода:**
```
Generating REALITY key pair...
Private key: AABBCCDD...
Public key: EEFFGGHH...
Short ID: 0123456789abcdef
```

**ВАЖНО**: Скопируйте и сохраните эти значения в безопасное место!

- **Private Key** - для конфигурации Xray на сервере
- **Public Key** - для базы данных главного сервера и VPN клиентов
- **Short ID** - для REALITY протокола

### Шаг 4: Настройка конфигурации Xray

**ВАЖНО:** Сначала настройте .env файл (Шаг 5), затем вернитесь сюда.

**Автоматический способ (рекомендуется):**

После настройки .env используйте CLI скрипт:

```bash
cd /opt/sfkt/node-service

# Дайте права на выполнение
chmod +x scripts/xray_config.sh

# Примените конфигурацию из .env
sudo scripts/xray_config.sh apply
```

Скрипт автоматически:
- Загрузит REALITY ключи из .env
- Обновит конфигурацию Xray
- Проверит конфигурацию на ошибки
- Перезагрузит Xray сервис

**Ручной способ:**

```bash
# Откройте конфигурацию Xray
nano /usr/local/etc/xray/config.json
```

Замените плейсхолдеры на реальные значения из шага 3:

1. Найдите `"privateKey": "PRIVATE_KEY_PLACEHOLDER"`
2. Замените на `"privateKey": "ваш-приватный-ключ"`
3. Найдите `"SHORT_ID_PLACEHOLDER"`
4. Замените на ваш Short ID

**Сохраните файл**: Ctrl+O, Enter, Ctrl+X

**Проверьте конфигурацию:**
```bash
xray run -test -config /usr/local/etc/xray/config.json
```

Должно быть: `Configuration OK.`

### Шаг 5: Настройка переменных окружения Node Agent

```bash
# Создайте .env файл из примера
cd /opt/sfkt/node-service
cp .env.example .env

# Отредактируйте .env
nano .env
```

**Заполните все переменные:**

```bash
# === Информация о ноде ===
NODE_NAME=Moscow-Node-1
NODE_HOSTNAME=moscow1.yourdomain.com  # или IP адрес
NODE_IP=45.80.228.195  # публичный IP вашего сервера
NODE_PORT=443

# === Геолокация ===
NODE_COUNTRY=Russia
NODE_COUNTRY_CODE=RU
NODE_CITY=Moscow

# === REALITY ключи (из шага 3) ===
REALITY_PRIVATE_KEY=ваш-приватный-ключ-из-шага-3
REALITY_PUBLIC_KEY=ваш-публичный-ключ-из-шага-3
REALITY_SHORT_ID=ваш-short-id-из-шага-3

# === SNI для маскировки ===
NODE_SNI=vk.com

# === Подключение к главному серверу ===
MAIN_SERVER_URL=https://sfkt.mxl.wtf
NODE_API_KEY=YOUR_NODE_API_SECRET_FROM_MAIN_SERVER

# === Интервалы синхронизации (опционально) ===
SYNC_INTERVAL=30
HEALTH_CHECK_INTERVAL=60
USER_SYNC_INTERVAL=60
INBOUND_TAG=vless-in
```

**КРИТИЧЕСКИ ВАЖНО**:
- `NODE_API_KEY` должен совпадать с `NODE_API_SECRET` в `.env` файле главного сервера!
- Используйте реальный публичный IP адрес в `NODE_IP`
- Если есть домен, используйте его в `NODE_HOSTNAME`, иначе укажите IP

**Сохраните файл**: Ctrl+O, Enter, Ctrl+X

### Шаг 6: Создание docker-compose.yml

```bash
# Создайте docker-compose.yml из примера
cp docker-compose.example.yml docker-compose.yml

# Можете просмотреть содержимое
cat docker-compose.yml
```

Файл должен содержать конфигурацию для node-agent с:
- `network_mode: host` - для доступа к хосту
- `privileged: true` - для управления systemd
- Монтирование `/usr/local/etc/xray` - для управления конфигурацией
- Монтирование systemd сокетов - для `systemctl` команд

### Шаг 7: Запуск Xray

```bash
# Запустите Xray сервис
systemctl start xray

# Проверьте статус
systemctl status xray
```

**Ожидаемый вывод:**
```
● xray.service - Xray Service
     Loaded: loaded (/etc/systemd/system/xray.service; enabled; vendor preset: enabled)
     Active: active (running) since ...
```

**Проверьте, что Xray слушает порт 443:**
```bash
ss -tulpn | grep 443
```

Должно быть: `LISTEN 0 4096 0.0.0.0:443 0.0.0.0:* users:(("xray",...)`

### Шаг 8: Запуск Node Agent

```bash
# Запустите контейнер node-agent
docker compose up -d --build

# Дождитесь запуска (10-15 секунд)
sleep 15

# Проверьте статус
docker compose ps
```

**Ожидаемый вывод:**
```
NAME                    IMAGE                      STATUS
sfkt_node_agent        node-service-node-agent    Up (healthy)
```

### Шаг 9: Проверка работоспособности

**Проверьте логи Node Agent:**
```bash
docker compose logs -f
```

**Ожидаемые сообщения в логах:**
```
Starting Node Agent...
✓ Registered as node XXX
Starting traffic sync loop (interval: 30s)
Starting health check loop (interval: 60s)
Starting user sync loop (interval: 60s)
✓ Health check sent successfully
✓ User sync complete: added 0, removed 0, total 0
```

**Проверьте логи Xray:**
```bash
journalctl -u xray -f
```

**Проверьте подключение к главному серверу:**
```bash
curl https://sfkt.mxl.wtf/api/health
```

Должен вернуть: `{"status":"ok"}`

### Шаг 10: Регистрация ноды на главном сервере

Если NODE_ID не был указан в .env, нода автоматически зарегистрируется при первом запуске.

**Проверка в логах:**
```bash
docker compose logs | grep -i "registered"
```

Должно быть: `✓ Registered as node XXXXXX`

**Сохраните NODE_ID** (необязательно, но рекомендуется для явного указания):
```bash
# Извлеките NODE_ID из логов
docker compose logs | grep "Registered as node" | tail -1

# Добавьте в .env файл (опционально)
echo "NODE_ID=полученный-id" >> .env

# Перезапустите node agent
docker compose restart
```

## Проверка VPN подключения

### Получение subscription URL

Subscription URL генерируется на главном сервере для каждого пользователя. Для тестирования:

1. Войдите в Telegram бот SFKT
2. Нажмите "Настройки" → "Subscription URL"
3. Скопируйте URL (начинается с `vless://`)

### Тестирование подключения

Используйте VPN клиент (v2rayN, v2rayNG, Streisand и т.д.):

1. Добавьте subscription URL в клиент
2. Обновите список серверов
3. Подключитесь к вашей ноде
4. Проверьте доступ к интернету

**Проверка в логах Xray на сервере:**
```bash
# Включите debug логи временно
nano /usr/local/etc/xray/config.json
# Измените "loglevel": "warning" на "loglevel": "debug"

# Перезагрузите конфигурацию
systemctl reload xray

# Смотрите логи
journalctl -u xray -f

# После тестирования верните loglevel обратно на "warning"
```

## Мониторинг

### Проверка статуса сервисов

```bash
# Статус Xray
systemctl status xray

# Статус Node Agent
docker compose ps

# Логи Xray
journalctl -u xray -n 100

# Логи Node Agent
docker compose logs --tail=100

# Использование ресурсов
htop
docker stats
```

### Проверка синхронизации

```bash
# Проверьте, что трафик синхронизируется
docker compose logs | grep "Synced traffic"

# Проверьте, что пользователи синхронизируются
docker compose logs | grep "User sync complete"

# Проверьте health checks
docker compose logs | grep "Health check sent"
```

### Проверка пользователей в Xray

```bash
# Посмотрите текущих пользователей
cat /usr/local/etc/xray/config.json | jq '.inbounds[0].settings.clients'

# Или без jq
cat /usr/local/etc/xray/config.json | grep -A 5 '"clients"'
```

## Обслуживание

### Обновление ноды

```bash
cd /opt/sfkt/node-service

# Получите последние изменения
git pull

# Пересоберите и перезапустите node agent
docker compose down
docker compose up -d --build

# Проверьте логи
docker compose logs -f
```

### Обновление Xray

```bash
cd /opt/sfkt/node-service/scripts

# Переустановите Xray (скачает последнюю версию)
./install_xray_host.sh

# Перезапустите сервис
systemctl restart xray

# Проверьте версию
xray version

# Проверьте статус
systemctl status xray
```

### Резервное копирование

**Важные файлы для бэкапа:**
```bash
# Создайте директорию для бэкапов
mkdir -p /root/backups

# Скопируйте важные файлы
cp /opt/sfkt/node-service/.env /root/backups/
cp /usr/local/etc/xray/config.json /root/backups/
cp /opt/sfkt/node-service/docker-compose.yml /root/backups/

# Создайте архив
tar -czf /root/backups/sfkt-node-backup-$(date +%Y%m%d).tar.gz \
    /opt/sfkt/node-service/.env \
    /usr/local/etc/xray/config.json \
    /opt/sfkt/node-service/docker-compose.yml

# Скачайте бэкап на локальную машину
# (с локальной машины)
scp root@your-server-ip:/root/backups/sfkt-node-backup-*.tar.gz ~/
```

## Troubleshooting

### Xray не запускается

```bash
# Проверьте логи на ошибки
journalctl -u xray -n 50 --no-pager

# Проверьте конфигурацию
xray run -test -config /usr/local/etc/xray/config.json

# Проверьте права доступа
ls -la /usr/local/etc/xray/config.json

# Проверьте, что порт 443 не занят
ss -tulpn | grep :443
```

### Ошибка: "address already in use" или порт 443 занят

**Причина**: Порт 443 уже используется другим сервисом (обычно nginx или apache).

**Решение**:

```bash
# 1. Найдите процесс, занимающий порт 443
sudo ss -tulpn | grep :443
# или
sudo lsof -i :443

# 2. Если это nginx - остановите и отключите его
sudo systemctl stop nginx
sudo systemctl disable nginx
sudo systemctl status nginx  # Должен показать "inactive (dead)"

# 3. Если это apache2 - остановите и отключите
sudo systemctl stop apache2
sudo systemctl disable apache2
sudo systemctl status apache2  # Должен показать "inactive (dead)"

# 4. Убедитесь, что порт свободен
sudo ss -tulpn | grep :443
# Не должно быть вывода

# 5. Запустите Xray
sudo systemctl start xray
sudo systemctl status xray

# 6. Проверьте, что Xray слушает на порту 443
sudo ss -tulpn | grep :443
# Должен показать процесс xray
```

**Альтернатива**: Если вам необходим веб-сервер на этом же сервере, измените порт VPN в .env файле:
```bash
nano /opt/sfkt/node-service/.env
# Измените NODE_PORT=443 на NODE_PORT=8443
```
Затем пересоздайте конфигурацию и не забудьте открыть новый порт в firewall.

### Node Agent не может управлять Xray

```bash
# Проверьте, что контейнер запущен с privileged
docker compose config | grep privileged

# Проверьте монтирование systemd
docker compose exec node-agent ls -la /var/run/dbus/system_bus_socket
docker compose exec node-agent ls -la /run/systemd

# Проверьте, что systemctl работает в контейнере
docker compose exec node-agent systemctl status xray
```

### Нода не регистрируется на главном сервере

```bash
# Проверьте доступность главного сервера
curl -v https://sfkt.mxl.wtf/api/health

# Проверьте NODE_API_KEY в .env
cat .env | grep NODE_API_KEY

# Проверьте, что он совпадает с NODE_API_SECRET на главном сервере

# Проверьте логи node agent
docker compose logs | grep -i "register\|401\|403"
```

### VPN не подключается

```bash
# 1. Проверьте Xray
systemctl status xray
journalctl -u xray -n 50

# 2. Проверьте порт 443
ss -tulpn | grep :443

# 3. Проверьте firewall
ufw status
iptables -L -n -v

# 4. Проверьте, что пользователь добавлен
cat /usr/local/etc/xray/config.json | jq '.inbounds[0].settings.clients'

# 5. Включите debug логи
nano /usr/local/etc/xray/config.json
# Измените "loglevel": "debug"
systemctl reload xray
journalctl -u xray -f

# 6. Проверьте подключение с клиента
# Убедитесь, что используется правильный Public Key из шага 3
```

### Высокая нагрузка на CPU/RAM

```bash
# Проверьте использование ресурсов
htop
docker stats

# Проверьте количество подключений
ss -s
netstat -an | grep :443 | wc -l

# Проверьте логи на аномалии
journalctl -u xray --since "1 hour ago" | grep -i error
docker compose logs --since 1h | grep -i error

# При необходимости перезапустите сервисы
systemctl restart xray
docker compose restart
```

## Безопасность

### Рекомендации по безопасности

1. **Используйте сильные ключи** - не используйте примеры из документации
2. **Регулярно обновляйте систему**: `apt update && apt upgrade`
3. **Минимизируйте открытые порты** - только 22 (SSH) и 443 (VPN)
4. **Используйте SSH ключи** вместо паролей
5. **Настройте fail2ban** для защиты от брутфорса
6. **Мониторьте логи** на подозрительную активность

### Установка fail2ban (опционально)

```bash
# Установите fail2ban
apt install -y fail2ban

# Создайте локальную конфигурацию
cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local

# Включите защиту SSH
nano /etc/fail2ban/jail.local
# Найдите [sshd] и установите enabled = true

# Запустите fail2ban
systemctl enable fail2ban
systemctl start fail2ban

# Проверьте статус
fail2ban-client status sshd
```

## Автоматизация

### Автоматический перезапуск при сбое

Systemd автоматически перезапускает Xray при сбоях (настроено в официальном сервисе).

Docker Compose автоматически перезапускает node-agent (`restart: unless-stopped`).

### Мониторинг с оповещениями

Главный сервер SFKT автоматически мониторит:
- Health checks (каждые 60 секунд)
- Traffic sync (каждые 30 секунд)
- Node availability

При проблемах администратор получит уведомление в Telegram.

## Контакты и поддержка

При возникновении проблем:
1. Проверьте раздел Troubleshooting выше
2. Посмотрите логи: `journalctl -u xray -n 100` и `docker compose logs`
3. Откройте issue на GitHub: https://github.com/yourusername/sfkt/issues
