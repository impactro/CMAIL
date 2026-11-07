"""Product-owned adapter for a pinned CUI snapshot; no adjacent checkout at runtime."""
import json
from functools import lru_cache
from pathlib import Path
from starlette.staticfiles import StaticFiles
from starlette.responses import FileResponse
from starlette.exceptions import HTTPException


@lru_cache(maxsize=8)
def _receipt(vendor, stamp):
    value = json.loads((vendor / 'cui.asset.json').read_text(encoding='utf8'))
    if value.get('package') != '@crania/ui' or value.get('contract') != 'cui.ui.v1':
        raise ValueError('Invalid CUI receipt')
    release = value['release']
    if not release or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789.-' for c in release):
        raise ValueError('Invalid CUI release')
    return value


def resource(package, static, alias):
    """Resolve an explicit legacy alias. Unknown names retain the product fallback."""
    package = Path(package)
    vendor = package / static / 'vendor/cui'
    receipt = vendor / 'cui.asset.json'
    if not receipt.is_file():
        return package / alias
    value = _receipt(vendor, receipt.stat().st_mtime_ns)
    name = value.get('resources', {}).get(alias)
    if name is None:
        return package / alias
    if name not in value['files'] or any(p.startswith('.') or ':' in p or '\\' in p for p in Path(name).parts):
        raise ValueError('Invalid CUI resource')
    path = (vendor / value['release'] / name).resolve()
    path.relative_to(vendor.resolve())
    return path


class CuiStaticFiles(StaticFiles):
    def __init__(self, *, package, static, **kwargs):
        self.package, self.static = Path(package), static
        super().__init__(directory=str(self.package / static), **kwargs)

    async def get_response(self, path, scope):
        if scope['method'] not in ('GET', 'HEAD'):
            raise HTTPException(405)
        path = path.replace('\\', '/')
        if path.startswith('vendor/cui/') and path.endswith('.html'):
            raise HTTPException(404)  # Templates are exposed only through product routes.
        alias = self.static + '/' + ('index.html' if path in ('', '.') else path)
        file = resource(self.package, self.static, alias)
        if file != self.package / alias and file.is_file():
            return FileResponse(file, headers={'Cache-Control': 'no-cache'})
        response = await super().get_response(path, scope)
        if path.startswith('vendor/cui/') and not path.endswith('cui.asset.json'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return response


def template_environment(package, static='static'):
    from jinja2 import BaseLoader, ChoiceLoader, FileSystemLoader, TemplateNotFound
    class CuiLoader(BaseLoader):
        def get_source(self, environment, template):
            file = resource(package, static, 'templates/' + template)
            if not file.is_file():
                raise TemplateNotFound(template)
            stamp = file.stat().st_mtime_ns
            return file.read_text(encoding='utf8'), str(file), lambda: file.is_file() and file.stat().st_mtime_ns == stamp
    return ChoiceLoader([CuiLoader(), FileSystemLoader(str(Path(package) / 'templates'))])
