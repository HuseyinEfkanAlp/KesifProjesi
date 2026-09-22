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
  | 'column' | 'shear_wall' | 'beam' | 'slab' | 'foundation' | 'parapet'
  | 'wall' | 'door' | 'window'
  | 'tray' | 'cable' | 'conduit' | 'fixture'
  | 'pipe' | 'duct' | 'mech_fixture'

export const ETYPE_LABELS: Record<EType, string> = {
  column: 'Kolon',
  shear_wall: 'Perde',
  beam: 'Kiriş',
  slab: 'Döşeme',
  foundation: 'Temel',
  parapet: 'Parapet',
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
  structural: ['column', 'shear_wall', 'beam', 'slab', 'foundation', 'parapet'],
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
  column: '#d62728', shear_wall: '#9467bd', beam: '#1f77b4', slab: '#2ca02c', foundation: '#ff7f0e', parapet: '#b5651d',
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
  /** Aynı anda çalışan ekip sayısı; bir ekipteki kişi sayısı normdur (rules.CREW_SIZE) */
  crew_count: number
  concrete_waste_pct: number
  rebar_waste_pct: number
  rebar_layers?: string           // '' (çizimden oku) | 'cift' | 'tek'
  rebar_prefab_pct?: number       // hazır kesilmiş - bükülmüş gelen demir %
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
  /** projenin genel beton sınıfı (C30/37); malzeme fiyatı bu ürüne girilir */
  concrete_class: string
  /** eleman tipine özel beton sınıfı (boş: genel sınıf) */
  concrete_class_foundation: string
  concrete_class_column: string
  concrete_class_shear_wall: string
  concrete_class_beam: string
  concrete_class_slab: string
  /** grobeton sınıfı (C16/20) */
  lean_concrete_class: string
  /** donatı çeliği sınıfı (B420C) */
  rebar_grade: string
  /** kalıp malzemesi: plywood / ahsap / celik / tunel */
  formwork_material: string
}

export interface Project {
  blocks?: string[]                // kullanıcı düzeltmesi; boş = çizimden okunan liste geçerli
  /** Çizimden okunan blok bilgisi: kapsam, vaziyette görülenler, planı yüklenmemişler */
  blocks_detected?: { blocks: string[]; site: string[]; missing: string[]; source: 'cizim' | 'elle' }
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
export type PlanStatus = 'present' | 'partial' | 'missing' | 'skipped' | 'optional_missing'

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
  drawings: { id: number; label: string; discipline: Discipline; block?: string }[]
  via: string | null
  missing_blocks?: string[]        // bu tipi olmayan bloklar (C3)
}

export interface PlanCheckSummary {
  missing_required: number
  present: number
  total_required: number
  complete: boolean
  warnings: string[]
}

export interface PlanCheck extends PlanCheckSummary {
  /** Projedeki bloklar (tanımlı + çizimlerden tanınan) */
  blocks?: string[]
  /** Çizimde geçen ama proje bloklarına eklenmemiş adlar */
  site_missing?: string[]
  project_blocks?: string[]
  /** Tipi yüklü ama bazı bloklarda eksik olan plan sayısı */
  partial?: number
  groups: { code: string; label: string; types: PlanTypeStatus[]; missing: number; partial?: number; present: number }[]
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
  block?: string                   // yapı bloğu; '' = ortak / tüm bina
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
  /** Paftanın nasıl bulunduğu; "+split": kutu, içindeki pafta başlıklarına göre bölündü */
  source: string
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
  /** İçerik türü: "plan" ölçülecek çizim, "antet" proje bilgi tablosu, "bos" çizimsiz çerçeve,
   *  "cetvel" poz / ürün listesi ya da lejant (geometrisi ölçülmez, yazıları okunur) */
  kind?: 'plan' | 'antet' | 'bos' | 'cetvel'
  /** Plan olmayan içeriğin listede gösterilen açıklaması */
  kind_note?: string
}

