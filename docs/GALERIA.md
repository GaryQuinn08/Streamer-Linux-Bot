# Compartir un diseño en la galería

El sitio es estático. El editor funciona sin cuenta y tus cambios se quedan
en tu navegador hasta que tú decidas descargarlos o compartirlos. La galería
muestra diseños revisados: no recibe archivos de forma automática ni ejecuta
el HTML que suban otras personas.

1. Crea tu diseño en el editor y comprueba que funcione con una muestra.
2. En el editor, pulsa **Proponer diseño en GitHub** para abrir una
   solicitud con los ajustes ya escritos; agrega autor, licencia y
   descripción. GitHub te pide iniciar sesión y tú decides si publicarla.
   Un mantenedor incorporará el diseño tras revisarlo. Si prefieres
   enviar el cambio directamente, haz un fork y abre un pull request con
   una entrada en [docs/galeria/designs.json](galeria/designs.json). Usa un
   ID nuevo y corto, texto descriptivo, autor y una licencia que permita
   reutilizar tu diseño (por ejemplo, CC0 si es tuyo y quieres permitirlo).
3. Incluye una captura si ayuda a revisar el diseño.
   No adjuntes cookies, credenciales, conversaciones privadas, imágenes
   ajenas sin permiso ni un archivo de configuración de la aplicación.
4. Un mantenedor revisa el diseño y lo incorpora al catálogo. Una vez
   publicado, cualquiera puede abrirlo en el editor y descargar su copia.

## Campos permitidos

El objeto `preset` acepta solo `mode` (`alert`, `chat`, `events`), nombre,
plantillas de texto (`title`, `body`), colores hexadecimales de seis
dígitos (`accent`, `textColor`, `background`), número de mensajes
(`max`), tamaño (`size`), duración en segundos (`duration`) y opacidad
(`opacity`, porcentaje). Los campos que omitas toman los valores de la
plantilla. No agregues HTML, JavaScript, hojas de estilos ni URL a la
entrada: el editor ya permite personalizar una copia local.

## Si la comunidad crece

- **GitHub Pages + revisión por pull request** es el punto de partida.
  Conserva el código y catálogo en un solo repositorio. La web puede
  mostrar el número de diseños que decidamos publicar, pero no recibe
  registros ni subidas por sí sola.
- **Editor estático + API y almacenamiento** si se requieren perfiles,
  envíos directos, búsqueda y reportes. Por ejemplo, Workers con R2, o un
  servicio de autenticación y almacenamiento como Supabase. Requiere
  moderación, cuotas, respaldo y un mecanismo de retirada. Mantener
  previsualizaciones aisladas: nunca servir HTML de usuarios desde el
  origen del editor.
- **Servidor propio con Docker** si prefieres guardar y moderar todo en
  tu infraestructura. El código del editor y del servicio seguiría en
  este mismo repositorio.
