# GeoDE frontend

Run from the repository root with Pixi 0.80.0:

```bash
pixi run -e frontend frontend:build
pixi run -e frontend frontend:install
pixi run -e frontend npm --prefix web/frontend run dev
```

Set `VITE_API_URL` for the backend you are developing against. For native Vite,
export it in the shell; Docker passes it as a build argument from the root `.env`.
The frontend uses Node 22, React, TypeScript, and Vite. `npm ci` uses the committed
package lock. See [web deployment](../../docs/installation/web-interface.md) and
[development checks](../../docs/development/contributing.md).
