# Conectores de eventos

Los conectores externos de esta beta requieren pruebas con cuentas en
directo. No pegues tokens en chats, capturas, issues ni en el repositorio.
Los botones de **Inicio** muestran el estado y **Registro** muestra errores
sin imprimir las credenciales.

## TikTok LIVE: dos posibilidades

- **TikTok directo**: ejecuta `bash instalar.sh --tiktok` en el clon.
  En Conexiones elige el conector directo e introduce el @usuario que ya esté
  en vivo. Recibe regalos terminados, seguidores y chat (incluye comandos
  que comienzan con `!`). Usa la biblioteca de terceros [TikTokLive](https://github.com/isaackogan/TikTokLive),
  sin solicitar contraseña; el servicio de firma externo puede limitar
  conexiones o romperse. En servidor: `servidor --tiktok directo --canal @usuario`.
- **TikFinity**: activa su [Event API](https://tikfinity.com/) en la máquina
  que corre TikFinity. El bot lee `ws://127.0.0.1:21213/`; en Linux, usa
  un túnel privado desde esa máquina si TikFinity vive en Windows. Por
  ejemplo, desde Windows: `ssh -N -o ExitOnForwardFailure=yes -R 127.0.0.1:21213:127.0.0.1:21213 usuario@servidor`.
  El bot utiliza esa API local, no instala TikFinity. En servidor:
  `servidor --tiktok tikfinity`. No ejecutes ambos conectores para el
  mismo directo simultáneamente.

## Iniciar sesión desde la app

En **Conexiones → Twitch / YouTube**, pulsa **Conectar**. El navegador
predeterminado abre la página oficial del proveedor y el bot recibe la
autorización automáticamente. No introduzcas contraseñas, tokens ni
datos de desarrollador en el bot.

- **Twitch:** elige la cuenta dueña del canal. El bot detecta su ID y
  escucha eventos de lectura (chat, seguidores, suscripciones, bits y
  recompensas según las capacidades del canal).
- **YouTube:** elige la cuenta o canal correcto. El bot busca el directo
  activo más reciente que tenga chat. Recibe chat, Super Chat, Super
  Stickers y nuevas membresías; no ejecuta acciones por el historial.

Si aparece **No habilitado en esta instalación**, al proyecto le falta
aprovisionar un cliente OAuth para esa plataforma. Ese paso lo hace el
mantenedor con la [guía de registro](OAUTH.md), no cada streamer. Si ya
habías configurado el cliente con la beta anterior, el bot todavía puede
usarlo. Los tokens solo existen en memoria; si vencen, vuelve a conectar.

### Servidor sin interfaz

El modo `servidor` conserva las variables de entorno, sin abrir navegador.
Para Twitch usa `--twitch` con `SLB_TWITCH_CLIENT_ID`, `SLB_TWITCH_BROADCASTER_ID`
y `SLB_TWITCH_TOKEN`. Para YouTube usa `--youtube` con `SLB_YOUTUBE_TOKEN`
y `SLB_YOUTUBE_LIVE_CHAT_ID`. Introduce los tokens localmente; evita
dejarlos en el historial de la terminal o en archivos del repositorio.

## Kick (webhook firmado, solo servidor)

1. Instala el extra: `bash instalar.sh --servidor --kick`.
2. Descarga la clave pública PEM **actual** desde el
   [endpoint oficial de Kick](https://api.kick.com/public/v1/public-key)
   y guarda solo la clave pública en un archivo `kick.pem`. Vuelve a
   descargarla y reinicia el bot si Kick la rota.
3. Inicia `~/.local/bin/streamer-linux-bot-server servidor --kick-clave /ruta/kick.pem --kick-canal ID_NUMERICO`.
   Abre exclusivamente `POST /webhooks/kick` mediante un proxy HTTPS con
   límites de solicitudes y tamaño; destino interno `127.0.0.1:8770`.
   No publiques el puerto del catálogo. El receptor verifica la firma,
   vigencia, canal y duplicados.
4. Registra esa URL en tu app de desarrollador Kick y suscribe los
   eventos mediante la [API oficial de eventos](https://github.com/KickEngineering/KickDevDocs/blob/main/events/introduction.md)
   con el permiso `events:subscribe`. El bot **recibe** los webhooks;
   no gestiona OAuth ni registra suscripciones. Eventos soportados:
   `chat.message.sent`, `channel.followed`, `channel.subscription.new`,
   `channel.subscription.renewal` y `kicks.gifted`.

Esta versión solo recibe eventos; no publica mensajes por sí sola.
