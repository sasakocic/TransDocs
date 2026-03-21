# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-03-21

### Added
- New `--api_url` argument that accepts base URL and automatically appends `/api/generate`
- Improved translation prompt with better instructions for preserving technical content
- Support for CPU-only Ollama instances (no GPU required)
- Test document creation script (`create_test_doc.py`)
- Web interface template (`templates/upload.html`)

### Changed
- Updated default API URL to `http://localhost:11434` (base URL only)
- Enhanced prompt engineering for professional translations similar to DeepL
- Better error handling and logging

### Fixed
- API endpoint construction now works with base URLs like `http://localhost:11434/`
- Improved language detection reliability
