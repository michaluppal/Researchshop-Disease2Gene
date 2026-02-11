# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Disease2Gene standalone app.

Build with:
    python3 -m PyInstaller Disease2Gene.spec

Produces:
    dist/Disease2Gene.app  (macOS)
    dist/Disease2Gene.exe  (Windows)
"""

import os
import sys
import platform

block_cipher = None

# SPECPATH = directory containing this spec file (packaging/)
# PROJECT_ROOT = repository root (one level up) where modules/, gui/, data/ live
ROOT = SPECPATH
PROJECT_ROOT = os.path.dirname(SPECPATH)

# Platform-appropriate icon
if sys.platform == 'win32':
    ICON_FILE = os.path.join(ROOT, 'Disease2Gene.ico')
else:
    ICON_FILE = os.path.join(ROOT, 'Disease2Gene.icns')

# Collect all module files
module_files = []
for f in os.listdir(os.path.join(PROJECT_ROOT, 'modules')):
    if f.endswith('.py'):
        module_files.append((os.path.join(PROJECT_ROOT, 'modules', f), 'modules'))

a = Analysis(
    [os.path.join(ROOT, 'disease2gene_launcher.py')],
    pathex=[ROOT, PROJECT_ROOT],
    binaries=[],
    datas=[
        # Flask static files (HTML/CSS/JS)
        (os.path.join(PROJECT_ROOT, 'gui', 'static'), os.path.join('gui', 'static')),
        # Flask app server
        (os.path.join(PROJECT_ROOT, 'gui', 'app_server.py'), 'gui'),
        # All pipeline modules
        *[(os.path.join(PROJECT_ROOT, 'modules', f), 'modules') for f in os.listdir(os.path.join(PROJECT_ROOT, 'modules')) if f.endswith('.py')],
        # Reference data (HGNC gene database)
        (os.path.join(PROJECT_ROOT, 'data', 'reference'), os.path.join('data', 'reference')),
    ],
    hiddenimports=[
        'flask',
        'Bio',
        'Bio.Entrez',
        'pandas',
        'tqdm',
        'requests',
        'bs4',
        'trafilatura',
        'lxml',
        'lxml.html',
        'lxml.etree',
        'lxml_html_clean',
        'google.genai',
        'google.genai.types',
        'openpyxl',
        'json',
        'gzip',
        'pickle',
        'concurrent.futures',
        'multiprocessing',
        'xml.etree.ElementTree',
        'uuid',
        'dataclasses',
        'functools',
        'contextlib',
        'pathlib',
        'signal',
        'logging',
        'threading',
        'queue',
        'webbrowser',
        're',
        'io',
        'math',
        'collections',
        'subprocess',
        # Modules
        'modules',
        'modules.config',
        'modules.pubmed_data_collector',
        'modules.full_text_fetcher',
        'modules.abstract_screener',
        'modules.gemini_extractor',
        'modules.gemini_rate_limiter',
        'modules.gene_validator',
        'modules.pipeline_orchestrator',
        'modules.progress_tracker',
        'modules.variant_normalizer',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'playwright',  # Too large to bundle; full-text can fall back to other methods
        'tkinter',
        'matplotlib',
        'scipy',
        'IPython',
        'notebook',
        'pytest',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'qtpy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if platform.system() == 'Darwin':
    # macOS: Create .app bundle
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='Disease2Gene',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,  # No terminal window
        disable_windowed_traceback=False,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='Disease2Gene',
    )
    app = BUNDLE(
        coll,
        name='Disease2Gene.app',
        icon=ICON_FILE,
        bundle_identifier='pl.researchshop.disease2gene',
        info_plist={
            'CFBundleName': 'Disease2Gene',
            'CFBundleDisplayName': 'Disease2Gene',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.15',
        },
    )
else:
    # Windows: Create .exe
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='Disease2Gene',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,  # No terminal window
        disable_windowed_traceback=False,
        icon=ICON_FILE,
    )
