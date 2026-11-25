"""
Rendu « Roblox 3D Ciné » : le moteur three.js (core/cine_engine/engine/film.html) tourne dans Chrome sans fenêtre,
Clipoa lui sert les fichiers en local puis capture chaque image et l'encode avec ffmpeg.
Adapté du moteur Docteur Shark v3.4 (GTAO, bloom de nuit, lumière de contour, étalonnage, visages vivants).
"""
import base64
import functools
import http.server
import json
import os
import socketserver
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config import FFMPEG_PATH
from core.cine_setup import ENGINE_DIR, EPISODES_DIR, FONTS_DIR, THREE_DIR, find_chrome

POST = {
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131,vignette=PI/4,noise=alls=7:allf=t",
    "bw": "hue=s=0,eq=contrast=1.08,vignette=PI/4,noise=alls=6:allf=t",
}
GPU_ARGS = ["--ignore-gpu-blocklist", "--enable-gpu-rasterization", "--no-sandbox"]
SOFT_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--no-sandbox"]


def _map_path(url_path: str) -> Optional[Path]:
    p = url_path.split("?", 1)[0]
    routes = (
        ("/engine/node_modules/three/", THREE_DIR),
        ("/assets/fonts/", FONTS_DIR),
        ("/episodes/", EPISODES_DIR),
        ("/engine/", ENGINE_DIR / "engine"),
    )
    for prefix, base in routes:
        if p.startswith(prefix):
            rel = p[len(prefix):]
            target = (base / rel).resolve()
            if str(target).startswith(str(base.resolve())):
                return target
    return None


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def translate_path(self, path):
        t = _map_path(path)
        return str(t) if t else "/nonexistent"

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


_TYPES = dict(http.server.SimpleHTTPRequestHandler.extensions_map)
_TYPES.update({".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json", ".ttf": "font/ttf"})
_Handler.extensions_map = _TYPES


def _serve():
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


class CinePage:
    """Ouvre film.html pour un épisode ; à utiliser avec `with`."""

    def __init__(self, ep: str, w: int = 1080, h: int = 1920, fps: int = 30, quality: str = "", soft: bool = False):
        self.ep, self.w, self.h, self.fps, self.quality, self.soft = ep, w, h, fps, quality, soft
        self.logs: List[str] = []

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.httpd, port = _serve()
        self.pw = sync_playwright().start()
        chrome = find_chrome()
        args = SOFT_ARGS if (self.soft or os.environ.get("CLIPOA_CINE_SOFT") == "1") else GPU_ARGS
        kw = {"headless": True, "args": args}
        if chrome:
            kw["executable_path"] = chrome
        self.browser = self.pw.chromium.launch(**kw)
        self.page = self.browser.new_page(viewport={"width": self.w, "height": self.h}, device_scale_factor=1)
        self.page.on("console", lambda m: self.logs.append(f"[{m.type}] {m.text}") if "GPU stall" not in m.text else None)
        self.page.on("pageerror", lambda e: self.logs.append(f"[pageerror] {e}"))
        self.page.on("response", lambda r: self.logs.append(f"[error] 404 {r.url}") if r.status >= 400 and not r.url.endswith("favicon.ico") else None)
        url = f"http://127.0.0.1:{port}/engine/film.html?ep={self.ep}&w={self.w}&h={self.h}&fps={self.fps}&{self.quality}"
        self.page.goto(url)
        try:
            self.page.wait_for_function("window.__ready === true", timeout=180000)
        except Exception:
            errs = [l for l in self.logs if "error" in l.lower()][-8:]
            raise RuntimeError("La scène 3D ne démarre pas : " + (" | ".join(errs) or "délai dépassé"))
        return self

    def __exit__(self, *exc):
        for fn in (lambda: self.browser.close(), lambda: self.pw.stop(), lambda: self.httpd.shutdown()):
            try:
                fn()
            except Exception:
                pass

    def shots(self) -> List[Dict[str, Any]]:
        return self.page.evaluate("window.__shots")

    def frame_jpeg(self, f: int) -> bytes:
        u = self.page.evaluate("f => window.__renderFrame(f)", f)
        return base64.b64decode(u.split(",", 1)[1])


def preview(ep: str, out_dir: str, frac: float = 0.55, w: int = 540, h: int = 960) -> Dict[str, Any]:
    """Une image par plan + défauts détectés (caméra dans un objet, tête coupée, personnages qui se traversent, image noire)."""
    os.makedirs(out_dir, exist_ok=True)
    problems: List[str] = []
    images: List[str] = []
    with CinePage(ep, w, h, quality="aos=4&pds=4") as cp:
        shots = cp.shots()
        for i, s in enumerate(shots):
            try:
                n = cp.page.evaluate("i => window.__setupShot(i)", i)
                f = max(0, min(n - 1, int(n * frac)))
                img = cp.frame_jpeg(f)
                path = os.path.join(out_dir, f"{i:02d}_{s['name']}.jpg")
                open(path, "wb").write(img)
                images.append(path)
                for x in cp.page.evaluate("i => window.__check(i)", i):
                    problems.append(f"plan {i} ({s['name']}) : {x}")
                if _mean_luma(path) < 12:
                    problems.append(f"plan {i} ({s['name']}) : image presque noire")
            except Exception as e:
                problems.append(f"plan {i} ({s.get('name')}) : erreur JavaScript {str(e)[:200]}")
        errs = [l for l in cp.logs if ("pageerror" in l or "[error]" in l) and "Failed to load resource" not in l][-6:]
    problems += [f"console : {e[:200]}" for e in errs]
    return {"shots": shots, "images": images, "problems": problems}


def _mean_luma(path: str) -> float:
    try:
        from PIL import Image
        im = Image.open(path).convert("L").resize((54, 96))
        return sum(im.getdata()) / (54 * 96)
    except Exception:
        return 128.0


def film(ep: str, out_path: str, w: int = 1080, h: int = 1920, fps: int = 30,
         progress: Optional[Callable[[int, int], None]] = None) -> str:
    """Rend tous les plans dans un seul MP4 (sans son). Retourne le chemin."""
    out_path = str(Path(out_path).resolve())
    out_dir = Path(out_path).parent / (Path(out_path).stem + "_plans")
    out_dir.mkdir(parents=True, exist_ok=True)
    parts: List[str] = []
    with CinePage(ep, w, h, fps=fps) as cp:
        shots = cp.shots()
        frames_total = sum(max(1, round(s["end"] * fps) - round(s["start"] * fps)) for s in shots)
        done = 0
        for i, s in enumerate(shots):
            n = cp.page.evaluate("i => window.__setupShot(i)", i)
            vf = ["format=yuv420p"]
            if s.get("post") in POST:
                vf.insert(0, POST[s["post"]])
            if s.get("flash"):
                vf.append("fade=t=in:st=0:d=0.12:color=white")
            part = str(out_dir / f"{i:02d}.mp4")
            ff = subprocess.Popen([FFMPEG_PATH, "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg",
                                   "-framerate", str(fps), "-i", "-", "-vf", ",".join(vf), "-c:v", "libx264",
                                   "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps), part],
                                  stdin=subprocess.PIPE)
            for f in range(n):
                ff.stdin.write(cp.frame_jpeg(f))
                done += 1
                if progress and done % 15 == 0:
                    progress(done, frames_total)
            ff.stdin.close()
            if ff.wait() != 0:
                raise RuntimeError(f"Encodage du plan {i} impossible")
            parts.append(part)
    lst = out_dir / "liste.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    subprocess.run([FFMPEG_PATH, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", out_path], check=True)
    return out_path
