import re
from pathlib import Path
from typing import Dict, List, Optional

import docx
import pdfplumber
import pytesseract
from PIL import Image
from rapidfuzz import process, fuzz

ROLE_SKILLS = {
    # Core Tech Roles
    "frontend developer": ["javascript", "react", "html", "css", "ui/ux", "git"],
    "backend developer": ["python", "java", "node.js", "sql", "django", "flask", "docker", "aws"],
    "web developer": ["javascript", "react", "node.js", "html", "css", "sql", "git"],
    "ai/ml engineer": ["python", "machine learning", "nlp", "tensorflow", "pytorch", "data analysis", "sql"],
    "data scientist": ["python", "r", "sql", "machine learning", "statistics", "data visualization", "pandas"],
    "mobile app developer": ["swift", "kotlin", "react native", "flutter", "java", "ios", "android"],

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

# Default keyword skills used for rudimentary matching. Combine base list with all role-specific skills.
BASE_SKILLS = [
    "python", "java", "c++", "javascript", "react", "angular", "node.js", "flask", "django",
    "sql", "nosql", "excel", "git", "docker", "kubernetes", "aws", "azure", "gcp", "nlp",
    "machine learning", "data analysis", "presentation", "communication", "leadership"
]
DEFAULT_SKILLS = sorted(list(set(BASE_SKILLS + [skill for skills in ROLE_SKILLS.values() for skill in skills])))

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}


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

    for role, required_skills in ROLE_SKILLS.items():
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
