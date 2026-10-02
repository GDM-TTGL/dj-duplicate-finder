# DJ Duplicate Finder

Aplicación de escritorio en español para revisar coincidencias de audio y video, comparar copias y mover archivos a cuarentena reversible. La versión estable actual es **v3.0.4**.

## Descargar e instalar

Abre la pestaña **Releases** y descarga **DJ_Duplicate_Finder_v3_Setup.exe**. El instalador incluye Python, la aplicación y FFmpeg/ffprobe. No hace falta instalarlos por separado.

Para actualizar una instalación existente, descarga **DJ_Duplicate_Finder_v3_Actualizacion.zip** desde el Release y, dentro de la app, usa **Aplicar actualización**. La app valida los archivos del paquete antes de instalarlo.

Este repositorio es privado. Los Releases también requieren iniciar sesión en GitHub con una cuenta que tenga acceso al repositorio.

## Código

- app.py: interfaz Tkinter, selección de carpetas, revisión, actualización en Windows.
- core.py: análisis local, hashes, metadatos, firmas de audio, CSV, cuarentena y restauración.
- tests/: pruebas del motor de análisis y de las operaciones reversibles.
- assets/: iconos y ajuste del icono de la barra de tareas de Windows.
- build_macos.sh: kit de compilación para un .dmg nativo en Mac. La versión para Mac debe compilarse en macOS.
- Installer.cs: instalador de Windows.

Los binarios grandes no se guardan en el historial Git. Los instaladores y paquetes de actualización se publican como archivos en Releases.

## Publicar una actualización

1. Compila la nueva versión y genera el instalador y el ZIP incremental.
2. Crea un Release nuevo con una etiqueta mayor, por ejemplo v3.0.5.
3. Adjunta el instalador, el ZIP de actualización y el archivo SHA-256.
4. Quien ya tiene la app descarga el ZIP desde Releases e instala la actualización desde la interfaz. Para instalaciones nuevas, descarga el Setup.

No publiques credenciales ni tokens de GitHub en el código ni dentro del instalador.

## Uso y seguridad

El análisis es local. La aplicación no borra archivos de forma permanente: **Mover marcados** utiliza la carpeta _DJ_DUPLICADOS y crea un registro para restaurar. Revisa manualmente cada coincidencia y conserva respaldos. Consulta LEEME_Mac.txt y Avisos de terceros.txt para detalles de plataforma y dependencias.
