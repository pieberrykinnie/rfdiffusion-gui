# rfd-web

The web application package for rfdiffusion-gui.

## Configuration
See `env.example` for environment variables. Uses `uv` for python management. 
Run with `uv run uvicorn rfd_web.app:create_app --factory --host 127.0.0.1 --port 8000`.

## Testing
`uv run pytest` runs the test suite (requires pytest-asyncio and httpx).
