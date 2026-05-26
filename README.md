# hexos-jellyfin

HexOS-branded first-run setup shim for Jellyfin. Wraps the official
`jellyfin/jellyfin` image (the same image the TrueNAS community catalog
uses), holds startup behind a branded setup UI, then hands off to the real
Jellyfin once configuration completes.

This is a shim, not a fork — additive only. We override the entrypoint and
add a thin layer of HexOS automation; the image stays maintained upstream.

## How it works

The official Jellyfin image has no s6-overlay, so the boot sequence is
wrapped via `entrypoint.sh`:

1. **Already configured?** If `/config/config/system.xml` has
   `IsStartupWizardCompleted=true` (or our `/config/.hexos-configured`
   marker exists), exec straight into `/jellyfin/jellyfin`. `/config`
   persists across restarts, so configured servers take this fast path.
2. **First run:** start the Flask setup server (`setup_server.py`) on
   `:8096`. It serves the branded two-screen UI plus stubs for
   `/System/Info/Public` (sentinel `ProductName="HexOS Setup"`) and
   `/health` (so the container's healthcheck passes during setup).
3. The user clicks **Set up Jellyfin**. Flask generates the admin password,
   returns the credentials to the browser, and writes the signal file
   `/tmp/jellyfin-setup-go`.
4. The entrypoint stops Flask, frees `:8096`, spawns the configurator
   (`jellyfin_hook.py`) in the background, and execs into real Jellyfin.
5. The configurator polls until Jellyfin's API is up, then drives the
   startup wizard: admin user → server config → libraries → hardware
   transcoding → complete. It writes the `.hexos-configured` marker and
   exits.
6. The browser polls `/System/Info/Public`, `/Users`, and
   `/Library/VirtualFolders`; when all three pass it shows the credentials
   and redirects to Jellyfin's login.

## Configuration applied

- **Admin user:** `admin` with a random `secrets.token_urlsafe(18)` password
  (shown once in the browser; never logged).
- **Libraries:** Movies (`/movies`), Shows (`/shows`), Music (`/music`).
  Paths that aren't mounted are skipped (graceful degradation).
- **Transcoding:** auto-detected — `qsv` if `/dev/dri/renderD128` exists,
  `nvenc` if `/dev/nvidia*` exists, otherwise `none`.

## Mounts

Mount host paths to `/config`, `/cache`, and the library paths
(`/movies`, `/shows`, `/music`). `/config` must persist.

## Local development

```sh
docker compose up --build
# open http://localhost:8096
```

Reset for a clean first-run test:

```sh
docker compose down && rm -rf data/config data/cache
```

## Image

Published to `ghcr.io/joshualmejia/hexos-jellyfin` by the GitHub Actions
workflow on push to `main` and on tags.

## Branding assets

`static/Urbanist.woff2` and `static/hexostextlogo.svg` are placeholders
(marked with `SWAP:` comments). Drop the real HexOS assets in with the same
filenames; no code changes needed.
