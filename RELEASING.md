# Publicación de Releases

Repositorio: `GDM-TTGL/dj-duplicate-finder` (privado).

Para cada versión, sube estos artefactos en GitHub → Releases → Draft a new release:

- instalador completo `.exe` para instalaciones nuevas;
- paquete incremental `.zip` para el botón «Aplicar actualización»;
- `CHECKSUM_SHA256` correspondiente.

No añadas los instaladores al historial Git: el setup supera el límite de tamaño de un archivo Git normal. Al descargar un update privado desde Releases, iniciar sesión con una cuenta autorizada y después elegir ese ZIP en la aplicación.
