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
  "ROLE: Expert form transcription specialist.\n"
  "CRITICAL MISSION: Extract EXACTLY what is handwritten in EACH field location. NO interpretation, NO correction, NO assumptions.\n"
  "SCHEMA EXACT: {\n"
  "  \"document_type\": \"Kosu\",\n"
  "  \"Titre du document\": null,\n"
  "  \"Référence du document\": null,\n"
  "  \"Date du document\": null,\n"
  "  \"Equipe\": null,\n"
  "  \"Nom Ligne\": null,\n"
  "  \"Code ligne\": null,\n"
  "  \"Jour\": null,\n"
  "  \"Semaine\": null,\n"
  "  \"Numéro OF\": null,\n"
  "  \"Ref PF\": null,\n"
  "  \"Suivi horaire\": [ { \"Heure\": null, \"Nombre d'Opérateurs\": null, \"Objectif Qté / H\": null, \"Quantité pièces bonnes\": null, \"Productivité\": null } ],\n"
  "  \"Total / Equipe\": { \"Heures Dépensées\": null, \"Objectif Qté / EQ\": null, \"Qté pièces Bonnes / EQ\": null, \"Productivité / EQ\": null },\n"
  "  \"Règles d'escalade\": [ { \"Productivité\": null, \"Personne à informer\": null } ],\n"
  "  \"remark\": null\n"
  "}\n"
  "ABSOLUTE RULES (ZERO TOLERANCE FOR VIOLATIONS):\n"
  "1. Look at EACH field's specific location on the form - DO NOT copy values between fields\n"
  "2. 'Nom Ligne' = ALWAYS a descriptive TEXT/STRING (words, names, descriptions)\n"
  "3. 'Code ligne' = ALWAYS a NUMERIC VALUE (numbers only: 1, 2, 10, 25, etc.)\n"
  "4. If you see text in Code ligne field -> it's WRONG, extract the number only\n"
  "5. If you see numbers in Nom Ligne field -> look again, should be text description\n"
  "6. These fields are COMPLETELY DIFFERENT and MUST have different types of values\n"
  "7. Copy EXACTLY what you see handwritten - no cleaning, no formatting, no interpretation\n"
  "8. Empty/illegible = null. NEVER guess or invent values\n"
  "9. VERIFICATION: Code ligne should be numeric, Nom Ligne should be text\n"
  "EXAMPLES:\n"
  "- Correct: \"Nom Ligne\": \"Ligne production A\", \"Code ligne\": \"15\"\n"
  "- Correct: \"Nom Ligne\": \"Montage\", \"Code ligne\": \"3\"\n"
  "- WRONG: \"Nom Ligne\": \"15\", \"Code ligne\": \"15\" (both numeric)\n"
  "- WRONG: \"Nom Ligne\": \"Production\", \"Code ligne\": \"Production\" (same value)\n"
  "Return ONLY the JSON object."
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

# ---------------- Kosu verification and recovery (like Rebut) -----------------
def verify_kosu_header(img: PIL.Image.Image, data: dict, model) -> dict:
  """Verify header fields with safe error handling."""
  if not isinstance(data, dict):
    print("[verify_kosu_header] Data is not a dict")
    return data
    
  header_fields = ['Equipe', 'Nom Ligne', 'Code ligne', 'Jour', 'Semaine', 'Numéro OF', 'Ref PF']
  header_summary = {k: data.get(k) for k in header_fields}
  
  # Check for suspicious duplicate values
  duplicate_issues = []
  values = [v for v in header_summary.values() if v not in (None, '', 'null')]
  for i, v1 in enumerate(values):
    for j, v2 in enumerate(values):
      if i != j and v1 == v2:
        fields_with_same_value = [k for k, val in header_summary.items() if val == v1]
        if len(fields_with_same_value) > 1:
          duplicate_issues.append(f"SUSPICIOUS: '{v1}' appears in multiple fields: {fields_with_same_value}")
  
  prompt = (
    f"Verify EACH header field separately in this Kosu form. Current extraction: {json.dumps(header_summary, ensure_ascii=False)}\n"
    f"ATTENTION: Duplicate value issues detected: {duplicate_issues}\n"
    "Look at the form and verify EACH field independently:\n"
    "- 'Nom Ligne': Usually a descriptive name (text)\n"
    "- 'Code ligne': Usually a short code/number (alphanumeric)\n"
    "- 'Equipe': Team identifier (number or roman numeral)\n"
    "- Other fields: Check actual handwritten values\n\n"
    "Return JSON only: {\"header_corrections\": [{\"field\": \"field_name\", \"extracted_value\": \"current\", \"correct_value\": \"actual_handwritten_or_null\"}]}\n"
    "CRITICAL RULES:\n"
    "- Look at EACH field location separately on the form\n"
    "- If two fields have same value but different locations have different writing -> correct them\n"
    "- Copy EXACTLY what is handwritten in each specific field location\n"
    "- If field is blank/illegible -> null\n"
    "- DO NOT assume similar fields have similar values"
  )
  
  text = safe_model_call(model, [prompt, img], "verify_kosu_header")
  if not text:
    return data
    
  result = safe_json_parse(text, {}, "verify_kosu_header")
  corrections = result.get('header_corrections', []) if isinstance(result, dict) else []
  
  for correction in corrections:
    if not isinstance(correction, dict):
      continue
    field = correction.get('field')
    correct_value = correction.get('correct_value')
    if field in data and correct_value is not None:
      print(f"[Kosu] Corrected {field}: '{correction.get('extracted_value')}' -> '{correct_value}'")
      data[field] = correct_value
  
  return data

