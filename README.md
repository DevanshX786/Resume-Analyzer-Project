# 🚀 Resume Analyzer API

An intelligent backend API that mathematically analyzes parsed resumes and provides customized feedback based on predefined tech stacks (like Web Development, AI/ML, Blockchain, and more).

## ✨ Features
- **Smart Text Extraction**: Uses `pdfplumber` and `python-docx` to easily process PDFs and Word Documents.
- **Automated Skill Detection**: Cross-references resume keywords against a massive technical dictionary using fuzzy matching.
- **Fresher-Friendly Feedback**: Scans intelligently for "Education", "Projects", and external "GitHub/LinkedIn" links, skipping arbitrary "years of experience" requirements.
- **AI Career Counselor**: Recommends the Top 3 career paths a candidate is closest to achieving, while generating a direct study guide of the tech skills they are currently missing.

## 🛠️ Quick Start

### 1. Set Up Environment
Create and activate your Python virtual environment:
```bash
python -m venv .venv

# Windows:
.\.venv\Scripts\activate

# Mac/Linux:
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Server
Launch the built-in FastAPI development server:
```bash
uvicorn app.main:app --reload
```

Then visit the interactive swagger dashboard to test it out:
👉 **http://127.0.0.1:8000/docs**
