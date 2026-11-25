# Streamer Linux Bot (v2)

Aplicación de escritorio para Linux que automatiza tu stream: recibe eventos
(chat, seguidores, regalos, donaciones...), los pasa por **triggers** y ejecuta
**acciones** (alertas en pantalla, cambios de escena en OBS, sonidos, TTS...).

## Beta 0.2.0 para Linux

Esta primera beta está preparada para **Debian 13** (verificada en amd64).
Tiene simulador sin cuenta, dos overlays para OBS, configuración de OBS desde
la ventana, regla editable de regalos con sonido opcional, importación de
overlays y tutorial. Twitch, YouTube, Kick, la cola de música y Piper siguen
pendientes. Los conectores de TikTok son experimentales y no se requieren para
probar la app. La compatibilidad con otras distribuciones aún no se valida.

### Instalar

Descarga el paquete y ejecuta el comando desde la carpeta que lo contiene:

```bash
sudo apt install ./streamer-linux-bot_0.2.0~beta1_all.deb
```

Abre **Streamer Linux Bot** desde el menú o con `streamer-linux-bot`. Para
probar alertas necesitas OBS con **Fuente de navegador** disponible. Para
controlar escenas y fuentes se usa el WebSocket de OBS Studio v5, configurado
en **Inicio**; la contraseña se introduce en cada sesión y no se guarda. El
paquete Debian usa el cliente WebSocket v5 ligero de la app (aiohttp);
el entorno de desarrollo sigue admitiendo `obsws-python`.

### Compilar o ejecutar desde el código

```bash
sh packaging/debian/build.sh                       # genera dist/*.deb
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

### TikTok LIVE experimental

- **TikTok directo (Linux):** requiere instalar el conector de terceros
  [TikTokLive](https://github.com/isaackogan/TikTokLive) en la carpeta de
  dependencias del usuario. No se instala automáticamente, no pide tu
  contraseña y el servicio de firma de terceros puede limitar o interrumpir
  la conexión. En Debian, si decides probarlo:

  ```bash
  sudo apt install python3-venv
  python3 -m venv ~/.local/share/streamer-linux-bot/tiktok-tools
  ~/.local/share/streamer-linux-bot/tiktok-tools/bin/pip install \
    --target "${XDG_DATA_HOME:-$HOME/.local/share}/streamer-linux-bot/tiktok-deps" TikTokLive
  ```

  Reinicia Streamer Linux Bot, elige **TikTok directo** y escribe el @usuario
  que está en directo. La beta procesa chat, seguidores y regalos.
- **TikFinity (Event API local):** usa `ws://127.0.0.1:21213/`. La
  [app oficial de TikFinity](https://tikfinity.com/) ofrece esa API en Windows;
  en Linux, esta opción requiere que ya tengas un puente que exponga la API
  en ese puerto local. La beta no instala el puente.

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
Contiene ajustes, triggers y acciones. El archivo se guarda con permisos
600 y no incluye la contraseña de OBS.

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
