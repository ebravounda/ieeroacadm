import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Bot, RefreshCw, Copy, Eye, Clock, ShieldAlert } from "lucide-react";
import { api, errMsg, fmtDate, fmtNota } from "@/lib/api";
import { PageHeader, AiBadge, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";

function GradeForm({ sub, onDone }) {
  const opens = sub.questions.filter((q) => q.type === "open" && (sub.question_scores || {})[q.id] == null);
  const [grades, setGrades] = useState({});
  const [feedback, setFeedback] = useState("");
  const save = () => api.post(`/submissions/${sub.id}/grade`, { grades, feedback }).then((r) => { toast.success("Calificación guardada"); onDone(r.data); }).catch((e) => toast.error(errMsg(e)));
  return (
    <div className="border-2 border-indigo-200 bg-indigo-50 rounded-xl p-4 space-y-3" data-testid="grade-form">
      <p className="font-semibold text-sm">Corregir preguntas de desarrollo (0–100% de logro)</p>
      {opens.map((q, i) => (
        <div key={q.id} className="flex items-center gap-3">
          <span className="text-sm flex-1 truncate">{q.text}</span>
          <Input type="number" min={0} max={100} className="w-24 bg-white" value={grades[q.id] ?? ""} onChange={(e) => setGrades({ ...grades, [q.id]: e.target.value === "" ? undefined : Number(e.target.value) })} data-testid={`grade-input-${i}`} />
        </div>
      ))}
      <Textarea placeholder="Comentario para el estudiante (opcional)" value={feedback} onChange={(e) => setFeedback(e.target.value)} className="bg-white" data-testid="grade-feedback" />
      <Button onClick={save} disabled={opens.some((q) => grades[q.id] === undefined)} data-testid="grade-save-button">Guardar calificación</Button>
    </div>
  );
}

function ChoiceReview({ sub }) {
  const qs = sub.questions.filter((q) => q.type !== "open");
  if (!qs.length) return null;
  const picked = (q) => { const a = sub.answers[q.id]; return Array.isArray(a) ? a.map(String) : a == null ? [] : [String(a)]; };
  const right = (q) => (q.type === "multiple" ? q.correct_multi || [] : [q.correct]).map(String);
  return (
    <div className="space-y-3" data-testid="choice-review">
      <p className="font-semibold text-sm">Preguntas y respuestas del test</p>
      {qs.map((q, i) => (
        <div key={q.id} className="border rounded-lg p-4" data-testid={`review-question-${i}`}>
          <div className="flex justify-between gap-2"><p className="text-sm font-semibold">{i + 1}. {q.text}</p><span className={`text-xs font-mono shrink-0 ${(sub.question_scores || {})[q.id] === 100 ? "text-emerald-700" : "text-rose-600"}`} data-testid={`review-result-${i}`}>{(sub.question_scores || {})[q.id] === 100 ? "Correcta" : "Incorrecta"}</span></div>
          <ul className="mt-2 space-y-1">
            {q.options.map((o, k) => {
              const ok = right(q).includes(String(k)); const mine = picked(q).includes(String(k));
              return <li key={k} className={`text-sm rounded px-2 py-1 flex justify-between gap-2 ${ok ? "bg-emerald-50 text-emerald-800" : mine ? "bg-rose-50 text-rose-700" : "text-slate-600"}`} data-testid={`review-q${i}-option-${k}`}><span>{o}</span><span className="text-xs shrink-0">{ok && "Correcta"}{ok && mine && " · "}{mine && "Respuesta del alumno"}</span></li>;
            })}
          </ul>
          {!picked(q).length && <p className="text-xs text-slate-400 mt-1">(sin respuesta)</p>}
        </div>
      ))}
    </div>
  );
}

const AttemptBadge = ({ s }) => <span className={`text-xs rounded-full px-2 py-0.5 font-semibold ${(s.attempt || 1) > 1 ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-600"}`} data-testid={`submission-attempt-${s.id}`}>{(s.attempt || 1) === 1 ? "Primer intento" : (s.attempt === 2 ? "Segundo intento" : `Intento ${s.attempt}`)}</span>;

function Detail({ sub, onReanalyze, busy, onGraded }) {
  const ai = sub.ai_analysis;
  const per = Object.fromEntries((ai?.answers || []).map((a) => [a.question_id, a]));
  return (
    <div className="space-y-5 mt-4" data-testid="ai-detector-detail">
      {sub.status === "en_revision" && <GradeForm sub={sub} onDone={onGraded} />}
      <div className="bg-[#0F172A] text-white rounded-xl p-5">
        <p className="text-xs uppercase tracking-wider text-teal-300 flex items-center gap-1"><Bot size={14} /> Análisis Claude</p>
        {ai ? (
          <>
            <p className="text-4xl font-heading font-extrabold mt-2" data-testid="ai-detector-percentage">{ai.percentage}%</p>
            <Progress value={ai.percentage} className="h-2 mt-2 bg-slate-700" />
            <p className="text-sm text-slate-300 mt-3">{ai.summary}</p>
          </>
        ) : <p className="mt-2 text-sm text-slate-300">Estado: {sub.ai_status}</p>}
        <Button size="sm" variant="secondary" className="mt-4" disabled={busy} onClick={onReanalyze} data-testid="ai-detector-reanalyze"><RefreshCw size={14} className={`mr-1 ${busy ? "animate-spin" : ""}`} /> Reanalizar</Button>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs">
        <div className="border rounded-lg p-3"><Eye size={14} className="mx-auto mb-1" /><b className="text-lg">{sub.behavior.tab_switches}</b><p>cambios de pestaña</p></div>
        <div className="border rounded-lg p-3"><Copy size={14} className="mx-auto mb-1" /><b className="text-lg">{sub.behavior.paste_events}</b><p>textos pegados</p></div>
        <div className="border rounded-lg p-3" data-testid="submission-copy-attempts"><ShieldAlert size={14} className="mx-auto mb-1" /><b className="text-lg">{sub.behavior.copy_attempts ?? 0}</b><p>intentos de copia</p></div>
        <div className="border rounded-lg p-3"><Clock size={14} className="mx-auto mb-1" /><b className="text-lg">{Math.round(sub.behavior.duration_sec / 60)}</b><p>minutos</p></div>
      </div>
      {sub.course_reset && <p className="text-sm bg-rose-50 border border-rose-200 text-rose-700 rounded-lg p-3" data-testid="submission-course-reset">Reprobó la evaluación final: su avance fue reiniciado y debe cursar todos los módulos nuevamente.</p>}
      <ChoiceReview sub={sub} />
      {sub.questions.filter((q) => q.type === "open").map((q) => (
        <div key={q.id} className="border rounded-lg p-4">
          <div className="flex justify-between gap-2"><p className="text-sm font-semibold">{q.text}</p><div className="flex gap-2 items-center shrink-0">{(sub.question_scores || {})[q.id] != null && <span className="text-xs font-mono">{sub.question_scores[q.id]}%</span>}<AiBadge value={per[q.id]?.percentage} /></div></div>
          <p className="text-sm text-slate-700 mt-2 bg-slate-50 rounded p-3 whitespace-pre-wrap">{sub.answers[q.id] || "(sin respuesta)"}</p>
          {per[q.id]?.reasoning && <p className="text-xs text-slate-500 mt-2">{per[q.id].reasoning}</p>}
        </div>
      ))}
    </div>
  );
}

export default function Submissions() {
  const [subs, setSubs] = useState([]);
  const [sel, setSel] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/submissions").then((r) => setSubs(r.data));
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);
  const reanalyze = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/submissions/${sel.id}/analyze`); setSel({ ...sel, ...data }); load(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader eyebrow="Evaluaciones" title="Entregas y detección de IA" subtitle="Cada respuesta abierta es analizada por Claude para estimar el porcentaje de contenido generado con IA." />
      {subs.length === 0 ? <Empty text="Aún no hay evaluaciones rendidas." testId="submissions-empty" /> : (
        <div className="bg-white border rounded-xl divide-y" data-testid="submissions-list">
          {subs.map((s) => (
            <button key={s.id} onClick={() => setSel(s)} className="w-full text-left p-4 flex flex-wrap items-center gap-4 hover:bg-slate-50 transition-colors" data-testid={`submission-row-${s.id}`}>
              <div className="flex-1 min-w-[200px]"><p className="font-medium">{s.student_name}</p><p className="text-xs text-slate-500">{s.course_title} · {s.module_title} · {fmtDate(s.created_at)}</p></div>
              <AttemptBadge s={s} />
              {s.status === "en_revision" ? <span className="text-xs rounded-full px-2 py-0.5 bg-indigo-100 text-indigo-700 font-semibold" data-testid={`submission-status-${s.id}`}>Por corregir</span>
                : <span className={`text-sm font-mono font-semibold ${s.passed ? "text-emerald-700" : "text-rose-600"}`} data-testid={`submission-status-${s.id}`}>{s.score}% · {fmtNota(s.nota)}</span>}
              {s.ai_status === "completado" ? <AiBadge value={s.ai_analysis.percentage} testId={`submission-ai-${s.id}`} /> : <span className="text-xs text-slate-400" data-testid={`submission-ai-${s.id}`}>IA: {s.ai_status}</span>}
            </button>
          ))}
        </div>
      )}
      <Sheet open={!!sel} onOpenChange={(o) => !o && setSel(null)}>
        <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
          {sel && <><SheetHeader><SheetTitle className="flex items-center gap-2">{sel.student_name} <AttemptBadge s={sel} /></SheetTitle><p className="text-sm text-slate-500">{sel.course_title} · {sel.module_title} · {sel.status === "en_revision" ? "Por corregir" : `Logro ${sel.score}% · Nota ${fmtNota(sel.nota)}`}</p></SheetHeader><Detail sub={sel} onReanalyze={reanalyze} busy={busy} onGraded={(d) => { setSel({ ...sel, ...d }); load(); }} /></>}
        </SheetContent>
      </Sheet>
    </>
  );
}
