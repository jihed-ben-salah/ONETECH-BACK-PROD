"""Clean functional extraction script (multi‑image Rebut strategy)."""

import os, json, re
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
import PIL.Image
import google.generativeai as genai

try:
  import cv2  # type: ignore
  import numpy as np  # type: ignore
except ImportError:  # optional
  cv2 = None  # type: ignore
  np = None  # type: ignore

GEMINI_PRO_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
JSON_FENCE = "```json"
JSON_FENCE_BLOCK_PATTERN = r"```json\s*([\s\S]*?)\s*```"
DEFAUTS_DOC_TYPE = 'Défauts'

# ---------------- Prompts -----------------
REBUT_MULTI_PROMPT = (
  "ROLE: Expert transcription for French 'Formulaire de déclaration Rebuts'.\n"
  "GOAL: Output ONLY valid JSON with keys: document_type, header, items, notes.\n"
  "RULES: Never invent text; blank/illegible => null. Do NOT autofill total_scrapped.\n"
  "One JSON row per physical handwritten table row; skip fully blank lines; keep order.\n"
  "HEADER constraint: 'equipe' MUST be Roman numeral (I,II,III,IV,V,VI,VII,VIII,IX,X). If Arabic digit 1-10 is written convert to Roman. If any other letters (Team A, QA, L, 2A etc) -> null. Only characters I,V,X allowed.\n"
  "SCHEMA:{\n  \"document_type\": \"Rebut\",\n  \"header\": {\"jap\":null,\"ligne\":null,\"of_number\":null,\"mat_number\":null,\"equipe\":null,\"date\":null,\"visa\":null},\n  \"items\": [{\"reference\":null,\"reference_fjk\":null,\"designation\":null,\"quantity\":null,\"unit\":null,\"type\":null,\"total_scrapped\":null}],\n  \"notes\": []}\n"
  "Return ONLY that JSON object."
)

KOSU_PROMPT = (
  "Extract ONLY handwritten values from 'Suivi Productivité' form. JSON only: {"
  "\"document_type\":\"Kosu\",\"header\":{\"equipe\":null,\"nom_ligne\":null,\"code_ligne\":null,\"date\":null,\"semaine\":null,\"numero_of\":null,\"ref_pf\":null},"
  "\"team_summary\":{\"heures_deposees\":null,\"objectif_qte_eq\":null,\"qte_realisee\":null},\"remark\":null}"
  " Blank/illegible=>null. Constraint: 'equipe' must be Roman numeral I..X (convert digit 1-10 to Roman; anything else -> null)."
)

NPT_PROMPT = (
  "Extract NPT form -> JSON only: {\"document_type\":\"NPT\",\"header\":{\"uap\":null,\"date\":null,\"equipe\":null},"
  "\"downtime_events\":[{\"codes_ligne\":null,\"ref_pf\":null,\"designation\":null,\"mod_impacte\":null,\"npt_minutes\":null,\"heure_debut_d_arret\":null,\"heure_fin_d_arret\":null,\"cause_npt\":null,\"numero_di\":null,\"commentaire\":null,\"validation\":null}]}"
  " One object per handwritten row; blank->null. Constraints: 'uap' digits only (strip 'UAP', keep 1-3 digits; any letters/punctuation like '0.4' -> null). 'equipe' Roman numeral I..X (convert digit 1-10 to Roman; others -> null)."
)

# ---------------- Rebut Post‑processing -----------------
def verify_rebut_totals(img: PIL.Image.Image, data: dict, model) -> dict:
  items = data.get('items') or []
  if not items:
    return data
  summary = [{"reference": it.get('reference'), "extracted_total": it.get('total_scrapped')} for it in items]
  prompt = (
    f"Verify which TOTAL SCRAPPED cells contain handwritten digits. Rows: {json.dumps(summary, ensure_ascii=False)}\n"
    "Return JSON only {\"handwritten_totals\":[{\"reference\":ref,\"has_total\":true|false}]}. If unsure false."
  )
  try:
    resp = model.generate_content([prompt, img])
    txt = resp.text or '{}'
    if JSON_FENCE in txt:
      txt = re.search(JSON_FENCE_BLOCK_PATTERN, txt).group(1)
    verdict = json.loads(txt).get('handwritten_totals', [])
    vmap = {v.get('reference'): v.get('has_total') for v in verdict if isinstance(v, dict)}
    for it in items:
      if vmap.get(it.get('reference')) is False:
        it['total_scrapped'] = None
  except Exception as e:
    print(f"[Rebut] totals verify fail: {e}")
  return data

