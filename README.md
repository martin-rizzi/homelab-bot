# homelab-bot

Telegram bot que responde con el estado del sistema Linux. Sin dependencias externas — solo stdlib de Python 3.

## Respuestas

Cualquier mensaje devuelve el estado del sistema. Comandos específicos:

- `/status` — uptime, CPU temp, RAM, disco, batería, load, Docker
- `/docker` — detalle de cada contenedor
- `/help` — lista de comandos

## Variables de entorno

```
TELEGRAM_BOT_TOKEN=<token del bot>
TELEGRAM_CHAT_ID=<chat id autorizado>
```

Solo responde mensajes del `CHAT_ID` configurado.

## Instalación

```bash
cp homelab-bot.py /usr/local/bin/homelab-bot.py
chmod +x /usr/local/bin/homelab-bot.py
```

Servicio systemd (`/etc/systemd/system/homelab-bot.service`):

```ini
[Unit]
Description=Homelab Telegram status bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/homelab-bot.env
ExecStart=/usr/bin/python3 /usr/local/bin/homelab-bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now homelab-bot.service
```

## Compatibilidad

Desarrollado para Debian 12. Lee métricas directamente de `/proc` y `/sys`, por lo que funciona en cualquier Linux sin instalar nada.

La temperatura de CPU busca el sensor `coretemp` en `/sys/class/hwmon`. La batería lee `/sys/class/power_supply/BAT0` — si el sistema no tiene batería, simplemente no aparece en el status.