def recover_kosu_missing_header(img: PIL.Image.Image, data: dict, model) -> dict:
  """Find missing header fields with safe error handling."""
  if not isinstance(data, dict):
    print("[recover_kosu_missing_header] Data is not a dict")
    return data
    
  header_fields = ['Equipe', 'Nom Ligne', 'Code ligne', 'Jour', 'Semaine', 'Numéro OF', 'Ref PF']
  current_values = {k: data.get(k) for k in header_fields}
  empty_fields = [k for k, v in current_values.items() if v in (None, '', 'null')]
  
  if not empty_fields:
    return data
    
  prompt = (
    f"Find handwritten values for these empty header fields: {empty_fields}\n"
    f"Current values: {json.dumps(current_values, ensure_ascii=False)}\n"
    "Return JSON only: {\"recovered_fields\": [{\"field\": \"field_name\", \"value\": \"handwritten_value_or_null\"}]}\n"
    "RULES: Extract EXACTLY what is handwritten. No guessing or interpretation."
  )
  
  text = safe_model_call(model, [prompt, img], "recover_kosu_missing_header")
  if not text:
    return data
    
  result = safe_json_parse(text, {}, "recover_kosu_missing_header")
  recovered = result.get('recovered_fields', []) if isinstance(result, dict) else []
  
  for recovery in recovered:
    if not isinstance(recovery, dict):
      continue
    field = recovery.get('field')
    value = recovery.get('value')
    if field in empty_fields and value not in (None, '', 'null'):
      print(f"[Kosu] Recovered {field}: '{value}'")
      data[field] = value
  
  return data

def verify_kosu_table_data(img: PIL.Image.Image, data: dict, model) -> dict:
  """Verify table data with safe error handling."""
  if not isinstance(data, dict):
    print("[verify_kosu_table_data] Data is not a dict")
    return data
    
  suivi = data.get('Suivi horaire', [])
  if not suivi:
    return data
    
  # Create summary of current table data
  table_summary = []
  for i, row in enumerate(suivi[:8]):  # Focus on hours 1-8
    if any(row.get(k) not in (None, '', 'null') for k in row.keys() if k != 'Heure'):
      table_summary.append({
        'row_index': i,
        'heure': row.get('Heure'),
        'has_data': True,
        'values': {k: v for k, v in row.items() if k != 'Heure' and v not in (None, '', 'null')}
      })
  
  prompt = (
    f"Verify handwritten table data for Suivi horaire. Current extraction: {json.dumps(table_summary, ensure_ascii=False)}\n"
    "Check if the extracted values match actual handwriting in the hourly tracking table.\n"
    "Return JSON only: {\"table_corrections\": [{\"row_index\": i, \"field\": \"field_name\", \"correct_value\": \"actual_handwritten_or_null\"}]}\n"
    "RULES: Only extract what is clearly handwritten. No calculations or interpretations."
  )
  
  text = safe_model_call(model, [prompt, img], "verify_kosu_table_data")
  if not text:
    return data
    
  result = safe_json_parse(text, {}, "verify_kosu_table_data")
  corrections = result.get('table_corrections', []) if isinstance(result, dict) else []
  
  for correction in corrections:
    if not isinstance(correction, dict):
      continue
    row_idx = correction.get('row_index')
    field = correction.get('field')
    correct_value = correction.get('correct_value')
    
    if (isinstance(row_idx, int) and 0 <= row_idx < len(suivi) and 
        field in suivi[row_idx] and correct_value is not None):
      suivi[row_idx][field] = correct_value
      
  return data

# ---------------- Kosu post-processing (French schema) -----------------
ROMAN_MAP = {1:'I',2:'II',3:'III',4:'IV',5:'V',6:'VI',7:'VII',8:'VIII',9:'IX',10:'X'}
VALID_ROMANS = set(ROMAN_MAP.values())