def recover_rebut_missing_rows(img: PIL.Image.Image, data: dict, model) -> dict:
  items = data.get('items') or []
  slim = [{"reference": it.get('reference'), "quantity": it.get('quantity')} for it in items]
  prompt = (
    f"Find ADDITIONAL Rebut rows with handwriting not in: {json.dumps(slim, ensure_ascii=False)}\n"
    "Return JSON {\"additional_items\":[{...}]} using same schema. Only rows with handwriting. Blank->null."
  )
  try:
    resp = model.generate_content([prompt, img])
    txt = resp.text or '{}'
    if JSON_FENCE in txt:
      txt = re.search(JSON_FENCE_BLOCK_PATTERN, txt).group(1)
    add = json.loads(txt).get('additional_items', [])
    existing = {it.get('reference') for it in items}
    cleaned: List[Dict[str, Any]] = []
    for it in add:
      if not isinstance(it, dict):
        continue
      for k,v in list(it.items()):
        if isinstance(v, str) and v.strip().lower() in ('', 'null'):
          it[k] = None
      ref = it.get('reference')
      if ref in existing and not any(it.get(k) for k in ['designation','quantity','unit','type','total_scrapped','reference_fjk']):
        continue
      cleaned.append({k: it.get(k) for k in ['reference','reference_fjk','designation','quantity','unit','type','total_scrapped']})
    if cleaned:
      data['items'] = items + cleaned
  except Exception as e:
    print(f"[Rebut] row recovery fail: {e}")
  return data

# ---------------- Rebut de-duplication -----------------
def _parse_number(val):
  if isinstance(val, (int, float)):
    return val
  if isinstance(val, str):
    s = val.strip().replace(',', '.')
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
      try:
        return float(s)
      except Exception:
        return None
  return None

def deduplicate_rebut_items(data: dict) -> dict:
  items = data.get('items') or []
  if not items:
    return data
  seen_order = []
  by_ref: Dict[str, Dict[str, Any]] = {}
  for row in items:
    ref = row.get('reference')
    if not ref or (isinstance(ref, str) and not ref.strip()):
      # keep anonymous rows as-is (can't safely dedupe)
      anon_key = f"__anon__{len(seen_order)}"
      seen_order.append(anon_key)
      by_ref[anon_key] = row
      continue
    norm = ref.strip()
    if norm not in by_ref:
      seen_order.append(norm)
      by_ref[norm] = row
      continue
    existing = by_ref[norm]
    # Count non-null fields in new row
    non_null_fields = [k for k,v in row.items() if v not in (None, '', 'null')]
    # If sparse (<=1 meaningful field) treat as noise unless it provides a missing total
    if len(non_null_fields) <= 2:  # allow reference + maybe one value
      # Possible mis-filed scrap count placed under quantity
      new_qty = _parse_number(row.get('quantity'))
      if (existing.get('total_scrapped') in (None, '', 'null') and
          new_qty is not None and new_qty <= 50 and
          # ensure existing quantity is different style (likely real quantity with decimal/comma)
          _parse_number(existing.get('quantity')) != new_qty):
        existing['total_scrapped'] = int(new_qty) if float(new_qty).is_integer() else new_qty
      # Fill any missing descriptor fields if provided
      for f in ['designation','unit','type','reference_fjk']:
        if existing.get(f) in (None,'','null') and row.get(f) not in (None,'','null'):
          existing[f] = row.get(f)
      continue
    # For richer duplicate, attempt merge (rare)
    for f,v in row.items():
      if f == 'reference':
        continue
      if existing.get(f) in (None,'','null') and v not in (None,'','null'):
        existing[f] = v
  # Rebuild list preserving first occurrence order
  data['items'] = [by_ref[k] for k in seen_order]
  return data

