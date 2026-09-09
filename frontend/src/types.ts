export type Discipline = 'structural' | 'architectural' | 'electrical' | 'mechanical' | 'standard' | 'rebar' | 'mapped'
/** Yüklerken "auto": disiplin, başlıktan tanınan plan tipinden gelir */
export type DisciplineChoice = Discipline | 'auto'

export const DISCIPLINES: Record<Discipline, string> = {
  structural: 'Statik (kalıp planı)',
  rebar: 'Donatı planı (demir metraj tablosu)',
  architectural: 'Mimari (sezgisel)',
  electrical: 'Elektrik (sezgisel)',
  mechanical: 'Mekanik (sezgisel)',
  standard: 'KSF standart çizim (tüm disiplinler)',
  mapped: 'Katman eşlemeli (cephe / çatı / peyzaj / diğer)',
}

export type EType =
  | 'column' | 'shear_wall' | 'beam' | 'slab' | 'foundation'
  | 'wall' | 'door' | 'window'
  | 'tray' | 'cable' | 'conduit' | 'fixture'
  | 'pipe' | 'duct' | 'mech_fixture'

export const ETYPE_LABELS: Record<EType, string> = {
  column: 'Kolon',
  shear_wall: 'Perde',
  beam: 'Kiriş',
  slab: 'Döşeme',
  foundation: 'Temel',
  wall: 'Duvar',
  door: 'Kapı',
  window: 'Pencere',
  tray: 'Kablo tavası',
  cable: 'Kablo',
  conduit: 'Boru',
  fixture: 'Armatür / priz / anahtar',
  pipe: 'Boru (mekanik)',
  duct: 'Hava kanalı',
  mech_fixture: 'Mekanik cihaz / vitrifiye',
}

export const ETYPES_BY_DISCIPLINE: Record<Discipline, EType[]> = {
  structural: ['column', 'shear_wall', 'beam', 'slab', 'foundation'],
  architectural: ['wall', 'door', 'window'],
  electrical: ['tray', 'cable', 'conduit', 'fixture'],
  mechanical: ['pipe', 'duct', 'mech_fixture'],
  standard: [],   // KSF çiziminde tipler katman adından gelir (katalog kalem kodu)
  rebar: [],      // donatı paftası: yalnız metraj tablosu okunur
  mapped: [],     // katman -> katalog kalemi eşlemesi
}

/** Statik tipler (beton/kalıp/demir metrajı) */
export const STRUCTURAL_ETYPES = ETYPES_BY_DISCIPLINE.structural

/** Katman eşlemede seçilebilen tipler: disiplinin elemanları (+ statikte döşeme boşluğu); ek disiplinlerin tipleri de eklenir */
export function layerTypeLabels(discipline: Discipline, extras: Discipline[] = []): Record<string, string> {
  const out: Record<string, string> = {}
  for (const d of [discipline, ...extras]) {
    if (d === 'standard' || d === 'rebar' || d === 'mapped') continue
    const prefix = extras.length ? `${DISCIPLINES[d].split(' (')[0]}: ` : ''
    for (const t of ETYPES_BY_DISCIPLINE[d]) out[t] = prefix + ETYPE_LABELS[t]
    if (d === 'structural') out.hole = prefix + 'Döşeme boşluğu (şaft)'
  }
  return out
}

/** Aynı paftaya eklenebilen (sezgisel) disiplinler */
export const HEURISTIC_DISCIPLINES: Discipline[] = ['structural', 'architectural', 'electrical', 'mechanical']

export const ETYPE_COLORS: Record<EType, string> = {
  column: '#d62728', shear_wall: '#9467bd', beam: '#1f77b4', slab: '#2ca02c', foundation: '#ff7f0e',
  wall: '#8c564b', door: '#e377c2', window: '#17becf',
  tray: '#bcbd22', cable: '#ff9896', conduit: '#c5b0d5', fixture: '#7f7f7f',
  pipe: '#2a9d8f', duct: '#8ab17d', mech_fixture: '#e9c46a',
}

