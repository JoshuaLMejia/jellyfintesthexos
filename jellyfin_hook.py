#!/usr/bin/env python3
# hexos-jellyfin configurator.
# spawned by entrypoint.sh as a background process just before jellyfin
# starts. polls until jellyfin's api is up, then drives the startup wizard:
# admin user, server config, libraries, hardware transcoding, complete.
# stdlib only; logs json lines to stdout (captured to /config/hexos-setup.log).
# never logs the generated password.

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

# -- config --
BASE = "http://127.0.0.1:8096"
CREDS_FILE = "/tmp/hexos-creds.json"
SIGNAL_FILE = "/tmp/jellyfin-setup-go"
MARKER_FILE = "/config/.hexos-configured"
VERSION = "1.0.0"

LIBRARIES = [
    {"name": "Movies", "collectionType": "movies", "path": "/movies"},
    {"name": "Shows", "collectionType": "tvshows", "path": "/shows"},
    {"name": "Music", "collectionType": "music", "path": "/music"},
]

DEVICE_ID = uuid.uuid4().hex


def log(event, **kw):
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "event": event}
    rec.update(kw)
    print(json.dumps(rec), flush=True)


# -- http helpers --
def _request(method, path, body=None, token=None, emby_auth=False):
    url = BASE + path
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
    if token:
        headers["Authorization"] = 'MediaBrowser Token="%s"' % token
    if emby_auth:
        headers["X-Emby-Authorization"] = (
            'MediaBrowser Client="HexOS", Device="Setup", '
            'DeviceId="%s", Version="%s"' % (DEVICE_ID, VERSION)
        )
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        status = resp.status
    parsed = json.loads(raw) if raw else None
    return status, parsed


def get(path, token=None):
    return _request("GET", path, token=token)


def post(path, body=None, token=None, emby_auth=False):
    return _request("POST", path, body=body, token=token, emby_auth=emby_auth)


# -- step 1: wait for the real jellyfin api --
def wait_for_api():
    # gate on /startup/user, not /system/info/public: the public endpoint
    # answers (with the real productname) before the startup-wizard routes
    # are registered, so posting the admin user too early gets a 404.
    # a 200 from /startup/user means the wizard routes are live and the
    # wizard is still open.
    for attempt in range(1, 21):  # 20 tries, 5s apart (~100s)
        try:
            status, _ = get("/Startup/User")
            if status == 200:
                log("api_ready", attempt=attempt)
                return True
            log("api_wait", attempt=attempt, status=status)
        except urllib.error.HTTPError as e:
            # 404 = wizard routes not up yet; 503 = still starting.
            log("api_wait", attempt=attempt, status=e.code)
        except (urllib.error.URLError, OSError) as e:
            # econnrefused during the flask->jellyfin handoff; tolerate it.
            log("api_wait_refused", attempt=attempt, error=str(e))
        time.sleep(5)
    log("api_timeout")
    return False


# -- step 2-3: create admin user --
def set_admin_user(username, password):
    for attempt in range(1, 4):
        try:
            post("/Startup/User", body={"Name": username, "Password": password})
            log("admin_user_set", username=username)
            return True
        except urllib.error.HTTPError as e:
            log("admin_user_error", attempt=attempt, status=e.code)
        except (urllib.error.URLError, OSError) as e:
            log("admin_user_error", attempt=attempt, error=str(e))
        time.sleep(5)
    return False


# -- step 4: server configuration --
def set_configuration():
    body = {
        "UICulture": "en-US",
        "MetadataCountryCode": "US",
        "PreferredMetadataLanguage": "en",
    }
    for attempt in range(1, 4):
        try:
            post("/Startup/Configuration", body=body)
            log("configuration_set")
            return True
        except (urllib.error.URLError, OSError) as e:
            log("configuration_error", attempt=attempt, error=str(e))
        time.sleep(5)
    return False


# -- step 4b: remote access (best effort; the real wizard issues this) --
def set_remote_access():
    body = {"EnableRemoteAccess": True, "EnableAutomaticPortMapping": False}
    try:
        post("/Startup/RemoteAccess", body=body)
        log("remote_access_set")
    except (urllib.error.URLError, OSError) as e:
        log("remote_access_skipped", error=str(e))


