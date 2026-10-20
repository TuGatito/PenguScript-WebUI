/* webui_pengu.h - PenguScript glue for the WebUI C header.
 *
 * The WebUI public header declares three enums as bare tags:
 *
 *     enum webui_browser { ... };
 *
 * PenguScript resolves an `omen` to a plain C type name, so a variable of
 * type `webui_browser` would be emitted as `webui_browser x;`, which C
 * rejects ("unknown type name; use the enum keyword"). These typedefs give
 * every tag the name the binding emits, without touching webui.h itself.
 */
#ifndef PENGU_WEBUI_PENGU_H
#define PENGU_WEBUI_PENGU_H

#include "webui.h"

typedef enum webui_browser webui_browser;
typedef enum webui_runtime webui_runtime;
typedef enum webui_event webui_event;

#endif /* PENGU_WEBUI_PENGU_H */
