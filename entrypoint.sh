#!/usr/bin/env bash
# hexos-jellyfin entrypoint wrapper.
# replaces the s6 cont-init mechanism used by the plex shim; the official
# jellyfin image has no s6, so we wrap the entrypoint directly.

set -u

PY=/opt/hexos/venv/bin/python
SIGNAL=/tmp/jellyfin-setup-go
SYSTEM_XML=/config/config/system.xml
LOG=/config/hexos-setup.log

log() { echo "[hexos-jellyfin] $*"; }

# -- fast path: already configured --
# /config persists across restarts (truenas storage); once the wizard is
# done we skip flask entirely and boot straight into jellyfin.
if grep -q '<IsStartupWizardCompleted>true</IsStartupWizardCompleted>' "$SYSTEM_XML" 2>/dev/null; then
  log "already configured, skipping setup"
  exec /jellyfin/jellyfin
fi

if [ -f /config/.hexos-configured ]; then
  log "hexos marker present, skipping setup"
  exec /jellyfin/jellyfin
fi

# -- first run: serve the branded setup ui on :8096 --
log "first run; starting setup server"
rm -f "$SIGNAL"
"$PY" /opt/hexos/setup_server.py &
FLASK_PID=$!

# -- block until the browser triggers handoff via the signal file --
while [ ! -f "$SIGNAL" ]; do
  # bail out if flask died unexpectedly
  if ! kill -0 "$FLASK_PID" 2>/dev/null; then
    log "setup server exited before handoff; starting jellyfin anyway"
    break
  fi
  sleep 1
done

# -- release the port cleanly so jellyfin can re-bind :8096 --
log "handoff signal received; stopping setup server"
kill "$FLASK_PID" 2>/dev/null
wait "$FLASK_PID" 2>/dev/null
sleep 1

# -- spawn the configurator; setsid keeps it alive across the exec below --
log "spawning configurator"
setsid "$PY" /opt/hexos/jellyfin_hook.py >>"$LOG" 2>&1 &

# -- hand off to real jellyfin (takes over as the main process) --
log "starting jellyfin"
exec /jellyfin/jellyfin