# -- step 5: authenticate, mint admin token --
def authenticate(username, password):
    for attempt in range(1, 4):
        try:
            status, data = post(
                "/Users/AuthenticateByName",
                body={"Username": username, "Pw": password},
                emby_auth=True,
            )
            token = (data or {}).get("AccessToken")
            if token:
                log("authenticated")
                return token
            log("authenticate_no_token", attempt=attempt, status=status)
        except (urllib.error.URLError, OSError) as e:
            log("authenticate_error", attempt=attempt, error=str(e))
        time.sleep(5)
    return None


# -- step 6: libraries (skip missing paths; verify; backoff retry) --
def existing_libraries(token):
    try:
        _, data = get("/Library/VirtualFolders", token=token)
        return {lib.get("Name") for lib in (data or [])}
    except (urllib.error.URLError, OSError):
        return set()


def create_libraries(token):
    created = []
    for lib in LIBRARIES:
        if not os.path.isdir(lib["path"]):
            log("library_skipped_no_path", name=lib["name"], path=lib["path"])
            continue

        delay = 5.0
        for attempt in range(1, 11):  # 10 tries, exp backoff capped at 20s
            try:
                qs = (
                    "/Library/VirtualFolders?name=%s&collectionType=%s"
                    "&paths=%s&refreshLibrary=true"
                    % (lib["name"], lib["collectionType"], lib["path"])
                )
                post(qs, body={}, token=token)
            except (urllib.error.URLError, OSError) as e:
                log("library_post_error", name=lib["name"], attempt=attempt, error=str(e))

            # verify it actually persisted (jellyfin sometimes 200s without saving).
            if lib["name"] in existing_libraries(token):
                log("library_created", name=lib["name"])
                created.append(lib["name"])
                break
            log("library_retry", name=lib["name"], attempt=attempt)
            time.sleep(delay)
            delay = min(delay * 1.5, 20.0)
        else:
            log("library_failed", name=lib["name"])
    return created


# -- step 7: hardware transcoding (best effort) --
def detect_gpu():
    if os.path.exists("/dev/dri/renderD128"):
        # intel/amd; qsv is the modern intel path, vaapi the amd path.
        # default to qsv for intel-class igpus; amd users can adjust.
        return "qsv"
    for name in os.listdir("/dev") if os.path.isdir("/dev") else []:
        if name.startswith("nvidia"):
            return "nvenc"
    return "none"


def configure_transcoding(token):
    gpu = detect_gpu()
    try:
        _, enc = get("/System/Configuration/encoding", token=token)
        enc = enc or {}
        if gpu == "none":
            enc["HardwareAccelerationType"] = "none"
            enc["EnableHardwareEncoding"] = False
        else:
            enc["HardwareAccelerationType"] = gpu
            enc["EnableHardwareEncoding"] = True
            if gpu in ("qsv", "vaapi"):
                enc["VaapiDevice"] = "/dev/dri/renderD128"
        post("/System/Configuration/encoding", body=enc, token=token)
        log("transcoding_configured", gpu=gpu)
    except (urllib.error.URLError, OSError) as e:
        log("transcoding_skipped", gpu=gpu, error=str(e))


# -- step 8: complete the wizard --
def complete_wizard():
    for attempt in range(1, 4):
        try:
            post("/Startup/Complete", body={})
            log("wizard_completed")
            return True
        except (urllib.error.URLError, OSError) as e:
            log("complete_error", attempt=attempt, error=str(e))
        time.sleep(5)
    return False


# -- step 9: cleanup --
def cleanup(username):
    try:
        os.remove(SIGNAL_FILE)
    except OSError:
        pass
    try:
        os.remove(CREDS_FILE)
    except OSError:
        pass
    try:
        with open(MARKER_FILE, "w") as f:
            json.dump(
                {
                    "version": VERSION,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "admin_username": username,
                },
                f,
            )
    except OSError as e:
        log("marker_error", error=str(e))


def main():
    log("hook_start")
    try:
        with open(CREDS_FILE) as f:
            creds = json.load(f)
    except OSError as e:
        log("creds_missing", error=str(e))
        return
    username = creds["username"]
    password = creds["password"]

    if not wait_for_api():
        return
    set_admin_user(username, password)
    set_configuration()
    set_remote_access()
    token = authenticate(username, password)
    if not token:
        log("abort_no_token")
        return
    create_libraries(token)
    configure_transcoding(token)
    complete_wizard()
    cleanup(username)
    log("hook_done")


if __name__ == "__main__":
    main()
