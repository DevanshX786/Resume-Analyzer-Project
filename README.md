# ResumeAnalyzer

ResumeAnalyzer is a FastAPI + Streamlit application that analyzes resumes, compares detected skills against a target specialization, and provides feedback and role suggestions.

For custom specializations, the app uses Gemini to generate core skills and caches them in MongoDB for faster reuse.

## 🚀 Try It Out

**[Launch ResumeAnalyzer Live](https://resume-analyzer-devansh.streamlit.app/)** — Start comparing your resume to any role instantly, no installation required!

## Features
- Resume parsing for PDF, DOCX/DOC, TXT, and image files.
- Skill extraction using keyword and fuzzy matching.
- Target specialization comparison (predefined roles or custom role title).
- Gemini-powered dynamic skill generation for custom roles.
- MongoDB cache for generated role skills to reduce repeated AI calls.
- Role recommendations and feedback summaries.

## User Flow
1. User selects a specialization.
2. User uploads a resume.
3. App extracts text and detects skills.
4. App resolves required skills:
	- Predefined role: uses predefined/master role skills.
	- Custom role: checks MongoDB cache first, then Gemini on cache miss.
5. App compares detected vs required skills and returns missing skills, feedback, and top role suggestions.

## Tech Stack
- Backend: FastAPI
- Frontend: Streamlit
- AI: Gemini (model: gemini-2.5-flash-lite)
- Database: MongoDB Atlas (or local MongoDB)

## Environment Variables
Create a .env file in the project root with:

```env
GEMINI_API_KEY=your_gemini_api_key
MONGODB_URI=your_mongodb_connection_string
MONGODB_DB_NAME=resume_analyzer
MONGODB_COLLECTION=role_cache
MONGODB_MASTER_COLLECTION=role_skills_master
ROLE_CACHE_TTL_DAYS=30
ROLE_CACHE_FAILURE_TTL_MINUTES=15
BACKEND_URL=http://127.0.0.1:8000
```

Notes:
- GOOGLE_API_KEY is also accepted as a fallback alias.
- MONGODB_COLLECTION defaults to role_cache.

## Local Setup
1. Create and activate virtual environment.

```bash
python -m venv .venv

# Windows
.\.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Run backend.

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

4. Run frontend (new terminal).

```bash
streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

5. Open:
- Frontend: http://127.0.0.1:8501
- API docs: http://127.0.0.1:8000/docs

## Caching Behavior (Custom Roles)
- On first custom role request, Gemini returns skills and app stores them in MongoDB role_cache.
- On subsequent requests for the same role, app serves skills from cache.
- Cache entries expire using TTL (ROLE_CACHE_TTL_DAYS).
- If AI fails temporarily, stale cached data can be used when available.

## Deployment Notes
- Render services are defined in render.yaml.
- Set GEMINI_API_KEY and MONGODB_URI in Render environment variables.
- If auto-deploy is enabled, pushing to the connected branch redeploys automatically.
