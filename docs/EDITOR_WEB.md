# Editor web de overlays

El editor vive en `docs/editor/` y la galería revisada en `docs/galeria/`.
No pide una cuenta ni acceso a tus transmisiones. Las muestras son ficticias.
El HTML descargado se vuelve dinámico cuando el bot lo sirve localmente.

## Probar desde el repositorio

Desde la carpeta que clonaste, ejecuta:

```bash
python3 -m http.server 8080 --bind 127.0.0.1 --directory docs
```

Abre `http://127.0.0.1:8080/`. Si el puerto está ocupado, cambia `8080`
por otro libre tanto en el comando como en la URL. No expongas este
servidor de prueba a Internet.

## Importar el diseño en el bot

1. Elige **Alerta**, **Multichat** o **Actividad**, ajusta controles o
   edita el HTML y CSS del diseño y usa la muestra para comprobarlo.
2. Descarga el HTML. Conserva el archivo si quieres una copia local.
3. Abre **Overlays → Importar HTML…** en Streamer Linux Bot y selecciona
   lo que descargaste. Importa solo archivos de confianza.
4. En el catálogo del bot, copia su URL local a una fuente **Navegador**
   de OBS o **Enlace** de LIVE Studio cuando el enlace local sea accesible.
   No pegues la URL de GitHub Pages en OBS: es el editor, no tu overlay.
5. **Alerta:** en la subacción **Mostrar alerta**, escoge como destino
   tu diseño importado. **Multichat y Actividad:** escuchan eventos
   nuevos del bot; no hace falta asignar una acción ni abrir otro overlay.
   No replican el historial.

Usa **Abrir diseño…** en el editor para retomar un archivo exportado por este
estudio. Si vuelves a exportar con el mismo nombre, confirma el reemplazo
al importarlo de nuevo en el bot: así conservas su ID, la URL y el destino
referenciado por las acciones. Si el navegador añadió un sufijo al nombre
(por ejemplo «(1)»), vuelve a ponerle el nombre anterior antes de importarlo.
Después recarga la fuente de OBS para ver el HTML nuevo.

También puedes copiar un enlace de ajustes visuales. Ese enlace no incluye
el HTML/CSS personalizado; comparte el archivo HTML solo si quieres
entregar una copia completa del diseño.

## Qué significan las etiquetas

El catálogo interactivo en el editor muestra los campos admitidos
por cada tipo y un ejemplo. No todos los eventos proporcionan los mismos
valores. Por ejemplo, `{gift_name}` y `{count}` son del regalo; un
seguidor normalmente solo trae `{user}`, `{platform}` y `{type}`.
En una alerta, `{title}` y `{text}` son los datos de **Mostrar alerta**;
`{event_text}` es el texto original del evento si existe. Actualiza la
app a la beta 10 o posterior para que las alertas HTML reciban las
etiquetas del evento además de título y mensaje.

## Publicar con GitHub Pages

Desde la cuenta con permisos del repositorio: **Settings → Pages →
Build and deployment → Deploy from a branch**. Selecciona
`refactor/overlay-boundary`, carpeta `/docs` y guarda. Cuando GitHub
termine, usa la URL que aparece en **Settings → Pages**. Cuando el
editor entre a `main`, puedes cambiar la fuente a `main` y mantener
`/docs`. El sitio no necesita un workflow ni contraseñas.

La publicación por rama y los límites están documentados en [fuentes de
publicación de GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
y [límites de GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).
Para añadir diseños y comparar otras arquitecturas, consulta [Galería](GALERIA.md).

## Aprovechar diseños de Streamlabs u otras plataformas

- **Ya tienes una URL de widget:** pégala directamente en una fuente
  **Navegador** de OBS. El widget sigue ejecutándose en Streamlabs, no
  recibe eventos de Streamer Linux Bot. No compartas la URL en la galería.
  [Instrucciones de Streamlabs](https://streamlabs.com/content-hub/post/how-to-locate-and-use-streamlabs-widget-urls).
- **Quieres una alerta propia en el bot:** abre **Adaptar una alerta de
  Streamlabs** en el editor, elige el evento y pega la **plantilla de
  mensaje**. El editor traduce `{name}` a `{user}` y `{amount}` según
  el evento: importe y moneda en donaciones o `{bits}` en Twitch. Las
  etiquetas sin equivalente se señalan antes de exportar. Usa **Descargar
  HTML → Overlays → Importar HTML…** y selecciona el overlay en la
  subacción de tu evento. No importa escenas, archivos `.overlay`,
  JavaScript, sonidos ni las reglas de Streamlabs.
- **Tienes HTML/CSS propios:** puedes copiar el marcado y estilos
  compatibles a sus pestañas y sustituir las etiquetas de eventos.
  No pegues código privado o diseños que no tienes permiso de reutilizar.
