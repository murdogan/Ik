# ruff: noqa: E501

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.api.openapi import PUBLIC_TAG

router = APIRouter(tags=[PUBLIC_TAG])


@router.get(
    "/",
    response_class=HTMLResponse,
    summary="Serve public landing page",
    description=(
        "Serves the public Wealthy Falcon HR landing page HTML for browser requests. This "
        "endpoint is outside the tenant-scoped JSON API surface and does not require tenant "
        "headers."
    ),
    response_description="Public landing page HTML.",
)
def landing_page() -> str:
    return """
<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Wealthy Falcon HR - Hazırlanıyor</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root{--bg:#f6fbf8;--card:#fff;--ink:#17231f;--muted:#66736d;--line:#dfe9e4;--green:#1f7a56;--green2:#35a477;--mint:#dff4e9;--blue:#316bff;--amber:#f4b84a;--shadow:0 24px 70px rgba(28,64,49,.13);--radius:28px}
    *{box-sizing:border-box} body{margin:0;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink);background:radial-gradient(circle at 12% 10%,rgba(53,164,119,.18),transparent 34%),radial-gradient(circle at 90% 6%,rgba(49,107,255,.11),transparent 30%),linear-gradient(180deg,#fbfffd 0%,var(--bg) 62%,#eef7f2 100%);min-height:100vh;overflow-x:hidden}.wrap{max-width:1180px;margin:0 auto;padding:28px 24px 56px}
    nav{display:flex;align-items:center;justify-content:space-between;margin-bottom:52px}.brand{display:flex;align-items:center;gap:12px;font-weight:800;letter-spacing:-.03em;font-size:22px}.logo{width:42px;height:42px;border-radius:14px;background:linear-gradient(135deg,var(--green),var(--green2));display:grid;place-items:center;color:#fff;box-shadow:0 12px 28px rgba(31,122,86,.22)}.navlinks{display:flex;gap:24px;color:var(--muted);font-weight:600;font-size:14px}.navcta{border:1px solid var(--line);background:rgba(255,255,255,.72);padding:12px 16px;border-radius:999px;font-weight:700;color:var(--ink);box-shadow:0 8px 24px rgba(20,40,30,.06)}
    .hero{display:grid;grid-template-columns:1.02fr .98fr;gap:46px;align-items:center}.eyebrow{display:inline-flex;align-items:center;gap:10px;border:1px solid #cfe7dc;background:rgba(255,255,255,.72);padding:9px 13px;border-radius:999px;color:var(--green);font-weight:800;font-size:13px;margin-bottom:18px}.dot{width:8px;height:8px;border-radius:50%;background:var(--green2);box-shadow:0 0 0 6px rgba(53,164,119,.14)}
    h1{font-size:64px;line-height:1.02;margin:0 0 20px;letter-spacing:-.065em;max-width:680px}.lead{font-size:20px;line-height:1.65;color:var(--muted);margin:0 0 28px;max-width:610px}.actions{display:flex;gap:14px;align-items:center;margin:30px 0 30px;flex-wrap:wrap}.btn{border:0;border-radius:18px;padding:16px 22px;font-size:15px;font-weight:800;text-decoration:none;display:inline-flex;align-items:center;gap:10px}.btn.primary{background:var(--green);color:#fff;box-shadow:0 18px 38px rgba(31,122,86,.28)}.btn.secondary{background:#fff;color:var(--ink);border:1px solid var(--line)}
    .trust{display:flex;gap:18px;flex-wrap:wrap;color:var(--muted);font-size:14px;font-weight:600}.trust span{display:flex;gap:8px;align-items:center}.check{color:var(--green);font-weight:900}.product{position:relative}.panel{background:rgba(255,255,255,.82);border:1px solid rgba(223,233,228,.9);border-radius:34px;box-shadow:var(--shadow);padding:18px;backdrop-filter:blur(16px)}.app{background:#fff;border:1px solid var(--line);border-radius:26px;overflow:hidden;min-height:540px}.topbar{height:64px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 20px;background:#fbfdfc}.search{width:230px;height:34px;border-radius:12px;background:#eef6f2;color:#7c8a84;font-size:13px;display:flex;align-items:center;padding-left:12px;font-weight:600}.avatar{width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#233,#6fa)}
    .appbody{display:grid;grid-template-columns:152px 1fr;min-height:476px}.side{border-right:1px solid var(--line);padding:18px 12px;background:#fcfefd}.side div{height:36px;border-radius:12px;margin-bottom:8px;padding:10px;color:#708078;font-size:12px;font-weight:700}.side .active{background:var(--mint);color:var(--green)}.main{padding:22px;background:linear-gradient(180deg,#fff 0%,#fbfdfc 100%)}.dashhead{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}.dashhead h3{margin:0;font-size:22px;letter-spacing:-.04em}.dashhead p{margin:6px 0 0;color:var(--muted);font-size:13px}.pill{background:#edf7f1;color:var(--green);padding:9px 11px;border-radius:999px;font-size:12px;font-weight:800}
    .cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px}.metric{border:1px solid var(--line);border-radius:18px;padding:14px;background:#fff}.metric b{display:block;font-size:24px;letter-spacing:-.04em}.metric span{font-size:12px;color:var(--muted);font-weight:700}.wide{display:grid;grid-template-columns:1.1fr .9fr;gap:12px}.box{border:1px solid var(--line);border-radius:20px;background:#fff;padding:16px}.box h4{margin:0 0 12px;font-size:14px}.row{display:flex;align-items:center;justify-content:space-between;border-top:1px solid #eef2ef;padding:12px 0;color:#56645e;font-size:13px;font-weight:600}.row:first-of-type{border-top:0}.tag{font-size:11px;border-radius:999px;padding:6px 8px;background:#f2f6f4;color:#66736d}.tag.green{background:#e2f5eb;color:var(--green)}.tag.amber{background:#fff3d7;color:#9a6500}
    .floating{position:absolute;right:-22px;bottom:40px;background:#17231f;color:white;border-radius:22px;padding:18px 20px;box-shadow:0 22px 48px rgba(23,35,31,.22);width:246px}.floating b{font-size:34px;letter-spacing:-.05em}.floating p{margin:6px 0 0;color:#c9d6d0;font-size:13px;line-height:1.45}.features{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:54px}.feature{background:rgba(255,255,255,.72);border:1px solid var(--line);border-radius:24px;padding:22px}.feature h3{margin:0 0 8px;font-size:17px}.feature p{margin:0;color:var(--muted);line-height:1.55;font-size:14px}.icon{width:38px;height:38px;border-radius:14px;display:grid;place-items:center;background:var(--mint);margin-bottom:14px;color:var(--green);font-weight:900}
    @media(max-width:900px){.hero{grid-template-columns:1fr}h1{font-size:46px}.navlinks{display:none}.features{grid-template-columns:1fr}.cards,.wide{grid-template-columns:1fr}.floating{position:static;width:auto;margin-top:16px}.appbody{grid-template-columns:1fr}.side{display:none}}
  </style>
</head>
<body>
  <div class="wrap">
    <nav>
      <div class="brand"><div class="logo">WF</div><span>Wealthy Falcon HR</span></div>
      <div class="navlinks"><span>Çalışanlar</span><span>İzinler</span><span>Bordro</span><span>Raporlar</span></div>
      <div class="navcta">Staging / Test Ortamı</div>
    </nav>
    <section class="hero">
      <div>
        <div class="eyebrow"><span class="dot"></span> Türkiye ekipleri için modern HRMS hazırlanıyor</div>
        <h1>İnsan kaynaklarını karmaşadan çıkarıp tek ekranda yönetin.</h1>
        <p class="lead">Wealthy Falcon HR; çalışan bilgileri, izin talepleri, onboarding, dokümanlar ve raporları sade bir platformda toplar.</p>
        <div class="actions"><a class="btn primary" href="#">Demo talep et →</a><a class="btn secondary" href="/docs">API Docs</a><a class="btn secondary" href="/health">Health</a></div>
        <div class="trust"><span><b class="check">✓</b> KOBİ ve orta ölçekli ekipler</span><span><b class="check">✓</b> KVKK odaklı yapı</span><span><b class="check">✓</b> Mobil uyumlu self-servis</span></div>
      </div>
      <div class="product"><div class="panel"><div class="app"><div class="topbar"><div class="search">Çalışan, ekip veya belge ara</div><div class="avatar"></div></div><div class="appbody"><div class="side"><div class="active">Dashboard</div><div>Çalışanlar</div><div>İzinler</div><div>Onboarding</div><div>Dokümanlar</div><div>Raporlar</div></div><div class="main"><div class="dashhead"><div><h3>Bugünün İK özeti</h3><p>Operasyon, izin ve onboarding akışı</p></div><div class="pill">Canlı demo</div></div><div class="cards"><div class="metric"><b>248</b><span>Aktif çalışan</span></div><div class="metric"><b>12</b><span>Bekleyen izin</span></div><div class="metric"><b>7</b><span>Yeni onboarding</span></div></div><div class="wide"><div class="box"><h4>Öncelikli işler</h4><div class="row"><span>3 izin talebi onay bekliyor</span><span class="tag amber">Bugün</span></div><div class="row"><span>2 deneme süresi bitiyor</span><span class="tag">Bu hafta</span></div><div class="row"><span>Yeni çalışan evrak kontrolü</span><span class="tag green">Hazır</span></div></div><div class="box"><h4>Departman dağılımı</h4><div class="row"><span>Operasyon</span><b>86</b></div><div class="row"><span>Satış</span><b>54</b></div><div class="row"><span>Merkez</span><b>31</b></div></div></div></div></div></div></div><div class="floating"><b>%42</b><p>Tekrarlayan İK operasyonlarında hedeflenen zaman kazanımı.</p></div></div>
    </section>
    <section class="features"><div class="feature"><div class="icon">1</div><h3>Çalışan merkezi</h3><p>Personel kartı, iletişim, ekip, belge ve iş geçmişi tek düzenli profilde toplanır.</p></div><div class="feature"><div class="icon">2</div><h3>İzin ve onay akışı</h3><p>İzin talepleri, yönetici onayı ve takvim etkisi sade bir akışla yönetilir.</p></div><div class="feature"><div class="icon">3</div><h3>Yönetici dashboard</h3><p>İK müdürü bekleyen işler, riskler ve ekip dağılımını ilk ekranda görür.</p></div></section>
  </div>
</body>
</html>
"""
