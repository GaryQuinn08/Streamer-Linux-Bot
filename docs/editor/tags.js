/* Catálogo de campos que Streamer Linux Bot entrega a los diseños. */
(() => {
  const tag = (key, label, description, example) => ({key, label, description, example});
  const identity = [
    tag("user", "Usuario", "Nombre visible de la persona que originó el evento.", "Luna"),
    tag("platform", "Plataforma", "Origen: twitch, youtube, kick, tiktok o system.", "tiktok"),
  ];
  const type = tag("type", "Tipo de evento", "Tipo normalizado, por ejemplo gift, follow, donation, chat o timer.", "gift");
  const eventType = tag("event_type", "Tipo de evento (alias)", "Alias de {type}.", "gift");
  const body = tag("body", "Mensaje configurado", "Solo en el HTML: inserta lo que escribiste en el control Mensaje.", "¡Gracias!");
  const cardTitle = tag("title", "Título configurado", "Solo en el HTML: inserta lo que escribiste en el control Título.", "Luna");
  const gifts = [
    tag("gift_name", "Regalo", "Nombre del regalo: TikTok o Kicks cuando esté disponible.", "Rose"),
    tag("count", "Cantidad", "Cantidad del regalo o racha final.", "3"),
  ];
  const donations = [
    tag("amount", "Importe", "Importe de la donación, sin símbolo de moneda.", "25"),
    tag("currency", "Moneda", "Código de moneda de la donación.", "MXN"),
  ];
  const demo = tag("simulated", "Prueba", "Indica que el mensaje se generó como muestra en el bot.", "true");
  window.SLB_TAGS = {
    alert: [
      ...identity, type, eventType, ...gifts, ...donations,
      tag("title", "Título", "En el control Título, usa el título de «Mostrar alerta». En el HTML, inserta el título configurado en el editor.", "¡Nuevo regalo!"),
      tag("alert_title", "Título de la acción", "Campo Título de «Mostrar alerta», incluso dentro del HTML.", "¡Nuevo regalo!"),
      tag("alert_text", "Mensaje de la acción (alias)", "Alias explícito de {text} para el mensaje de «Mostrar alerta».", "Gracias por apoyar el directo"),
      tag("text", "Mensaje de la acción", "Texto del campo Mensaje de «Mostrar alerta».", "Gracias por apoyar el directo"),
      tag("image", "URL de imagen de la acción", "Dirección configurada en la acción. La vista segura la trata como texto.", "https://ejemplo.invalid/rosa.png"),
      tag("event_text", "Texto original del evento", "Mensaje de chat, comentario de donación o texto del canje cuando el evento lo incluya.", "¡Qué buen directo!"),
      tag("value", "Valor del evento", "Valor recibido del conector; puede ser importe, bits o valor del regalo según el evento.", "3"),
      tag("command", "Comando", "Comando de chat sin el prefijo !.", "hola"),
      tag("bits", "Bits", "Cantidad de Bits de un cheer de Twitch.", "100"),
      tag("tier", "Nivel de suscripción", "Identificador del nivel devuelto por Twitch.", "1000"),
      tag("reward", "Recompensa", "Nombre de la recompensa canjeada en Twitch.", "Elige una escena"),
      tag("timer", "Temporizador", "Nombre del temporizador que ejecutó la acción.", "Recordatorio"),
      tag("timer_id", "ID del temporizador", "Identificador interno del temporizador.", "demo"),
      tag("interval", "Intervalo", "Segundos configurados en el temporizador.", "60"), demo, body,
    ],
    chat: [
      ...identity, tag("text", "Mensaje", "Texto publicado por la persona en el chat.", "¡Hola, chat!"), demo, cardTitle, body,
    ],
    events: [
      ...identity, type, eventType, ...gifts, ...donations,
      tag("text", "Mensaje de chat", "Texto que el feed entrega en eventos de chat.", "¡Hola, chat!"),
      tag("ts", "Marca de tiempo", "Fecha del evento en segundos Unix.", "1780444800"),
      tag("time", "Hora local", "Hora del evento formateada para mostrar en pantalla.", "20:30"),
      tag("event_label", "Evento en texto", "Descripción breve en español del evento cuando está disponible.", "envió un regalo"),
      cardTitle, body,
    ],
  };
})();
