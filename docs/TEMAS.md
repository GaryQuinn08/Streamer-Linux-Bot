# Temas y paquetes de overlays

Un **overlay** es una pieza. Un **tema** reúne piezas con el mismo estilo: alerta, multichat, actividad, banner, marco de cámara y pantallas de inicio, pausa y cierre. Puedes descargar un tema completo o solo las piezas que necesites.

Este flujo toma como referencia la [guía de instalación de Streamlabs](https://support.streamlabs.com/hc/en-us/articles/46362056951451-How-to-Add-an-Overlay-to-Your-Stream) y sus [temas de widgets](https://support.streamlabs.com/hc/en-us/articles/25763343552795-What-Are-Widget-Themes-and-How-to-Use-Them). Los 20 temas originales de la colección oficial llevan el crédito de Gary Quinn. No leen archivos `.overlay` de Streamlabs ni instalan colecciones de escenas de OBS.

## Descargar e importar

1. Abre **Galería → Temas completos**. Elige un tema y descarga el pack o una pieza. No se exige cuenta. El contador mide descargas iniciadas, no personas únicas.
2. Con Streamer Linux Bot **0.2.0 beta 11** o posterior, abre **Overlays → Importar tema (.slbpack)…**. Cada pieza aparecerá como entrada separada. No reemplaza tus overlays existentes.
3. Copia las URLs de cada pieza a fuentes **Navegador** de OBS. En **Mostrar alerta**, asigna la pieza de alerta importada. Chat y actividad escuchan sus canales locales. Coloca el marco encima de tu cámara y ajusta el tamaño. La importación no crea ni modifica escenas de OBS.

También puedes descargar una pieza `.html` e importarla como antes. En OBS, usa su URL local desde el bot, no la URL del editor o la galería.

## Armar y compartir

1. Abre **Arma tu tema**. Crea piezas desde cero o carga varios HTML exportados por nuestro editor. Solo se incluye una pieza por tipo.
2. Nombra el pack, ajusta sus textos y colores y descárgalo.
3. En **Mi cuenta**, inicia sesión con Google. Guarda tu alias y, si quieres, una biografía privada. Puedes tener perfil sin publicar nada. Si quieres publicar, pulsa **Convertirme en editor**. No necesitas aprobación.
4. En **Comunidad → Publicar un tema**, elige la licencia y carga el `.slbpack`. El crédito público sale del alias. No se publican el correo ni la biografía.

El `.slbpack` conserva ajustes visuales y animaciones. No contiene HTML, CSS o JavaScript personalizado, imágenes o audio. El sitio y el bot regeneran el HTML. Los HTML personalizados del editor siguen disponibles por separado para uso individual.

## Actualizar desde el repositorio

En la carpeta que ya clonaste:

```bash
git pull --ff-only
bash instalar.sh --tiktok
```

Puedes omitir `--tiktok` si no usas esa integración.