/** Alt tip açıklaması (statik: temel tipi; mimari: malzeme; elektrik: boyut/kesit/kategori) */
export const SUBTYPE_LABELS: Record<string, string> = {
  raft: 'radye', strip: 'sürekli', net: 'net alan',
  ytong: 'Ytong / gazbeton', tugla: 'Tuğla', bims: 'Bims', alcipan: 'Alçıpan', beton: 'Betonarme', tas: 'Taş',
  armatur: 'Aydınlatma armatürü', acil: 'Acil aydınlatma', priz: 'Priz', anahtar: 'Anahtar', buat: 'Buat', pano: 'Pano',
  data: 'Data / telefon', yangin: 'Yangın algılama', diger: 'Diğer',
}

export interface ProjectParams {
  wall_height: number | null
  plaster_sides: number
  paint_sides: number
  cable_drop: number
  cable_waste_pct: number
  tray_waste_pct: number
  work_hours_per_day: number
  concrete_waste_pct: number
  rebar_waste_pct: number
  tie_wire_kg_per_t: number
  plywood_sheet_m2: number
  formwork_reuse: number
  formwork_oil_l_per_m2: number
  nails_kg_per_m2: number
  /** brüt cephe alanı m² (boş: görünüşten ya da kalıp planından otomatik) */
  facade_gross_m2: number | null
  /** cephe sistemi katalog kodu (MANTOLAMA_SISTEM…); miktarı net cephe alanından */
  facade_system: string
  roof_area_m2: number | null
  roof_system: string
  /** şap / kaplama yapılan mahal türleri (virgülle) */
  finish_rooms: string
  finish_area_m2: number | null
  screed_cm: number
  lean_concrete_cm: number
  /** kapatılan türetme kuralları (virgülle) */
  derived_off: string
}

export interface Project {
  id: number
  name: string
  description: string
  storey_height: number
  slab_thickness: number
  vat_rate: number
  rebar_ratios: Record<string, number>
  params: ProjectParams
  drawing_count: number
  created_at: string
  plan_check: PlanCheckSummary
  levels?: { levels: number[]; heights: number[]; effective: number; source: string; per_drawing: Record<string, { height: number; source: string; kot: number | null }> }
}

/** Plan seti: proje için gerekli pafta tipleri (planset.py) */
export type PlanLevel = 'required' | 'optional' | 'skip'
export type PlanStatus = 'present' | 'missing' | 'skipped' | 'optional_missing'

export interface PlanType {
  code: string
  group: string
  group_label: string
  label: string
  discipline: Discipline
  level: PlanLevel
  hint: string
  analyze: boolean
  satisfies: string[]
}

export interface PlanTypeStatus extends PlanType {
  status: PlanStatus
  drawings: { id: number; label: string; discipline: Discipline }[]
  via: string | null
}

export interface PlanCheckSummary {
  missing_required: number
  present: number
  total_required: number
  complete: boolean
  warnings: string[]
}

export interface PlanCheck extends PlanCheckSummary {
  groups: { code: string; label: string; types: PlanTypeStatus[]; missing: number; present: number }[]
  unknown: { id: number; label: string; discipline: Discipline }[]
  plan_set: Record<string, PlanLevel>
  levels: PlanLevel[]
}

export interface LayerInfo {
  /** Eşleme kullanıcı onayı olmadan katman adından yapıldı (düşük güven) */
  auto?: boolean
  name: string
  count: number
  etype: string | null
  etype_label: string | null
  suggested?: string | null
  mapped_code?: string | null
  mapped_measure?: string | null
  /** etiket sayımında sayılacak yazı deseni (düzenli ifade) */
  mapped_pattern?: string | null
}

