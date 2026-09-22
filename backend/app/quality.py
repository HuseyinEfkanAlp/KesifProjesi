"""Read-only completeness checks. A clean check is not engineering approval."""
from collections import Counter
from .planset import PLAN_TYPE_BY_CODE
from .quantity.boq import DEFAULT_PARAMS


def build_quality(drawings, elements, items, summary, params, plan_check, cost=None):
    issues = []

    def add(code, message, severity="review", drawing=None):
        issues.append({"code": code, "severity": severity, "message": message,
                       "drawing_id": drawing.id if drawing else None,
                       "drawing": (drawing.label or drawing.filename) if drawing else None})

    by_drawing = {}
    for e in elements:
        by_drawing.setdefault(e.drawing_id, []).append(e)
    if not drawings:
        add("no_drawings", "Henüz çizim yüklenmedi; metraj üretilemez.", "blocking")
    for d in drawings:
        pt = PLAN_TYPE_BY_CODE.get(d.plan_type)
        if pt and not pt.analyze:
            continue
        es = by_drawing.get(d.id, [])
        if not d.analyzed_at:
            add("not_analyzed", "Pafta henüz analiz edilmedi.", "blocking", d)
        elif not any(e.included for e in es):
            add("empty_drawing", "Metraja giren eleman bulunamadı. Plan tipini, birimi ve dış referansları kontrol edin.", "blocking", d)
        if not d.plan_type:
            add("unknown_plan", "Plan tipi belirlenmedi; disiplin ve kapsam kontrol edilmeli.", "blocking", d)
        if not d.unit_detected and not d.unit_override:
            add("unknown_unit", "Çizim birimi doğrulanamadı; bilinen bir ölçüyle kontrol edin.", "blocking", d)
        excluded = sum(not e.included for e in es)
        if excluded:
            add("excluded_elements", f"{excluded} eleman metraj dışında; dışlama kararlarını kontrol edin.", "review", d)
        low = sum(e.included and e.confidence < .7 for e in es)
        if low:
            add("low_confidence", f"{low} dahil eleman düşük güvenle tanındı; geometriyi doğrulayın.", "review", d)
        for warning in dict.fromkeys(d.warnings or []):
            # Preserve all original evidence; never interpret an unmatched label as a volume.
            # "ölçülmeden kaldı" / "hiçbir keşif kalemi üretmedi": paftanın büyük bölümü keşfe girmiyor demektir,
            # inceleme notu değil eksiktir (bkz. analyzer._dominant_unmapped, standard.measure_layer).
            blocking = any(s in warning for s in ("hiçbir kirişe atanmadı", "kapalı bir hücreye düşmedi", "plan geometrisi yok",
                                                  "hiçbir keşif kalemi üretmedi", "ölçülmeden kaldı"))
            add("unresolved_geometry" if blocking else "drawing_warning", warning,
                "blocking" if blocking else "review", d)
        warned = [e for e in es if e.included and e.warnings]
        if warned:
            add("element_warnings", f"{len(warned)} elemanda ölçüm uyarısı var; Elemanlar ekranında inceleyin.", "review", d)
    if plan_check.get("missing_required", 0):
        add("missing_plans", f"Seçili proje kapsamında {plan_check['missing_required']} gerekli plan eksik.", "blocking")
    for w in summary.get("warnings", []):
        add("quantity_warning", w)
    ratio = sum(g.get("rebar_ratio_kg", 0) for g in summary.get("groups", []))
    if ratio > 0:
        add("estimated_rebar", f"{ratio:,.2f} kg donatı beton × oran hesabıdır; kesin donatı metrajı değildir.")
    counts = Counter()
    for i in items:
        if i.detail.get("info") or i.detail.get("system"):
            continue
        if i.detail.get("recipe"):
            counts['recipe'] += 1
        elif i.detail.get("derived") or i.detail.get("roof_auto") or i.detail.get("facade_source") == 'estimated':
            counts['derived'] += 1
    if counts:
        add("derived_items", f"{counts['recipe']} reçete ve {counts['derived']} türetilmiş kalem var; katsayı ve uygulama detayları projeye göre doğrulanmalı.")
    # Only surface assumptions relevant to quantities actually produced.
    kinds = {i.kind for i in items}
    relevant = {}
    if "beton" in kinds:
        relevant.update(concrete_class="Beton sınıfı", concrete_waste_pct="Beton firesi (%)")
    if "demir" in kinds:
        relevant.update(rebar_grade="Donatı çeliği sınıfı", rebar_waste_pct="Demir firesi (%)")
    if "kalip" in kinds:
        relevant.update(formwork_material="Kalıp malzemesi", formwork_reuse="Kalıp tekrar kullanımı")
    for kind, key, label in [("kazi", "excavation_depth_m", "Kazı derinliği (m)"),
                             ("kazi", "excavation_margin", "Kazı çalışma / şev payı"),
                             ("grobeton", "lean_concrete_cm", "Grobeton kalınlığı (cm)"),
                             ("sap", "screed_cm", "Şap kalınlığı (cm)"),
                             ("kablo", "cable_waste_pct", "Kablo firesi (%)"),
                             ("tava", "tray_waste_pct", "Tava firesi (%)")]:
        if kind in kinds:
            relevant[key] = label
    # Çizimden okunan değer varsayılan sayılmaz: türetilen kalem kaynağını detail.param_source ile taşır.
    # {kalem türü: (parametre, grup -> değer)} — şap grubu cm, kazı grubu cm cinsindendir.
    PLAN_READ_KINDS = {"sap": ("screed_cm", 1.0), "kazi": ("excavation_depth_m", 0.01),
                       "grobeton": ("lean_concrete_cm", 1.0)}
    PLAN_SOURCES = {"rooms": "mahal notundan", "drawing": "çizim notundan", "note": "kesitte yazılı",
                    "kots": "kesit kotlarından", "foundation_kot": "temel kotundan"}
    plan_read = {}
    for i in items:
        src = (i.detail or {}).get("param_source")
        if i.kind in PLAN_READ_KINDS and src in PLAN_SOURCES:
            key, factor = PLAN_READ_KINDS[i.kind]
            try:
                plan_read[key] = (round(float(i.group) * factor, 2), src)
            except (TypeError, ValueError):
                pass
    assumptions = []
    for k, label in relevant.items():
        if k in plan_read:
            value, src = plan_read[k]
            assumptions.append({"key": k, "label": label, "value": value, "source": "drawing",
                                "detail": PLAN_SOURCES[src]})
        else:
            assumptions.append({"key": k, "label": label, "value": params.get(k, DEFAULT_PARAMS[k]),
                                "source": "user" if k in params else "default"})
    defaults = sum(x['source'] == 'default' for x in assumptions)
    if defaults:
        add("default_parameters", f"{defaults} hesap parametresi program varsayılanı; çizimden doğrulanmış bilgi değildir.")
    if cost is not None:
        for key, message in [("missing_materials", "ürünün malzeme fiyatı eksik"), ("missing_labor", "kalemin işçilik fiyatı sıfır veya eksik")]:
            n = len(cost.get(key, []))
            if n:
                add(key, f"{n} {message}; tutar tamamlanmış proje maliyeti değildir.", "blocking")
        duration = cost.get("duration", {})
        if duration.get("missing_rates") or duration.get("missing_crew"):
            add("incomplete_duration", "Süre için eksik işçilik normu veya ekip bilgisi var; takvim süresi doğrulanmadı.")
    return {"status": "incomplete" if any(x['severity'] == 'blocking' for x in issues) else "review_required",
            "label": "Eksik / kontrol gerekli" if any(x['severity'] == 'blocking' for x in issues) else "Uzman kontrolü gerekli",
            "certified": False, "issues": issues, "assumptions": assumptions,
            "estimated_rebar_kg": round(ratio, 3), "derived_counts": dict(counts),
            "notice": "Bu sonuç hesap taslağıdır. Çizim, ölçü kuralları ve şartnameyle bağımsız karşılaştırılmadan kesin metraj sayılmaz."}