def _to_number(val):
  if isinstance(val,(int,float)): return val
  if isinstance(val,str):
    s = val.strip().replace(',', '.').replace(' ', '')
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
      try:
        f = float(s)
        return int(f) if f.is_integer() else f
      except: return None
  return None

def post_process_kosu(data: dict) -> dict:
  """Minimal post-processing - only basic cleanup, no interpretation."""
  if not isinstance(data, dict):
    return data
    
  # Only normalize Equipe if it's clearly a digit that should be Roman
  equipe = data.get('Equipe')
  if isinstance(equipe, str) and equipe.strip().isdigit():
    digit = int(equipe.strip())
    if 1 <= digit <= 10:
      data['Equipe'] = ROMAN_MAP.get(digit, equipe)
  elif isinstance(equipe, (int, float)) and 1 <= int(equipe) <= 10:
    data['Equipe'] = ROMAN_MAP.get(int(equipe), equipe)
  
  # Ensure Suivi horaire has proper structure (don't fill missing hours automatically)
  sh = data.get('Suivi horaire', [])
  if isinstance(sh, list):
    cleaned_rows = []
    for r in sh:
      if isinstance(r, dict):
        # Only keep rows that have actual data
        if any(v not in (None, '', 'null') for v in r.values()):
          cleaned_rows.append(r)
    data['Suivi horaire'] = cleaned_rows
  
  # Clean Total / Equipe - keep as extracted
  te = data.get('Total / Equipe', {})
  if isinstance(te, dict):
    # Only basic type conversion for clearly numeric values
    for k, v in te.items():
      if isinstance(v, str) and v.strip().replace(',', '.').replace(' ', '').isdigit():
        try:
          te[k] = int(float(v.strip().replace(',', '.')))
        except:
          pass  # Keep original value
  
  return data

# ---------------- Safe Model Call Wrappers -----------------
def safe_model_call(model, inputs, operation_name="extraction"):
  """Safe wrapper for model calls with comprehensive error handling."""
  try:
    if not inputs:
      print(f"[{operation_name}] No inputs provided")
      return None
      
    resp = model.generate_content(inputs)
    if not resp:
      print(f"[{operation_name}] Model returned None response")
      return None
      
    if not hasattr(resp, 'text') or resp.text is None:
      print(f"[{operation_name}] Model response has no text")
      return None
      
    return resp.text
  except Exception as e:
    print(f"[{operation_name}] Model call failed: {e}")
    return None

def safe_json_parse(text, default=None, operation_name="parsing"):
  """Safe JSON parsing with fallback."""
  if not text:
    print(f"[{operation_name}] Empty text provided")
    return default or {}
    
  try:
    # Extract JSON from markdown if present
    if JSON_FENCE in text:
      match = re.search(JSON_FENCE_BLOCK_PATTERN, text)
      if match:
        text = match.group(1)
      else:
        print(f"[{operation_name}] JSON fence found but no content extracted")
        return default or {}
    
    result = json.loads(text)
    if result is None:
      print(f"[{operation_name}] JSON parsed to None")
      return default or {}
      
    return result
  except json.JSONDecodeError as e:
    print(f"[{operation_name}] JSON decode error: {e}")
    return default or {}
  except Exception as e:
    print(f"[{operation_name}] Unexpected parsing error: {e}")
    return default or {}

# ---------------- Enhanced Image Processing -----------------
def preprocess_for_ocr(img: PIL.Image.Image) -> PIL.Image.Image:
  try:
    if cv2 is None or np is None:
      return img.convert('L')
    
    # Convert to grayscale
    g = cv2.cvtColor(np.array(img.convert('RGB')), cv2.COLOR_RGB2GRAY)
    
    # Multiple preprocessing approaches for better handwriting detection
    # 1. Adaptive threshold (existing)
    adaptive = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 11)
    
    # 2. Morphological operations to clean noise
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(adaptive, cv2.MORPH_CLOSE, kernel)
    
    # 3. Contrast enhancement using CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(g)
    
    # 4. Choose best version based on content
    if (cleaned > 200).mean() < 0.4:
      cleaned = 255 - cleaned
    
    # 5. Sharpen for better text clarity
    kernel_sharpen = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(enhanced, -1, kernel_sharpen)
    
    # Combine enhanced and cleaned versions
    final = cv2.addWeighted(cleaned, 0.7, sharpened, 0.3, 0)
    
    return PIL.Image.fromarray(final)
  except Exception as e:
    print(f"Enhanced preprocessing failed: {e}, using basic conversion")
    return img.convert('L')

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

