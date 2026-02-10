# 🔬 Disease2Gene

**An AI-powered pipeline for extracting disease–gene associations from biomedical literature.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-green.svg)](https://python.org)
[![SoftwareX](https://img.shields.io/badge/Paper-SoftwareX-orange.svg)](publication/)

Disease2Gene automates the systematic extraction of gene–disease relationships from PubMed literature. It combines PubMed search, full-text retrieval, LLM-based information extraction (Google Gemini), and gene name validation (HGNC) into a single, reproducible pipeline — accessible through a local web interface.

---

## ✨ Features

| Feature                | Description                                                                      |
| ---------------------- | -------------------------------------------------------------------------------- |
| **PubMed Search**      | Query PubMed with keywords or raw syntax, browse and select papers interactively |
| **Full-Text Fetching** | Retrieve full text from PMC, Unpaywall, Sci-Hub fallbacks                        |
| **LLM Extraction**     | Extract structured gene data using Google Gemini with custom column definitions  |
| **Gene Validation**    | Validate and normalize gene names against the HGNC database                      |
| **Web GUI**            | Local browser-based interface — no command line needed                           |
| **Standalone App**     | Installable macOS `.app` (DMG) and Windows `.exe`                                |

## 🚀 Quick Start

### Option 1: Standalone App (Recommended)

**macOS:** Download `Disease2Gene.dmg` → drag to Applications → double-click to launch.

### Option 2: Run from Source

```bash
# 1. Clone this repo
git clone https://github.com/michaluppal/RS_SOFTWAREX.git
cd RS_SOFTWAREX

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch
python gui/app_server.py
# → Opens http://localhost:8050 in your browser
```

### Option 3: One-Click Launcher

```bash
# macOS / Linux
bash packaging/start.sh

# Windows
packaging\start.bat
```

## 🔑 Prerequisites

| Requirement               | How to Get                                                              |
| ------------------------- | ----------------------------------------------------------------------- |
| **Python 3.9+**           | [python.org/downloads](https://python.org/downloads)                    |
| **Google Gemini API Key** | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (free) |
| **NCBI Email**            | Any valid email for PubMed API access                                   |

## 🧬 How It Works

```
┌─────────────┐     ┌───────────────┐     ┌──────────────┐     ┌──────────────┐
│  PubMed     │────▶│  Full-Text    │────▶│  Gemini LLM  │────▶│  HGNC Gene   │
│  Search     │     │  Retrieval    │     │  Extraction   │     │  Validation  │
└─────────────┘     └───────────────┘     └──────────────┘     └──────────────┘
       │                                                              │
       │              User selects papers                             │
       │              & defines columns                               ▼
       │                                                     ┌──────────────┐
       └────────────────────────────────────────────────────▶│  Excel/CSV   │
                                                             │  Results     │
                                                             └──────────────┘
```

## 📁 Project Structure

```
RS_SOFTWAREX/
├── modules/          # Core pipeline (search, fetch, extract, validate)
├── gui/              # Flask web interface
├── data/reference/   # HGNC gene database
├── evaluation/       # Reproducible evaluation suite
├── publication/      # SoftwareX article (LaTeX)
├── packaging/        # Standalone app build tools
└── docker/           # Container deployment
```

## 📊 Evaluation

The `evaluation/` directory contains ground truth data, analysis notebooks, and scripts to reproduce the results reported in the SoftwareX paper.

```bash
cd evaluation
conda env create -f environment.yml
conda activate disease2gene-eval
jupyter notebook evaluation_analysis.ipynb
```

## 🏗️ Building the Standalone App

```bash
# macOS
cd packaging
pip install pyinstaller
python -m PyInstaller Disease2Gene.spec
bash create_custom_dmg.sh   # Creates dist/Disease2Gene.dmg
```

## 📄 Citation

If you use Disease2Gene in your research, please cite:

```bibtex
@article{uppal2025disease2gene,
  title     = {Disease2Gene: An AI-Powered Pipeline for Systematic Extraction
               of Gene–Disease Associations from Biomedical Literature},
  author    = {Uppal, Michał},
  journal   = {SoftwareX},
  year      = {2025},
  publisher = {Elsevier}
}
```

## 📝 License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please open an issue or submit a pull request.

---

**Built with ❤️ at [ResearchShop.pl](https://researchshop.pl)**
