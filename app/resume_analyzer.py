import re
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
import time

import docx
import pdfplumber
import pytesseract
from PIL import Image
from rapidfuzz import process, fuzz
import google.generativeai as genai
import os
import json
from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

# Load local environment variables when running outside managed hosting.
load_dotenv()

# Initialize Gemini API strictly from environment variables.
# Accept GOOGLE_API_KEY as a fallback alias for compatibility.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017")
MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME", "resume_analyzer")
MONGODB_COLLECTION = os.environ.get("MONGODB_COLLECTION", "role_cache")
MONGODB_MASTER_COLLECTION = os.environ.get("MONGODB_MASTER_COLLECTION", "role_skills_master")
ROLE_CACHE_TTL_DAYS = int(os.environ.get("ROLE_CACHE_TTL_DAYS", "90"))
ROLE_CACHE_FAILURE_TTL_MINUTES = int(os.environ.get("ROLE_CACHE_FAILURE_TTL_MINUTES", "60"))
ROLE_PREDEFINED_FUZZY_THRESHOLD = int(os.environ.get("ROLE_PREDEFINED_FUZZY_THRESHOLD", "90"))


BOOTSTRAP_ROLE_SKILLS = {
    # Core Tech Roles
    "frontend developer": ["javascript", "react", "html", "css", "ui/ux", "git"],
    "backend developer": ["python", "java", "node.js", "sql", "django", "flask", "docker", "aws"],
    "web developer": ["javascript", "react", "node.js", "html", "css", "sql", "git"],
    "ai/ml engineer": ["python", "machine learning", "nlp", "tensorflow", "pytorch", "data analysis", "sql"],
    "data scientist": ["python", "r", "sql", "machine learning", "statistics", "data visualization", "pandas"],
    "mobile app developer": ["swift", "kotlin", "react native", "flutter", "java", "ios", "android"],
    "android developer": ["kotlin", "java", "android", "android studio", "jetpack compose", "mvvm", "retrofit", "room", "git", "gradle"],

    # Specialized Tech Roles
    "blockchain developer": ["solidity", "ethereum", "smart contracts", "rust", "go", "cryptography", "web3.js"],
    "devops engineer": ["aws", "azure", "docker", "kubernetes", "ci/cd", "linux", "bash", "terraform"],
    "cybersecurity analyst": ["network security", "linux", "python", "ethical hacking", "wireshark", "risk management"],

    # Non-Tech & Corporate Roles
    "product manager": ["agile", "scrum", "roadmap planning", "jira", "communication", "user research", "data analysis"],
    "digital marketer": ["seo", "sem", "content marketing", "google analytics", "social media", "copywriting"],
    "sales representative": ["crm", "salesforce", "cold calling", "b2b", "negotiation", "communication", "account management"],
    "human resources": ["recruiting", "employee relations", "onboarding", "ats", "interviewing", "communication"]
}

ROLE_ALIASES = {
    "android dev": "android developer",
    "backend dev": "backend developer",
    "frontend dev": "frontend developer",
    "ios dev": "ios developer",
    "ml engineer": "ai/ml engineer",
}

ROLE_TOKEN_EXPANSIONS = {
    "dev": "developer",
    "eng": "engineer",
}

# Default keyword skills used for rudimentary matching. Combine base list with all role-specific skills.
BASE_SKILLS = [
    "python", "java", "c++", "javascript", "react", "angular", "node.js", "flask", "django",
    "sql", "nosql", "excel", "git", "docker", "kubernetes", "aws", "azure", "gcp", "nlp",
    "machine learning", "data analysis", "presentation", "communication", "leadership"
]
DEFAULT_SKILLS = sorted(list(set(BASE_SKILLS + [skill for skills in BOOTSTRAP_ROLE_SKILLS.values() for skill in skills])))

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}

