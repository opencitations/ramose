import base64
import json
import shlex

import requests
from IPython.display import IFrame


def call(url, *, method="GET", headers=None, data=None, basic_auth=None, show_headers=False, max_lines=40):
    parts = ["curl"]
    if show_headers:
        parts.append("-i")
    if method != "GET":
        parts += ["-X", method]
    if basic_auth:
        parts += ["-u", f"{basic_auth[0]}:{basic_auth[1]}"]
    if data is not None:
        parts += ["-H", "Content-type: application/json", "--data", json.dumps(data)]
    for key, value in (headers or {}).items():
        parts += ["-H", f"{key}: {value}"]
    parts.append(url)
    print(" ".join(shlex.quote(part) for part in parts), "\n")

    response = requests.request(method, url, headers=headers, json=data, auth=basic_auth, timeout=120)
    print(f"# {response.status_code} {response.reason}")
    if show_headers:
        for key, value in response.headers.items():
            if key.lower() in {"content-type", "link"} or any(token in key.lower() for token in ("total", "count", "page")):
                print(f"# {key}: {value}")
    print()

    if "json" in response.headers.get("Content-Type", ""):
        body = json.dumps(response.json(), indent=2, ensure_ascii=False)
    else:
        body = response.text
    lines = body.splitlines()
    print("\n".join(lines[:max_lines]))
    if len(lines) > max_lines:
        print(f"... ({len(lines) - max_lines} more lines)")


def embed_swagger(spec, *, base_url, height=600):
    page = (
        '<!doctype html><html><head>'
        '<base href="%s">'
        '<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">'
        '</head><body><div id="swagger-ui"></div>'
        '<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>'
        '<script>window.ui = SwaggerUIBundle({spec: %s, dom_id: "#swagger-ui"});</script>'
        '</body></html>' % (base_url, json.dumps(spec))
    )
    src = "data:text/html;base64," + base64.b64encode(page.encode()).decode()
    return IFrame(src, width="100%", height=height)
