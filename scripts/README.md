# SFKT Node Scripts

Вспомогательные скрипты для управления VPN нодой.

## xray_config.sh

CLI для управления конфигурацией Xray и обновлением ключей из `.env` файла.

### Использование

```bash
sudo scripts/xray_config.sh <command>
```

### Команды

#### `apply` - Применить конфигурацию (рекомендуется)
Обновляет конфигурацию из .env, проверяет и перезагружает Xray.

```bash
sudo scripts/xray_config.sh apply
```

Это самая часто используемая команда. Выполняет:
1. Загружает переменные из .env
2. Обновляет `/usr/local/etc/xray/config.json`
3. Валидирует конфигурацию
4. Перезагружает Xray сервис

#### `status` - Проверить статус
Показывает статус Xray и конфигурации.

```bash
sudo scripts/xray_config.sh status
```

Выводит:
- Статус Xray сервиса (running/stopped)
- Наличие плейсхолдеров в конфигурации
- Значения переменных из .env
- Проверку порта 443

#### `update` - Обновить конфигурацию
Только обновляет config.json из .env, без перезагрузки.

```bash
sudo scripts/xray_config.sh update
```

#### `validate` - Проверить конфигурацию
Проверяет текущую конфигурацию на ошибки.

```bash
sudo scripts/xray_config.sh validate
```

#### `reload` - Перезагрузить Xray
Перезагружает Xray сервис (применяет изменения в config.json).

```bash
sudo scripts/xray_config.sh reload
```

#### `upgrade` - Обновить Xray
Обновляет Xray binary до последней версии.

```bash
sudo scripts/xray_config.sh upgrade
```

**Внимание:** Останавливает Xray на время обновления.

#### `show` - Показать конфигурацию
Выводит текущую конфигурацию Xray (JSON).

```bash
sudo scripts/xray_config.sh show
```

#### `reset` - Сбросить к шаблону
Восстанавливает конфигурацию из шаблона (создает backup).

```bash
sudo scripts/xray_config.sh reset
```

### Переменные окружения (.env)

Скрипт использует следующие переменные из `.env`:

| Переменная | Обязательно | Описание |
|-----------|-------------|----------|
| `REALITY_PRIVATE_KEY` | Да | Private key для REALITY протокола |
| `REALITY_SHORT_ID` | Да | Short ID для REALITY |
| `NODE_SNI` | Нет | SNI для маскировки (default: vk.com) |
| `NODE_PORT` | Нет | Port для Xray (default: 443) |

### Примеры использования

**Первоначальная настройка:**

```bash
# 1. Установите Xray
sudo scripts/install_xray_host.sh

# 2. Настройте .env файл
nano .env
# Добавьте REALITY_PRIVATE_KEY и REALITY_SHORT_ID

# 3. Примените конфигурацию
sudo scripts/xray_config.sh apply
```

**Изменение REALITY ключей:**

```bash
# 1. Сгенерируйте новые ключи
./scripts/generate_reality_keys.sh

# 2. Обновите .env
nano .env
# Вставьте новые REALITY_PRIVATE_KEY и REALITY_SHORT_ID

# 3. Примените изменения
sudo scripts/xray_config.sh apply
```

**Изменение SNI или порта:**

```bash
# 1. Обновите .env
nano .env
# Измените NODE_SNI или NODE_PORT

# 2. Примените изменения
sudo scripts/xray_config.sh apply
```

**Диагностика проблем:**

```bash
# Проверьте статус
sudo scripts/xray_config.sh status

# Проверьте конфигурацию на ошибки
sudo scripts/xray_config.sh validate

# Посмотрите текущую конфигурацию
sudo scripts/xray_config.sh show | jq '.inbounds[0].streamSettings.realitySettings'

# Проверьте логи Xray
journalctl -u xray -n 50
```

## install_xray_host.sh

Устанавливает Xray на хост систему.

### Использование

```bash
sudo scripts/install_xray_host.sh
```

Выполняет:
- Загружает и устанавливает Xray-core через официальный скрипт
- Создает systemd сервис
- Устанавливает шаблон конфигурации
- Настраивает права доступа

После установки используйте `xray_config.sh apply` для настройки.

## generate_reality_keys.sh

Генерирует REALITY ключи для Xray.

### Использование

```bash
./scripts/generate_reality_keys.sh
```

Выводит:
- Private Key (для сервера)
- Public Key (для клиентов)
- Short ID

**Важно:** Сохраните эти значения в .env файл!

### Пример

```bash
$ ./scripts/generate_reality_keys.sh
Generating REALITY key pair...
Private key: iK4E8gI-owJwANXa1C2-NKwDg2B5dEPLJm9bI0muHmY
Public key: Jh7lE4lIsaVdayyPexymlI5FTjXP0ShlR0Nnt5aNdBk
Short ID: 94b8f34e

# Добавьте в .env:
REALITY_PRIVATE_KEY=iK4E8gI-owJwANXa1C2-NKwDg2B5dEPLJm9bI0muHmY
REALITY_PUBLIC_KEY=Jh7lE4lIsaVdayyPexymlI5FTjXP0ShlR0Nnt5aNdBk
REALITY_SHORT_ID=94b8f34e
```

## Типичные сценарии

### Развертывание новой ноды

```bash
# 1. Установка Xray
sudo scripts/install_xray_host.sh

# 2. Генерация ключей
./scripts/generate_reality_keys.sh

# 3. Настройка .env (вставьте ключи из шага 2)
cp .env.example .env
nano .env

# 4. Применение конфигурации
sudo scripts/xray_config.sh apply

# 5. Запуск node agent
docker compose up -d --build
```

### Ротация ключей

```bash
# 1. Генерация новых ключей
./scripts/generate_reality_keys.sh

# 2. Обновление .env
nano .env

# 3. Применение новых ключей
sudo scripts/xray_config.sh apply

# 4. Обновление публичного ключа в базе данных главного сервера
# (через админ панель или API)
```

### Обновление Xray до новой версии

```bash
# 1. Обновление binary
sudo scripts/xray_config.sh upgrade

# 2. Проверка версии
xray version

# 3. Проверка работоспособности
systemctl status xray
journalctl -u xray -n 20
```

### Восстановление после сбоя

```bash
# 1. Проверка статуса
sudo scripts/xray_config.sh status

# 2. Проверка конфигурации
sudo scripts/xray_config.sh validate

# 3. Если конфигурация повреждена - восстановление
sudo scripts/xray_config.sh reset
sudo scripts/xray_config.sh apply

# 4. Перезапуск при необходимости
systemctl restart xray
```
