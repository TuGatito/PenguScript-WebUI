#!/usr/bin/env python3
"""Stage the native part of the `PenguScript-WebUI` PenguScript binding.

Invoked by `pengu add <repo> --trust` and re-run by `pengu update`. It must
leave the static library in ./lib/ under the name the binding links against
(`link "webui"` -> `-lwebui`), so the consumer's `pengu build` finds it via
`-Llib`.

Where the archive comes from (first hit wins):

    $WEBUI_LIB                 a prebuilt libwebui.a / libwebui-2-static.a
    lib/libwebui.a             already staged by a previous run
    lib/libwebui-2-static.a    an archive copied from a WebUI release
    (download)                 the pinned WEBUI_VERSION release for this OS

The committed include/webui.h is authoritative: it is the header
`pengu bind` generated pengu/webui.d.pengu from, so this script never
overwrites it. The release header is extracted only when include/webui.h is
missing, and the two are compared (a mismatch is reported, not applied).

A prebuilt WebUI system library is also fine for consumers: the binding links
with `-lwebui`, so `-L/usr/local/lib -lwebui` (or a WEBUI_LIB point) works.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(HERE, "lib")
INC_DIR = os.path.join(HERE, "include")

WEBUI_VERSION = os.environ.get("WEBUI_VERSION", "2.5.0-beta.3")
RELEASE_URL = (
    "https://github.com/webui-dev/webui/releases/download/{version}/{asset}"
)

# The archive member that carries the static library inside every release zip.
ARCHIVE_MEMBER = "libwebui-2-static.a"
HEADER_MEMBER = "include/webui.h"

ASSETS = {
    ("Linux", "x86_64"): "webui-linux-gcc-x64.zip",
    ("Linux", "amd64"): "webui-linux-gcc-x64.zip",
    ("Linux", "aarch64"): "webui-linux-gcc-arm64.zip",
    ("Linux", "arm64"): "webui-linux-gcc-arm64.zip",
    ("Linux", "armv7l"): "webui-linux-gcc-arm.zip",
    ("Linux", "armv6l"): "webui-linux-gcc-arm.zip",
    ("Darwin", "x86_64"): "webui-macos-clang-x64.zip",
    ("Darwin", "arm64"): "webui-macos-clang-arm64.zip",
    ("Windows", "AMD64"): "webui-windows-gcc-x64.zip",
    ("Windows", "x86_64"): "webui-windows-gcc-x64.zip",
}


def log(message: str) -> None:
    print("[cbind] " + message, flush=True)


def release_asset() -> str | None:
    """The release archive for this OS/arch, or None when unsupported."""
    override = os.environ.get("WEBUI_ASSET")
    if override:
        return override
    return ASSETS.get((platform.system(), platform.machine()))


def already_staged() -> str | None:
    """Returns an existing archive that can be staged as libwebui.a."""
    env = os.environ.get("WEBUI_LIB")
    if env and os.path.isfile(env):
        return env
    for name in ("libwebui.a", ARCHIVE_MEMBER):
        path = os.path.join(LIB_DIR, name)
        if os.path.isfile(path):
            return path
    return None


def download_release(asset: str) -> tuple[str, bytes | None]:
    """Downloads the release zip; extracts the library, returns (url, header)."""
    url = RELEASE_URL.format(version=WEBUI_VERSION, asset=asset)
    log("downloading " + url)
    fd, tmp = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        with urllib.request.urlopen(url, timeout=120) as response, open(tmp, "wb") as out:
            shutil.copyfileobj(response, out)
    except Exception as exc:  # noqa: BLE001
        os.unlink(tmp)
        raise RuntimeError(f"download failed: {exc}") from exc

    header = None
    try:
        with zipfile.ZipFile(tmp) as archive:
            names = archive.namelist()
            lib_name = next((n for n in names if n.endswith("/" + ARCHIVE_MEMBER)), None)
            hdr_name = next((n for n in names if n.endswith("/" + HEADER_MEMBER)), None)
            if lib_name is None:
                raise RuntimeError(f"{asset} does not contain {ARCHIVE_MEMBER}")
            if hdr_name:
                header = archive.read(hdr_name)
            with archive.open(lib_name) as src, open(
                os.path.join(LIB_DIR, "libwebui.a"), "wb"
            ) as dst:
                shutil.copyfileobj(src, dst)
    finally:
        os.unlink(tmp)
    return url, header


def stage_header(header: bytes | None, url: str) -> None:
    """Installs include/webui.h only when missing; reports a version mismatch."""
    if header is None:
        return
    current = os.path.join(INC_DIR, "webui.h")
    if not os.path.isfile(current):
        os.makedirs(INC_DIR, exist_ok=True)
        with open(current, "wb") as f:
            f.write(header)
        log("extracted include/webui.h")
        return
    with open(current, "rb") as f:
        existing = f.read()
    if existing != header:
        log(
            "note: include/webui.h differs from the "
            + url.rsplit("/", 1)[-1]
            + " header; keeping the committed one (regenerate the binding if you "
            "upgrade WEBUI_VERSION)"
        )


def main() -> int:
    os.makedirs(LIB_DIR, exist_ok=True)
    os.makedirs(INC_DIR, exist_ok=True)

    target = os.path.join(LIB_DIR, "libwebui.a")
    existing = already_staged()
    if existing:
        if os.path.abspath(existing) != os.path.abspath(target):
            shutil.copyfile(existing, target)
            log(f"staged {os.path.relpath(existing, HERE)} -> lib/libwebui.a")
            # `pengu` turns every archive in lib/ into a -l flag, so keeping the
            # release-named input next to the staged copy would link WebUI
            # twice. It is a build artifact (regenerated on demand), not a
            # second library.
            if os.path.abspath(existing) == os.path.abspath(
                os.path.join(LIB_DIR, ARCHIVE_MEMBER)
            ):
                os.unlink(existing)
                log("removed the staging copy; lib/libwebui.a is the only archive")
        else:
            log("lib/libwebui.a is already staged")
        return 0

    asset = release_asset()
    if not asset:
        log(f"no prebuilt WebUI archive for {platform.system()}/{platform.machine()}")
        log("set WEBUI_LIB to a libwebui.a / libwebui-2-static.a, or WEBUI_ASSET "
            "to the release zip name (e.g. webui-linux-gcc-x64.zip)")
        return 1
    try:
        url, header = download_release(asset)
    except RuntimeError as exc:
        log(str(exc))
        log("offline? drop WebUI's libwebui-2-static.a into lib/ or set WEBUI_LIB")
        return 1
    stage_header(header, url)
    log(f"staged WebUI {WEBUI_VERSION} -> lib/libwebui.a")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