# ---------------- Kosu multi-segment support -----------------
def slice_vertical_segments(img: PIL.Image.Image, max_height: int = 1400, overlap: int = 120) -> List[PIL.Image.Image]:
  """Split tall KOSU images so the model sees all table sections."""
  w, h = img.size
  if h <= max_height + 200:
    return [img]
  segments: List[PIL.Image.Image] = []
  top = 0
  while top < h:
    bottom = min(h, top + max_height)
    segments.append(img.crop((0, top, w, bottom)))
    if bottom == h:
      break
    top = bottom - overlap
  return segments

def create_field_focused_crops(img: PIL.Image.Image, doc_type: str) -> List[PIL.Image.Image]:
  """Create focused crops for critical fields to improve accuracy."""
  crops = [img]  # Always include full image
  
  if doc_type == 'Kosu':
    w, h = img.size
    # Header region (top 25%)
    header_crop = img.crop((0, 0, w, int(h * 0.25)))
    crops.append(header_crop)
    
    # Table region (middle 50%)
    table_crop = img.crop((0, int(h * 0.25), w, int(h * 0.75)))
    crops.append(table_crop)
    
    # Summary region (bottom 25%)
    summary_crop = img.crop((0, int(h * 0.75), w, h))
    crops.append(summary_crop)
    
  elif doc_type == 'NPT':
    w, h = img.size
    # Header-focused crop
    header_crop = img.crop((0, 0, w, int(h * 0.3)))
    crops.append(header_crop)
    
  return crops

def gather_kosu_images_with_preprocessing(base_image_path: str) -> List[PIL.Image.Image]:
  try:
    base = PIL.Image.open(base_image_path)
  except Exception as e:
    print(f"[Kosu] open fail: {e}")
    return []
  
  # Get vertical segments
  segments = slice_vertical_segments(base)
  
  # Create focused crops for each segment
  all_images = []
  for seg in segments:
    processed_seg = preprocess_for_ocr(seg)
    all_images.append(processed_seg)
    
    # Add focused field crops
    focused_crops = create_field_focused_crops(seg, 'Kosu')
    for crop in focused_crops[1:]:  # Skip full image (already added)
      all_images.append(preprocess_for_ocr(crop))
  
  return all_images

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
def extract_with_confidence_retry(model, prompt: str, images: List[PIL.Image.Image], max_retries: int = 2) -> dict:
  """Extract with confidence checking and safe error handling."""
  if not isinstance(images, list) or not images:
    print("[extract_with_confidence_retry] No valid images provided")
    return {}
    
  best_result = {}
  best_confidence = 0
  
  for attempt in range(max_retries + 1):
    try:
      # Add confidence instruction to prompt
      enhanced_prompt = prompt + "\n\nALSO: Add a 'extraction_confidence' field (0-100) indicating how confident you are about the extracted values."
      
      # Use safe model call
      result_text = safe_model_call(model, [enhanced_prompt] + images, f"confidence_extraction_attempt_{attempt}")
      if not result_text:
        continue
      
      # Use safe JSON parse
      data = safe_json_parse(result_text, {}, f"confidence_extraction_attempt_{attempt}")
      if not isinstance(data, dict):
        continue
      
      confidence = data.get('extraction_confidence', 50)
      if not isinstance(confidence, (int, float)):
        confidence = 50
      
      # Calculate confidence based on data completeness
      non_null_fields = sum(1 for v in data.values() if v not in (None, '', 'null', []))
      total_fields = len(data)
      completeness_confidence = (non_null_fields / total_fields) * 100 if total_fields > 0 else 0
      
      # Combine model confidence with completeness
      combined_confidence = (confidence + completeness_confidence) / 2
      
      if combined_confidence > best_confidence:
        best_confidence = combined_confidence
        best_result = data.copy()
        best_result['final_confidence'] = combined_confidence
      
      # If confidence is high enough, stop retrying
      if combined_confidence >= 80:
        break
        
      print(f"[Extraction] Attempt {attempt + 1}: confidence {combined_confidence:.1f}%")
      
    except Exception as e:
      print(f"[Extraction] Attempt {attempt + 1} failed: {e}")
      continue
  
  return best_result

