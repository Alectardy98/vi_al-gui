"""A browser provider must not change the desktop add-on package format."""
import importlib.util
from pathlib import Path
import tempfile
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src/main/python'))
from addon_runtime.packages import inspect_package


def test_browser_providers_stay_out_of_desktop_addon_zips():
    root = ROOT
    spec = importlib.util.spec_from_file_location('build_addons', root / 'util/packaging/build_addons.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary)
        for manifest in sorted((root / 'addons').glob('*/addon.json')):
            archive = module.build(manifest.parent, output)
            assert inspect_package(archive)['id'] == manifest.parent.name
            with zipfile.ZipFile(archive) as source:
                assert not any(name.startswith('web/') for name in source.namelist())
