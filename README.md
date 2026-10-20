# PenguScript-WebUI

PenguScript binding for [WebUI](https://webui.me) — use any web browser as a
GUI, with PenguScript in the backend and HTML5 in the frontend.

The binding covers the complete **WebUI 2.5.0-beta.3** C API in
[`include/webui.h`](include/webui.h): all 96 functions, the four enums, the
`webui_event_t` rune and the `WEBUI_VERSION` / `WEBUI_MAX_IDS` /
`WEBUI_MAX_ARG` constants.

## Install

From any PenguScript project:

    pengu add <this-repo-url> --trust

`--trust` is required the first time because `build.py` stages the native
library. It uses, in order: `$WEBUI_LIB`, an archive already in `lib/`, or the
pinned WebUI release for the current OS/arch (downloaded from GitHub). See
[`build.py`](build.py) for the overrides.

## Use

```pengu
import webui

weave on_click with e as ref to webui_event_t into void:
    calling webui.return_string with e, "Hello from PenguScript!"

weave main into int:
    var window as size_t is calling webui.new_window
    calling webui.bind with window, "myFunction", on_click

    var shown as bool is calling webui.show with window, """
        <button onclick="myFunction()">Click me</button>
        <script src="/webui.js"></script>
        """
    if not shown:
        return 1
    calling webui.wait
    return 0
```

A complete, buildable program lives in [`examples/hello.pengu`](examples/hello.pengu).

## API shape

Every C function is reachable with the `webui_` prefix removed, because the
binding sets `insignia webui_`:

| C | PenguScript |
|---|---|
| `webui_new_window()` | `calling webui.new_window` |
| `webui_show(window, html)` | `calling webui.show with window, html` |
| `webui_bind(window, "f", cb)` | `calling webui.bind with window, "f", cb` |
| `webui_set_config(...)` | `calling webui.set_config with ...` |
| `webui_wait()` | `calling webui.wait` |

- **Types** — `webui_browser`, `webui_runtime`, `webui_event`,
  `webui_config` and `webui_event_t` are exported as runes/omens, qualified as
  `webui.webui_event_t` (or imported unqualified).
- **Enum variants** — `webui.Chrome`, `webui.NoBrowser`, `webui.Deno`,
  `webui.WEBUI_EVENT_CONNECTED`, `webui.show_wait_connection`, …
- **Constants** — `webui.WEBUI_VERSION`, `webui.WEBUI_MAX_IDS`,
  `webui.WEBUI_MAX_ARG`.
- **Callbacks** — pass a `weave` whose signature matches the C prototype, e.g.
  `weave handler with e as ref to webui_event_t into void`.
- **C strings** — parameters declared `const char *` are
  `ref to frozen char`; string literals and `let s as ref to frozen char is
  "..."` bindings are accepted directly.

## Regenerate the declarations

`include/webui.h` is authoritative. After replacing it, regenerate the binding
with:

    python3 tools/generate_binding.py

The script runs `pengu bind` with `--prefix webui_` and then applies the four
fixes WebUI's header needs (enum-tag typedefs from `include/webui_pengu.h`,
inline callback types, `WEBUI_VERSION`, per-platform `link` lines); see the
script's docstring for the why. Do not edit `pengu/webui.d.pengu` by hand.

## Structure

```
PenguScript-WebUI/
|-- pengu.toml
|-- build.py                     # stages the native library into lib/
|-- pengu/
|   `-- webui.d.pengu            # generated declarations (include/link/declare)
|-- tools/
|   `-- generate_binding.py      # pengu bind + header-specific fixes
|-- include/
|   |-- webui.h                  # the real C header (authoritative)
|   `-- webui_pengu.h            # enum-tag typedefs for PenguScript
|-- examples/
|   `-- hello.pengu              # minimal browser window + callback
|-- c/                           # optional C glue (empty for this binding)
`-- lib/                         # libwebui.a, staged by build.py
```

The `link "webui"` statements in [`pengu/webui.d.pengu`](pengu/webui.d.pengu)
propagate to the consumer's link line automatically. They are conditional:
`pthread`, `dl` and `m` on Linux, `ws2_32`/`ole32`/`shell32`/`user32` on
Windows. On macOS WebUI also needs the frameworks its own build normally adds
(`-framework Cocoa -framework WebKit`), which `link "..."` cannot express — add
them to your project's `ldflags`. See the PenguScript `docs/BINDINGS.md` for the
full contract.
