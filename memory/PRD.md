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

## Backlog
- P1: Per-teacher course ownership restrictions.
- P2: Attendance reports per live class export; certificate PDF generation server-side.
