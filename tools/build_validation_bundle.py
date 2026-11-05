"""Build source-free read-only validation harness; never include local secrets."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    files = {
        'tests/conftest.py':'tests/conftest.py',
        'tests/live/test_readonly.py':'tests/live/test_readonly.py',
        'docs/validation/README.md':'README.md',
        'docs/validation/live-plan.example.json':'live-plan.example.json',
        'docs/validation/live-plan.example.md':'live-plan.example.md',
    }
    contents = {dest:(root/source).read_bytes() for source,dest in files.items()}
    contents['README.md'] = contents['README.md'].decode('utf-8').replace(
        '[installed-package.md](../installed-package.md)',
        'installed-package.md (localizar na distribuição instalada por metadata)').encode('utf-8')
    contents['pytest.ini'] = b'[pytest]\ntestpaths = tests\nmarkers =\n    live: real opt-in\n    gmail_api: Gmail web\n    gmail_file_api: Gmail file API\n    gmail_file_smtp: Gmail SMTP\n    outlook: Graph\n    imap: IMAP\n'
    manifest = {'schemaVersion':1, 'package':'crania-cmail',
                'purpose':'read-only-opt-in-no-implementation',
                'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in contents.items()}}
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output/'cmail-validation-readonly.zip'
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in contents.items(): archive.writestr(name, raw)
        archive.writestr('manifest.json', json.dumps(manifest, indent=2))
    print(json.dumps({'archive':str(path.resolve()), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))


if __name__ == '__main__': main()