_mongo_client: Optional[MongoClient] = None
_role_cache_collection: Optional[Collection] = None
_role_master_collection: Optional[Collection] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_role_key(role_name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s+/.-]", " ", role_name.lower())
    cleaned = re.sub(r"\b(senior|sr|junior|jr|lead|principal|staff|intern)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned in ROLE_ALIASES:
        return ROLE_ALIASES[cleaned]

    tokens = [ROLE_TOKEN_EXPANSIONS.get(tok, tok) for tok in cleaned.split(" ")]
    expanded = " ".join(tokens).strip()
    return ROLE_ALIASES.get(expanded, expanded)


def _role_key_variants(role_key: str) -> List[str]:
    variants = {role_key}

    if "developer" in role_key:
        variants.add(role_key.replace("developer", "dev"))
    if "engineer" in role_key:
        variants.add(role_key.replace("engineer", "eng"))

    return [v for v in variants if v]


def _sanitize_skills(skills: List[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for skill in skills:
        cleaned = str(skill).strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _get_role_cache_collection() -> Optional[Collection]:
    global _mongo_client, _role_cache_collection, _role_master_collection

    if _role_cache_collection is not None and _role_master_collection is not None:
        return _role_cache_collection

    try:
        _mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=1500)
        _mongo_client.admin.command("ping")
        db = _mongo_client[MONGODB_DB_NAME]

        cache_collection = db[MONGODB_COLLECTION]
        cache_collection.create_index([("role_key", ASCENDING)], unique=True)
        cache_collection.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
        _role_cache_collection = cache_collection

        master_collection = db[MONGODB_MASTER_COLLECTION]
        master_collection.create_index([("role_key", ASCENDING)], unique=True)
        _role_master_collection = master_collection
        _seed_role_master_collection(master_collection)

        return _role_cache_collection
    except PyMongoError as e:
        print(f"MongoDB unavailable, continuing without cache: {e}")
        _role_cache_collection = None
        _role_master_collection = None
        return None


def _get_role_master_collection() -> Optional[Collection]:
    global _role_master_collection
    if _role_master_collection is not None:
        return _role_master_collection
    _ = _get_role_cache_collection()
    return _role_master_collection


def _seed_role_master_collection(collection: Collection) -> None:
    try:
        if collection.estimated_document_count() > 0:
            return

        now = _utcnow()
        docs = []
        for role_key, skills in BOOTSTRAP_ROLE_SKILLS.items():
            docs.append(
                {
                    "role_key": role_key,
                    "display_role": role_key.title(),
                    "skills": _sanitize_skills(skills),
                    "source": "bootstrap",
                    "created_at": now,
                    "updated_at": now,
                }
            )
        if docs:
            collection.insert_many(docs, ordered=False)
    except PyMongoError as e:
        print(f"Failed seeding role master collection: {e}")


def _get_cached_role_skills(role_key: str) -> Optional[List[str]]:
    collection = _get_role_cache_collection()
    if collection is None:
        return None

    now = _utcnow()
    doc = collection.find_one(
        {"role_key": {"$in": _role_key_variants(role_key)}, "expires_at": {"$gt": now}}
    )
    if not doc:
        return None

    collection.update_one(
        {"_id": doc["_id"]},
        {"$set": {"last_used_at": now}, "$inc": {"hit_count": 1}},
    )
    return _sanitize_skills(doc.get("skills", []))


def _get_stale_cached_role_skills(role_key: str) -> Optional[List[str]]:
    collection = _get_role_cache_collection()
    if collection is None:
        return None

    doc = collection.find_one({"role_key": {"$in": _role_key_variants(role_key)}})
    if not doc:
        return None
    return _sanitize_skills(doc.get("skills", []))


def _resolve_predefined_role_skills(role_key: str) -> Optional[List[str]]:
    collection = _get_role_master_collection()
    if collection is None:
        return BOOTSTRAP_ROLE_SKILLS.get(role_key)

    variants = _role_key_variants(role_key)
    doc = collection.find_one({"role_key": {"$in": variants}})
    if doc:
        return _sanitize_skills(doc.get("skills", []))

    role_keys = [d.get("role_key", "") for d in collection.find({}, {"role_key": 1, "_id": 0})]
    role_keys = [k for k in role_keys if k]
    if not role_keys:
        return None

    match = process.extractOne(role_key, role_keys, scorer=fuzz.ratio)
    if match and match[1] >= ROLE_PREDEFINED_FUZZY_THRESHOLD:
        best = collection.find_one({"role_key": match[0]})
        if best:
            return _sanitize_skills(best.get("skills", []))
    return None


def _get_master_roles_map() -> Dict[str, List[str]]:
    collection = _get_role_master_collection()
    if collection is None:
        return BOOTSTRAP_ROLE_SKILLS

    roles_map: Dict[str, List[str]] = {}
    for doc in collection.find({}, {"role_key": 1, "skills": 1, "_id": 0}):
        key = str(doc.get("role_key", "")).strip().lower()
        if not key:
            continue
        roles_map[key] = _sanitize_skills(doc.get("skills", []))

    return roles_map or BOOTSTRAP_ROLE_SKILLS


def _save_role_skills(role_key: str, display_role: str, skills: List[str], source: str = "gemini") -> None:
    collection = _get_role_cache_collection()
    if collection is None:
        return

    now = _utcnow()
    clean_skills = _sanitize_skills(skills)
    if clean_skills:
        expires_at = now + timedelta(days=ROLE_CACHE_TTL_DAYS)
    else:
        expires_at = now + timedelta(minutes=ROLE_CACHE_FAILURE_TTL_MINUTES)
    payload = {
        "role_key": role_key,
        "display_role": display_role,
        "skills": clean_skills,
        "source": source,
        "last_used_at": now,
        "expires_at": expires_at,
    }

    collection.update_one(
        {"role_key": role_key},
        {
            "$set": payload,
            "$setOnInsert": {"created_at": now, "hit_count": 0},
        },
        upsert=True,
    )


def resolve_requested_skills(job_skills: str) -> List[str]:
    clean_input = (job_skills or "").strip()
    if not clean_input:
        return []

    if "," in clean_input:
        return _sanitize_skills(clean_input.split(","))

    role_key = _normalize_role_key(clean_input)
    predefined = _resolve_predefined_role_skills(role_key)
    if predefined is not None:
        return predefined

    start = time.perf_counter()
    cached = _get_cached_role_skills(role_key)
    if cached is not None:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        print(f"Role cache hit for '{role_key}' in {elapsed_ms}ms")
        return cached

    ai_skills = _sanitize_skills(get_dynamic_skills_from_ai(role_key))
    if not ai_skills:
        stale = _get_stale_cached_role_skills(role_key)
        if stale:
            print(f"Using stale cache for '{role_key}' due to temporary AI issue")
            return stale

    source = "gemini" if ai_skills else "gemini_unavailable"
    _save_role_skills(role_key=role_key, display_role=clean_input, skills=ai_skills, source=source)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    print(f"Role cache miss for '{role_key}'. Gemini+save path took {elapsed_ms}ms")
    return ai_skills


# Determine file type and extract plain text accordingly.
# Supports PDF, DOCX/DOC, images (OCR), and raw text.
def extract_text_from_file(file_path: Path) -> str:
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        with pdfplumber.open(str(file_path)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)

    if suffix in {".doc", ".docx"}:
        document = docx.Document(str(file_path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    if suffix in IMAGE_EXTENSIONS:
        img = Image.open(str(file_path))
        text = pytesseract.image_to_string(img)
        return text

    return file_path.read_text(encoding="utf-8", errors="ignore")


# Normalize whitespace characters and remove repeated blank lines.
def normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


# Identify common resume sections like education, experience, skills, and projects.
# This supports project B: section extraction, ready for more detailed parsing later.
def extract_sections(text: str) -> Dict[str, str]:
    # Use lowercase for matching but keep original text for extraction
    text_lower = text.lower()
    section_headers = ["experience", "education", "skills", "projects", "certifications", "summary", "objective"]
    
    # Track the start index of each section
    found_sections = []
    for header in section_headers :
        # Match header at start of line or with a bit of prefix (like icons)
        match = re.search(r"(?i)^\\s*(?:[\\W_]*)\\s*" + re.escape(header), text, re.MULTILINE)
        if match:
            found_sections.append((match.start(), header))
    
    # Sort by appearance in the text
    found_sections.sort()
    
    sections = {header: "" for header in section_headers}
    
    for i in range(len(found_sections)):
        start_idx, header = found_sections[i]
        end_idx = found_sections[i+1][0] if i+1 < len(found_sections) else len(text)
        
        # Extract from original text
        section_raw = text[start_idx:end_idx].strip()
        
        # Better header removal: find the first actual content line
        lines = section_raw.splitlines()
        if lines:
            # If the first line is mostly just the header, remove it
            first_line = lines[0].lower()
            if header in first_line and len(first_line) < len(header) + 5:
                content = "\n".join(lines[1:]).strip()
            else:
                # Header might be at the start of the first line
                content = re.sub(r"(?i)^\\s*(?:[\\W_]*)\\s*" + re.escape(header) + r"[:\\s-]*", "", section_raw, count=1).strip()
            
            # Final Cleanup: If it's still very lowercase, let's at least capitalize lines
            if content.islower():
                content = "\n".join([line.capitalize() for line in content.splitlines()])
                
            sections[header] = content

    return sections


# Extract skills from text using exact keyword matching and fuzzy matching
# (exact first, and then fuzzy match to cover small variations/typos).
def extract_skills(text: str, skill_bank: Optional[List[str]] = None) -> List[str]:
    if skill_bank is None:
        skill_bank = DEFAULT_SKILLS

    text_lower = text.lower()
    found = set()

    for skill in skill_bank:
        pattern = r"\\b" + re.escape(skill.lower()) + r"\\b"
        if re.search(pattern, text_lower):
            found.add(skill)

    for skill in skill_bank:
        if skill in found:
            continue
        score = process.extractOne(skill, [text_lower], scorer=fuzz.partial_ratio)
        if score and score[1] >= 90:
            found.add(skill)

    return sorted(found)


# Basic heuristics to find name, email, and phone in resume text.
def basic_profile_summary(text: str) -> Dict[str, str]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    profile = {"name": "", "email": "", "phone": ""}

    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+", text)
    if email_match:
        profile["email"] = email_match.group(0)

    phone_match = re.search(r"(?:\\+?\\d[\\d\\s().-]{7,}\\d)", text)
    if phone_match:
        profile["phone"] = phone_match.group(0).strip()

    for line in lines[:8]:
        if any(k in line.lower() for k in ["experience", "education", "skills", "summary", "objective"]):
            continue
        if re.match(r"^[A-Z][a-z]+(?: [A-Z][a-z]+)*$", line):
            profile["name"] = line
            break

    return profile


# Generate simple feedback/foundations for improvement based on skills and key terms.
def give_feedback(text: str, detected_skills: List[str], job_skills: Optional[List[str]] = None) -> Dict[str, object]:
    feedback = {"highlights": [], "improvements": []}

    if not text.strip():
        feedback["improvements"].append("Resume text appears empty. Please upload a valid file.")
        return feedback

    if detected_skills:
        feedback["highlights"].append(f"Found {len(detected_skills)} skill keywords in your resume.")
    else:
        feedback["improvements"].append("No core skills detected. Add a Skills section.")

    if job_skills:
        job_skills_norm = [s.strip().lower() for s in job_skills if s.strip()]
        missing = [s for s in job_skills_norm if s not in [x.lower() for x in detected_skills]]
        if missing:
            feedback["improvements"].append("Consider adding these job-target skills: " + ", ".join(missing))
        else:
            feedback["highlights"].append("You have all target job skills listed!")

    text_lower = text.lower()

    # Fresher-focused heuristics
    if "education" not in text_lower:
        feedback["improvements"].append("Include an 'Education' section with your degree, institution, and graduation year/GPA.")

    if "projects" not in text_lower and "project" not in text_lower:
        feedback["improvements"].append("Add a 'Projects' section to showcase academic or personal coding projects, highlighting the tech stack used.")

    if "github" not in text_lower and "linkedin" not in text_lower:
        feedback["improvements"].append("Consider adding links to your GitHub and LinkedIn profiles for recruiters to view your work.")

    if not re.search(r"\b(\d+%|\d+\s+(?:increase|decrease|revenue|users|students|teams|events))\b", text_lower):
        feedback["improvements"].append("Try to quantify achievements (even in projects or clubs) with metrics, such as team size, numbers, or percentages.")

    if "skills" not in text_lower:
        feedback["improvements"].append("Add a dedicated 'Skills' section so your capabilities are easily scannable.")

    return feedback


# Algorithm to mathematically cross-reference detected skills with predefined job roles.
def suggest_roles(detected_skills: List[str]) -> List[Dict[str, object]]:
    detected_set = set([s.lower() for s in detected_skills])
    suggestions = []
    roles_map = _get_master_roles_map()

    for role, required_skills in roles_map.items():
        req_set = set([s.lower() for s in required_skills])
        overlap = req_set.intersection(detected_set)
        
        match_percentage = (len(overlap) / len(req_set)) * 100 if req_set else 0
        missing_skills = list(req_set - overlap)

        if match_percentage > 0:
            suggestions.append({
                "role": role.title(),
                "match_percentage": round(match_percentage, 1),
                "matched_skills": list(overlap),
                "missing_skills_to_learn": missing_skills
            })

    # Sort roles primarily by highest match percentage
    suggestions.sort(key=lambda x: x["match_percentage"], reverse=True)
    
    # Return Top 3 best matching career paths
    return suggestions[:3]

# Initialize Gemini Model
gemini_model = genai.GenerativeModel('gemini-2.5-flash-lite')

def get_dynamic_skills_from_ai(role_name: str) -> List[str]:
    """Uses Agentic AI to fetch the top 10 core technical skills for any arbitrary job role."""
    prompt = f"""
    Role: "{role_name}".
    Return exactly 8 core technical skills as a JSON array of lowercase strings.
    No explanation, no markdown, no extra keys.
    Example output: ["python", "aws", "kubernetes", "sql", "ci/cd"]
    """
    try:
        response = gemini_model.generate_content(
            prompt,
            generation_config={"temperature": 0.1, "max_output_tokens": 120},
        )
        text = response.text.replace("```json", "").replace("```", "").strip()
        skills = json.loads(text)
        if isinstance(skills, list) and len(skills) > 0:
            return [str(s).strip().lower() for s in skills]
        return []
    except Exception as e:
        print(f"Agentic AI Failed: {e}")
        return []
