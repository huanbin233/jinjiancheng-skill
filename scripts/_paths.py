"""Shared paths for jinjiancheng-investing skill."""
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent   # scripts/
PROJECT_ROOT = SCRIPTS_DIR.parent                # project root

# Core data paths
DATA_DIR      = PROJECT_ROOT / "data"
ARTICLES_DIR  = PROJECT_ROOT / "articles"
RAW_HTML_DIR  = PROJECT_ROOT / "raw" / "html"
RAW_TEXT_DIR  = PROJECT_ROOT / "raw" / "text"
PDF_DIR       = PROJECT_ROOT / "pdf"
MANUAL_DIR    = PROJECT_ROOT / "manual"

# Individual file paths
LINKS_FILE        = DATA_DIR / "gongzhonghao.json"
MANIFEST_FILE     = DATA_DIR / "links_manifest.json"
INDEX_FILE        = DATA_DIR / "articles_index.json"
DISCOVERED_FILE   = DATA_DIR / "discovered_links.json"
MAP_FILE          = DATA_DIR / "filename_map.json"
MANUAL_FILE       = MANUAL_DIR / "长期配置操作手册.md"

# Browser profiles
BROWSER_PROFILE_DIR      = PROJECT_ROOT / ".browser_profile"
DRISSION_PROFILE_DIR     = BROWSER_PROFILE_DIR / "drission_wechat"
PLAYWRIGHT_PROFILE_DIR   = BROWSER_PROFILE_DIR / "wechat"

# Backward compatibility alias
ROOT = PROJECT_ROOT
