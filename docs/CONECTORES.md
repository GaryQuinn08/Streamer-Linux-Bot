# Conectores de eventos

Los conectores externos de esta beta requieren pruebas con cuentas en
directo. No pegues tokens en chats, capturas, issues ni en el repositorio.
Los botones de **Inicio** muestran el estado y **Registro** muestra errores
sin imprimir las credenciales.

## TikTok LIVE: dos posibilidades

- **TikTok directo**: ejecuta `bash instalar.sh --tiktok` en el clon.
  En Inicio elige el conector directo e introduce el @usuario que ya esté
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

## Twitch (EventSub)

En la misma terminal en la que abrirás el bot, define
`SLB_TWITCH_CLIENT_ID`, `SLB_TWITCH_BROADCASTER_ID` (ID numérico) y
`SLB_TWITCH_TOKEN` (token OAuth de usuario del propio titular del canal,
sin el prefijo `Bearer`). Requiere una [app propia en Twitch](https://dev.twitch.tv/docs/authentication/register-app/)
y [obtener un token de usuario](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/).
Para no dejar el token en el historial, usa `read -rs SLB_TWITCH_TOKEN; export SLB_TWITCH_TOKEN` en Bash.
Pulsa **Conectar Twitch** o usa `servidor --twitch`.
Los permisos correspondientes son `user:read:chat`,
`moderator:read:followers`, `channel:read:subscriptions`,
`bits:read` y `channel:read:redemptions`. Twitch puede rechazar tipos
individuales según los permisos y capacidades de tu canal.
No hay flujo de inicio de sesión ni renovación automática en la app.

## YouTube (chat en vivo)

Habilita YouTube Data API, obtén un token OAuth de usuario con
`https://www.googleapis.com/auth/youtube.readonly` y el `liveChatId` de un
directo vigente con chat. Exporta `SLB_YOUTUBE_TOKEN` y
`SLB_YOUTUBE_LIVE_CHAT_ID` en la terminal que abra el bot.
Pulsa **Conectar YouTube** o usa `servidor --youtube`. El bot no ejecuta
acciones por chat histórico; comienza con los eventos nuevos. Recibe chat,
Super Chat, Super Stickers y nuevas membresías. Usa el método
[LiveChatMessages: list](https://developers.google.com/youtube/data/live/reference/rest/v3/liveChatMessages/list):
consume cuota del proyecto y no renueva el token.

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
