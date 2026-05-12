# Instalación del bot en Debian

## Requisitos

- Python 3
- `speedtest-cli` (ya debe estar instalado)
- Acceso de root o sudo

## Pasos de instalación

### 1. Copiar el script a `/usr/local/bin/`

```bash
sudo cp homelab-bot.py /usr/local/bin/homelab-bot.py
sudo chmod +x /usr/local/bin/homelab-bot.py
```

### 2. Crear archivo de configuración

Crear `/etc/homelab-bot.env` con tus credenciales:

```bash
sudo cat > /etc/homelab-bot.env << 'EOF'
TELEGRAM_BOT_TOKEN=tu_token_aqui
TELEGRAM_CHAT_ID=tu_chat_id_aqui
EOF
```

Reemplaza:
- `tu_token_aqui` con el token del bot de Telegram
- `tu_chat_id_aqui` con tu ID de chat de Telegram

Asegurar permisos:
```bash
sudo chmod 600 /etc/homelab-bot.env
```

### 3. Instalar el servicio systemd

```bash
sudo cp homelab-bot.service /etc/systemd/system/homelab-bot.service
sudo systemctl daemon-reload
sudo systemctl enable homelab-bot
sudo systemctl start homelab-bot
```

### 4. Verificar que está funcionando

```bash
sudo systemctl status homelab-bot
```

Debería mostrar: `active (running)`

### 5. Ver logs

```bash
sudo journalctl -u homelab-bot -f
```

## Actualizar el bot

Si hay actualizaciones del código:

```bash
# Descargar cambios
git pull origin main

# Copiar nuevo código
sudo cp homelab-bot.py /usr/local/bin/homelab-bot.py

# Reiniciar el servicio
sudo systemctl restart homelab-bot
```

## Comandos disponibles

Envía cualquier mensaje al bot para obtener el estado actual. Comandos específicos:

- `/status` — estado del sistema completo
- `/docker` — detalle de contenedores
- `/bateria` — estado de batería y tiempo restante
- `/procesos` — top 5 procesos por consumo
- `/internet` — velocidad de conexión (speedtest)
- `/temperatura` — estadísticas de temperatura últimas 24h
- `/help` — lista de comandos

## Solución de problemas

**El servicio no inicia:**
```bash
sudo systemctl status homelab-bot
sudo journalctl -u homelab-bot -n 20
```

**Error: "TELEGRAM_BOT_TOKEN not found"**
- Verificar que `/etc/homelab-bot.env` existe y tiene contenido
- Verificar que no hay espacios o caracteres especiales en el token

**Error: "docker: command not found"**
- El bot seguirá funcionando, solo que mostrará error en `/docker`
- Es opcional — no es necesario tener Docker instalado

**Error: "temperature.json: permission denied"**
- El archivo se guarda en `/tmp/temperature.json` (temporal)
- Se limpia automáticamente después de 24h
- Si hay error, revisar permisos de `/tmp/`
