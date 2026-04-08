# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for RP3 — Composite Failure Surrogate Application."""

import os
import customtkinter
import CTkToolTip
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None

_app_dir = os.path.abspath('.')
_ctk_dir = os.path.dirname(customtkinter.__file__)
_ctkt_dir = os.path.dirname(CTkToolTip.__file__)

# Collect xgboost data files and libs (avoid collect_all which imports testing)
xgb_datas = collect_data_files('xgboost')
xgb_bins = collect_dynamic_libs('xgboost')
xgb_hiddens = collect_submodules('xgboost',
    filter=lambda name: 'testing' not in name and 'dask' not in name)

a = Analysis(
    ['surrogate_app.py'],
    pathex=[_app_dir],
    binaries=[] + xgb_bins,
    datas=[
        ('_models_data.py', '.'),
        ('rp3.ico', '.'),
        (_ctk_dir, 'customtkinter/'),
        (_ctkt_dir, 'CTkToolTip/'),
    ] + xgb_datas,
    hiddenimports=[
        'customtkinter',
        'CTkToolTip',
        'CTkToolTip.ctk_tooltip',
        'numpy',
        'xgboost',
        'xgboost.core',
        'xgboost.sklearn',
        'sklearn',
        'sklearn.ensemble',
        'sklearn.ensemble._forest',
        'sklearn.ensemble._gb',
        'sklearn.preprocessing',
        'sklearn.preprocessing._data',
        'sklearn.utils',
        'sklearn.utils._typedefs',
        'sklearn.utils._heap',
        'sklearn.utils._sorting',
        'sklearn.utils._vector_sentinel',
        'sklearn.neighbors._partition_nodes',
        'scipy',
        'scipy.special',
        'scipy.special._cdflib',
        'plotly',
        'kaleido',
        'PIL',
    ] + xgb_hiddens,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'matplotlib', 'IPython', 'jupyter'],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RP3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='rp3.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='RP3',
)
