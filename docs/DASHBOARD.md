# Inicio: estado y métricas de tus directos

El panel es privado, dentro de la app. No se añade al overlay público, no inicia
una emisión ni autoriza cuentas por su cuenta. Pulsa **Ir a la conexión** en la
tarjeta para configurar esa plataforma.

- **Conector** describe el enlace del bot: conectado, esperando, escuchando,
  desconectado o con un problema. **En directo** requiere una confirmación
  separada. Puedes estar conectado a Twitch y no estar transmitiendo.
- **Fuera de directo** aparece cuando la plataforma confirma ese estado.
  **Sin confirmar** significa que aún no hay señal, o que caducó. No es un error
  ni equivale a fuera de línea.
- **Espectadores** muestra la última cifra válida. **Pico observado** es el
  máximo que el bot vio en esa conexión; no es el récord oficial de la plataforma.
  No se suma el público entre plataformas: una persona puede estar en dos.
- Los contadores son las interacciones recibidas desde que abriste el bot,
  no estadísticas históricas ni totales del canal. Las pruebas del bot no
  cuentan. Un cero en interacciones significa que el bot no recibió ninguna,
  no que la plataforma no haya registrado esa interacción. «—» en audiencia
  significa que no se pudo obtener esa cifra. Los ingresos de YouTube se
  muestran separados por moneda, sin conversión.

## Qué se detecta en cada plataforma

| Plataforma | Cómo detecta el directo | Métricas que puede recibir |
| --- | --- | --- |
| Twitch | Tras conectar EventSub, consulta [Get Streams](https://dev.twitch.tv/docs/api/reference/#get-streams) cada minuto. | Audiencia, pico observado, título e inicio. Chat, seguidores, subs, bits y canjes según permisos; la tarjeta muestra cuántos tipos de EventSub se activaron. |
| TikTok directo | Conecta tu @usuario en **Conexiones**. Si TikTokLive informa que el canal está fuera de directo o que el LIVE terminó, vuelve a consultar cada 90 segundos mientras no lo desconectes. Si el conector no oficial falla, lo muestra como error en vez de repetir sin límite. | Sala, audiencia y pico cuando llega el dato, chat, seguidores, regalos, diamantes informados, me gusta y compartidos recibidos. |
| TikTok por TikFinity | Abrir el puente no confirma un LIVE. El panel usa el dato de sala `roomUser` de la [Event API de TikFinity](https://staging.tikfinity.com/tiktok/actionsandevents), si está disponible. | Cifra de audiencia y pico, y los eventos que envía el puente. Si no hay datos nuevos de sala, el directo queda sin confirmar. |
| YouTube | Con el navegador autorizado, busca automáticamente un directo activo cada minuto; una vez en vivo, sigue el chat. | Título, inicio, espectadores si [YouTube devuelve la cifra](https://developers.google.com/youtube/v3/docs/videos#liveStreamingDetails), pico, chat, miembros nuevos y Super Chats / Stickers. Un ID manual de chat no indica por sí solo cuál es el video, por lo que no hay cifra de audiencia en ese modo. |
| Kick | Receptor avanzado con [webhook firmado](CONECTORES.md#kick-webhook-firmado). Espera avisos de inicio/fin; si conectas después de iniciar, puede no haber aviso. Pasados cinco minutos, conserva la descripción del último aviso, pero el estado actual queda sin confirmar. | Chat, seguidores, eventos de sub y Kicks recibidos. El webhook de estado no trae espectadores. |

**OBS:** si conectas WebSocket, el panel comprueba la salida de emisión de OBS
y muestra reconexión o cuadros perdidos si la app los informa. Esto no confirma
que la señal haya llegado a una plataforma. El contador de fuentes de overlay
es el número de conexiones al servidor local, no una confirmación de qué se ve
en la escena.

## Prueba rápida, sin empezar un directo público

1. Abre **Inicio**. Sin conectar cuentas, las plataformas deben decir
   **Sin confirmar**; no deben aparecer cifras de espectadores inventadas.
2. Pulsa **Chat y voz (TTS)** para revisar el acceso. Vuelve a Inicio. En
   **Conexiones** prueba **Mensaje de chat** y **Regalo (TikTok)**; no deben
   cambiar los totales de Inicio.
3. Conecta Twitch mientras no emites. Espera la consulta y verifica que el
   conector diga **conectado** y el estado **Fuera de directo**.
4. Cuando vayas a hacer una emisión de prueba, deja Inicio abierto. Comprueba
   que marque **En directo**, que llegue un mensaje y que se actualice la
   audiencia cuando la plataforma la comunique. Al terminar, espera la
   siguiente consulta o el aviso de cierre. Para TikTok, prueba primero en
   modo directo y no conectes también TikFinity para la misma sala.
