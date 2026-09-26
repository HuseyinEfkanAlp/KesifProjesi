"""Çelik profil adı → kg/m ve plandaki genişlik (başlık / çap / kenar, m).

Hadde profilleri (HEA / HEB / HEM / IPE / UPN / IPN) Euronorm tablolarından (EN 10365 anma ağırlıkları).
Boru (Ø114.3x4 = CHS) ve kutu (120x80x4 = RHS / SHS) profil kesitten hesaplanır: çelik yoğunluğu 7850 kg/m³.
  boru: A = π (d − t) t        kutu: A = 2 t (a + b) − 4 t²   (köşe yarıçapı ihmal: tablodan %2–3 fazla)
"""
from __future__ import annotations

import math
import re

RO = 7850.0   # kg/m³

# profil boyu (mm) -> kg/m
_HEA = {100: 16.7, 120: 19.9, 140: 24.7, 160: 30.4, 180: 35.5, 200: 42.3, 220: 50.5, 240: 60.3, 260: 68.2, 280: 76.4,
        300: 88.3, 320: 97.6, 340: 105.0, 360: 112.0, 400: 125.0, 450: 140.0, 500: 155.0, 550: 166.0, 600: 178.0}
_HEB = {100: 20.4, 120: 26.7, 140: 33.7, 160: 42.6, 180: 51.2, 200: 61.3, 220: 71.5, 240: 83.2, 260: 93.0, 280: 103.0,
        300: 117.0, 320: 127.0, 340: 134.0, 360: 142.0, 400: 155.0, 450: 171.0, 500: 187.0, 550: 199.0, 600: 212.0}
_HEM = {100: 41.8, 120: 52.1, 140: 63.2, 160: 76.2, 180: 88.9, 200: 103.0, 220: 117.0, 240: 157.0, 260: 172.0,
        280: 189.0, 300: 238.0}
_IPE = {80: 6.0, 100: 8.1, 120: 10.4, 140: 12.9, 160: 15.8, 180: 18.8, 200: 22.4, 220: 26.2, 240: 30.7, 270: 36.1,
        300: 42.2, 330: 49.1, 360: 57.1, 400: 66.3, 450: 77.6, 500: 90.7, 550: 106.0, 600: 122.0}
_IPE_B = {80: 46, 100: 55, 120: 64, 140: 73, 160: 82, 180: 91, 200: 100, 220: 110, 240: 120, 270: 135, 300: 150,
          330: 160, 360: 170, 400: 180, 450: 190, 500: 200, 550: 210, 600: 220}
_UPN = {80: 8.64, 100: 10.6, 120: 13.4, 140: 16.0, 160: 18.8, 180: 22.0, 200: 25.3, 220: 29.4, 240: 33.2, 260: 37.9,
        280: 41.8, 300: 46.2}
_UPN_B = {80: 45, 100: 50, 120: 55, 140: 60, 160: 65, 180: 70, 200: 75, 220: 80, 240: 85, 260: 90, 280: 95, 300: 100}
_IPN = {80: 5.94, 100: 8.34, 120: 11.1, 140: 14.3, 160: 17.9, 180: 21.9, 200: 26.2, 220: 31.1, 240: 36.2, 260: 41.9,
        280: 47.9, 300: 54.2}
_IPN_B = {80: 42, 100: 50, 120: 58, 140: 66, 160: 74, 180: 82, 200: 90, 220: 98, 240: 106, 260: 113, 280: 119, 300: 125}

PROFILE_RE = re.compile(
    r"(?P<hadde>(?P<fam>HE\s*[ABM]|IPE|UPN|NPU|IPN|NPI)\s*(?P<n>\d{2,3}))"
    r"|(?P<boru>[ØøΦ⌀]\s*(?P<d>\d{2,4}(?:[.,]\d)?)\s*[xX×*]\s*(?P<t>\d{1,2}(?:[.,]\d)?))"
    r"|(?P<kutu>(?<![\d.,])(?P<a>\d{2,3})\s*[xX×*]\s*(?P<b>\d{2,3})\s*[xX×*]\s*(?P<k>\d{1,2}(?:[.,]\d)?)(?![\d.,]))")


def _f(s: str) -> float:
    return float(s.replace(",", "."))


def parse_profile(text: str) -> dict | None:
    """Yazıdaki çelik profil: {"name", "kg_m", "width" (m, plandaki genişlik), "family"}; tanınmazsa None."""
    m = PROFILE_RE.search(text or "")
    if not m:
        return None
    if m.group("hadde"):
        fam = re.sub(r"\s+", "", m.group("fam").upper()).replace("NPU", "UPN").replace("NPI", "IPN")
        n = int(m.group("n"))
        tablo = {"HEA": _HEA, "HEB": _HEB, "HEM": _HEM, "IPE": _IPE, "UPN": _UPN, "IPN": _IPN}[fam]
        if n not in tablo:
            return None
        if fam.startswith("HE"):
            gen = min(n, 300)
        else:
            gen = {"IPE": _IPE_B, "UPN": _UPN_B, "IPN": _IPN_B}[fam][n]
        return {"name": f"{fam}{n}", "kg_m": tablo[n], "width": gen / 1000.0, "family": fam}
    if m.group("boru"):
        d, t = _f(m.group("d")), _f(m.group("t"))
        if not (15 <= d <= 1200 and 1 <= t <= 40 and t < d / 2):
            return None
        kg = math.pi * (d - t) * t * 1e-6 * RO
        return {"name": f"Ø{m.group('d')}x{m.group('t')}", "kg_m": round(kg, 2), "width": d / 1000.0, "family": "CHS"}
    a, b, t = _f(m.group("a")), _f(m.group("b")), _f(m.group("k"))
    if not (20 <= b <= a <= 600 and 1 <= t <= 30 and t < b / 2):
        return None
    kg = (2 * t * (a + b) - 4 * t * t) * 1e-6 * RO
    # kutu profil planda dar ya da geniş yüzüyle görünebilir
    return {"name": f"{int(a)}x{int(b)}x{m.group('k')}", "kg_m": round(kg, 2), "width": b / 1000.0, "width2": a / 1000.0,
            "family": "RHS"}
