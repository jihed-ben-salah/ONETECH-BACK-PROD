#!/usr/bin/env python
import os
import sys
from pathlib import Path

# Ensure parent repository root (containing process_forms.py) is on PYTHONPATH
PARENT_ROOT = Path(__file__).resolve().parent.parent
if str(PARENT_ROOT) not in sys.path:
    sys.path.insert(0, str(PARENT_ROOT))

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
