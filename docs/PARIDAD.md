# Diseño funcional: Streamer.bot y TikFinity en Linux

Este inventario compara familias de funciones públicas, no afirma compatibilidad de formatos, APIs, extensiones ni paridad individual con todos los disparadores de terceros. **Beta** significa implementado con pruebas automatizadas; si una cuenta real no se ha probado, se indica.

## Conectar sin panel de desarrollador

| Plataforma | Experiencia de referencia | Decisión para Streamer Linux Bot | Estado |
|---|---|---|---|
| Twitch | Streamer.bot abre OAuth para la cuenta principal; cuenta bot opcional y reconexión automática. | Proveer un Client ID público **del proyecto** en el instalador; OAuth PKCE en navegador. Mostrar la cuenta conectada y, después, separar la cuenta bot y guardar la autorización en el almacén del sistema. | Recepción real confirmada en Linux Mint con un ID configurado. Envío manual con permiso adicional; pendiente probarlo en un canal real. Falta aprovisionar el ID en nuevas instalaciones. No se pide registro individual. |
| YouTube | Streamer.bot abre Google OAuth para la cuenta principal y, opcionalmente, la del bot. | Distribuir un cliente de escritorio del proyecto, consentimientos y permisos de YouTube aprobados según el caso. Probar canales personales y de marca. | Navegador y recepción experimental; no hay cliente de distribución ni prueba real. |
| Kick | Streamer.bot usa OAuth más su integración web para reenviar webhooks. | La instalación normal no debe pedir un servidor público al streamer. Para ofrecerlo, el proyecto necesita un retransmisor HTTPS con firma verificada, asociación por canal y autorización. El receptor autogestionado permanece opcional. | Receptor firmado experimental; no hay vinculación/servicio alojado. |
| TikTok | TikFinity web combina una sesión de su producto con el @usuario del LIVE. Su cliente local ofrece funciones adicionales para escribir en chat y exponer eventos. | Ofrecer **Escuchar LIVE** con el @usuario como modo principal en Linux, indicar si aún no está en vivo, y conservar TikFinity como puente opcional. No tratar la lectura pública como autorización para escribir al chat. | Lectura directa no oficial de chat, seguidores y regalos; prueba real pendiente. No requiere cuenta de TikFinity. |
| Spotify | TikFinity ofrece solicitudes de canciones tras enlazar Spotify. | Separar escucha privada de fuentes autorizadas para retransmitir. No exigir Spotify para instalar, escuchar TikTok ni lanzar alertas. | La beta solo controla una cola privada cuando se configura Spotify. Overlay de título/artista opcional de Spotify de escritorio o servicios web elegidos mediante la extensión del bot. Sin reproducción pública de servicios comerciales ni solicitudes desde el chat. |

