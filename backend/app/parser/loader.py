"""DXF dosyasını okur, blokları patlatır, her şeyi metre cinsine çevirir.

Çıktı: Drawing - düz (flatten edilmiş) entity listesi. Yaylar/eğriler kısa
doğru parçalarına bölünür; böylece dedektörler yalnızca nokta listeleriyle çalışır.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

import ezdxf
from ezdxf import path as ezpath
from ezdxf.entities import DXFEntity

Point = tuple[float, float]
Kind = Literal["polygon", "polyline", "line", "text", "insert"]

# $INSUNITS kodları -> metreye çarpan
INSUNITS_TO_M = {
    1: 0.0254,   # inch
    2: 0.3048,   # feet
    4: 0.001,    # mm
    5: 0.01,     # cm
    6: 1.0,      # m
}
UNIT_NAME = {0.001: "mm", 0.01: "cm", 1.0: "m", 0.0254: "inch", 0.3048: "feet"}
UNIT_SCALE = {"mm": 0.001, "cm": 0.01, "m": 1.0}


@dataclass
class Entity:
    kind: Kind
    layer: str
    points: list[Point]            # metre
    closed: bool = False
    text: str = ""                 # kind == "text" için düz metin; kind == "insert" için blok adı
    height: float = 0.0            # yazı yüksekliği (metre)
    handle: str = ""
    source: str = ""               # DXF entity tipi (LWPOLYLINE, HATCH, INSERT>LINE ...)
    block: str = ""                # INSERT içinden geliyorsa blok adı

    @property
    def is_closed_polygon(self) -> bool:
        return self.kind == "polygon" and len(self.points) >= 3


@dataclass
class Drawing:
    path: str
    unit: str                      # "mm" | "cm" | "m"
    scale: float                   # çizim birimi -> metre çarpanı
    unit_detected: bool            # $INSUNITS'ten mi geldi (True) yoksa tahmin mi (False)
    entities: list[Entity] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def by_layer(self, layer: str) -> list[Entity]:
        return [e for e in self.entities if e.layer == layer]

    def texts(self) -> list[Entity]:
        return [e for e in self.entities if e.kind == "text"]

    def inserts(self) -> list[Entity]:
        """Üst düzey blok yerleşimleri (kapı/pencere/armatür sembolleri); points = bloğun çevreleyen kutusu."""
        return [e for e in self.entities if e.kind == "insert"]

    def layer_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.entities:
            counts[e.layer] = counts.get(e.layer, 0) + 1
        return counts


def _flatten_path(p: ezpath.Path, tol: float) -> list[Point]:
    return [(v.x, v.y) for v in p.flattening(tol)]


def _dedupe(pts: list[Point], eps: float = 1e-9) -> list[Point]:
    out: list[Point] = []
    for pt in pts:
        if not out or math.dist(out[-1], pt) > eps:
            out.append(pt)
    if len(out) > 1 and math.dist(out[0], out[-1]) <= eps:
        out.pop()
    return out


def _convert(entity: DXFEntity, scale: float, insert_layer: str | None, block: str) -> Iterable[Entity]:
    """Tek bir DXF entity'sini Entity listesine çevirir (blok patlatma dahil)."""
    t = entity.dxftype()
    layer = entity.dxf.layer
    # Blok içindeki entity "0" katmanındaysa INSERT'in katmanını alır (AutoCAD davranışı)
    if block and layer == "0" and insert_layer:
        layer = insert_layer
    handle = entity.dxf.handle if entity.dxf.hasattr("handle") else ""
    src = ("INSERT>" if block else "") + t
    tol = 0.005 / max(scale, 1e-9)  # ~5 mm flatten toleransı (çizim biriminde)

    if t == "INSERT":
        try:
            subs = list(entity.virtual_entities())
        except Exception:
            return
        converted: list[Entity] = []
        for sub in subs:
            converted.extend(_convert(sub, scale, entity.dxf.layer, entity.dxf.name))
        yield from converted
        if not block:
            # Üst düzey blok: sembol sayımı (kapı, pencere, armatür) için tek bir "insert" kaydı; kutu = alt nesnelerin sınırı
            ins = entity.dxf.insert
            xs = [p[0] for e in converted if e.kind != "text" for p in e.points]
            ys = [p[1] for e in converted if e.kind != "text" for p in e.points]
            if xs:
                pts = [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]
            else:
                pts = [(ins.x * scale, ins.y * scale)]
            yield Entity("insert", layer, pts, closed=True, text=str(entity.dxf.name), handle=handle,
                         source="INSERT", block=str(entity.dxf.name))
        return

    if t in ("TEXT", "MTEXT", "ATTRIB"):
        try:
            txt = entity.plain_text() if hasattr(entity, "plain_text") else entity.dxf.text
        except Exception:
            txt = getattr(entity.dxf, "text", "")
        ins = entity.dxf.insert
        h = float(getattr(entity.dxf, "char_height", None) or getattr(entity.dxf, "height", 0.0) or 0.0)
        yield Entity("text", layer, [(ins.x * scale, ins.y * scale)], text=str(txt).strip(),
                     height=h * scale, handle=handle, source=src, block=block)
        return

    if t == "HATCH":
        try:
            paths = ezpath.from_hatch(entity)
        except Exception:
            return
        for p in paths:
            pts = _dedupe([(x * scale, y * scale) for x, y in _flatten_path(p, tol)])
            if len(pts) >= 3:
                yield Entity("polygon", layer, pts, closed=True, handle=handle, source=src, block=block)
        return

    if t in ("SOLID", "TRACE", "3DFACE"):
        vs = [entity.dxf.vtx0, entity.dxf.vtx1, entity.dxf.vtx3, entity.dxf.vtx2]  # SOLID köşe sırası çapraz
        pts = _dedupe([(v.x * scale, v.y * scale) for v in vs])
        if len(pts) >= 3:
            yield Entity("polygon", layer, pts, closed=True, handle=handle, source=src, block=block)
        return

    if t in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"):
        try:
            p = ezpath.make_path(entity)
        except Exception:
            return
        pts = _dedupe([(x * scale, y * scale) for x, y in _flatten_path(p, tol)])
        if len(pts) < 2:
            return
        closed = bool(getattr(entity, "is_closed", False)) or t == "CIRCLE" or p.is_closed
        if t == "LINE":
            yield Entity("line", layer, pts, handle=handle, source=src, block=block)
        elif closed and len(pts) >= 3:
            yield Entity("polygon", layer, pts, closed=True, handle=handle, source=src, block=block)
        else:
            yield Entity("polyline", layer, pts, handle=handle, source=src, block=block)
        return
    # DIMENSION, LEADER, POINT, vb. yok sayılır


