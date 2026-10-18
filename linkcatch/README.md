# LinkCatch Engine

Python/FastAPI + yt-dlp + FFmpeg + Deno. Intended for one private LinkCatch Site.

## Deploy on Render

Create a Docker web service from this folder. If this folder is `linkcatch` in the repository, set Docker context to `linkcatch` and Dockerfile path to `linkcatch/Dockerfile`. Select the Free plan and set `ENGINE_API_KEY` to at least 32 cryptographically random characters. Set health check path to `/health`.

Configure the Site runtime secrets `ENGINE_URL` (the HTTPS Render origin) and `ENGINE_API_KEY` (same value), then redeploy the Site.

Do not expose the API key to browser code. The Site proxies only fixed API paths, and downloads stream through the proxy. No cookies, browser profiles, login credentials or DRM bypass are used. Public videos may still be restricted by platform anti-bot rules or cloud IP blocks. Supported domains are listed in app.py; actual extractor availability depends on yt-dlp and platform changes.

Jobs are ephemeral with a 30-minute TTL. Restarting the service invalidates jobs. Downloads allow 20-minute videos, 300 MiB total output, two concurrent workers, 8 queued/running jobs and 64 retained job records. Free Render instances may sleep; the frontend displays a wake-up state. This is not a high-volume public service.

Update yt-dlp by rebuilding the Docker image regularly. Dependencies resolve at build time; record the successful deployment versions for repeatable production builds.

## Local

Install FFmpeg and Deno, run `pip install -r requirements.txt`, set `ENGINE_API_KEY`, then `uvicorn app:app --host 127.0.0.1 --port 10000`.
