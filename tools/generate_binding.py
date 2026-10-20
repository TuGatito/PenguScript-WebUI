#!/usr/bin/env python3
"""Generate pengu/webui.d.pengu from include/webui.h.

`pengu bind` does the bulk of the translation, but four things in WebUI's
public header need a hand:

  * `enum webui_browser`, `enum webui_runtime` and `enum webui_event` are bare
    C tags (`enum webui_browser { ... };`), not typedefs.  PenguScript's `omen`
    emits a plain `webui_browser` type name, so the binding also includes
    `include/webui_pengu.h`, which adds the missing typedefs.
  * WebUI declares its callbacks as inline function-pointer parameters with no
    named C typedef, so `pengu bind` invents `alias CallbackN ...`; a call site
    would then cast to `webui_CallbackN`, which C does not define.  The aliases
    are inlined into the `declare` signatures instead.
  * `WEBUI_VERSION` follows a value-less `#define _WEBUI_H`, which the
    generator's `#define` scanner swallows; it is restored here.
  * the `link` lines depend on the platform.

Regenerate with:

    python3 tools/generate_binding.py

The committed `include/webui.h` stays authoritative: this script only reads
it.  Set `PENGU` to use a specific CLI binary.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HEADER = os.path.join(ROOT, "include", "webui.h")
OUTPUT = os.path.join(ROOT, "pengu", "webui.d.pengu")
BRIDGE_HEADER = "webui_pengu.h"

# `webui_` (with the underscore) is the insignia: `pengu bind` strips it from
# every C name and `insignia webui_` adds it back, so a consumer writes
# `webui.show` and the C call is `webui_show`.
PREFIX = "webui_"

BANNER = """\
## PenguScript declaration binding for the WebUI C library (include/webui.h).
##
## GENERATED FILE - do not edit by hand. Regenerate with:
##
##     python3 tools/generate_binding.py
##
## which runs
##
##     pengu bind include/webui.h --prefix webui_ --output pengu/webui.d.pengu \\
##         --links webui --cpp-flags=-U__linux__
##
## and then applies what `pengu bind` cannot express for this header: the enum
## tag typedefs from include/webui_pengu.h, inline callback types, the
## WEBUI_VERSION constant and the per-platform link lines.  See
## tools/generate_binding.py for the details.
##
## Consumers use it with:
##
##     import webui
##     var window as size_t is calling webui.new_window
##     calling webui.show with window, "<html><body>Hello</body></html>"
##     calling webui.wait
"""

LINKS = """\
# Native libraries this binding needs. `link` statements propagate to the
# consumer's link line automatically (see docs/BINDINGS.md).
when os == "windows":
    link "webui"
    link "ws2_32"
    link "ole32"
    link "shell32"
    link "user32"
else when os == "linux":
    link "webui"
    link "pthread"
    link "dl"
    link "m"
else:
    link "webui"
"""


def run_bind() -> str:
    """Runs `pengu bind` and returns the generated text."""
    pengu = os.environ.get("PENGU") or shutil.which("pengu")
    if not pengu:
        sys.exit("error: the `pengu` CLI is not on PATH (set PENGU=/path/to/pengu)")

    fd, tmp = tempfile.mkstemp(suffix=".d.pengu")
    os.close(fd)
    try:
        cmd = [
            pengu, "bind", HEADER,
            "--prefix", PREFIX,
            "--output", tmp,
            "--links", "webui",
            # WebUI's Linux block includes dirent.h/poll.h/... which the
            # minimal `pengu bind` stub set does not provide. The declarations
            # we need are outside every platform guard, so skip the block for
            # parsing; the real webui.h still reaches the C compiler through
            # `include`.
            "--cpp-flags=-U__linux__",
            # Never import a sibling binding: this file is the whole webui
            # module.
            "--auto-import=",
        ]
        print("[bind] " + " ".join(cmd), flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0:
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="")
            sys.exit(f"error: pengu bind failed (exit {result.returncode})")
        with open(tmp, encoding="utf-8") as f:
            return f.read()
    finally:
        os.unlink(tmp)


def inline_callback_aliases(text: str) -> str:
    """Replaces `alias CallbackN` with the function-pointer type it names.

    The aliases are dropped because no matching typedef exists in webui.h;
    spelling the type inline makes codegen emit a cast to the real C function
    pointer type (`void (*)(webui_event_t*)`) instead of `webui_CallbackN`.
    """
    aliases = re.findall(r"^alias (Callback\d+) as (.+)$", text, flags=re.MULTILINE)
    for name, target in aliases:
        text = re.sub(rf"^alias {re.escape(name)} as .*\n\n", "", text, flags=re.MULTILINE)
        text = text.replace(f"as {name}", f"as {target.strip()}")
    return text


def restore_version(text: str, header_text: str) -> str:
    """Adds `const WEBUI_VERSION as string is "..."` back to the constants."""
    match = re.search(r'^\s*#\s*define\s+WEBUI_VERSION\s+"([^"]+)"', header_text, flags=re.MULTILINE)
    if not match:
        return text
    version = match.group(1)
    const = f'const WEBUI_VERSION as string is "{version}"'
    if const in text:
        return text
    marker = "# -- Constants (#define) ------------------------------\n\n"
    if marker in text:
        return text.replace(marker, marker + const + "\n", 1)
    # No numeric/string constants were emitted at all.
    return text.replace("link \"webui\"\n", f"link \"webui\"\n\n# -- Constants (#define) ------------------------------\n\n{const}\n", 1)


def apply_fixes(generated: str, header_text: str) -> str:
    text = generated

    # 1. The enum-tag typedefs live next to the real header.
    text = text.replace('include "webui.h"\n',
                        'include "webui.h"\ninclude "webui_pengu.h"\n', 1)

    # 2. Callbacks: no C typedef exists for them.
    text = inline_callback_aliases(text)

    # 3. Restore WEBUI_VERSION.
    text = restore_version(text, header_text)

    # 4. Per-platform link lines replace the single generated `link "webui"`.
    text = text.replace('link "webui"\n', LINKS, 1)

    # 5. Replace the generator banner with the maintenance banner.
    text = re.sub(r"\A## PenguScript declaration binding generated by 'pengu bind'\.\n"
                  r"## Source header: [^\n]*\n",
                  BANNER, text, count=1)
    return text


def main() -> int:
    if not os.path.isfile(HEADER):
        sys.exit(f"error: header not found: {HEADER}")
    with open(HEADER, encoding="utf-8", errors="replace") as f:
        header_text = f.read()

    generated = run_bind()
    if "include \"webui.h\"" not in generated:
        sys.exit("error: unexpected `pengu bind` output (no `include \"webui.h\"` line)")

    text = apply_fixes(generated, header_text)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[bind] wrote {os.path.relpath(OUTPUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