/** Ruhsat antedinden (proje bilgi tablosu) okunanlar */
export interface TitleBlock {
  fields: Record<string, string>
  concrete_class: string
  rebar_grade: string
  foundation_kind: string
  storey_count: number | null
  area_m2: number | null
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
  /** Pafta sayılmayıp listeden çıkarılan artık küme sayısı (üç çizgilik parçalar, yalnız yazı taşıyan köşeler) */
  dropped?: number
  /** Pafta düzeninin dışına kaçmış, sınır kutusunu şişiren nesne sayısı */
  strays?: number
  /** Dosyanın antedinden okunanlar; boş proje parametrelerine yazılır */
  titleblock?: TitleBlock
  titleblock_summary?: string
}

/** Yükleme yanıtı: dosya çok paftalıysa önce pafta seçilir */
export interface SheetSelection {
  needs_sheet_selection: true
  source: SourceInfo
  sheets: SheetInfo[]
}

/** Otonom yükleme: sistem paftaları kendisi seçti, hangisini neden aldığını rapor eder */
export interface IntakeResult {
  drawings: Drawing[]
  intake: {
    picked: { index: number; title: string; plan_type: string; plan_type_label: string
              discipline: string; entity_count: number }[]
    skipped: { index: number; title: string; reason: string; entity_count: number }[]
    /** plan büyüklüğünde ama tipi tanınamayan paftalar — metraja girmedi, bildirilir */
    unknown: { index: number; title: string; reason: string; entity_count: number }[]
    note: string
  }
}

export type UploadResult = Drawing | SheetSelection | IntakeResult

export const isSheetSelection = (r: UploadResult): r is SheetSelection =>
  (r as SheetSelection).needs_sheet_selection === true

export const isIntakeResult = (r: UploadResult): r is IntakeResult =>
  Array.isArray((r as IntakeResult).drawings) && !!(r as IntakeResult).intake

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
  /** Aynı kalemi tüketen elemanların ortak anahtarı: "column|100/100". Sunucuda hesaplanır;
   *  plan önizlemesindeki çokgenin data-group değeriyle birebir aynıdır. */
  group?: string
  /** Grubun okunur etiketi: "100/100", "radye 70 cm", "30 cm ytong" */
  section?: string
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
  sources?: Record<string, number>
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
  rebar_by_source?: Record<string, number>
  warnings?: string[]
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
  /** Güven rozeti: sayının nereden geldiği (backend: app/confidence.py) */
  confidence: Confidence
}

