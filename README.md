# DJ Duplicate Finder

Aplicación de escritorio en español para revisar coincidencias de audio y video, comparar copias y mover archivos a cuarentena reversible. La versión estable actual es **v3.0.5**.

## Descargar e instalar

Abre la pestaña **Releases** y descarga `DJ_Duplicate_Finder_v3_Setup.exe`. El instalador incluye Python, la aplicación y FFmpeg/ffprobe. No hace falta instalarlos por separado.

En Windows, la app busca nuevas versiones al abrirse si ya configuraste GitHub. También puedes elegir **Buscar actualizaciones**. La primera vez, crea un token fine-grained para este repositorio privado con permiso **Contents: Read-only** y pégalo en la app. Se guarda en el Administrador de credenciales de Windows. Después, la app descarga el paquete del Release, comprueba el SHA-256 publicado por GitHub y ofrece instalarlo; se cierra y vuelve a abrir al terminar.

Para empezar desde una instalación v3.0.4 o anterior, instala una vez el Setup v3.0.5 sobre la carpeta actual. Las versiones previas no incluyen el actualizador de GitHub.

Este repositorio es privado. Los Releases también requieren iniciar sesión en GitHub con una cuenta que tenga acceso al repositorio.

## Código

- `app.py`: interfaz Tkinter, selección de carpetas, revisión y actualización en Windows.
- `updates.py`: consulta autenticada de Releases privados, Administrador de credenciales y descarga con verificación SHA-256.
- `core.py`: análisis local, hashes, metadatos, firmas de audio, CSV, cuarentena y restauración.
- `tests/`: pruebas del motor de análisis y de las operaciones reversibles.
- `assets/`: iconos y ajuste del icono de la barra de tareas de Windows.
- `build_macos.sh`: kit de compilación para un `.dmg` nativo en Mac. La versión para Mac debe compilarse en macOS.
- `Installer.cs`: instalador de Windows.

Los binarios grandes no se guardan en el historial Git. Los instaladores y paquetes de actualización se publican como archivos en Releases.

## Publicar una actualización

1. Compila la nueva versión y genera el instalador y el ZIP incremental.
2. Crea un Release nuevo con una etiqueta mayor, por ejemplo `v3.0.6`.
3. Adjunta `DJ_Duplicate_Finder_v3_Setup.exe`, `DJ_Duplicate_Finder_v3_Actualizacion.zip` y el checksum SHA-256.
4. Al iniciar, una app ya configurada consulta el Release más reciente. Para instalar, el usuario confirma desde la ventana de la app. Instalaciones nuevas usan el Setup.

No publiques credenciales ni tokens de GitHub en el código ni dentro del instalador.

## Uso y seguridad

El análisis es local. La aplicación no borra archivos de forma permanente: `Mover marcados` utiliza la carpeta `_DJ_DUPLICADOS` y crea un registro para restaurar. Revisa manualmente cada coincidencia y conserva respaldos. Consulta `LEEME_Mac.txt` y `Avisos de terceros.txt` para detalles de plataforma y dependencias.
