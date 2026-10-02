import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, PlayCircle, Lock, ArrowRight, Hourglass, ListTodo } from "lucide-react";
import { api, fmtNota } from "@/lib/api";
import { PageHeader, Empty } from "@/components/Common";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";

const STATE = {
  completado: { icon: CheckCircle2, cls: "text-emerald-600", label: "Completado" },
  en_curso: { icon: PlayCircle, cls: "text-teal-600", label: "En curso" },
  bloqueado: { icon: Lock, cls: "text-slate-400", label: "Bloqueado" },
};

function ModuleLine({ m }) {
  const s = STATE[m.state];
  const Icon = s.icon;
  return (
    <div className={`py-3 ${m.state === "bloqueado" ? "opacity-60" : ""}`} data-testid={`progress-module-${m.id}`}>
      <div className="flex items-center gap-3">
        <Icon size={18} className={s.cls} />
        <p className="flex-1 text-sm font-medium">{m.title}</p>
        <span className="text-xs text-slate-500">{m.tasks_done}/{m.tasks_total} tareas</span>
        {m.exam_status === "en_revision" && <span className="text-xs rounded-full px-2 py-0.5 bg-indigo-100 text-indigo-700 flex items-center gap-1"><Hourglass size={12} /> En revisión</span>}
        <span className={`text-xs font-semibold ${s.cls}`} data-testid={`progress-module-state-${m.id}`}>{s.label}</span>
        {m.nota != null && <span className="text-xs font-mono font-bold w-8 text-right">{fmtNota(m.nota)}</span>}
      </div>
      {m.pending_tasks.length > 0 && (
        <ul className="ml-8 mt-2 space-y-1" data-testid={`progress-pending-${m.id}`}>
          {m.pending_tasks.map((t) => <li key={t} className="text-xs text-slate-600 flex items-center gap-2"><ListTodo size={12} className="text-amber-600" /> Pendiente: {t}</li>)}
        </ul>
      )}
    </div>
  );
}

function CourseProgress({ c }) {
  return (
    <div className="bg-white border rounded-xl p-6 shadow-sm" data-testid={`progress-course-${c.course_id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-mono text-slate-400">{c.code || "CURSO"}</p>
          <h3 className="text-lg font-semibold">{c.title}</h3>
        </div>
        <div className="text-right">
          <p className="text-xs text-slate-500">Promedio módulos</p>
          <p className="font-heading font-bold text-xl">{fmtNota(c.grades.modules_avg_nota)}</p>
        </div>
      </div>
      <div className="flex justify-between text-xs text-slate-500 mt-4 mb-1.5"><span>Avance</span><span>{c.progress}%</span></div>
      <Progress value={c.progress} className="h-2" />
      <div className="divide-y mt-4">{c.modules.map((m) => <ModuleLine key={m.id} m={m} />)}</div>
      <div className="mt-5 rounded-lg bg-[#0F172A] text-white p-4 flex flex-col sm:flex-row sm:items-center gap-3" data-testid={`progress-next-step-${c.course_id}`}>
        <div className="flex-1"><p className="text-xs uppercase tracking-wider text-teal-300">Siguiente paso</p><p className="text-sm mt-0.5">{c.next_step.text}</p></div>
        <Button asChild variant="secondary" size="sm"><Link to={c.next_step.link} data-testid={`progress-next-step-link-${c.course_id}`}>Ir ahora <ArrowRight size={14} className="ml-1" /></Link></Button>
      </div>
    </div>
  );
}

export default function MyProgress() {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/my/progress").then((r) => setRows(r.data)); }, []);
  if (!rows) return <p className="text-slate-500">Cargando…</p>;
  return (
    <>
      <PageHeader eyebrow="Aula virtual" title="Mi avance" subtitle="Revisa qué módulos completaste, qué tareas tienes pendientes y cuál es tu siguiente paso en cada curso." />
      {rows.length === 0 ? <Empty text="Aún no estás matriculado en ningún curso." testId="progress-empty" />
        : <div className="grid lg:grid-cols-2 gap-6">{rows.map((c) => <CourseProgress key={c.course_id} c={c} />)}</div>}
    </>
  );
}