/** Dört kademe: ölçüldü → adından tanındı → varsayımla türetildi → tahmin. En kötü girdi kazanır. */
export interface Confidence {
  code: 'olculdu' | 'tanindi' | 'turetildi' | 'tahmin'
  label: string
  icon: string
  note: string
  /** Kanıtın kademelere dağılımı (miktar payı, 0-1) */
  shares: Partial<Record<'olculdu' | 'tanindi' | 'turetildi' | 'tahmin', number>>
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
  quality: QualityReport
  summary: QuantitySummary
  lines: QuantityLine[]
  boq: Boq
  /** Çizimdeki donatı yazılarından okunan çap dağılımı: eleman tipi -> paylar ("*": proje geneli) */
  rebar_mix?: Record<string, { dia_mm: number; share: number }[]>
  /** Çap bazında demir: metraj + oran + fire, işçilik saatleri */
  rebar?: RebarReport
  /** Ana kalemler: beton / kalıp / demir / duvar / sıva / boya */
  headline?: HeadlineSection[]
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
  /** Kalemin kullandığı ürün: malzeme fiyatı buradan gelir, aynı ürünü kullanan bütün kalemler tek fiyattan
   *  hesaplanır (kolon / perde / kiriş / döşeme betonu tek "C30/37 hazır beton" satırından). Boş: salt işçilik. */
  material_key?: string
  material_name?: string
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

/** Bir mahal (ya da bağımsız bölüm) ve kendi keşif kalemleri */
export interface SpaceRow {
  key: string
  name: string
  kind: 'mahal' | 'grup'
  /** "DAİRE 1 / HOL" */
  path: string
  area: number
  label_area: number
  drawing: string
  drawing_id: number
  parent: string | null
  children: string[]
  items: BoqItem[]
  /** mahalin kendi ölçülerinden türetilenler: şap, kaplama, tavan, sıva-boya */
  derived: { key: string; kind: string; label: string; unit: string; quantity: number
             note: string; source: string; derived: true }[]
  /** mahal kodu (L_Z_01) */
  code: string
  /** çokgen çevresi (m) — 0 ise sınır doğrulanmadı */
  perimeter: number
  /** 'drawing': sınır çizimden ölçüldü ve yazıdaki alanla tutuyor · 'label': yalnız mahal yazısından */
  area_source: 'drawing' | 'label' | 'polygon'
  diff_pct: number
  finish: { code?: string; spec?: string; text?: string }
  screed_cm: number
  /** yalnız grup için: kendi + çocuklarının toplamı */
  total_items?: BoqItem[]
  total_area?: number
}

export interface SpaceBreakdown {
  spaces: SpaceRow[]
  unassigned: BoqItem[]
  unassigned_reason: string
  /** hangi pafta hangi mahal setine, ne kaymayla yazıldı */
  alignment: { drawing: string; to: string; dx: number; dy: number; how: string; hit: number; total: number }[]
  warnings: string[]
}

export interface RoofInfo {
  area: number
  source: 'measured' | 'manual' | 'estimated' | 'none'
  detail: string
  system: string
  /** 'zones': her bölge sistemini kendi içindeki nottan aldı */
  system_source: 'manual' | 'evidence' | 'zones' | ''
  candidates: string[]
  /** Çatı planındaki kapalı alanlar: bölge başına sistem ve kanıt */
  zones: { drawing: string; system: string; area: number; note: string; conflict: string[]
           source: 'note' | 'layer' | 'conflict' }[]
}

export interface FinishArea {
  area: number
  source: 'manual' | 'rooms' | 'none'
  detail: string
  keywords: string[]
  rooms: { drawing: string; name: string; area_m2: number; included: boolean
           finish: string; finish_spec: string; finish_text: string; screed_cm: number }[]
  excluded: string[]
  excluded_area: number
  /** Kaplama tipi mahal notundan okunanlar (tip başına alan) */
  by_finish: { code: string; spec: string; area: number; rooms: string[]; texts: string[] }[]
  /** Şap kalınlığı: mahal notu > çizim notu > parametre > varsayılan */
  by_screed: { cm: number; area: number; rooms: string[]; source: 'rooms' | 'drawing' | 'param' | 'default'; detail: string }[]
  /** Kaplama tipi yazılmamış alan (m²) */
  untyped_area: number
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
  /** kalemin kullandığı ürün (malzeme fiyatı buradan gelir); boş: salt işçilik kalemi */
  material_key: string
  material_name: string
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

/** Ürün (malzeme) fiyat satırı: malzeme fiyatı eleman türüne değil ürüne girilir (C30/37 beton, Ø12 demir…) */
export interface MaterialPrice {
  id: number
  key: string
  name: string
  unit: string
  unit_price: number
  brand: string
  note: string
  kind: string
  kind_label: string
  work_group: string
  work_group_label: string
  quantity: number
  /** bu ürünü kullanan keşif kalemleri */
  items: { key: string; label: string; quantity: number }[]
  in_boq: boolean
}

export interface MaterialIn {
  key: string
  unit_price?: number
  brand?: string
  note?: string
}

/** Malzeme seçim listeleri (beton sınıfı, donatı sınıfı, kalıp malzemesi) */
export interface MaterialOptions {
  concrete_classes: string[]
  concrete_types: Record<string, string>
  rebar_grades: string[]
  formwork_materials: Record<string, string>
}

/** Tedarikçi / taşeron (fiyat bankası) */
export interface Supplier {
  id: number
  name: string
  contact: string
  phone: string
  email: string
  note: string
  created_at: string
  price_count?: number
}

/** Fiyat bankasında bir ürünün bir tedarikçideki fiyat satırı */
export interface PriceBookRow {
  id: number
  scope: 'material' | 'labor'
  key: string
  name: string
  unit: string
  supplier_id: number | null
  supplier_name: string
  unit_price: number
  labor_price: number
  hours_per_unit: number
  crew_size: number
  brand: string
  note: string
  preferred: boolean
  updated_at: string
}

/** Fiyat girilebilecek ürün (ya da işçilik kalem türü) ve teklifleri */
export interface PriceBookProduct {
  key: string
  name: string
  unit: string
  discipline: string
  discipline_label: string
  work_group: string
  work_group_label: string
  rows: PriceBookRow[]
  /** geçerli fiyat: seçili satır, yoksa en düşük */
  price: number
  brand: string
  supplier_name: string
  hours_per_unit: number
  crew_size: number
  /** bu ürün projelerde geçiyor mu */
  in_projects: boolean
}

export interface PriceBook {
  scope: 'material' | 'labor'
  products: PriceBookProduct[]
  suppliers: Supplier[]
}

export interface PriceBookIn {
  key: string
  scope?: 'material' | 'labor'
  id?: number
  supplier_id?: number | null
  unit_price?: number
  labor_price?: number
  hours_per_unit?: number
  crew_size?: number
  brand?: string
  note?: string
  preferred?: boolean
}

export interface SupplierIn {
  name: string
  contact?: string
  phone?: string
  email?: string
  note?: string
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
  /** ürün bazında malzeme toplamı */
  by_material: { key: string; name: string; unit: string; brand: string; unit_price: number; quantity: number; total: number; lines: number }[]
  by_discipline: { discipline: string; label: string; material: number; labor: number; total: number; hours: number; days: number }[]
  /** İş grubu bazında (kaba yapı, ince işler, mekanik, elektrik, altyapı) */
  by_group: { group: string; label: string; material: number; labor: number; total: number; hours: number; days: number; lines: number }[]
  missing_prices: string[]
  /** fiyatı girilmemiş ürün anahtarları */
  missing_materials: string[]
  missing_labor: string[]
  missing_ranked?: MissingRanked
  duration: {
    hours_per_day: number; total_hours: number; man_days: number
    sequential_days: number; parallel_days: number
    missing_rates: string[]; missing_crew: string[]
    /** Ekibi program normundan gelen kalemler (kullanıcı girişi değil) */
    norm_crew?: string[]
    /** Bu takvim süresi için sahada gereken ortalama kişi sayısı */
    implied_headcount: number
    /** Eşzamanlı ekip sayısı (proje parametresi) */
    crew_count: number
  }
}

export interface QualityReport {
  status: 'incomplete' | 'review_required'
  label: string
  certified: boolean
  notice: string
  estimated_rebar_kg: number
  derived_counts: Record<string, number>
  issues: {
    code: string; severity: 'blocking' | 'review'; message: string; drawing_id: number | null; drawing: string | null
    /** Tek tıkla uygulanabilen düzeltme (varsa): kontrol listesinde düğme olarak çıkar */
    fix?: { action: 'storey_height_auto'; label: string }
  }[]
  assumptions: { key: string; label: string; value: string | number | null; source: 'default' | 'user' | 'drawing'
                 /** source 'drawing' ise nereden okundu (mahal notundan / çizim notundan) */
                 detail?: string }[]
  /** Sonucu ikinci bir yoldan sınayan bağımsız kontroller (backend: selfcheck.py) */
  selfcheck?: SelfCheck
  /** Kapsam sahipliği: aynı nesneyi ikinci kez çizen pafta onu tekrar saymaz (backend: quantity/scope.py) */
  scope?: ScopeReport
  /** Keşfin güven dağılımı ve tek cümlelik özeti (backend: app/confidence.py) */
  confidence?: { counts: Record<string, number>; total: number; shares: Record<string, number>; sentence: string }
  /** Çizimden türetilen kat sayısı: kot dizisi ve planı yüklenmemiş katlar (backend: app/derive.py) */
  storey_count?: { total: number | null; levels: number[]; unowned: number[] }
}

/** Hangi miktar hangi paftadan sayıldı: düşen kopya, eklenen fark, sahibi olmayan kalem. */
export interface ScopeReport {
  notes: {
    /** duplicate = ikinci kez sayılmadı, addition = yalnız bu paftada var, unmatched = eşleşmedi (ikisi de sayıldı), orphan = yetkili pafta yok */
    kind: 'duplicate' | 'addition' | 'unmatched' | 'orphan'
    etype: string; etype_label: string; block: string; kot: string | null
    drawing_id: number; drawing: string; owner_id: number | null; owner: string
    /** geometri = nesneler üst üste düştü, miktar = konum kanıtı yok */
    method: 'geometri' | 'miktar'
    dropped_count: number; dropped_qty: number; added_count: number; added_qty: number
    unit: string; severity: 'info' | 'review'; message: string
  }[]
  duplicate_count: number
  addition_count: number
}

/** Kendini doğrulayan / yanlışlayan kontroller. "kararsiz" = kontrol dairesel olurdu ya da kanıt yok. */
export interface SelfCheck {
  checks: {
    kod: string; ad: string; kapsam: string
    sonuc: 'destekliyor' | 'celisiyor' | 'kararsiz'
    aciklama: string; olculen: number | null; beklenen: string
    /** Bu kontrolü dairesel olmaktan çıkaran şey; "YOK — ..." ise kontrol bir şey kanıtlamaz */
    bagimsizlik: string
  }[]
  destekleyen: number
  celisen: number
  kararsiz: number
  ozet: string
  notice: string
}

/** Demir raporu: çap bazında metraj + oran + fire, işçilik ve sarf (backend: quantity/rebar_report.py) */
export interface RebarRow {
  dia_mm: number
  metraj_kg: number
  ratio_kg: number
  fire_kg: number
  order_kg: number
  length_m: number
  targets: Record<string, number>
  sources: Record<string, number>
}
export interface RebarReport {
  rows: RebarRow[]
  totals: { metraj_kg: number; ratio_kg: number; fire_kg: number; order_kg: number }
  unsized: { metraj_kg: number; ratio_kg: number; fire_kg: number; groups: string[] } | null
  labour: { key: string; label: string; hours: number }[]
  labour_hours: number
  extras: { key: string; label: string; quantity: number; unit: string }[]
}

/** Ana kalem (beton / kalıp / demir / duvar / sıva / boya): toplam, ayrıştırma, döküm.
 *  Backend: quantity/headline.py — `net` ölçülen, `total` sipariş (fire dahil). */
export interface HeadlineRow {
  label: string
  quantity: number
  count?: number
  /** demir: çap satırı */
  dia_mm?: number
  metraj_kg?: number
  ratio_kg?: number
  fire_kg?: number
  order_kg?: number
  length_m?: number
  targets?: Record<string, number>
  /** duvar: brüt / düşülen / zaten net */
  gross_m2?: number
  openings_m2?: number
  already_net_m2?: number
  review?: boolean
}
export interface HeadlineSection {
  kind: string
  label: string
  unit: string
  total: number
  net: number
  waste: number
  /** demir: oranla tahmin edilen kısım */
  estimated?: number
  /** duvar: brüt alan, düşülen boşluk, çizimde zaten kesilmiş boşluk */
  gross?: number
  deducted?: number
  already_net?: number
  rows: HeadlineRow[]
  unsized?: RebarReport['unsized']
  labour: { key: string; label: string; hours: number }[]
  labour_hours: number
  extras: { key: string; label: string; quantity: number; unit: string }[]
}


/** İçeri alınmış birim fiyat listesi satırı (ÇŞB / firma pozu). Bedel her şey dahildir. */
export interface PozRow {
  id: number
  poz: string
  name: string
  unit: string
  price: number
  supplier_name: string
  note: string
  updated_at: string
}

export interface PozBook {
  rows: PozRow[]
  notice: string
}

export interface PozImportResult {
  okunan: number
  atlanan: number
  tekrar: number
  yeni: number
  guncellenen: number
  ornek: { poz: string; name: string; unit: string; price: number }[]
  notice: string
}


/** Fiyatı girilmemiş kalemler, etki sırasına göre (tutar tahmini değil; büyüklük sıralaması) */
export interface MissingRanked {
  labor: { key: string; label: string; kind: string; kind_label: string; unit: string; quantity: number; hours: number; poz: string; eksik: string }[]
  materials: { key: string; name: string; unit: string; quantity: number; kalem: number }[]
  notice: string
}