Documentación oficial: [Twitch en Streamer.bot](https://docs.streamer.bot/guide/platforms/twitch), [YouTube](https://docs.streamer.bot/guide/platforms/youtube/), [Kick](https://docs.streamer.bot/guide/platforms/kick), [conexión a TikFinity](https://tikfinity.zerody.one/landing/#faq), [PKCE de Twitch](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#pkce-enhanced-authorization-code-grant-flow), [modos de Spotify](https://developer.spotify.com/documentation/web-api/concepts/quota-modes). Los datos de registro del proyecto se mantienen fuera de la interfaz del streamer; ver [guía de mantenimiento](OAUTH.md).

## Qué hay y cómo comprobarlo

| Familia y referencia | En Linux hoy | Qué falta para aproximar la referencia |
|---|---|---|
| [Acciones, colas e historial](https://docs.streamer.bot/guide/core/actions) | Tres paneles, varias reglas por acción, subacciones ordenadas, prueba manual, historial de sesión con duración y resultado, temporizadores periódicos y colas con nombre en orden de llegada. El historial permite pausar nuevos inicios y cancelar ejecuciones. | Grupos de acciones, pausa por cola y reintentos. |
| [Disparadores](https://docs.streamer.bot/api/triggers) y [subacciones](https://docs.streamer.bot/api/sub-actions) | Eventos normalizados, filtros y cooldown por regla. Pasos de sonido, voz, alerta, OBS, espera, audio autorizado y registro; condiciones con dos ramas y llamadas a otras acciones en la misma ejecución. | Valores persistentes, eventos de OBS, temporizadores por actividad de chat y audio avanzado; catalogar por conector antes de añadir tipos sin fuente real. |
| [Comandos](https://docs.streamer.bot/guide/core/commands), [variables](https://docs.streamer.bot/guide/core/variables), [temporizadores](https://docs.streamer.bot/guide/core/timers) y [chat](https://docs.streamer.bot/guide/extra-features/chat/) | Lectura unificada, filtro por plataforma, overlay multichat y envío manual a Twitch. Comandos entrantes con `!`, alias y espera global o por usuario; permisos por rol del chat para Twitch y YouTube, y plantillas del evento. | Respuestas automáticas, envío a otras plataformas, moderación, grupos propios y permisos de rol fuera de Twitch/YouTube, variables globales/por usuario, temporizadores por actividad de chat, citas, créditos e interacciones con espectadores. |
| [Overlays de TikFinity](https://tikfinity.zerody.one/tiktok/obsoverlays) | Catálogo con URL individual para OBS y LIVE Studio, alertas editables/importables, actividad, chat multiplataforma y meta de regalos o seguidores de TikTok. | Metas de likes, monedas y suscripciones, ranking, alertas más ricas, marcos y animaciones. Ya se pueden añadir overlays HTML propios; no se promete importar enlaces alojados de TikFinity. |
| [TikFinity: sonidos, TTS, comunidad y juegos](https://tikfinity.zerody.one/landing/) | Alerta por regalo, sonido y TTS desde acciones; eventos de prueba. | Varias reglas rápidas por regalo, cola de voces con filtros y moderación, puntos y niveles, historial de espectadores, rueda, retos y subatón, controles de juego con permiso explícito. |
| [Aplicaciones y APIs de Streamer.bot](https://docs.streamer.bot/) | OBS cambia escena, visibilidad, volumen, silencio, filtros y reinicia medios; LIVE Studio por fuente Enlace si está disponible; WebSocket de overlays solo local. Perfiles de escritorio y headless en Linux. | Más controles y eventos de OBS (grabación, estado de medios y escenas), Streamlabs, Meld y PolyPop; controladores Stream Deck, MIDI, teclas, voz; API externa autenticada y extensiones aisladas. LIVE Studio por enlace no implica control de escenas. |
| [Intercambio de acciones](https://docs.streamer.bot/guide/core/import-export) | Importación validada de overlays y paquetes nativos de acciones con revisión previa; sus disparadores importados quedan apagados. | Copia/restauración del perfil completo y traducción de formatos de terceros. No ejecutar C# ni macros de paquetes ajenos; traducir solo tipos compatibles cuando exista un importador. |
| [Integraciones de Streamer.bot](https://docs.streamer.bot/guide/integrations) | TikFinity como puente y adaptación a eventos comunes. | Donaciones y servicios externos (p. ej., Ko-fi, StreamElements, Streamlabs), Discord y herramientas para stream. Integrar cada una según sus permisos y API. |

### Prueba rápida de esta beta

1. **Chat → Simular mensaje**. Debe verse como prueba; al elegir TikTok, la muestra Twitch deja de aparecer. Esto no publica nada en un chat.
2. **Acciones → Ejecutar con regalo de prueba → Historial**. Comprueba origen, estado y tiempo. Si un paso falla, **Registro** muestra el motivo.
3. **Overlays → Meta del LIVE**. Elige regalos o seguidores, personaliza título/color y pega el enlace en una fuente de navegador. Prueba el overlay desde la app. La muestra dura unos segundos y no incrementa el contador real. Recargar la fuente no borra el progreso; reiniciar el bot sí.
4. El criterio para anunciar **vinculación lista** es instalar desde Git sin datos previos, pulsar **Conectar**, autorizar en el navegador y observar un mensaje real en **Chat**. No se debe requerir a ese streamer un token, un Client ID ni un panel de desarrollador. La beta todavía no cumple ese criterio para Twitch, YouTube y Kick.
5. Para la meta real, prueba un regalo o seguimiento en un LIVE de TikTok y comprueba que se ve en OBS/LIVE Studio. Las pruebas automáticas no sustituyen esa verificación de servicio.

6. **Overlays → Chat multiplataforma → Probar en OBS** muestra ejemplos marcados como prueba en la fuente de navegador. Puedes seleccionar plataformas, ocultar insignias, ajustar tamaño, líneas visibles, duración, fondo y color de nombres. Los mensajes reales solo se muestran a partir de que abres la fuente: no se reproduce el historial.
7. **Conexiones → Autorizar envío manual al chat de Twitch** permite pedir un permiso adicional al conectar. Luego usa **Chat → Enviar a Twitch** y verifica el resultado en Twitch. Una prueba del overlay o del simulador nunca publica nada en un chat externo.


### Automatización beta 19

1. En **Acciones**, edita dos acciones. Ponles la misma **Cola** (p. ej., `Alertas`). Añade a la primera una espera de 10 segundos. Ejecuta ambas con **Ejecutar con regalo de prueba**. **Historial** debe mostrar la primera **En curso**, la segunda **En espera**. Una acción con otra cola o sin nombre puede avanzar mientras tanto.
2. En **Historial**, pulsa **Pausar nuevas acciones**. Las acciones en curso pueden terminar, pero las pendientes no comienzan hasta reanudar. Selecciona una ejecución y pulsa **Cancelar ejecución** para detenerla. Los efectos ya enviados no se revierten; una solicitud en curso a OBS puede terminar primero. El límite es 16 ejecuciones activas y 128 pendientes; si se llena, se marca **Descartada: cola llena**. Cola e historial se vacían al cerrar el bot.
3. Para usar comandos, crea un disparador con evento `command`; escribe `hola, saludo` en **Alias del comando** y elige **Espera por usuario**. Después de `!hola`, la misma persona tendrá que esperar antes de usar `!saludo`, pero otro usuario puede activarlo si no hay espera global. La espera separa plataformas y compara el nombre recibido, no es un permiso de identidad. El filtro existente **Comando exacto** se conserva y acepta su valor además de los alias.
4. En una fuente de chat ya abierta, guarda el ajuste que oculta el nombre de la plataforma. Continúa recibiendo mensajes y no tienes que pegar otra URL. Las fuentes configuradas para una sola plataforma no amplían su alcance.
5. En **Chat → Probar voz**, verifica que la voz diga «Luna dice…». Con lectura habilitada y una plataforma seleccionada, un mensaje nuevo debe leerse con el nombre que trae su conector.

La beta 20 agrega [condiciones, variables locales y reutilización de acciones](AUTOMATIZACION.md).
La beta 21 añade permisos verificados, más controles de OBS y paquetes de acciones nativos.
Metas adicionales, juegos, puntos, permisos fuera de Twitch/YouTube e integraciones de terceros siguen pendientes.


### Automatización beta 21

- **Disparadores** sirve para buscar el conjunto completo; en **Acciones** se
  edita la misma regla en el contexto de su acción. No se guardan dos copias.
  Selecciona un evento para ver qué conectores lo entregan. Un evento avanzado
  no crea por sí solo una conexión con la plataforma.
- **Quién puede activarlo** puede exigir titular o moderador en chat/comandos
  de Twitch y YouTube. El bot usa los datos del servicio, no el nombre
  visible. Un chat simulado o un rol sin verificar no activa la regla.
  En Twitch Shared Chat tampoco concede roles de otro canal. Prueba con una
  cuenta autorizada y otra normal antes de depender de ello en directo.
- Prueba volumen, silencio, filtros o reinicio de multimedia en una escena
  de prueba: ejecutar la acción en el bot envía el cambio real a OBS.
- En **Acciones → Exportar…** puedes guardar la acción seleccionada y sus
  dependencias en un archivo `.slbactions`. Revisa textos y nombres antes
  de compartirlo. **Importar…** muestra un resumen y crea copias, nunca
  reemplaza el perfil ni ejecuta nada; habilita los disparadores solo después
  de revisarlos. No admite código, archivos locales de audio ni credenciales
  de perfil, ni paquetes de Streamer.bot o TikFinity.