def validate_extraction_against_template(data: dict, doc_type: str) -> dict:
  """Validate extracted data against expected field patterns."""
  validation_rules = {
    'Kosu': {
      'Equipe': {'pattern': r'^(I{1,3}|IV|V|VI{0,3}|IX|X|[1-9]|10)$', 'type': 'team_id'},
      'Code ligne': {'pattern': r'^\d+$', 'type': 'number'},  # MUST be numeric only
      'Semaine': {'pattern': r'^\d{1,2}$', 'type': 'week_number'},
      'Numéro OF': {'pattern': r'^[A-Z0-9\-/]{1,20}$', 'type': 'reference'},
    },
    'NPT': {
      'uap': {'pattern': r'^\d{1,3}$', 'type': 'number'},
      'equipe': {'pattern': r'^(I{1,3}|IV|V|VI{0,3}|IX|X)$', 'type': 'roman_numeral'},
    },
    'Rebut': {
      'equipe': {'pattern': r'^(I{1,3}|IV|V|VI{0,3}|IX|X)$', 'type': 'roman_numeral'},
      'jap': {'pattern': r'^\d{1,4}$', 'type': 'number'},
    }
  }
  
  rules = validation_rules.get(doc_type, {})
  warnings = []
  
  for field, rule in rules.items():
    value = data.get(field)
    if value and isinstance(value, str):
      if not re.match(rule['pattern'], value.strip()):
        warnings.append(f"Field '{field}' value '{value}' doesn't match expected {rule['type']} pattern")
        # Try to clean common issues
        if rule['type'] == 'number':
          clean_val = re.sub(r'[^\d]', '', value)
          if clean_val:
            data[field] = clean_val
            warnings.append(f"  -> Auto-corrected to '{clean_val}'")
  
def cross_validate_fields(data: dict, doc_type: str) -> dict:
  """Cross-validate fields with comprehensive None handling."""
  if not isinstance(data, dict):
    print(f"[cross_validate_fields] Expected dict, got {type(data)}")
    return data
    
  corrections = []
  
  try:
    if doc_type == 'Kosu':
      # Enforce strict type rules for Nom Ligne and Code ligne
      nom_ligne = data.get('Nom Ligne')
      code_ligne = data.get('Code ligne')
      
      # Code ligne MUST be numeric
      if code_ligne and isinstance(code_ligne, str):
        # Try to extract numbers from Code ligne
        numeric_part = re.sub(r'[^\d]', '', code_ligne.strip())
        if not numeric_part:
          corrections.append(f"INVALID: Code ligne '{code_ligne}' must be numeric - clearing value")
          data['Code ligne'] = None
        elif numeric_part != code_ligne.strip():
          corrections.append(f"CLEANED: Code ligne '{code_ligne}' -> '{numeric_part}' (extracted numbers)")
          data['Code ligne'] = numeric_part
      elif code_ligne and not isinstance(code_ligne, (int, float)):
        corrections.append(f"INVALID: Code ligne '{code_ligne}' must be numeric - clearing value")
        data['Code ligne'] = None
      
      # Nom Ligne MUST be text/string (not purely numeric)
      if nom_ligne and isinstance(nom_ligne, str):
        if nom_ligne.strip().isdigit():
          corrections.append(f"INVALID: Nom Ligne '{nom_ligne}' should be descriptive text, not a number")
          # Check if this number should be in Code ligne instead
          if not data.get('Code ligne'):
            corrections.append(f"MOVED: '{nom_ligne}' moved from Nom Ligne to Code ligne")
            data['Code ligne'] = nom_ligne.strip()
          data['Nom Ligne'] = None
      elif nom_ligne and isinstance(nom_ligne, (int, float)):
        corrections.append(f"INVALID: Nom Ligne '{nom_ligne}' should be text, not numeric")
        if not data.get('Code ligne'):
          corrections.append(f"MOVED: '{nom_ligne}' moved from Nom Ligne to Code ligne")
          data['Code ligne'] = str(nom_ligne)
        data['Nom Ligne'] = None
      
      # Check for duplicate values (after type corrections)
      nom_ligne = data.get('Nom Ligne')
      code_ligne = data.get('Code ligne')
      if (nom_ligne and code_ligne and 
          isinstance(nom_ligne, str) and isinstance(code_ligne, str) and
          nom_ligne.strip().lower() == code_ligne.strip().lower()):
        corrections.append(f"DUPLICATE: Same value '{nom_ligne}' in both Nom Ligne and Code ligne - clearing Nom Ligne")
        data['Nom Ligne'] = None
      
      # Check for duplicate values across other header fields
      other_header_fields = ['Equipe', 'Jour', 'Semaine', 'Numéro OF', 'Ref PF']
      field_values = {}
      
      for field in other_header_fields:
        value = data.get(field)
        if value and isinstance(value, str) and value.strip():
          clean_value = value.strip().lower()
          if clean_value in field_values:
            corrections.append(f"DUPLICATE VALUE: '{value}' appears in both '{field_values[clean_value]}' and '{field}'")
            data[field] = None
          else:
            field_values[clean_value] = field
      
      # Validate team identifiers
      equipe = data.get('Equipe')
      if equipe and isinstance(equipe, str):
        if not re.match(r'^(I{1,3}|IV|V|VI{0,3}|IX|X|[1-9]|10)$', equipe.strip()):
          corrections.append(f"INVALID TEAM ID: '{equipe}' - should be Roman numeral I-X or digit 1-10")
          data['Equipe'] = None
      
      # Validate week numbers
      semaine = data.get('Semaine')
      if semaine and isinstance(semaine, str):
        week_num = re.sub(r'[^\d]', '', semaine)
        if week_num and (int(week_num) < 1 or int(week_num) > 53):
          corrections.append(f"INVALID WEEK: '{semaine}' - should be 1-53")
          data['Semaine'] = None
    
    elif doc_type == 'NPT':
      # UAP should be digits only
      uap = data.get('uap')
    if uap and isinstance(uap, str):
      if not re.match(r'^\d{1,3}$', uap.strip()):
        clean_uap = re.sub(r'[^\d]', '', uap)
        if clean_uap:
          corrections.append(f"CLEANED UAP: '{uap}' -> '{clean_uap}'")
          data['uap'] = clean_uap
        else:
          corrections.append(f"INVALID UAP: '{uap}' - should be digits only")
          data['uap'] = None
    
    elif doc_type == 'Rebut':
      # JAP should be numeric
      jap = data.get('jap')
      if jap and isinstance(jap, str):
        if not re.match(r'^\d{1,4}$', jap.strip()):
          clean_jap = re.sub(r'[^\d]', '', jap)
          if clean_jap:
            corrections.append(f"CLEANED JAP: '{jap}' -> '{clean_jap}'")
            data['jap'] = clean_jap
          else:
            corrections.append(f"INVALID JAP: '{jap}' - should be digits only")
            data['jap'] = None
    
    if corrections:
      data['cross_validation_corrections'] = corrections
      print(f"[{doc_type}] Cross-validation corrections: {len(corrections)}")
    
    return data
    
  except Exception as e:
    print(f"[cross_validate_fields] Error: {e}")
    return data

