from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
from tempfile import NamedTemporaryFile

from .resume_analyzer import extract_text_from_file, extract_sections, extract_skills, give_feedback, ROLE_SKILLS, suggest_roles

# Core app instance
app = FastAPI(title="ResumeAnalyzer", version="1.0")

# Health check endpoint
@app.get("/")
async def root():
    return {"message": "ResumeAnalyzer API is running"}


# Analyze endpoint receives uploaded resume files and optional job skills
# Includes text extraction, resume section detection, and skill matching.
@app.post("/analyze")
async def analyze_resume(file: UploadFile = File(...), job_skills: str = Form(None)):
    supported_types = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "text/plain",
        "image/png",
        "image/jpeg",
        "image/bmp",
        "image/tiff",
    ] 

    if file.content_type not in supported_types:
        raise HTTPException(status_code=400, detail="Supported formats: PDF, DOCX, DOC, TXT, PNG, JPG, BMP, TIFF")

    suffix = Path(file.filename).suffix or ".txt"
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        extracted_text = extract_text_from_file(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    # Normalize and extract sections for education/experience/skills.
    normalized_text = extracted_text.strip()
    sections = extract_sections(normalized_text)

    # Studio: Skill matching using word lookup + fuzzy logic
    detected_skills = extract_skills(normalized_text)

    requested_skills = []
    if job_skills:
        clean_job = job_skills.strip().lower()
        if clean_job in ROLE_SKILLS:
            requested_skills = ROLE_SKILLS[clean_job]
        else:
            requested_skills = [skill.strip().lower() for skill in job_skills.split(",")]

    missing_skills = [skill for skill in requested_skills if skill and skill not in [s.lower() for s in detected_skills]]

    # Generate feedback based on detected and requested skills
    feedback = give_feedback(normalized_text, detected_skills, requested_skills)

    # Calculate Career Path Suggestions
    role_suggestions = suggest_roles(detected_skills)

    return JSONResponse({
        "filename": file.filename,
        "content_type": file.content_type,
        "extracted_length": len(normalized_text),
        "detected_skills": detected_skills,
        "requested_skills": requested_skills,
        "missing_skills": missing_skills,
        "role_suggestions": role_suggestions,
        "sections": sections,
        "feedback": feedback,
        "extracted_text_sample": normalized_text[:1000],
    })