def _guess_scale(entities: list[Entity]) -> tuple[float, str]:
    """$INSUNITS yoksa çizimin boyutundan birim tahmin et (bina planı varsayımı)."""
    xs = [p[0] for e in entities for p in e.points]
    ys = [p[1] for e in entities for p in e.points]
    if not xs:
        return 1.0, "m"
    extent = max(max(xs) - min(xs), max(ys) - min(ys))
    if extent < 500:        # 500 birimden küçük -> metre çizilmiş
        return 1.0, "m"
    if extent < 50_000:     # 500 .. 50.000 birim -> cm
        return 0.01, "cm"
    return 0.001, "mm"


def load_dxf(path: str | Path, unit_override: str | None = None) -> Drawing:
    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()
    warnings: list[str] = []

    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    if unit_override and unit_override in UNIT_SCALE:
        scale, unit, detected = UNIT_SCALE[unit_override], unit_override, True
    elif insunits in INSUNITS_TO_M:
        scale = INSUNITS_TO_M[insunits]
        unit = UNIT_NAME.get(scale, "m")
        detected = True
    else:
        raw: list[Entity] = []
        for e in msp:
            raw.extend(_convert(e, 1.0, None, ""))
        scale, unit = _guess_scale(raw)
        detected = False
        warnings.append(
            f"Çizimde birim bilgisi ($INSUNITS) yok; boyutlardan '{unit}' tahmin edildi. Gerekirse birimi elle seçin."
        )

    entities: list[Entity] = []
    for e in msp:
        entities.extend(_convert(e, scale, None, ""))

    layers = sorted({e.layer for e in entities} | {l.dxf.name for l in doc.layers})
    return Drawing(path=str(path), unit=unit, scale=scale, unit_detected=detected,
                   entities=entities, layers=layers, warnings=warnings)
