# -*- mode: python ; coding: utf-8 -*-
import os, sys, sysconfig
from PyInstaller.utils.hooks import collect_submodules

# Only collect sklearn.preprocessing and its minimal dependencies
sklearn_imports = (
    collect_submodules('sklearn.preprocessing') +
    collect_submodules('sklearn.utils') +
    collect_submodules('sklearn.base', filter=lambda name: 'test' not in name)
)
# Remove test modules
sklearn_imports = [m for m in sklearn_imports if '.tests' not in m and '.test_' not in m]

# Dynamically locate xgboost files instead of hardcoding user paths
import xgboost as _xgb
_xgb_dir = os.path.dirname(_xgb.__file__)
_xgb_dll = os.path.join(_xgb_dir, 'lib', 'xgboost.dll')
_xgb_ver = os.path.join(_xgb_dir, 'VERSION')

_binaries = [(_xgb_dll, 'xgboost/lib')] if os.path.exists(_xgb_dll) else []
_datas = [('_models_data.py', '.')]
if os.path.exists(_xgb_ver):
    _datas.insert(0, (_xgb_ver, 'xgboost'))

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=sklearn_imports + [
        'sklearn', 'sklearn.base', 'sklearn.exceptions',
        'xgboost', 'xgboost.core', 'xgboost.compat',
        'numpy', 'numpy._core',
        'scipy', 'scipy.sparse', 'scipy.special',
        'joblib', 'threadpoolctl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'torchvision', 'matplotlib', 'pandas', 'PIL', 'tkinter',
        'pytest', 'plotly', 'statsmodels', 'patsy', 'sympy',
        'IPython', 'notebook', 'sphinx', 'docutils',
        'pyarrow', 'sqlalchemy', 'lxml', 'openpyxl',
        'numba', 'llvmlite', 'skimage', 'kaleido',
        'botocore', 'boto3', 'fsspec',
        'cryptography', 'win32com',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='rp3-sidecar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
