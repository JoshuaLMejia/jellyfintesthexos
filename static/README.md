# static assets

Served by Flask at `/hexos-static/` during first-run setup. Replace these
files in place (same filenames) to rebrand; no code changes needed.

## logo

- `hexostextlogo.svg` — HexOS text logo, shown at the top of both screens.
  Rendered at 34px height (see `.logo` in `templates/index.html`).

## fonts

Urbanist, referenced by `@font-face` in `templates/index.html`:

| file                    | weight |
|-------------------------|--------|
| `Urbanist-Thin.woff`    | 100    |
| `Urbanist-Light.woff`   | 300    |
| `Urbanist-Regular.woff` | 400    |
| `Urbanist-Medium.woff`  | 500    |
| `Urbanist-Bold.woff`    | 700    |

If you swap font formats (e.g. to `.woff2`), update the `src` `url(...)`
and `format(...)` in the `@font-face` blocks accordingly.