def targeted_field_reextraction(img: PIL.Image.Image, data: dict, problem_fields: List[str], model, doc_type: str) -> dict:
  """Re-extract specific problematic fields with safe error handling."""
  if not isinstance(data, dict):
    print(f"[targeted_field_reextraction] Expected dict, got {type(data)}")
    return data
    
  if not problem_fields:
    return data
  
  try:
    field_specific_prompts = {
      'Equipe': "Look ONLY at the 'Equipe' field. Extract the exact handwritten value (digit or Roman numeral). Return JSON: {\"Equipe\": \"value_or_null\"}",
      'Nom Ligne': "Look ONLY at the 'Nom Ligne' field (line name). Extract the exact handwritten TEXT/DESCRIPTION. This MUST be descriptive text/words, NOT numbers. Return JSON: {\"Nom Ligne\": \"text_description_or_null\"}",
      'Code ligne': "Look ONLY at the 'Code ligne' field (line code). Extract ONLY the NUMBERS written there. This MUST be numeric only (like 1, 2, 15, 25). Ignore any text. Return JSON: {\"Code ligne\": \"numbers_only_or_null\"}",
      'uap': "Look ONLY at the 'UAP' field. Extract only the digits (1-3 digits). Ignore any 'UAP' prefix. Return JSON: {\"uap\": \"digits_only_or_null\"}",
      'jap': "Look ONLY at the 'JAP' field. Extract only the digits. Return JSON: {\"jap\": \"digits_only_or_null\"}"
    }
    
    for field in problem_fields:
      if field in field_specific_prompts:
        try:
          prompt = field_specific_prompts[field]
          
          # Use safe model call
          field_result = safe_model_call(model, [prompt, img], f"field_reextraction_{field}")
          if not field_result:
            continue
            
          # Use safe JSON parse
          field_data = safe_json_parse(field_result, {}, f"field_reextraction_{field}")
          if not isinstance(field_data, dict):
            continue
            
          if field in field_data and field_data[field] not in (None, '', 'null'):
            old_value = data.get(field)
            new_value = field_data[field]
            if old_value != new_value:
              data[field] = new_value
              print(f"[{doc_type}] Re-extracted {field}: '{old_value}' -> '{new_value}'")
        
        except Exception as e:
          print(f"[{doc_type}] Re-extraction failed for {field}: {e}")
    
    return data
    
  except Exception as e:
    print(f"[targeted_field_reextraction] Error: {e}")
    return data