# ---------------- Rebut numeric normalization -----------------
def normalize_rebut_numeric_fields(data: dict) -> dict:
  items = data.get('items') or []
  changed = False
  for it in items:
    q = it.get('quantity')
    if isinstance(q, str):
      qs = q.strip().replace(',', '.').replace(' ', '')
      if re.fullmatch(r"-?\d+(\.\d+)?", qs):
        try:
          num = float(qs)
          it['quantity'] = int(num) if num.is_integer() else num
        except Exception:
          it['quantity'] = None; changed = True
      else:
        it['quantity'] = None; changed = True
    ts = it.get('total_scrapped')
    if isinstance(ts, str):
      ts_s = ts.strip().replace(',', '.').replace(' ', '')
      if re.fullmatch(r"\d+", ts_s):
        try:
          it['total_scrapped'] = int(ts_s)
        except Exception:
          it['total_scrapped'] = None; changed = True
      else:
        it['total_scrapped'] = None; changed = True
    if isinstance(it.get('quantity'), (int,float)) and isinstance(it.get('total_scrapped'), (int,float)):
      if it['total_scrapped'] > it['quantity'] * 5 and it['total_scrapped'] > 50:
        it['total_scrapped'] = None; changed = True
  if changed:
    data['items'] = items
  return data

# ---------------- Image helpers -----------------
def preprocess_for_ocr(img: PIL.Image.Image) -> PIL.Image.Image:
  try:
    if cv2 is None or np is None:
      return img.convert('L')
    g = cv2.cvtColor(np.array(img.convert('RGB')), cv2.COLOR_RGB2GRAY)
    b = cv2.adaptiveThreshold(g,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,35,11)
    if (b>200).mean() < 0.4: b = 255 - b
    return PIL.Image.fromarray(b)
  except Exception:
    return img

def discover_rebut_crop_paths(base_image_path: str) -> List[str]:
  p = Path(base_image_path); stem = p.stem
  exts = {'.png','.jpg','.jpeg','.PNG','.JPG','.JPEG'}
  c: List[Path] = []
  for f in p.parent.glob(f"{stem}_crop*"):
    if f.suffix in exts and f.is_file(): c.append(f)
  crops = p.parent / 'crops'
  if crops.is_dir():
    for f in crops.glob(f"{stem}*"):
      if f.suffix in exts and f.is_file(): c.append(f)
  return [str(f) for f in sorted(set(c))][:12]

def gather_rebut_images_with_preprocessing(base_image_path: str) -> List[PIL.Image.Image]:
  out: List[PIL.Image.Image] = []
  for p in discover_rebut_crop_paths(base_image_path):
    try:
      out.append(preprocess_for_ocr(PIL.Image.open(p)))
    except Exception as e:
      print(f"[Rebut] crop load {p} failed: {e}")
  return out

# ---------------- Défauts simple placeholder -----------------
#########################
#  DEFauts Multi-Pass   #
#########################

DEFAUTS_PRIMARY_PROMPT = (
  "ROLE: Transcribe ONLY handwritten info from 'FORMULAIRE ENREGISTREMENT QUALITE (Défauts POSTE)'. "
  "OUTPUT: EXACTLY one JSON object – no commentary. BLANK or illegible => null. DO NOT GUESS. "
  "SCHEMA:{\n  \"document_type\":\"Défauts\",\n  \"entry_header\":{\"uap\":null,\"ligne\":null,\"n_poste\":null,\"operation\":null,\"code_famillier\":null,\"semaine\":null,\"annee\":null,\"mois\":null},\n  \"recorded_defects\":[{\"code\":null,\"day\":null,\"station\":null,\"raw_mark\":null}],\n  \"notes\":[]}\n"
  "RULES:\n- Only create a recorded_defects entry if a cell has a CLEAR handwritten mark.\n"
  "- Use day ENUM [Lun,Mar,Mer,Jeu,Ven,Sam]; if unsure -> null.\n"
  "- Use station ENUM [E1,E2,E3]; if unsure -> null.\n"
  "- code: copy the handwritten code (letters/numbers/dash) else null.\n"
  "- raw_mark: keep raw symbol ('X','XX','2X','3','✔'), do NOT aggregate.\n"
  "- NEVER fabricate rows to complete a pattern.\n"
  "FILTER: Ignore printed template artifacts or faint shadows." )

DEFAUTS_VERIFY_PROMPT_TEMPLATE = (
  """You will verify defect marks. For each entry decide if the raw_mark is a real handwritten mark. 
If ambiguous / artifact -> false. Return JSON {"verified":[{"index":i,"keep":true|false}]}."""
)

