"""Read-only source/temporary inventory; never opens message or credential files."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


def inventory(root: Path) -> dict:
    rows = []
    for directory in ('cmail', 'tests'):
        for path in sorted((root / directory).rglob('*')):
            if not path.is_file() or path.suffix not in {'.py', '.js', '.html', '.css'}:
                continue
            source = path.read_text(encoding='utf-8-sig')
            row = {'file': path.relative_to(root).as_posix(), 'lines': len(source.splitlines()),
                   'bytes': path.stat().st_size}
            if path.suffix == '.py':
                functions = [node for node in ast.walk(ast.parse(source))
                             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
                row['largestFunctionLines'] = max((node.end_lineno - node.lineno + 1
                                                    for node in functions), default=0)
            rows.append(row)
    temporary = []
    for name in ('.agents/temp', '.agents/backup', 'build', 'dist', '.pytest_cache'):
        paths = [path for path in (root / name).rglob('*') if path.is_file()]
        temporary.append({'directory': name, 'files': len(paths),
                          'bytes': sum(path.stat().st_size for path in paths)})
    return {'productionLines': sum(row['lines'] for row in rows if row['file'].startswith('cmail/')),
            'testLines': sum(row['lines'] for row in rows if row['file'].startswith('tests/')),
            'files': sorted(rows, key=lambda row: row['lines'], reverse=True),
            'temporary': temporary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    rendered = json.dumps(inventory(args.root.resolve()), indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding='utf-8')
    else:
        print(rendered)


if __name__ == '__main__':
    main()
