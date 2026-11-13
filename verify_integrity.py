"""Check the original release file hashes before numerical reproduction."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
manifest = json.loads((ROOT / 'MANIFEST_SHA256.json').read_text())
failures = []
for name, expected in manifest.items():
    path = ROOT / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        failures.append(name)
if failures:
    raise SystemExit('Missing or changed release files:\n' + '\n'.join(failures))
print(f'All {len(manifest)} release file hashes match.')
