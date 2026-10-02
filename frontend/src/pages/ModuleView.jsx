import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, CheckCircle2, Circle, Lock, Clock } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth, isStaff } from "@/context/AuthContext";
import { PageHeader } from "@/components/Common";
import ExamRunner, { ExamResult } from "@/components/ExamRunner";
import { MaterialBody, MAT_ICON, embedUrl } from "@/components/Materials";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

function TaskCard({ mat, i, done, onDone, staff }) {
  const Icon = MAT_ICON[mat.type];
  return (
    <div className={`bg-white border rounded-xl p-5 sm:p-6 ${done ? "border-emerald-200" : ""}`} data-testid={`task-${i}`}>
      <div className="flex items-center gap-3 mb-4">
        <span className="h-9 w-9 rounded-lg bg-teal-50 text-teal-700 grid place-items-center"><Icon size={18} /></span>
        <div className="flex-1"><p className="text-xs uppercase tracking-wider text-slate-400">Tarea {i + 1}</p><p className="font-semibold">{mat.title}</p></div>
        {done ? <CheckCircle2 className="text-emerald-600" data-testid={`task-done-${i}`} /> : <Circle className="text-slate-300" />}
      </div>
      <MaterialBody m={mat} />
      {!staff && !done && <Button size="sm" className="mt-4" onClick={onDone} data-testid={`task-complete-${i}`}>Marcar tarea como completada</Button>}
    </div>
  );
}

function TimeBar({ m }) {
  const pct = Math.min(100, (m.time_spent_min / m.min_minutes) * 100);
  return (
    <div className={`border rounded-xl p-4 mb-6 ${m.time_ok ? "bg-emerald-50 border-emerald-200" : "bg-white"}`} data-testid="module-time-requirement">
      <div className="flex items-center justify-between text-sm mb-2">
        <span className="flex items-center gap-2"><Clock size={16} className={m.time_ok ? "text-emerald-600" : "text-amber-600"} /> Tiempo mínimo de estudio</span>
        <b className="font-mono" data-testid="module-time-spent">{Math.floor(m.time_spent_min)} / {m.min_minutes} min</b>
      </div>
      <Progress value={pct} className="h-2" />
      <p className="text-xs text-slate-500 mt-2">{m.time_ok ? "Cumpliste el tiempo mínimo." : "El tiempo se cuenta mientras tienes este módulo abierto en pantalla."}</p>
    </div>
  );
}

function ExamSection({ m, onResult, result, setResult }) {
  const [retry, setRetry] = useState(0);
  const last = m.last_submission;
  if (m.completed) return <ExamResult result={last || { passed: true, score: 100, status: "calificada" }} />;
  if (result) {
    return (
      <ExamResult result={result}>
        {result.passed && <Button asChild><Link to={`/curso/${m.course_id}`} data-testid="module-continue-button">Continuar al siguiente módulo</Link></Button>}
        {result.passed === false && <Button variant="outline" onClick={() => { setResult(null); setRetry(retry + 1); }} data-testid="module-repeat-tasks-button">Repetir tareas del módulo</Button>}
      </ExamResult>
    );
  }
  if (last?.status === "en_revision") return <ExamResult result={last} />;
  if (!m.tasks_done || !m.time_ok) {
    return (
      <div className="bg-slate-100 rounded-xl p-6 flex flex-wrap items-center gap-3 text-slate-600" data-testid="module-exam-locked">
        <Lock size={18} /> {!m.tasks_done ? "Completa todas las tareas del módulo para habilitar el examen." : `Debes dedicar al menos ${m.min_minutes} min al módulo para habilitar el examen.`}
        {last?.passed === false && <span className="text-rose-600 text-sm">(Reprobaste el intento anterior: debes repetir las tareas.)</span>}
      </div>
    );
  }
  return <ExamRunner key={retry} quiz={m.quiz} submitUrl={`/modules/${m.id}/submit`} onResult={onResult} />;
}

export default function ModuleView() {
  const { id } = useParams();
  const { user } = useAuth();
  const staff = isStaff(user);
  const [m, setM] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const load = () => api.get(`/modules/${id}`).then((r) => setM(r.data)).catch((e) => setError(errMsg(e)));
  useEffect(() => { setResult(null); load(); }, [id]); // eslint-disable-line
  const needsTime = m && !staff && !m.completed && m.min_minutes > 0 && !m.time_ok;
  useEffect(() => {
    if (!needsTime) return;
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [needsTime]); // eslint-disable-line

  if (error) return <div className="bg-white border rounded-xl p-8" data-testid="module-locked-message"><p className="font-semibold">{error}</p><Link to="/" className="text-teal-700 text-sm">Volver</Link></div>;
  if (!m) return <p className="text-slate-500">Cargando…</p>;
  const mats = m.materials || [];
  const doneIds = m.completed_tasks || [];
  const hasQuiz = m.quiz?.questions?.length > 0;
  const back = staff ? `/cursos/${m.course_id}/editar` : `/curso/${m.course_id}`;
  const doneCount = mats.filter((x) => doneIds.includes(x.id)).length;
  const completeTask = (mid) => api.post(`/modules/${id}/tasks/${mid}/complete`).then(load).catch((e) => toast.error(errMsg(e)));
  const markDone = () => api.post(`/modules/${id}/complete`).then(() => { toast.success("Módulo completado"); load(); }).catch((e) => toast.error(errMsg(e)));

  return (
    <div className="max-w-3xl">
      <Link to={back} className="text-sm text-slate-500 flex items-center gap-1 mb-4 hover:text-slate-800" data-testid="module-back-link"><ArrowLeft size={14} /> Volver al curso</Link>
      <PageHeader eyebrow={`Módulo ${m.order}`} title={m.title} subtitle={m.description} />
      {m.content && <article className="bg-white border rounded-xl p-6 whitespace-pre-wrap leading-relaxed text-slate-700 mb-6" data-testid="module-content">{m.content}</article>}
      {m.video_url && <div className="aspect-video rounded-xl overflow-hidden bg-black mb-6"><iframe title="video" src={embedUrl(m.video_url)} className="w-full h-full" allowFullScreen /></div>}
      {!staff && !m.completed && m.min_minutes > 0 && <TimeBar m={m} />}
      {mats.length > 0 && (
        <>
          <div className="flex items-center justify-between mb-3"><h3 className="text-xl font-semibold">Tareas del módulo</h3>{!staff && <span className="text-sm text-slate-500" data-testid="tasks-progress">{doneCount}/{mats.length}</span>}</div>
          {!staff && <Progress value={(doneCount / mats.length) * 100} className="h-2 mb-4" />}
          <div className="space-y-4 mb-10">{mats.map((x, i) => <TaskCard key={x.id} mat={x} i={i} staff={staff} done={doneIds.includes(x.id)} onDone={() => completeTask(x.id)} />)}</div>
        </>
      )}
      {m.completed && !hasQuiz && <p className="mb-6 flex items-center gap-2 text-emerald-700 font-medium" data-testid="module-completed-badge"><CheckCircle2 size={18} /> Módulo completado</p>}
      {!staff && !hasQuiz && !m.completed && <Button onClick={markDone} disabled={!m.tasks_done || !m.time_ok} data-testid="module-mark-complete-button">Finalizar módulo</Button>}
      {!staff && hasQuiz && (
        <>
          <h3 className="text-xl font-semibold mb-4">Examen del módulo</h3>
          <ExamSection m={m} result={result} setResult={(r) => { setResult(r); if (!r) load(); }} onResult={(r) => { setResult(r); load(); }} />
        </>
      )}
    </div>
  );
}
