import re
from typing import Any, Dict

_ROMAN_MAP = {
    1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V',
    6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X'
}
_ALLOWED_ROMANS = set(_ROMAN_MAP.values())


def normalize_uap(value: Any):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        iv = int(value)
        return str(iv) if 0 < iv < 1000 else None
    s = str(value).strip().upper()
    s = s.replace('UAP', '').strip()
    s = re.sub(r'[^0-9]', '', s)
    if not s:
        return None
    if len(s) > 3:
        return None
    return s


def normalize_equipe(value: Any):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return _ROMAN_MAP[int(value)]
        except Exception:
            return None
    s = str(value).strip().upper().replace('É', 'E').replace('EQUIPE', '').replace('TEAM', '').strip()
    if s.isdigit():
        try:
            return _ROMAN_MAP[int(s)]
        except Exception:
            return None
    # Keep only roman numeral chars
    s2 = re.sub(r'[^IVXLCDM]', '', s)
    if s2 in _ALLOWED_ROMANS:
        return s2
    return None


def post_process_payload(data: Dict[str, Any]):
    if not isinstance(data, dict):
        return data
    header = data.get('header')
    if isinstance(header, dict):
        # uap
        for key in ['uap', 'UAP']:
            if key in header:
                header['uap'] = normalize_uap(header.get(key))
                if key != 'uap':
                    header.pop(key, None)
                break
        # equipe / team
        for key in ['equipe', 'team', 'EQUIPE', 'TEAM']:
            if key in header:
                header['equipe'] = normalize_equipe(header.get(key))
                if key != 'equipe':
                    header.pop(key, None)
                break
    return data