DEFAUTS_RECOVERY_PROMPT_TEMPLATE = (
  """Find additional handwritten defect marks (code/day/station) NOT in the provided list. 
Return JSON {"additional":[{"code":null,"day":null,"station":null,"raw_mark":null}]}. Only real marks; blank cells -> none."""
)

DEFAUTS_DAY_ALIASES = {"LUN":"Lun","MAR":"Mar","MER":"Mer","JEU":"Jeu","VEN":"Ven","SAM":"Sam"}

def discover_defauts_crop_paths(base_image_path: str) -> List[str]:
  # Reuse same pattern (_crop*, crops/ dir)
  return discover_rebut_crop_paths(base_image_path)

def gather_defauts_images_with_preprocessing(base_image_path: str) -> List[PIL.Image.Image]:
  out: List[PIL.Image.Image] = []
  for p in discover_defauts_crop_paths(base_image_path):
    try:
      out.append(preprocess_for_ocr(PIL.Image.open(p)))
    except Exception as e:
      print(f"[Défauts] crop load {p} fail: {e}")
  return out

def normalize_defauts_mark(raw: Any) -> Optional[int]:
  if raw is None:
    return None
  if isinstance(raw, (int, float)):
    return int(raw) if float(raw).is_integer() else int(raw)
  if not isinstance(raw, str):
    return None
  s = raw.strip().upper()
  if s == '':
    return None
  # Patterns: digits, repeated X/✓/✔, mixed '2X'
  if re.fullmatch(r"\d+", s):
    try: return int(s)
    except: return None
  # 2X or 3X etc
  m = re.fullmatch(r"(\d+)X", s)
  if m:
    try: return int(m.group(1))
    except: return None
  # Count repeated X / ✓ / ✔
  if re.fullmatch(r"[X✓✔]+", s):
    return len(s)
  return None

def normalize_defauts_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
  out = []
  for i,r in enumerate(records):
    code = r.get('code')
    day = r.get('day')
    station = r.get('station')
    raw_mark = r.get('raw_mark')
    count = normalize_defauts_mark(raw_mark)
    # Standardize day capitalization
    if isinstance(day,str):
      d = day.strip().title()
      if d.upper() in DEFAUTS_DAY_ALIASES: d = DEFAUTS_DAY_ALIASES[d.upper()]
      day = d
    out.append({
      'code': code.strip() if isinstance(code,str) else code,
      'day': day,
      'station': station.strip().upper() if isinstance(station,str) else station,
      'raw_mark': raw_mark,
      'count': count
    })
  return out

