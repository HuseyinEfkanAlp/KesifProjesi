"""Fiyat bankası ve tedarikçiler: proje bağımsız ürün / işçilik fiyatları, projeye devralma."""


def test_supplier_crud(client):
    s = client.post("/api/suppliers", json={"name": "Akçansa", "contact": "satış", "phone": "0212"}).json()
    assert s["id"] and s["price_count"] == 0
    assert client.post("/api/suppliers", json={"name": "  "}).status_code == 400
    up = client.patch(f"/api/suppliers/{s['id']}", json={"name": "Akçansa Beton", "note": "hazır beton"}).json()
    assert up["name"] == "Akçansa Beton" and up["note"] == "hazır beton"
    assert len(client.get("/api/suppliers").json()) == 1

    # tedarikçili fiyat satırı; tedarikçi silinince satır kalır, bağlantısı boşalır
    client.put("/api/pricebook", json=[{"key": "beton:c30_37", "unit_price": 4100, "supplier_id": s["id"]}])
    assert client.get("/api/suppliers").json()[0]["price_count"] == 1
    assert client.delete(f"/api/suppliers/{s['id']}").status_code == 204
    prod = next(p for p in client.get("/api/pricebook").json()["products"] if p["key"] == "beton:c30_37")
    assert prod["price"] == 4100 and prod["rows"][0]["supplier_id"] is None


def test_pricebook_products_and_best_price(client):
    book = client.get("/api/pricebook").json()
    keys = {p["key"] for p in book["products"]}
    assert {"beton:c30_37", "beton:c40_50", "demir:o12", "demir:o16", "kalip:plywood", "duvar:*"} <= keys
    assert all(p["price"] == 0 for p in book["products"])

    a = client.post("/api/suppliers", json={"name": "A Beton"}).json()
    b = client.post("/api/suppliers", json={"name": "B Beton"}).json()
    client.put("/api/pricebook", json=[
        {"key": "beton:c30_37", "unit_price": 4300, "supplier_id": a["id"], "brand": "A"},
        {"key": "beton:c30_37", "unit_price": 4050, "supplier_id": b["id"], "brand": "B"},
    ])
    prod = next(p for p in client.get("/api/pricebook").json()["products"] if p["key"] == "beton:c30_37")
    assert len(prod["rows"]) == 2 and prod["price"] == 4050 and prod["supplier_name"] == "B Beton"   # en düşük

    # pahalı olanı seç: geçerli fiyat artık o
    row_a = next(r for r in prod["rows"] if r["supplier_id"] == a["id"])
    client.put("/api/pricebook", json=[{"key": "beton:c30_37", "id": row_a["id"], "preferred": True}])
    prod = next(p for p in client.get("/api/pricebook").json()["products"] if p["key"] == "beton:c30_37")
    assert prod["price"] == 4300 and prod["supplier_name"] == "A Beton"
    assert sum(1 for r in prod["rows"] if r["preferred"]) == 1

    assert client.delete(f"/api/pricebook/{row_a['id']}").status_code == 204
    prod = next(p for p in client.get("/api/pricebook").json()["products"] if p["key"] == "beton:c30_37")
    assert len(prod["rows"]) == 1 and prod["price"] == 4050
    assert client.put("/api/pricebook", json=[{"key": "hicbiryerde:yok", "unit_price": 1}]).status_code == 400


def test_pricebook_fills_new_project(client, storey_dxf):
    """Bankada fiyat varsa yeni projenin ürün ve işçilik satırları kendiliğinden dolar; genel satır türe uygulanır."""
    client.put("/api/pricebook", json=[
        {"key": "beton:c30_37", "unit_price": 4400, "brand": "Nuh"},
        {"key": "demir:karisik", "unit_price": 32},
        {"key": "beton:*", "scope": "labor", "labor_price": 550, "hours_per_unit": 1.4, "crew_size": 5},
    ])
    pid = client.post("/api/projects", json={"name": "banka", "storey_height": 3.0, "slab_thickness": 0.15}).json()["id"]
    with open(storey_dxf, "rb") as f:
        client.post(f"/api/projects/{pid}/drawings", files={"file": ("kat.dxf", f, "application/dxf")},
                    data={"discipline": "structural"})

    mats = {m["key"]: m for m in client.get(f"/api/projects/{pid}/materials").json()}
    assert mats["beton:c30_37"]["unit_price"] == 4400 and mats["beton:c30_37"]["brand"] == "Nuh"
    cost = client.get(f"/api/projects/{pid}/cost").json()["cost"]
    col = next(l for l in cost["lines"] if l["key"] == "beton:column")
    assert col["unit_price"] == 4400 and col["labor_price"] == 550 and col["crew_size"] == 5

    # projede elle değiştirilen fiyat bankadan gelen değerin üstündedir ve korunur
    client.put(f"/api/projects/{pid}/materials", json=[{"key": "beton:c30_37", "unit_price": 5000}])
    client.put("/api/pricebook", json=[{"key": "beton:c30_37", "unit_price": 4600}])
    cost = client.get(f"/api/projects/{pid}/cost").json()["cost"]
    assert next(l for l in cost["lines"] if l["key"] == "beton:column")["unit_price"] == 5000

    # açıkça uygula: üzerine yazar
    r = client.post(f"/api/projects/{pid}/apply-pricebook?overwrite=true").json()
    assert r["materials"] >= 1
    cost = client.get(f"/api/projects/{pid}/cost").json()["cost"]
    assert next(l for l in cost["lines"] if l["key"] == "beton:column")["unit_price"] == 4600


def test_pricebook_labor_scope(client):
    book = client.get("/api/pricebook?scope=labor").json()
    keys = {p["key"] for p in book["products"]}
    assert {"beton:*", "duvar:*", "kalip:*", "demir:*"} <= keys
    assert all(k.endswith(":*") for k in keys)
    client.put("/api/pricebook", json=[{"key": "duvar:*", "scope": "labor", "labor_price": 260, "hours_per_unit": 0.9}])
    prod = next(p for p in client.get("/api/pricebook?scope=labor").json()["products"] if p["key"] == "duvar:*")
    assert prod["price"] == 260 and prod["hours_per_unit"] == 0.9
    # malzeme sekmesinde işçilik satırı görünmez
    mat = next(p for p in client.get("/api/pricebook").json()["products"] if p["key"] == "duvar:*")
    assert mat["price"] == 0
