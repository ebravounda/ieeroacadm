# PRD – IberoAcademy (iberoacademy.cl)

## Original problem statement
necesito crear una plataforma para un centro educativo La plataforma tendra esto:
- ingreso y matriculación automatizada y manual de estudiantes.
- control de asistencia a la plataforma del estudiante
- control de permanencia en la plataforma
- analisis de uso de IA para la resolución de examenes
- analítica de acceso y progreso de alumnos
- gestion de modulos y ramos en la plataforma
- avance de curso modular (para acceder al siguiente modulo debe completar el modulo de manera asincrónica.
- clases en vivo (con teams y google meets)
- evaluaciones por modulo
- evaluación final de cada curso
- diploma curso finalizado con nombre y apellidos del estudiante mas codigo qr de verificación del diploma firma del rector y vicerrector de la otec

Follow-up: la web se llama iberoacademy.cl; módulos 1,2,3 secuenciales; profesor rellena módulo con texto, videos, imágenes, PPT, PDF; examen por módulo (alternativas, selección múltiple, desarrollo) con % de aprobación configurable (default 75%); si reprueba repite las tareas; promedio = promedio % módulos promediado con examen final; notas chilenas 1-7; examen final requiere todos los módulos aprobados.

User choices: login con código al email; IA con Claude; Teams/Meet por enlace con botón "Abrir clase" en vivo; firmas PNG.

## Architecture
- FastAPI (`backend/server.py`, `backend/core.py`) + MongoDB + React (CRA, shadcn).
- Auth: passwordless OTP via Emergent-managed Resend → JWT (cookie + bearer/localStorage; `?auth=` for files).
- AI detection: Claude `claude-sonnet-5-5` via emergentintegrations (background task per submission).
- Files: Emergent object storage (`/api/files`).
- Roles: admin, docente, estudiante.

## Implemented (2026-10-02)
- OTP login, self-registration (auto-enroll), manual enrollment, CSV bulk import.
- Courses/modules CRUD, materials-as-tasks (texto/video/archivo/enlace), sequential unlocking.
- Module exams (single/multiple/open), default 75%, fail → tasks reset; open answers → teacher grading.
- Chilean grades 1.0–7.0 (exigencia = pass %), course final = avg(modules avg %, final %).
- Final exam gated; diploma with QR, nota final, rector/vicerrector PNG signatures; public /verificar/:code.
- Heartbeat attendance/permanence, analytics overview + per-student table + CSV export.
- Live classes (Teams/Meet link, live status, attendance on join).
- Claude AI-usage % per submission + behavior signals (tab switches, paste, time).

- Inline Office viewer (PPT/DOC/XLS) via 2h signed public URL + view.officeapps.live.com.
- Email to student when teacher grades a development exam (nota 1–7, logro, comentario).
- "Mi avance" student page (/mi-avance): per course module states, pending tasks, next step link (GET /api/my/progress).
- Live class email reminders: platform cron every 15 min (.emergent/crons.yml → POST /api/cron/class-reminders, WEBHOOK_CRON_SECRET), sends once per class 0–40 min before start.
- Live class attendance list per class (enrolled students Presente/Ausente, RUT, hora ingreso) + CSV export (GET /api/live-classes/{id}/attendance).
- Inactivity alerts: daily cron 10:00 America/Santiago → POST /api/cron/inactivity-alerts; emails students with unfinished courses and no activity in 7 days (max 1 alert / 7 days, includes next step).
- OTEC/SENCE course report tab in CourseEditor (GET /api/courses/{id}/report) + CSV export.
- Attendance certificates per finished live class (POST /api/live-classes/{id}/certificate, /certificado-asistencia/:code, public /verificar-asistencia/:code with QR).
- Per-course time tracking: heartbeat sends course_id/module_id from current route → db.course_sessions; OTEC report shows days/minutes per course plus platform totals.
- Weekly OTEC report email: cron Monday 08:00 America/Santiago → POST /api/cron/weekly-report; HTML tables per course sent to all active admins.
- Module minimum time (min_minutes, default 0): db.module_sessions tracks time on module page; exam/complete blocked until reached; reset on failed exam.
- Certificate approval flow: final pass → diploma status pendiente (code IBA-XXXX-XXXX) + email to active admins; admin approves in Diplomas → PDF (backend/certificate.py, pymupdf) stored in object storage, student email with motivational phrase + link to /verificar/{code} (email API has no attachments). Reject supported.
- Default template = customer's ZIP landscape design adapted (scripts/build_default_certificate.py → backend/assets/default_certificate.png) with IberoAcademy logo, QR bottom-left, 3 signatures (Rector Maximiliano Alcafuz Orellana, Vicerrectora Liliana Hernández Guerrero, Directora Académica Karolyne González Possamai). Admin can upload own PNG/JPG/PDF template + adjust layout + preview.
- IberoAcademy logo (frontend/public/logo.png) in sidebar, mobile header, login and all emails (core._brand uses PUBLIC_BASE remembered from last login host in db.app_meta).
- Bulk certificate approval: POST /api/diplomas/approve-bulk {ids}; checkboxes + "Aprobar seleccionados" in Diplomas → Solicitudes.
- Brand colors: tailwind `teal` scale remapped to IberoAcademy navy (#11305C) with yellow (#FBAD17) at 300/400; CSS vars primary navy, ring yellow; sidebar #0A2449; emails navy.
- Pending: customer must upload the 3 signature PNGs in Configuración.
- Public landing at / (logged-out): hero slider (admin-managed slides, 3 default images in public/landing), benefits/CV section, courses grid (published + show_on_landing; price, summary, image, modality), FAQ, enrollment dialog.
- Flow.cl payments (backend/shop.py): credentials stored in db.settings id=payments via admin "Sitio web" page (secret masked); checkout → Flow payment/create → redirect; confirm webhook + return URL call getStatus; status 2 → enroll + email. Admin "Pagos": list/filter, send payment link email, copy link, refresh, mark paid manually. Free courses enroll instantly.
- Flow NOT verified with real keys (customer hasn't provided sandbox keys yet).
- 2026-10-02: Landing "Alianzas estratégicas" section (#alianzas, after courses): 5 partner logos (AWS, Tramilex, GoRoky, Openfactura, Inmo Tramilex) in frontend/public/partners/*.png + country chips (Chile, España, México, Honduras, Perú).
- 2026-10-02: Legal pages /terminos and /privacidad (frontend/src/pages/Legal.jsx) per Chile (Ley 19.496, 19.628, 21.719) and Spain/EU (RGPD, LOPDGDD, LSSI, RDL 1/2007); company IBERO ACADEMY SpA RUT 78.486.869-9 Providencia. Footer links + company data. Mandatory accept checkbox in enroll dialog; backend /public/checkout requires accept_terms=true, stores users.terms_accepted_at. No cookie banner (customer choice). Placeholder pending: [correo de contacto].
- 2026-10-02: Customer asked about self-hosting on aaPanel + Cloudflare. Self-host caveats: EMERGENT_LLM_KEY, EMERGENT_EMAIL_KEY, object storage (INTEGRATION_PROXY_URL) and .emergent/crons.yml do not work outside Emergent → would need own OpenAI/Resend/storage keys + system cron (POST /api/cron/* with Bearer WEBHOOK_CRON_SECRET).

- 2026-10-02: Self-host support (aaPanel, iberoacademy.cl) via env switches in core.py: RESEND_API_KEY+MAIL_FROM → direct Resend API; OPENAI_API_KEY+OPENAI_MODEL → direct OpenAI chat completions (json_object); LOCAL_STORAGE_DIR → files on disk (path-traversal guarded). Without them, Emergent email/LLM/storage are used (preview unchanged). Deploy kit in /app/deploy: GUIA_AAPANEL.md, backend.env.example, nginx_iberoacademy.conf, crontab.txt (crons POST with Bearer WEBHOOK_CRON_SECRET and body {}).
- 2026-10-02: Admin "Integraciones" page (/integraciones, frontend/src/pages/Integrations.jsx; backend/integrations.py): Resend (key, mail_from, from name, test email), OpenAI (key, model, test), Flow (FlowSettings moved from Sitio web, embedded), Cron (lines to copy + regenerate secret). Stored in db.settings id=integrations; core.get_cfg() merges DB over env; keys returned only as ••••last4; clear:[...] removes. accept_cron uses DB cron_secret or env WEBHOOK_CRON_SECRET. WARNING: regenerating cron secret in Emergent preview/deploy breaks platform crons (they use env secret). Tested iteration_8: 100%.
- 2026-10-02: Self-host pip fix: backend/requirements-server.txt (no emergentintegrations/litellm/dev tools) — installs on clean venv without extra index; server boots; AI without OpenAI key fails gracefully. Customer server: Ubuntu 24.04 aarch64, app at /www/wwwroot/iberoacademy, Mongo in Docker iberoacademy-mongo 127.0.0.1:27022, backend pm2 port 8001. Repo github.com/ebravounda/ieeroacadm (public).
- 2026-10-02: ADMIN_EMAIL = info@iberoacademy.cl (preview .env + instalar.sh; MAIL_FROM info@iberoacademy.cl). Welcome email on every NEW enrollment (server.py send_welcome via asyncio.create_task, core.welcome_email_html): credentials (email + code login), meticulous study, module exams, min time, tracking of logins/time, final exam/certificate. Customer Resend key validated sending from info@iberoacademy.cl (key restricted to sending). Key NOT stored in repo (repo is public) — set on server .env. Tested iteration_9: 100%.
- 2026-10-02: LIVE on customer server https://iberoacademy.cl (verified externally: landing, login, /api). instalar.sh ran OK.
- 2026-10-02: Mass messaging (/mensajes, backend/messaging.py): templates CRUD with 4 seeded defaults, variables, [texto](url) links, audiences, preview/test/send background, history. Tested iteration_10 100%.
- 2026-10-02: SEO/social: index.html lang es-CL, title/description/keywords, canonical, geo, OG + Twitter (og-image.jpg 1200x630 generated), JSON-LD EducationalOrganization+WebSite, favicons/manifest, robots.txt, sitemap.xml, noscript content. New definitive Resend key provided by customer (validated) — set only on server .env/Integraciones, never in repo.
- 2026-10-02: Admin can edit student nombre/apellidos/RUT (Students.jsx EditUserDialog; PUT /api/users/{id} trims + requires nombre).
- 2026-10-02: Module sections: ModuleIn.sections [{id,title,description}], Material.section_id + type 'presentacion'; video accepts URL or uploaded MP4. SectionsEditor (Materials.jsx) with add/rename/reorder/delete; student ModuleView collapsible sections w/ per-section progress, any order. Legacy modules → single "Contenidos" section. Tested iteration_12: 100%.
- 2026-10-02: Import modules from pasted text (ChatGPT program): backend/importer.py POST /api/courses/{id}/import-modules {text, dry_run}; MÓDULO N → module, Lección/Tarea/Actividad/Recursos/Video → sections with texto material, URLs → video/enlace, Evaluación blocks + course-tail headings skipped. UI: ImportModules.jsx in CourseEditor Módulos tab (preview → import). Tested 100%. Then Markdown support (normalize(): headings, bold, code, bullets, tables, escapes, entities, [text](url) links w/o utm; fixture tests/sample_import_md.txt).
- 2026-10-02: Randomized tests: Quiz.draw_count (default 10) = questions per student drawn from module/final bank; per-student draw persisted in db.quiz_draws (options shuffled, correct remapped) until submit; submissions store attempt (UI "Primer/Segundo intento"); admin Submissions detail shows all choice questions with correct option + student answer. Final exam = 1 attempt: failing resets completed_modules/tasks/results + module_sessions (course_reset flag). Tested iteration_14: 100%. Needs deploy to iberoacademy.cl.
- 2026-10-02: Módulo 0 "Bienvenida al curso" in every course: real module (welcome=true, order 0) with video /bienvenida.mp4 (frontend/public); auto-created on course creation and backfilled on startup (ensure_welcome; in-progress enrollments auto-credited); must be marked seen + finalized to unlock Módulo 1; cannot be deleted; next_order = max order+1 (add_module + importer); MaterialBody plays direct .mp4 URLs with <video>. Tested iteration_15: 100%. Needs deploy to iberoacademy.cl.
- 2026-10-02: Admin impersonation "Ver como alumno" (Students page, admin only, active estudiantes): POST /api/users/{id}/impersonate → 1h token with imp claim; get_current_user blocks all non-GET (except logout) → read-only; /auth/me returns impersonated_by; db.impersonation_logs audit; yellow ImpersonationBar + "Volver a mi cuenta de admin" (admin token kept in localStorage otec_admin_token); heartbeat disabled while impersonating. Tested iteration_16: 100%.
- 2026-10-02: Final exam copy protection (ExamRunner protect prop, only FinalExam): no select/copy/cut/right-click/drag, Ctrl/Cmd+C/X/A/P/S/U and PrintScreen blocked with toast, print hidden; behavior.copy_attempts saved and shown in Evaluaciones ("intentos de copia"). Tested iteration_17: 100%. Needs deploy to iberoacademy.cl.



- P1: Per-teacher course ownership restrictions.
- P2: Attendance reports per live class export; certificate PDF generation server-side.
