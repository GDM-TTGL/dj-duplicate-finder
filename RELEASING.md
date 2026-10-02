# Publicación de Releases

Repositorio: `GDM-TTGL/dj-duplicate-finder` (privado).

Para cada versión, sube estos artefactos en GitHub → Releases → Draft a new release:

- instalador completo `.exe` para instalaciones nuevas;
- paquete incremental `DJ_Duplicate_Finder_v3_Actualizacion.zip`, con manifiesto que incluya `version`, `from_versions` y SHA-256 por archivo;
- `CHECKSUM_SHA256` correspondiente.

El actualizador consulta el Release estable más reciente con un token fine-grained de GitHub que tenga acceso al repositorio y permiso `Contents: Read-only`. GitHub devuelve el SHA-256 del adjunto; la aplicación compara el digest antes de abrir el ZIP y vuelve a comprobar los SHA-256 del manifiesto antes de instalar. Conserva el nombre del ZIP definido en `updates.py`.

No añadas los instaladores ni los paquetes grandes al historial Git. Las versiones anteriores a v3.0.5 deben instalar una vez el Setup nuevo; a partir de ahí, la app puede consultar GitHub al abrirse y actualizarse tras la confirmación del usuario.
