# hexos-jellyfin-shim
# branded first-run setup wrapper around the official jellyfin image.
# additive only; we override the entrypoint and hand off to /jellyfin/jellyfin.

FROM jellyfin/jellyfin:latest

# -- python + venv (rarely changes; cache early) --
# the official image is debian trixie with no python; install it.
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv \
 && rm -rf /var/lib/apt/lists/*

# -- venv + flask (the hook uses stdlib only) --
RUN python3 -m venv /opt/hexos/venv \
 && /opt/hexos/venv/bin/pip install --no-cache-dir flask==3.1.0

# -- app code (changes often; copy last) --
COPY setup_server.py jellyfin_hook.py /opt/hexos/
COPY templates/ /opt/hexos/templates/
COPY static/ /opt/hexos/static/
COPY entrypoint.sh /opt/hexos/entrypoint.sh
RUN chmod +x /opt/hexos/entrypoint.sh

ENTRYPOINT ["/opt/hexos/entrypoint.sh"]
