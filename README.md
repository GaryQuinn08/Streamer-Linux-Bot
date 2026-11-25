# Streamer Linux Bot (v2)

Aplicación de escritorio para Linux que automatiza tu stream: recibe eventos
(chat, seguidores, regalos, donaciones...), los pasa por **triggers** y ejecuta
**acciones** (alertas en pantalla, cambios de escena en OBS, sonidos, TTS...).

## Estado actual

Esto es un **esqueleto funcional**, no el producto terminado.

| Parte | Estado |
|---|---|
| Ventana principal (PySide6) | Funciona: Inicio, Triggers, Acciones, Overlays, Registro |
| Bus de eventos, triggers (filtros y cooldown), acciones | Funciona y tiene pruebas |
| Servidor local de overlays + WebSocket (aiohttp) | Funciona y tiene pruebas |
| Overlays incluidos: alerta de regalos, últimos eventos | Funcionan (sin imagen de vista previa todavía) |
| Importar overlays (.zip o carpeta) con validación | Funciona y tiene pruebas |
| Conector de OBS (obs-websocket) | Escrito, **sin probar contra un OBS real** |
| Twitch, YouTube, Kick, TikTok | **Pendientes** (aparecen como "pendiente de implementar") |
| Editor visual de triggers y acciones | Pendiente (por ahora se edita `config.json`) |
| Música (cola de canciones) y TTS con Piper | Pendiente (hay un TTS básico con espeak-ng) |
| Paquete `.deb` | Pendiente |

## Requisitos

- Ubuntu/Debian con Python 3.12
- Librería del sistema para Qt: `sudo apt install libxcb-cursor0`

## Ejecutar

```bash
cd ~/Documentos/streamer-linux-bot-v2
source .venv/bin/activate
pip install -r requirements.txt     # solo la primera vez
python run.py
```

## Probar que todo funciona

1. Abre la app y ve a **Inicio**.
2. Pulsa **Regalo (TikTok)**: se dispara el trigger "Regalo de TikTok", que
   ejecuta la acción "Alerta de regalo". Verás las líneas en **Registro**.
3. Ve a **Overlays**, elige "Alerta de regalos", pulsa **Abrir en el navegador**
   y vuelve a pulsar un evento de prueba: la tarjeta animada aparece en la página.
4. En OBS: Fuentes → + → Navegador → pega la URL (botón **Copiar URL para OBS**).

Pruebas automáticas:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

## Cómo fluye un evento

```
Conector o botón de prueba (Qt) → Event → EventBus ─┬→ Engine → triggers → acciones
                                                  └→ Actividad → overlay integrado de últimos eventos
Una acción "overlay_alert" envía una alerta solo al overlay seleccionado.
```

## Configuración

`~/.config/streamer-linux-bot/config.json` (se crea al primer arranque).
Contiene ajustes, triggers y acciones. Puede incluir la contraseña de OBS, así
que el archivo se guarda con permisos 600.

Ejemplo de trigger:

```json
{
  "id": "tiktok-rosas",
  "name": "Rosas grandes",
  "platform": "tiktok",
  "event_type": "gift",
  "filters": { "gift_name": "Rose", "min_value": 5 },
  "cooldown_s": 10,
  "action_id": "alert-gift"
}
```

Filtros disponibles: `min_value`, `gift_name`, `user`, `contains` (texto del
mensaje), `command`.

Pasos de acción disponibles: `log`, `wait`, `overlay_alert`, `obs_scene`,
`obs_source_visible`, `play_sound`, `tts`, `music_queue_add` (pendiente),
`chat_message` (pendiente). En los textos puedes usar `{user}`, `{platform}`,
`{type}` y los campos del evento (`{gift_name}`, `{count}`, `{amount}`...).

## Crear tu propio overlay

Crea una carpeta en `~/.local/share/streamer-linux-bot/overlays/<id>/` con:

```
manifest.json   id, name, description y params (opciones editables)
index.html      carga /sdk/overlay-sdk.js y tu script.js
style.css, script.js
```

Copia `slbot/overlays/builtin/gift-alert/` como punto de partida. Dentro del
script usa el SDK:

```js
const color = SLB.param("color", "#ff4d8d");            // opciones desde la URL
SLB.onAlert("mi-overlay", (msg) => { /* msg.title, msg.text */ });
```

El SDK se conecta a `/ws/<id>` según la URL del overlay; las URLs de las fuentes de
navegador en OBS no cambian. Los overlays propios reciben las alertas que las
acciones les dirigen. El feed integrado de últimos eventos es el único
suscriptor de actividad de plataforma, con datos limitados a los campos que
muestra. Si un overlay propio usaba `SLB.onEvent` o se conectaba directamente a
`/ws`, cámbialo para recibir alertas dirigidas con el SDK actualizado.

Regla de seguridad: muestra siempre nombres y mensajes con `textContent`, nunca
con `innerHTML`.

## Seguridad

- El servidor escucha solo en `127.0.0.1` y rechaza peticiones con `Origin` o
  `Host` que no sean locales.
- El servidor de overlays es de lectura: la simulación se inicia desde la ventana nativa.
- Los identificadores de los overlays integrados están reservados.
- Los overlays importados no se ejecutan en un entorno aislado. Ejecutan JavaScript dentro de OBS: importa solo los
  de gente de confianza (la app lo avisa antes de importar).