def final_sanity_check(data: dict, doc_type: str) -> dict:
  """Final validation with comprehensive None handling."""
  if not isinstance(data, dict):
    print(f"[final_sanity_check] Expected dict, got {type(data)}")
    return data
    
  issues = []
  
  try:
    if doc_type == 'Kosu':
      # Enforce strict type rules for critical fields
      nom_ligne = data.get('Nom Ligne')
      code_ligne = data.get('Code ligne')
      
      # Code ligne MUST be numeric
      if code_ligne:
        if isinstance(code_ligne, str) and not code_ligne.strip().isdigit():
          issues.append(f"CRITICAL: Code ligne '{code_ligne}' must be numeric only")
          data['Code ligne'] = None
        elif not isinstance(code_ligne, (str, int, float)):
          issues.append(f"CRITICAL: Code ligne '{code_ligne}' has invalid type")
          data['Code ligne'] = None
      
      # Nom Ligne MUST be descriptive text (not numbers)
      if nom_ligne:
        if isinstance(nom_ligne, str) and nom_ligne.strip().isdigit():
          issues.append(f"CRITICAL: Nom Ligne '{nom_ligne}' should be text, not numbers")
          data['Nom Ligne'] = None
        elif isinstance(nom_ligne, (int, float)):
          issues.append(f"CRITICAL: Nom Ligne '{nom_ligne}' should be text, not numeric")
          data['Nom Ligne'] = None
      
      # Check for exact duplicates in critical fields (after type enforcement)
      nom_ligne = data.get('Nom Ligne')
      code_ligne = data.get('Code ligne')
      equipe = data.get('Equipe')
      
      critical_values = {}
      for field, value in [('Nom Ligne', nom_ligne), ('Code ligne', code_ligne), ('Equipe', equipe)]:
        if value and isinstance(value, str) and value.strip():
          clean_val = value.strip().lower()
          if clean_val in critical_values:
            issues.append(f"CRITICAL: Duplicate value '{value}' in '{field}' and '{critical_values[clean_val]}'")
            data[field] = None
          else:
            critical_values[clean_val] = field
      
      # Validate team identifier
      equipe = data.get('Equipe')
      if equipe and not re.match(r'^(I{1,3}|IV|V|VI{0,3}|IX|X|[1-9]|10)$', str(equipe).strip()):
        issues.append(f"INVALID: Equipe '{equipe}' should be Roman numeral I-X or digit 1-10")
        data['Equipe'] = None
    
    elif doc_type == 'NPT':
      # UAP must be digits only
      uap = data.get('uap')
      if uap and not re.match(r'^\d{1,3}$', str(uap).strip()):
        issues.append(f"INVALID: UAP '{uap}' must be 1-3 digits only")
        data['uap'] = None
    
    elif doc_type == 'Rebut':
      # JAP must be digits only  
      jap = data.get('jap')
      if jap and not re.match(r'^\d{1,4}$', str(jap).strip()):
        issues.append(f"INVALID: JAP '{jap}' must be digits only")
        data['jap'] = None
    
    if issues:
      data['final_sanity_issues'] = issues
      print(f"[{doc_type}] Final sanity check found {len(issues)} issues")
    
    return data
    
  except Exception as e:
    print(f"[final_sanity_check] Error: {e}")
    return data

PROMPT_MAP = {'Rebut': REBUT_MULTI_PROMPT, 'Kosu': KOSU_PROMPT, 'NPT': NPT_PROMPT, DEFAUTS_DOC_TYPE: DEFAUTS_PRIMARY_PROMPT, 'Defauts': DEFAUTS_PRIMARY_PROMPT}

