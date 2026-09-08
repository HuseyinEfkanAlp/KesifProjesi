"""KÇS kataloğu API: disiplinler, kalemler, şablon DXF."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..services import load_catalog, save_catalog
from ..standard.catalog import LAYER_RE, MEASURES, parse_layer
from ..standard.template import build_template

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


class ItemIn(BaseModel):
    code: str
    discipline: str
    name: str
    measure: str
    unit: str | None = None
    spec_label: str | None = None
    example: str | None = None
    components: list[dict] | str | None = None   # [{"code","factor","spec"}] ya da "OSB×1:11; MERTEK×1.7"
    poz: str | None = None                       # ÇŞB poz numarası
    recipe: list[dict] | str | None = None       # reçete: "IS_ISKELESI×1; ANKRAJ_BULONU×1.5:M12; KALIP_ISKELESI×1H"


class DisciplineIn(BaseModel):
    code: str
    name: str


@router.get("")
def read_catalog():
    return load_catalog().to_dict()


@router.put("/items")
def upsert_item(body: ItemIn):
    cat = load_catalog()
    try:
        it = cat.upsert_item(body.model_dump())
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    save_catalog(cat)
    return it.to_dict()


@router.delete("/items/{code}", status_code=204)
def delete_item(code: str):
    cat = load_catalog()
    if not cat.remove_item(code):
        raise HTTPException(404, "Kalem bulunamadı")
    save_catalog(cat)


@router.put("/disciplines")
def upsert_discipline(body: DisciplineIn):
    cat = load_catalog()
    try:
        cat.upsert_discipline(body.code, body.name)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    save_catalog(cat)
    return {"disciplines": cat.disciplines}


@router.post("/reset")
def reset_catalog():
    """Kullanıcı değişikliklerini siler, varsayılan kataloğa döner."""
    from ..standard.catalog import Catalog
    cat = Catalog()
    save_catalog(cat)
    return cat.to_dict()


@router.get("/check-layer")
def check_layer(name: str):
    """Bir katman adının standarda uyup uymadığını söyler (arayüzdeki 'katman adı dene' kutusu)."""
    cat = load_catalog()
    p = parse_layer(name, cat)
    if p is None:
        return {"valid": False, "reason": "KSF-<DİSİPLİN>-<KALEM>[-<ÖZELLİK>] biçiminde değil", "pattern": LAYER_RE.pattern}
    return {"valid": True, "discipline": p.discipline, "discipline_name": cat.discipline_name(p.discipline),
            "code": p.code, "spec": p.spec, "known": p.known,
            "item": p.item.to_dict() if p.item else None,
            "measure": MEASURES[p.item.measure][0] if p.item else "katalogda yok: geometriye göre (blok adet / çizgi m / alan m²)"}


@router.get("/template.dxf")
def template_dxf():
    data = build_template(load_catalog())
    return Response(data, media_type="application/dxf",
                    headers={"Content-Disposition": 'attachment; filename="KSF_sablon.dxf"'})