export interface Drawing {
  id: number
  project_id: number
  filename: string
  label: string
  discipline: Discipline
  plan_type: string
  storey_count: number
  storey_height: number | null
  unit: string
  unit_override: string | null
  unit_detected: boolean
  layers: LayerInfo[]
  warnings: string[]
  element_count: number
  /** Aynı paftada çizilen ek sezgisel disiplinler (mimari paftada elektrik gibi) */
  disciplines?: Discipline[]
  /** Açılmamış ama katmanlarında kanıt olan disiplinler -> geometrik nesne sayısı */
  discipline_hints?: Partial<Record<Discipline, number>>
  /** Yazı yükseklikleri / etiketlerin desteklediği birim (aynı dosyanın paftaları arasında oylama için) */
  unit_verdict?: string | null
  /** Doğrama pozları: ölçü ve kapı / pencere bilgisi (plandaki "EMP1" yazıları bununla sayılır) */
  poz?: { sizes?: Record<string, number[]>; kinds?: Record<string, string>; prefixes?: string[] }
  /** Kısa özet: durum, bulunanlar ("99 duvar · 37 pencere"), tek cümlelik not */
  status?: DrawingStatus
  found?: string
  note?: string
}

export type DrawingStatus = 'ok' | 'empty' | 'problem' | 'untyped'
export const DRAWING_STATUS: Record<DrawingStatus, { label: string; cls: string }> = {
  ok: { label: 'Okundu', cls: 'st-present' },
  empty: { label: 'Boş', cls: 'st-optional_missing' },
  problem: { label: 'Sorun', cls: 'st-missing' },
  untyped: { label: 'Tip seçilmedi', cls: 'st-skipped' },
}

/** Çok paftalı dosyada tespit edilen bir pafta (çerçeve ya da nesne kümesi) */
export interface SheetInfo {
  index: number
  title: string
  bbox: number[]
  entity_count: number
  text_count: number
  titled: boolean
  source: 'frame' | 'cluster' | 'title'
  /** Paftadaki diğer başlık adayları (ana başlık yanlış yazılmışsa kalıp planını bunlardan tanırız) */
  titles: string[]
  /** Başlıktan tanınan plan tipi ve disiplin önerisi ("" = tanınamadı) */
  plan_type: string
  plan_type_label: string
  discipline: Discipline | ''
  /** false: kesit / detay gibi metraja girmeyen pafta (önceden işaretlenmez) */
  analyze: boolean
  /** Başlıksız küçük küme (merdiven detayı, pano tablosu, lejant): plan değil, seçili gelmez */
  fragment?: boolean
}

export interface SourceInfo {
  token: string
  filename: string
  size_mb: number
  entity_count: number
  can_use_whole: boolean
  /** Başlıktaki ($INSUNITS) birim ve yazı yüksekliğinden önerilen birim (bilgi) */
  unit?: string
  suggested_unit?: string
}

/** Yükleme yanıtı: dosya çok paftalıysa önce pafta seçilir */
export interface SheetSelection {
  needs_sheet_selection: true
  source: SourceInfo
  sheets: SheetInfo[]
}

export type UploadResult = Drawing | SheetSelection

export const isSheetSelection = (r: UploadResult): r is SheetSelection =>
  (r as SheetSelection).needs_sheet_selection === true

export interface Element {
  id: number
  drawing_id: number
  etype: EType
  subtype: string | null
  name: string | null
  layer: string
  b: number | null
  h: number | null
  thickness: number | null
  area: number
  length: number
  perimeter: number
  count: number
  confidence: number
  warnings: string[]
  label_raw: string | null
  source: string
  points: number[][]
  included: boolean
  manual: boolean
  meta?: Record<string, unknown>
}

export interface QuantityGroup {
  key: string
  label: string
  etype: string
  element_count: number
  concrete_m3: number
  formwork_m2: number
  rebar_kg: number
  rebar_source: 'oran' | 'tablo' | 'poz' | 'tablo+poz' | 'tablo+oran' | 'poz+oran' | 'tablo+poz+oran'
  rebar_ratio_kg?: number
  rebar_table_kg?: number
  rebar_kots_ratio?: string[]
}

export interface RebarDia {
  dia_mm: number
  weight_kg: number
  length_m: number
  targets: Record<string, number>
}

export interface DrawingSummary {
  drawing: string
  drawing_id: number | null
  kot: string | null
  groups: Record<string, { concrete_m3: number; formwork_m2: number; rebar_kg: number; count: number }>
  concrete_m3: number
  formwork_m2: number
  rebar_kg: number
  rebar_by_dia: Record<string, number>
  rebar_table_kg?: number
  rebar_target?: string
}

