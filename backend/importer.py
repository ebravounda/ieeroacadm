import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, new_id
from server import staff_only

router = APIRouter()

MOD_RE = re.compile(r"^m[oó]dulo\s+(\d+)\s*[:.\-–—]?\s*(.*)$", re.I)
LESSON_RE = re.compile(r"^(lecci[oó]n|tarea|unidad|tema)\s*\d*\b", re.I)
EXTRA_RE = re.compile(r"^(actividad(es)?( pr[aá]ctica)?|recursos?|material audiovisual|material descargable|videos?( recomendados?)?|caso|ejercicios?)\s*:?\s*$", re.I)
EVAL_RE = re.compile(r"^(evaluaci[oó]n|examen|prueba|cuestionario)\b", re.I)
OBJ_RE = re.compile(r"^objetivos?( (general|del m[oó]dulo))?\s*:?\s*(.*)$", re.I)
TAIL = {"EVALUACION DEL CURSO", "CERTIFICACION", "METODOLOGIA", "BIBLIOGRAFIA", "REQUISITOS DE APROBACION"}
URL_RE = re.compile(r"https?://\S+")
VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com")


def _plain(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").upper().strip(" :")


def _section(title):
    return {"id": new_id(), "title": title, "description": "", "lines": [], "links": []}


def parse_course_text(text: str):
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    modules, mod, sec, skip, title_next, obj_next = [], None, None, False, False, False
    for ln in lines:
        if not ln:
            continue
        m = MOD_RE.match(ln)
        if m:
            mod = {"title": m.group(2).strip(), "objective": "", "intro": [], "sections": []}
            modules.append(mod)
            sec, skip, title_next, obj_next = None, False, not m.group(2).strip(), False
            continue
        if mod is None:
            continue
        if _plain(ln) in TAIL:
            mod, sec = None, None
            continue
        if title_next:
            mod["title"], title_next = ln, False
            continue
        o = OBJ_RE.match(ln)
        if o and sec is None and not mod["objective"]:
            mod["objective"] = o.group(3).strip()
            obj_next = not mod["objective"]
            continue
        if obj_next:
            mod["objective"], obj_next = ln, False
            continue
        if LESSON_RE.match(ln) or EXTRA_RE.match(ln):
            sec, skip = _section(ln.rstrip(":")), False
            mod["sections"].append(sec)
            continue
        if EVAL_RE.match(ln) and len(ln) < 80:
            sec, skip = None, True
            continue
        if skip:
            continue
        target = sec["lines"] if sec else mod["intro"]
        target.append(ln)
        if sec:
            sec["links"] += URL_RE.findall(ln)
    out = []
    for i, md in enumerate(modules):
        sections, materials = [], []
        for s in md["sections"]:
            if not s["lines"]:
                continue
            sections.append({"id": s["id"], "title": s["title"], "description": ""})
            body = "\n".join(s["lines"])
            materials.append({"id": new_id(), "type": "texto", "title": s["title"], "body": body, "section_id": s["id"]})
            for url in dict.fromkeys(s["links"]):
                kind = "video" if any(h in url for h in VIDEO_HOSTS) else "enlace"
                materials.append({"id": new_id(), "type": kind, "title": "Video" if kind == "video" else "Recurso",
                                  "url": url, "section_id": s["id"]})
        if not sections and md["intro"]:
            sid = new_id()
            sections.append({"id": sid, "title": "Contenidos", "description": ""})
            materials.append({"id": new_id(), "type": "texto", "title": "Contenidos", "body": "\n".join(md["intro"]), "section_id": sid})
            md["intro"] = []
        out.append({"title": md["title"] or f"Módulo {i + 1}", "description": md["objective"][:300],
                    "content": "\n".join(([f"Objetivo: {md['objective']}"] if md["objective"] else []) + md["intro"]),
                    "sections": sections, "materials": materials})
    return out


class ImportIn(BaseModel):
    text: str = Field(min_length=20, max_length=400000)
    dry_run: bool = True


@router.post("/courses/{course_id}/import-modules")
async def import_modules(course_id: str, body: ImportIn, _=Depends(staff_only)):
    if not await db.courses.find_one({"id": course_id}, {"_id": 1}):
        raise HTTPException(404, "Curso no encontrado")
    mods = parse_course_text(body.text)
    if not mods:
        raise HTTPException(400, "No se encontraron módulos. Cada módulo debe comenzar con una línea 'MÓDULO 1', 'MÓDULO 2', etc.")
    summary = [{"title": m["title"], "sections": [s["title"] for s in m["sections"]], "contents": len(m["materials"])} for m in mods]
    if body.dry_run:
        return {"modules": summary}
    count = await db.modules.count_documents({"course_id": course_id})
    for i, m in enumerate(mods):
        mats = [{"body": "", "url": "", "file_id": "", "file_name": "", "content_type": "", **x} for x in m["materials"]]
        await db.modules.insert_one({"id": new_id(), "course_id": course_id, "order": count + i + 1, "video_url": "",
                                     "min_minutes": 0, "quiz": {"questions": [], "pass_score": 75}, **m, "materials": mats})
    return {"modules": summary, "created": len(mods)}
