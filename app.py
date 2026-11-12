#!/usr/bin/env python3
"""
BOXLAB - local parametric CAD front end.

    python3 app.py

Serves http://localhost:8765. Sliders in the browser, CadQuery on the
server. The browser never computes geometry; it only displays the mesh
the kernel produced, so what you see is what exports.
"""

import argparse
import io
import json
import os
import tempfile
import threading
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import cadquery as cq

import model as M

HERE = os.path.dirname(os.path.abspath(__file__))
KERNEL_LOCK = threading.Lock()   # OpenCascade is not reentrant


def export_bytes(obj, ext, **kw):
    """Export a CadQuery object to bytes via a temp file."""
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as fh:
        path = fh.name
    try:
        cq.exporters.export(obj, path, **kw)
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        os.unlink(path)


def mesh_stats(obj):
    """Bounding box and volume straight from the B-rep, no meshing needed."""
    shape = obj.val()
    bb = shape.BoundingBox()
    return {
        "bbox": [round(bb.xlen, 2), round(bb.ylen, 2), round(bb.zlen, 2)],
        "volume": round(shape.Volume() / 1000.0, 2),   # cm3
    }


def derived(p):
    """Numbers worth showing that fall out of the parameters."""
    inner_l, inner_w, cav_h = M._cavity_dims(p)
    cell_l = (inner_l - (p["cols"] - 1) * p["divider"]) / p["cols"]
    cell_w = (inner_w - (p["rows"] - 1) * p["divider"]) / p["rows"]
    return {
        "cell": [round(cell_l, 1), round(cell_w, 1), round(cav_h - p["divider_drop"], 1)],
        "cells": int(p["cols"] * p["rows"]),
        "cavity": [round(inner_l, 1), round(inner_w, 1), round(cav_h, 1)],
        "perimeters": round(p["wall"] / 0.4, 1),
        "floor_layers": round(p["floor"] / 0.2, 1),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass   # keep the terminal readable

    def _send(self, code, body, ctype, extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _params(self, qs):
        return M.merge_params({k: v[0] for k, v in qs.items()})

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)

        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")

        if u.path == "/defaults":
            return self._send(200, json.dumps(M.DEFAULTS), "application/json")

        if u.path == "/preview.stl":
            p = self._params(qs)
            errs = M.validate(p)
            if errs:
                return self._send(400, json.dumps({"errors": errs}), "application/json")
            with KERNEL_LOCK:
                asm = M.preview_assembly(p)
                data = export_bytes(asm, "stl", tolerance=0.01, angularTolerance=0.1)
                tray, lid = M.build_all(p)
                stats = {
                    "tray": mesh_stats(tray),
                    "lid": mesh_stats(lid) if lid else None,
                    "derived": derived(p),
                }
            return self._send(200, data, "model/stl",
                              {"X-Stats": json.dumps(stats)})

        if u.path == "/export":
            p = self._params(qs)
            errs = M.validate(p)
            if errs:
                return self._send(400, json.dumps({"errors": errs}), "application/json")
            name = qs.get("name", ["tray"])[0].strip() or "tray"
            name = "".join(c for c in name if c.isalnum() or c in "-_")
            with KERNEL_LOCK:
                tray, lid = M.build_all(p)
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                    z.writestr(f"{name}_tray.stl", export_bytes(
                        tray, "stl", tolerance=0.005, angularTolerance=0.05))
                    z.writestr(f"{name}_tray.step", export_bytes(tray, "step"))
                    z.writestr(f"{name}_tray.3mf", export_bytes(tray, "3mf"))
                    if lid is not None:
                        z.writestr(f"{name}_lid.stl", export_bytes(
                            lid, "stl", tolerance=0.005, angularTolerance=0.05))
                        z.writestr(f"{name}_lid.step", export_bytes(lid, "step"))
                        z.writestr(f"{name}_lid.3mf", export_bytes(lid, "3mf"))
                    z.writestr(f"{name}_parameters.json",
                               json.dumps(p, indent=2))
                    z.writestr(f"{name}_model.py", script_for(p))
            return self._send(
                200, buf.getvalue(), "application/zip",
                {"Content-Disposition": f'attachment; filename="{name}.zip"'})

        return self._send(404, "not found", "text/plain")


def script_for(p):
    """A standalone script reproducing exactly this part, for the archive."""
    lines = [
        "# Generated by BOXLAB. Standalone - edit and re-run with:",
        "#   python3 this_file.py",
        "import sys, os",
        "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))",
        "import cadquery as cq",
        "import model as M",
        "",
        "PARAMS = {",
    ]
    for k, v in p.items():
        lines.append(f"    {k!r}: {v!r},")
    lines += [
        "}",
        "",
        "tray, lid = M.build_all(PARAMS)",
        "cq.exporters.export(tray, 'tray.stl')",
        "cq.exporters.export(tray, 'tray.step')",
        "if lid is not None:",
        "    cq.exporters.export(lid, 'lid.stl')",
        "    cq.exporters.export(lid, 'lid.step')",
        "print('exported')",
    ]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    except OSError as e:
        print(f"Cannot bind port {a.port}: {e}")
        print(f"Something is already using it. Try:  python3 app.py --port {a.port + 1}")
        raise SystemExit(1)
    url = f"http://localhost:{a.port}"
    print(f"BOXLAB running at {url}   (ctrl-C to stop)")
    if not a.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
