"""DWG -> DXF dönüşümü (ODA File Converter ile).

libredwg (dwg2dxf) AutoCAD 2013+ dosyalarında katman tablosunu okuyamıyor (A4-A5 çizimlerinde görüldü);
ücretsiz ODA File Converter güvenilir. Kurulum: https://www.opendesign.com/guestfiles/oda_file_converter
Yol: KESIF_ODA_CONVERTER ortam değişkeni ya da bilinen kurulum yerleri.
"""
from __future__ import annotations

import glob
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

KNOWN_PATHS = {
    "Darwin": [
        "~/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter",
        "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter",
    ],
    "Windows": [
        r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe",
        r"C:\Program Files (x86)\ODA\ODAFileConverter*\ODAFileConverter.exe",
    ],
    "Linux": ["/usr/bin/ODAFileConverter", "/opt/ODAFileConverter/ODAFileConverter", "~/bin/ODAFileConverter"],
}


def find_oda_converter() -> str | None:
    env = os.environ.get("KESIF_ODA_CONVERTER")
    if env and Path(env).expanduser().exists():
        return str(Path(env).expanduser())
    for pat in KNOWN_PATHS.get(platform.system(), []):
        for hit in sorted(glob.glob(os.path.expanduser(pat)), reverse=True):
            if os.access(hit, os.X_OK):
                return hit
    w = shutil.which("ODAFileConverter")
    return w


def dwg_supported() -> bool:
    return find_oda_converter() is not None


def convert_dwg_to_dxf(src: Path, dest: Path, version: str = "ACAD2018", timeout: int = 900) -> Path:
    """src DWG dosyasını dest DXF olarak yazar. Dönüştürücü yoksa RuntimeError."""
    exe = find_oda_converter()
    if not exe:
        raise RuntimeError("ODA File Converter bulunamadı. DWG yüklemek için kurun ya da AutoCAD'de DXF olarak kaydedin.")
    with tempfile.TemporaryDirectory(prefix="kesif_dwg_") as tmp:
        tmp_in = Path(tmp) / "in"
        tmp_out = Path(tmp) / "out"
        tmp_in.mkdir()
        tmp_out.mkdir()
        # tek dosyalık giriş klasörü; uzantı küçük harf (filtre büyük/küçük harfe duyarlı)
        local = tmp_in / "input.dwg"
        shutil.copyfile(src, local)
        cmd = [exe, str(tmp_in), str(tmp_out), version, "DXF", "0", "1", "*.dwg"]
        try:
            subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise RuntimeError("DWG dönüşümü zaman aşımına uğradı (dosya çok büyük olabilir)")
        out = tmp_out / "input.dxf"
        if not out.exists() or out.stat().st_size < 1000:
            err = ""
            for f in tmp_out.glob("*.err"):
                err = f.read_text(errors="replace")[:300]
            raise RuntimeError("DWG dönüşümü başarısız" + (f": {err}" if err else ""))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out), str(dest))
    return dest
