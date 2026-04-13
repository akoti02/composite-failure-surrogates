# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

# Only collect sklearn.preprocessing and its minimal dependencies
sklearn_imports = (
    collect_submodules('sklearn.preprocessing') +
    collect_submodules('sklearn.utils') +
    collect_submodules('sklearn.base', filter=lambda name: 'test' not in name)
)
# Remove test modules
sklearn_imports = [m for m in sklearn_imports if '.tests' not in m and '.test_' not in m]

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[('C:/Users/akoti/AppData/Local/Programs/Python/Python313/Lib/site-packages/xgboost/lib/xgboost.dll', 'xgboost/lib')],
    datas=[('C:/Users/akoti/AppData/Local/Programs/Python/Python313/Lib/site-packages/xgboost/VERSION', 'xgboost'), ('_models_data.py', '.')],
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