export interface QuantitySummary {
  /** Kesit bazında: aynı tip ve kesitteki elemanlar tek satır (Kiriş 30x60: 98 adet, 392 m, 70,6 m³) */
  sections?: { key: string; group: string; etype: EType | string; label: string; section: string; element_count: number; length_m: number; area_m2: number; concrete_m3: number; formwork_m2: number; rebar_kg: number }[]
  groups: QuantityGroup[]
  totals: { concrete_m3: number; formwork_m2: number; rebar_kg: number }
  rebar_by_dia: RebarDia[]
  rebar_table_total_kg: number
  rebar_ratio_total_kg: number
  by_drawing: DrawingSummary[]
}

export interface QuantityLine {
  element_id: number
  etype: EType
  name: string | null
  subtype: string | null
  count: number
  multiplier: number
  concrete_m3: number
  formwork_m2: number
  rebar_kg: number
  total_concrete_m3: number
  total_formwork_m2: number
  total_rebar_kg: number
  notes: string[]
  drawing?: string
  drawing_id?: number
  layer?: string
  b?: number | null
  h?: number | null
  thickness?: number | null
  area?: number
  length?: number
  warnings: string[]
}

/** Keşif kalemi (tüm disiplinler) */
export interface BoqItem {
  key: string
  kind: string
  kind_label: string
  group: string
  label: string
  unit: string
  quantity: number
  count: number
  discipline: string
  discipline_label: string
  /** İş grubu: KABA / INCE / MEK / ELK / ALT */
  work_group: string
  work_group_label: string
  /** ÇŞB birim fiyat poz numarası (katalogdan ya da varsayılan eşlemeden; boş olabilir) */
  poz: string
  poz_name: string
  notes: string[]
  detail: Record<string, unknown>
}

export interface Boq {
  items: BoqItem[]
  by_discipline: { discipline: string; label: string; items: BoqItem[] }[]
  /** İş grubuna göre (kaba yapı, ince işler, mekanik, elektrik, altyapı) */
  by_group: { group: string; label: string; items: BoqItem[] }[]
  /** Tür toplamları: tüm duvar m², tüm cam m², tüm kapı adet… (sistem başlığı ve bilgi satırları hariç) */
  kind_totals: { kind: string; label: string; unit: string; quantity: number; count: number; items: number; work_group: string; work_group_label: string }[]
  work_groups: Record<string, string>
  /** Uygulanan ölçü kuralları (ÇŞB tarifleri) */
  rules: Record<string, { text: string; source: string }>
  kinds: Record<string, { label: string; unit: string; discipline: string }>
}

export interface QuantitiesResponse {
  summary: QuantitySummary
  lines: QuantityLine[]
  boq: Boq
  params: { storey_height: number; slab_thickness: number } & ProjectParams
  /** Kot yazılarından türeyen kat seviyeleri ve etkin kat yüksekliği (H girilmemişse bunlar kullanılır) */
  levels?: { levels: number[]; heights: number[]; effective: number; source: string; per_drawing: Record<string, { height: number; source: string; kot: number | null }> }
}

export interface PriceItem {
  id: number
  key: string
  name: string
  unit: string
  unit_price: number
  labor_price: number
  brand: string
  hours_per_unit: number
  crew_size: number
  set_fields?: string[]
  kind: string
  kind_label: string
  discipline: string
  discipline_label: string
  is_general: boolean
  work_group: string
  work_group_label: string
  /** Keşifteki miktar (genel satırda yok) */
  quantity: number | null
  poz: string
  recipe: boolean
}

/** KÇS kataloğu */
export interface CatalogItem {
  code: string
  discipline: string
  name: string
  measure: 'count' | 'length' | 'area' | 'wall_area' | 'volume' | 'label_count'
  measure_label: string
  unit: string
  spec_label: string
  example: string
  custom: boolean
  /** ÇŞB birim fiyat poz numarası (isteğe bağlı) */
  poz?: string
  /** Katmanlı sistem: ölçülünce ayrı kalem olarak yazılacak bileşenler (miktar × factor) */
  components: { code: string; factor: number; spec: string }[]
  is_system: boolean
  /** Reçete: keşfe girince kendiliğinden yazılan alt işler; times "H": çarpan × kat yüksekliği */
  recipe?: { code: string; factor: number; spec: string; times?: string }[]
  has_recipe?: boolean
}

