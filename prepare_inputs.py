"""Download checksum-pinned large public inputs from their original archives."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true', help='Verify existing inputs without network access.')
args = parser.parse_args()
manifest = json.loads((ROOT / 'PUBLIC_INPUTS.json').read_text())
for item in manifest:
    destination = ROOT / item['path']
    assert destination.resolve().is_relative_to(ROOT.resolve())
    if destination.exists():
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        if digest != item['sha256']:
            raise SystemExit(f'Checksum mismatch: {item["path"]}. Preserve or remove the local file before retrying.')
        print('Verified:', item['path'], flush=True)
        continue
    if args.check:
        raise SystemExit(f'Missing: {item["path"]}. Run python prepare_inputs.py first.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    print('Downloading:', item['path'], flush=True)
    fd, name = tempfile.mkstemp(prefix='.download-', dir=destination.parent)
    temporary = Path(name)
    try:
        sha = hashlib.sha256()
        request = urllib.request.Request(item['url'], headers={'User-Agent': 'EmissionsMarketsReplication/1.0'})
        with os.fdopen(fd, 'wb') as output, urllib.request.urlopen(request, timeout=180) as response:
            while chunk := response.read(1024 * 1024):
                sha.update(chunk)
                output.write(chunk)
        if sha.hexdigest() != item['sha256']:
            raise RuntimeError(f'Source checksum mismatch: {item["path"]}')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
print(f'All {len(manifest)} public input files verified.')
