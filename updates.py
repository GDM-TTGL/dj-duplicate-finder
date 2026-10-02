"""Secure access to the private GitHub release feed used by the Windows updater."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OWNER = "GDM-TTGL"
REPOSITORY = "dj-duplicate-finder"
API_ROOT = f"https://api.github.com/repos/{OWNER}/{REPOSITORY}"
UPDATE_ASSET = "DJ_Duplicate_Finder_v3_Actualizacion.zip"
CREDENTIAL_TARGET = f"DJ Duplicate Finder/GitHub/{OWNER}/{REPOSITORY}"
MAX_UPDATE_BYTES = 512 * 1024 * 1024


class UpdateError(Exception):
    pass


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),
        ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", ctypes.c_ulong),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", ctypes.c_ulong),
        ("AttributeCount", ctypes.c_ulong),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


def _cred_api():
    if os.name != "nt":
        raise UpdateError("La actualización desde GitHub está disponible en Windows.")
    return ctypes.WinDLL("Advapi32.dll", use_last_error=True)


def load_token() -> str | None:
    api = _cred_api()
    pointer = ctypes.POINTER(_CREDENTIAL)()
    api.CredReadW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
    api.CredReadW.restype = ctypes.c_int
    if not api.CredReadW(CREDENTIAL_TARGET, 1, 0, ctypes.byref(pointer)):
        error = ctypes.get_last_error()
        if error == 1168:  # ERROR_NOT_FOUND
            return None
        raise UpdateError(f"No se pudo leer la credencial de GitHub (Windows {error}).")
    try:
        credential = pointer.contents
        if not credential.CredentialBlob or not credential.CredentialBlobSize:
            return None
        raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return raw.decode("utf-16-le")
    finally:
        api.CredFree.argtypes = [ctypes.c_void_p]
        api.CredFree(pointer)


def save_token(token: str) -> None:
    token = token.strip()
    if not token or len(token) > 2048:
        raise UpdateError("El token de GitHub no es válido.")
    api = _cred_api()
    raw = token.encode("utf-16-le")
    blob = ctypes.create_string_buffer(raw)
    credential = _CREDENTIAL()
    credential.Type = 1  # CRED_TYPE_GENERIC
    credential.TargetName = CREDENTIAL_TARGET
    credential.CredentialBlobSize = len(raw)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE (scoped to current Windows user)
    credential.UserName = OWNER
    api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), ctypes.c_ulong]
    api.CredWriteW.restype = ctypes.c_int
    if not api.CredWriteW(ctypes.byref(credential), 0):
        raise UpdateError(f"Windows no pudo guardar la credencial ({ctypes.get_last_error()}).")


def _api_json(token: str) -> dict:
    request = urllib.request.Request(
        f"{API_ROOT}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "DJ-Duplicate-Finder-Updater",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            if response.status != 200:
                raise UpdateError(f"GitHub respondió con el estado {response.status}.")
            content = response.read(2 * 1024 * 1024 + 1)
            if len(content) > 2 * 1024 * 1024:
                raise UpdateError("La respuesta de GitHub excede el tamaño esperado.")
            release = json.loads(content.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise UpdateError("GitHub rechazó el acceso. Revisa el token y que tu cuenta tenga acceso al repositorio privado.") from exc
        raise UpdateError(f"GitHub no pudo consultar el Release (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(f"No se pudo conectar con GitHub: {exc}") from exc
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        raise UpdateError("GitHub no devolvió un Release estable válido.")
    return release


def get_latest_release(token: str) -> dict:
    release = _api_json(token)
    assets = release.get("assets", [])
    asset = next((item for item in assets if item.get("name") == UPDATE_ASSET and item.get("state") == "uploaded"), None)
    if not asset or not asset.get("url"):
        raise UpdateError("El Release más reciente no contiene el paquete de actualización esperado.")
    digest = asset.get("digest", "")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise UpdateError("GitHub no proporcionó el SHA-256 del paquete; se detuvo la descarga por seguridad.")
    return {"tag_name": release.get("tag_name", ""), "name": release.get("name", ""), "asset": asset}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_update(token: str, asset: dict) -> str:
    parsed_asset_url = urllib.parse.urlparse(str(asset.get("url", "")))
    expected_prefix = f"/repos/{OWNER}/{REPOSITORY}/releases/assets/"
    if parsed_asset_url.scheme != "https" or parsed_asset_url.hostname != "api.github.com" or not parsed_asset_url.path.startswith(expected_prefix):
        raise UpdateError("GitHub devolvió una dirección de paquete inesperada.")
    request = urllib.request.Request(
        asset["url"],
        headers={
            "Accept": "application/octet-stream",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "DJ-Duplicate-Finder-Updater",
        },
    )
    opener = urllib.request.build_opener(_NoRedirect)
    path = None
    try:
        try:
            response = opener.open(request, timeout=30)
        except urllib.error.HTTPError as redirect:
            if redirect.code not in (301, 302, 303, 307, 308):
                raise
            location = redirect.headers.get("Location")
            if not location:
                raise UpdateError("GitHub no devolvió el enlace seguro de descarga.") from redirect
            parsed = urllib.parse.urlparse(location)
            allowed_hosts = {"release-assets.githubusercontent.com", "github-releases.githubusercontent.com", "objects.githubusercontent.com"}
            if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
                raise UpdateError("GitHub devolvió un destino de descarga inesperado.") from redirect
            # This is a short-lived, signed URL; the GitHub token is intentionally not forwarded.
            response = urllib.request.urlopen(urllib.request.Request(location, headers={"User-Agent": "DJ-Duplicate-Finder-Updater"}), timeout=60)
        temporary = tempfile.NamedTemporaryFile(prefix="djdf-github-update-", suffix=".zip", delete=False)
        path = temporary.name
        digest = hashlib.sha256()
        total = 0
        with temporary, response:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > MAX_UPDATE_BYTES:
                    raise UpdateError("El paquete descargado excede el tamaño permitido.")
                digest.update(block)
                temporary.write(block)
        expected = asset.get("digest", "").removeprefix("sha256:").lower()
        if not total or digest.hexdigest().lower() != expected:
            os.unlink(path)
            raise UpdateError("El SHA-256 del paquete no coincide con el Release de GitHub. No se instaló.")
        return path
    except UpdateError:
        if path:
            try: os.unlink(path)
            except OSError: pass
        raise
    except urllib.error.HTTPError as exc:
        if path:
            try: os.unlink(path)
            except OSError: pass
        raise UpdateError(f"GitHub no pudo descargar el paquete (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if path:
            try: os.unlink(path)
            except OSError: pass
        raise UpdateError(f"Falló la descarga desde GitHub: {exc}") from exc
