from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["landing"])


@router.get("/", response_class=HTMLResponse)
def landing_page() -> str:
    return """
<!doctype html>
<html lang="tr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>IK Platform - Test Ortamı</title>
    <style>
      :root {
        color-scheme: light dark;
        font-family: Inter, system-ui, sans-serif;
      }
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #0f172a;
        color: #f8fafc;
      }
      main {
        width: min(720px, calc(100% - 32px));
        padding: 48px;
        border: 1px solid #334155;
        border-radius: 28px;
        background: linear-gradient(145deg, #111827, #1e293b);
        box-shadow: 0 24px 80px rgb(0 0 0 / 0.35);
      }
      .badge {
        display: inline-flex;
        padding: 8px 12px;
        border-radius: 999px;
        background: #2563eb;
        font-size: 14px;
        font-weight: 700;
      }
      h1 {
        font-size: clamp(36px, 7vw, 72px);
        margin: 24px 0 16px;
        line-height: 0.95;
      }
      p {
        color: #cbd5e1;
        font-size: 18px;
        line-height: 1.65;
        max-width: 58ch;
      }
      a { color: #93c5fd; font-weight: 700; }
      .links {
        display: flex;
        gap: 16px;
        flex-wrap: wrap;
        margin-top: 28px;
      }
    </style>
  </head>
  <body>
    <main>
      <span class="badge">Staging / Test Ortamı</span>
      <h1>IK Platform</h1>
      <p>
        Bu sayfa otomatik deploy ve smoke test için hazırlanmış geçici landing page'dir.
        Ürün fonksiyonları eklendikçe bu ekran gerçek test akışına dönüşecek.
      </p>
      <div class="links">
        <a href="/health">Health</a>
        <a href="/docs">API Docs</a>
      </div>
    </main>
  </body>
</html>
"""
