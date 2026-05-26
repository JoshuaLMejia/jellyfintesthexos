#!/usr/bin/env python3
# hexos-jellyfin setup server.
# serves the branded first-run ui on :8096 until the user clicks "set up".
# on start it generates the admin password, hands the browser the
# credentials, then drops a signal file so the entrypoint hands off to
# real jellyfin. the configurator (jellyfin_hook.py) does the api work.

import json
import os
import secrets
import threading

from flask import Flask, jsonify, render_template, request

# -- config --
ADMIN_USERNAME = "admin"
SIGNAL_FILE = "/tmp/jellyfin-setup-go"
CREDS_FILE = "/tmp/hexos-creds.json"
SENTINEL_PRODUCT = "HexOS Setup"

app = Flask(
    __name__,
    template_folder="/opt/hexos/templates",
    static_folder="/opt/hexos/static",
    static_url_path="/hexos-static",
)

# -- one-shot state --
_lock = threading.Lock()
_state = {"started": False, "username": ADMIN_USERNAME, "password": None}


# -- no-cache everywhere so the browser never serves a stale screen --
@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def _write_creds(username, password):
    # shared with the hook; root-only since the container runs as root.
    with open(CREDS_FILE, "w") as f:
        json.dump({"username": username, "password": password}, f)
    os.chmod(CREDS_FILE, 0o600)


def _signal_handoff():
    # write the signal file only after the response has flushed, so the
    # browser is guaranteed to receive the credentials before the
    # entrypoint kills this process.
    with open(SIGNAL_FILE, "w") as f:
        f.write("go\n")


# -- branded setup ui --
@app.route("/")
def index():
    return render_template(
        "index.html",
        username=_state["username"],
        password=_state["password"] or "",
    )


@app.route("/api/setup/start", methods=["POST"])
def setup_start():
    with _lock:
        if not _state["started"]:
            _state["started"] = True
            _state["password"] = secrets.token_urlsafe(18)  # ~24 chars
            _write_creds(_state["username"], _state["password"])
            # defer the signal so this response reaches the browser first.
            threading.Timer(0.5, _signal_handoff).start()

    return jsonify({"username": _state["username"], "password": _state["password"]})


# -- sentinel stub: lets the browser tell setup-flask from real jellyfin --
@app.route("/System/Info/Public")
def system_info_public():
    return jsonify(
        {
            "ProductName": SENTINEL_PRODUCT,
            "ServerName": SENTINEL_PRODUCT,
            "Version": "0.0.0",
            "Id": "setup",
            "OperatingSystem": "Linux",
            "StartupWizardCompleted": False,
        }
    )


# -- health stub: the base image healthcheck hits /health (plain text) --
@app.route("/health")
def health():
    return "Healthy", 200, {"Content-Type": "text/plain"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8096, threaded=True)