/** Projedeki katmanlı sistemler ve bileşen kararları */
export type ComponentSource = 'project' | 'manual' | 'default' | 'missing' | 'excluded'

export interface SystemComponent {
  code: string
  name: string
  unit: string
  discipline: string
  factor: number
  default_spec: string
  spec: string
  include: boolean
  source: ComponentSource
  evidence: string[]
  quantity: number
}

export interface ProjectSystem {
  code: string
  name: string
  discipline: string
  discipline_label: string
  unit: string
  quantity: number
  spec: string
  key: string
  components: SystemComponent[]
  missing: string[]
  system_evidence: string[]
}

export interface FacadeArea {
  gross: number
  net: number
  glass: number
  source: 'measured' | 'manual' | 'estimated' | 'none'
  detail: string
  per_drawing: { drawing: string; drawing_id: number; perimeter: number; storey_height: number; storey_count: number; area: number }[]
}

export interface RoofInfo {
  area: number
  source: 'measured' | 'manual' | 'estimated' | 'none'
  detail: string
  system: string
  system_source: 'manual' | 'evidence' | ''
  candidates: string[]
}

export interface FinishArea {
  area: number
  source: 'manual' | 'rooms' | 'none'
  detail: string
  keywords: string[]
  rooms: { drawing: string; name: string; area_m2: number; included: boolean }[]
  excluded: string[]
  excluded_area: number
}

export interface DerivedItem { key: string; label: string; quantity: number; unit: string; rule: string; note: string }
export interface ChecklistItem { code: string; text: string; level: 'required' | 'optional' }

export interface ProjectSystems {
  systems: ProjectSystem[]
  warnings: string[]
  missing: number
  evidence_codes: string[]
  facade: FacadeArea
  roof: RoofInfo
  finish: FinishArea
  derived: DerivedItem[]
  derived_off: string[]
  checklist: ChecklistItem[]
}

export interface Catalog {
  disciplines: Record<string, string>
  items: CatalogItem[]
  measures: Record<string, { label: string; unit: string }>
  by_discipline: { code: string; name: string; items: CatalogItem[] }[]
}

export interface LayerCheck {
  valid: boolean
  reason?: string
  discipline?: string
  discipline_name?: string
  code?: string
  spec?: string | null
  known?: boolean
  item?: CatalogItem | null
  measure?: string
}

export interface PriceIn {
  key: string
  unit_price?: number
  labor_price?: number
  brand?: string
  hours_per_unit?: number
  crew_size?: number
  clear?: string[]
}

export interface CostLine {
  work_group: string
  work_group_label: string
  poz: string
  recipe: boolean
  key: string
  kind: string
  kind_label: string
  group: string
  group_label: string
  discipline: string
  discipline_label: string
  unit: string
  quantity: number
  brand: string
  unit_price: number
  labor_price: number
  material_total: number
  labor_total: number
  total: number
  price_source: string
  labor_source: string
  hours_per_unit: number
  crew_size: number
  hours: number
  days: number
}

export interface CostResult {
  lines: CostLine[]
  material_subtotal: number
  labor_subtotal: number
  subtotal: number
  vat_rate: number
  vat: number
  grand_total: number
  by_kind: Record<string, number>
  by_discipline: { discipline: string; label: string; material: number; labor: number; total: number; hours: number; days: number }[]
  /** İş grubu bazında (kaba yapı, ince işler, mekanik, elektrik, altyapı) */
  by_group: { group: string; label: string; material: number; labor: number; total: number; hours: number; days: number; lines: number }[]
  missing_prices: string[]
  missing_labor: string[]
  duration: { hours_per_day: number; total_hours: number; sequential_days: number; parallel_days: number; missing_rates: string[] }
}