def compute_defauts_daily_totals(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
  totals: Dict[tuple, int] = {}
  for r in records:
    c = r.get('count')
    if c is None: continue
    key = (r.get('day'), r.get('station'))
    totals[key] = totals.get(key, 0) + int(c)
  return [ {'day':k[0],'station':k[1],'total_defauts':v} for k,v in sorted(totals.items()) ]

def refine_defauts_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
  seen = set()
  filtered: List[Dict[str, Any]] = []
  for r in records:
    day = r.get('day')
    station = r.get('station')
    raw = r.get('raw_mark')
    code = r.get('code')
    count = r.get('count')
    if raw in (None,'','null') and count in (None,'','null'):
      continue
    if day not in (None,'Lun','Mar','Mer','Jeu','Ven','Sam'):
      day = None
    if station not in (None,'E1','E2','E3'):
      station = None
    if isinstance(code,str):
      c = code.strip().upper()
      if not re.fullmatch(r"[A-Z0-9\-]{1,10}", c):
        code = None
      else:
        code = c
    key = (code, day, station, raw)
    if key in seen:
      continue
    seen.add(key)
    if isinstance(count, int) and count > 50:
      r['count'] = None
    r['code'] = code; r['day'] = day; r['station'] = station
    filtered.append(r)
  return filtered

def verify_defauts_marks(base_img: PIL.Image.Image, crops: List[PIL.Image.Image], data: dict, model) -> dict:
  recs = data.get('recorded_defects') or []
  if not recs: return data
  brief = [ {'index':i,'code':r.get('code'),'day':r.get('day'),'station':r.get('station'),'raw_mark':r.get('raw_mark')} for i,r in enumerate(recs) ]
  prompt = DEFAUTS_VERIFY_PROMPT_TEMPLATE + "\nEntries:" + json.dumps(brief, ensure_ascii=False)
  try:
    resp = model.generate_content([prompt, base_img] + crops)
    txt = resp.text or '{}'
    if JSON_FENCE in txt: txt = re.search(JSON_FENCE_BLOCK_PATTERN, txt).group(1)
    parsed = json.loads(txt)
    keep_map = {e.get('index'): e.get('keep') for e in parsed.get('verified', []) if isinstance(e, dict)}
    filtered = [r for i,r in enumerate(recs) if keep_map.get(i) is not False]
    data['recorded_defects'] = filtered
  except Exception as e:
    print(f"[Défauts] verify pass fail: {e}")
  return data

def recover_defauts_missing_marks(base_img: PIL.Image.Image, crops: List[PIL.Image.Image], data: dict, model) -> dict:
  recs = data.get('recorded_defects') or []
  existing = [ {'code':r.get('code'),'day':r.get('day'),'station':r.get('station')} for r in recs ]
  prompt = DEFAUTS_RECOVERY_PROMPT_TEMPLATE + "\nExisting:" + json.dumps(existing, ensure_ascii=False)
  try:
    resp = model.generate_content([prompt, base_img] + crops)
    txt = resp.text or '{}'
    if JSON_FENCE in txt: txt = re.search(JSON_FENCE_BLOCK_PATTERN, txt).group(1)
    parsed = json.loads(txt)
    add = parsed.get('additional', []) if isinstance(parsed, dict) else []
    cleaned = []
    present_keys = {(r.get('code'),r.get('day'),r.get('station')) for r in recs}
    for r in add:
      if not isinstance(r, dict): continue
      key = (r.get('code'), r.get('day'), r.get('station'))
      if key in present_keys: continue
      if all(r.get(f) in (None,'','null') for f in ['raw_mark']):
        continue
      cleaned.append(r)
    if cleaned:
      data['recorded_defects'] = recs + cleaned
  except Exception as e:
    print(f"[Défauts] recovery pass fail: {e}")
  return data

def extract_defauts_multi(image_path: str, model) -> Dict[str, Any]:
  try:
    base = PIL.Image.open(image_path)
  except FileNotFoundError:
    print('[Défauts] image not found')
    return {}
  crops = gather_defauts_images_with_preprocessing(image_path)
  try:
    resp = model.generate_content([DEFAUTS_PRIMARY_PROMPT, base] + crops if crops else [DEFAUTS_PRIMARY_PROMPT, base])
    txt = resp.text or '{}'
    if JSON_FENCE in txt: txt = re.search(JSON_FENCE_BLOCK_PATTERN, txt).group(1)
    parsed = json.loads(txt)
  except Exception as e:
    print(f"[Défauts] primary fail: {e}")
    return {}
  if parsed.get('document_type') != DEFAUTS_DOC_TYPE:
    parsed['document_type'] = DEFAUTS_DOC_TYPE
  # Ensure keys
  parsed.setdefault('entry_header', {k: None for k in ["uap","ligne","n_poste","operation","code_famillier","semaine","annee","mois"]})
  parsed.setdefault('recorded_defects', [])
  # Verify + recovery + re-verify
  parsed = verify_defauts_marks(base, crops, parsed, model)
  parsed = recover_defauts_missing_marks(base, crops, parsed, model)
  parsed = verify_defauts_marks(base, crops, parsed, model)
  # Normalize & totals
  norm = normalize_defauts_records(parsed.get('recorded_defects', []))
  norm = refine_defauts_records(norm)
  parsed['recorded_defects'] = norm
  parsed['defects_log'] = norm
  parsed['summary_data'] = {'daily_totals': compute_defauts_daily_totals(norm)}
  print(f"[Défauts] marks after normalization/refine: {len(norm)}")
  return {"data": parsed, "remark": f"Défauts extraction complete: {len(norm)} marks (refined)"}

# ---------------- Orchestrator -----------------
PROMPT_MAP = {'Rebut': REBUT_MULTI_PROMPT, 'Kosu': KOSU_PROMPT, 'NPT': NPT_PROMPT, DEFAUTS_DOC_TYPE: DEFAUTS_PRIMARY_PROMPT, 'Defauts': DEFAUTS_PRIMARY_PROMPT}

def extract_data_from_image(image_path: str, doc_type: str) -> Dict[str, Any]:
  model = genai.GenerativeModel(GEMINI_PRO_MODEL)
  if doc_type in ['Défauts','Defauts']:
    return extract_defauts_multi(image_path, model)
  try:
    base = PIL.Image.open(image_path)
  except FileNotFoundError:
    print("Image not found")
    return {}
  prompt = PROMPT_MAP.get(doc_type)
  if not prompt:
    print("Unsupported doc_type")
    return {}
  crops: List[PIL.Image.Image] = []
  if doc_type == 'Rebut':
    crops = gather_rebut_images_with_preprocessing(image_path)
  try:
    resp = model.generate_content([prompt, base] + crops if (doc_type=='Rebut' and crops) else [prompt, base])
    txt = resp.text or '{}'
    if JSON_FENCE in txt:
      txt = re.search(JSON_FENCE_BLOCK_PATTERN, txt).group(1)
    data = json.loads(txt)
    data.setdefault('document_type', doc_type)
  except Exception as e:
    print(f"Primary extraction fail: {e}")
    return {}
  if doc_type == 'Rebut':
    data = verify_rebut_totals(base, data, model)
    data = recover_rebut_missing_rows(base, data, model)
    data = verify_rebut_totals(base, data, model)
  data = deduplicate_rebut_items(data)
  data = verify_rebut_totals(base, data, model)
  data = normalize_rebut_numeric_fields(data)
  return {"data": data, "remark": f"{doc_type} extraction complete"}

# ---------------- Excel export -----------------
def save_data_to_excel(data: Dict[str, Any], output_filename: str):
  if not data:
    print("No data to export")
    return
  doc_type = data.get('document_type')
  try:
    with pd.ExcelWriter(output_filename, engine='openpyxl') as w:
      if doc_type == 'NPT':
        pd.DataFrame(data.get('downtime_events', [])).to_excel(w, 'Downtime Events', index=False)
      elif doc_type == 'Rebut':
        pd.DataFrame(data.get('items', [])).to_excel(w, 'Rebut Items', index=False)
      elif doc_type in ['Défauts','Defauts']:
        if 'entry_header' in data:
          pd.DataFrame([data['entry_header']]).to_excel(w, 'entry_header', index=False)
        if 'recorded_defects' in data:
          pd.DataFrame(data['recorded_defects']).to_excel(w, 'defects', index=False)
        if 'summary_data' in data:
          summary_val = data['summary_data']
          if isinstance(summary_val, dict):
            others = {k:v for k,v in summary_val.items() if k != 'daily_totals'}
            if others:
              pd.DataFrame([others]).to_excel(w, 'summary_meta', index=False)
            if isinstance(summary_val.get('daily_totals'), list):
              pd.DataFrame(summary_val['daily_totals']).to_excel(w, 'daily_totals', index=False)
          else:
            pd.DataFrame([summary_val]).to_excel(w, 'summary_data', index=False)
        if 'notes' in data and isinstance(data['notes'], list):
          pd.DataFrame(data['notes']).to_excel(w, 'notes', index=False)
      elif doc_type == 'Kosu':
        pd.DataFrame([data.get('team_summary', {})]).to_excel(w, 'Team Summary', index=False)
      else:
        for k,v in data.items():
          if isinstance(v, list) and v and isinstance(v[0], dict):
            pd.DataFrame(v).to_excel(w, k[:31], index=False)
          elif isinstance(v, dict):
            pd.DataFrame([v]).to_excel(w, k[:31], index=False)
    print(f"Excel saved: {output_filename}")
  except Exception as e:
    print(f"Excel export failed: {e}")

# ---------------- CLI -----------------
if __name__ == '__main__':
  import argparse
  p = argparse.ArgumentParser()
  p.add_argument('--image', required=True)
  p.add_argument('--type', required=True, choices=['Rebut','NPT','Kosu','Défauts','Defauts'])
  p.add_argument('--excel', default='output.xlsx')
  p.add_argument('--json', default='output.json')
  a = p.parse_args()
  res = extract_data_from_image(a.image, a.type)
  if res:
    Path(a.excel).parent.mkdir(parents=True, exist_ok=True)
    with open(a.json,'w',encoding='utf-8') as f:
      json.dump(res, f, ensure_ascii=False, indent=2)
    save_data_to_excel(res.get('data', {}), a.excel)