def extract_data_from_image(image_path: str, doc_type: str) -> Dict[str, Any]:
  """Main extraction orchestrator with comprehensive error handling."""
  try:
    if not image_path or not doc_type:
      print("[extract_data_from_image] Missing required parameters")
      return {"error": "Missing image_path or doc_type"}
    
    model = genai.GenerativeModel(GEMINI_PRO_MODEL)
    
    if doc_type in ['Défauts','Defauts']:
      return extract_defauts_multi(image_path, model)
    
    # Safe image loading
    try:
      base = PIL.Image.open(image_path)
    except FileNotFoundError:
      print(f"[extract_data_from_image] Image not found: {image_path}")
      return {"error": "Image not found"}
    except Exception as e:
      print(f"[extract_data_from_image] Image loading error: {e}")
      return {"error": f"Image loading failed: {e}"}
    
    # Get prompt safely
    prompt = PROMPT_MAP.get(doc_type)
    if not prompt:
      print(f"[extract_data_from_image] Unsupported doc_type: {doc_type}")
      return {"error": f"Unsupported document type: {doc_type}"}
    
    # Gather images with error handling
    crops: List[PIL.Image.Image] = []
    try:
      if doc_type == 'Rebut':
        crops = gather_rebut_images_with_preprocessing(image_path)
      elif doc_type == 'Kosu':
        crops = gather_kosu_images_with_preprocessing(image_path)
    except Exception as e:
      print(f"[extract_data_from_image] Image preprocessing error: {e}")
      # Continue with base image only
    
    # Use confidence-based extraction with safe model calls
    images_to_use = [base] + crops if (doc_type in ['Rebut','Kosu'] and crops) else [base]
    
    try:
      data = extract_with_confidence_retry(model, prompt, images_to_use)
    except Exception as e:
      print(f"[extract_data_from_image] Primary extraction error: {e}")
      data = None
    
    if not data or not isinstance(data, dict):
      print(f"[extract_data_from_image] Primary extraction failed for {doc_type}")
      return {"error": "Primary extraction failed", "document_type": doc_type}
      
    data.setdefault('document_type', doc_type)
    
    # Apply document-specific verification with error handling
    try:
      if doc_type == 'Rebut':
        data = verify_rebut_totals(base, data, model)
        data = recover_rebut_missing_rows(base, data, model)
        data = verify_rebut_totals(base, data, model)
        data = deduplicate_rebut_items(data)
        data = verify_rebut_totals(base, data, model)
        data = normalize_rebut_numeric_fields(data)
      elif doc_type == 'Kosu':
        # Apply multi-pass verification for Kosu with safety checks
        verified_header = verify_kosu_header(base, data, model)
        if verified_header is not None:
          data = verified_header
        
        recovered_header = recover_kosu_missing_header(base, data, model)
        if recovered_header is not None:
          data = recovered_header
        
        verified_table = verify_kosu_table_data(base, data, model)
        if verified_table is not None:
          data = verified_table
        
        processed_data = post_process_kosu(data)
        if processed_data is not None:
          data = processed_data
    except Exception as e:
      print(f"[extract_data_from_image] Document-specific verification error: {e}")
      # Continue with basic data
    
    # Apply validation pipeline with error handling
    try:
      # Template validation
      validated_data = validate_extraction_against_template(data, doc_type)
      if validated_data is not None:
        data = validated_data
      
      # Cross-field validation
      cross_validated_data = cross_validate_fields(data, doc_type)
      if cross_validated_data is not None:
        data = cross_validated_data
      
      # Identify problematic fields for re-extraction
      problem_fields = []
      if isinstance(data, dict):
        if 'validation_warnings' in data:
          for warning in data['validation_warnings']:
            if 'Field' in warning and 'doesn\'t match' in warning:
              try:
                field_name = warning.split("'")[1]
                problem_fields.append(field_name)
              except IndexError:
                continue
        
        if 'cross_validation_corrections' in data:
          for correction in data['cross_validation_corrections']:
            if 'DUPLICATE VALUE' in correction or 'INVALID' in correction or 'SWAPPED' in correction:
              # Extract field names from correction messages
              if 'Equipe' in correction:
                problem_fields.append('Equipe')
              if 'Nom Ligne' in correction:
                problem_fields.append('Nom Ligne')
              if 'Code ligne' in correction:
                problem_fields.append('Code ligne')
        
        # Re-extract problematic fields with focused prompts
        if problem_fields:
          problem_fields = list(set(problem_fields))  # Remove duplicates
          print(f"[{doc_type}] Re-extracting problematic fields: {problem_fields}")
          reextracted_data = targeted_field_reextraction(base, data, problem_fields, model, doc_type)
          if reextracted_data is not None:
            data = reextracted_data
        
        # Final sanity check
        final_checked_data = final_sanity_check(data, doc_type)
        if final_checked_data is not None:
          data = final_checked_data
      
    except Exception as e:
      print(f"[extract_data_from_image] Validation pipeline error: {e}")
      # Continue with extracted data
    
    # Final safety check - ensure data is not None
    if data is None:
      print(f"[extract_data_from_image] Data became None, returning minimal structure")
      data = {"document_type": doc_type, "status": "extraction_failed"}
    
    return {"data": data, "remark": f"{doc_type} extraction complete"}
    
  except Exception as e:
    print(f"[extract_data_from_image] Critical error: {e}")
    return {"error": f"Critical extraction error: {e}", "document_type": doc_type}

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
        if isinstance(data.get('Suivi horaire'), list) and data['Suivi horaire']:
          pd.DataFrame(data['Suivi horaire']).to_excel(w, 'Suivi_horaire', index=False)
        if isinstance(data.get('Total / Equipe'), dict):
          pd.DataFrame([data['Total / Equipe']]).to_excel(w, 'Total_Equipe', index=False)
        if isinstance(data.get("Règles d'escalade"), list) and data["Règles d'escalade"]:
          pd.DataFrame(data["Règles d'escalade"]).to_excel(w, 'Regles_Escalade', index=False)
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
