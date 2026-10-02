import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Lock, CheckCircle2, PlayCircle, Award, Trophy } from "lucide-react";
import { api, errMsg, fmtNota } from "@/lib/api";
import { useAuth, isStaff } from "@/context/AuthContext";
import { PageHeader } from "@/components/Common";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";

function ModuleRow({ m, i }) {
  const icon = m.completed ? <CheckCircle2 className="text-emerald-600" /> : m.unlocked ? <PlayCircle className="text-teal-600" /> : <Lock className="text-slate-400" />;
  const body = (
    <div className={`flex items-center gap-4 bg-white border rounded-xl p-5 transition-[transform,box-shadow] ${m.unlocked ? "hover:shadow-md hover:-translate-y-0.5" : "opacity-60"}`}>
      <span className="font-heading font-bold text-slate-300 text-2xl w-8">{String(i + 1).padStart(2, "0")}</span>
      <div className="flex-1"><p className="font-semibold">{m.title}</p><p className="text-sm text-slate-500">{m.description}</p></div>
      {icon}
    </div>
  );
  return m.unlocked ? <Link to={`/modulo/${m.id}`} data-testid={`module-flow-item-${i}`}>{body}</Link> : <div data-testid={`module-flow-item-${i}`} title="Completa el módulo anterior">{body}</div>;
}

function Grades({ g }) {
  const Cell = ({ label, nota, pct, testId, strong }) => (
    <div className={`rounded-xl p-4 ${strong ? "bg-teal-700 text-white" : "bg-white border"}`} data-testid={testId}>
      <p className={`text-xs uppercase tracking-wider ${strong ? "text-teal-100" : "text-slate-500"}`}>{label}</p>
      <p className="text-3xl font-heading font-extrabold mt-1">{fmtNota(nota)}</p>
      <p className={`text-xs ${strong ? "text-teal-100" : "text-slate-500"}`}>{pct ?? "—"}{pct !== null && pct !== undefined && "%"}</p>
    </div>
  );
  return (
    <div className="mt-6" data-testid="course-grades">
      <h3 className="text-lg font-semibold mb-3">Mis notas (escala 1,0 – 7,0)</h3>
      <div className="bg-white border rounded-xl divide-y mb-3">
        {g.modules.map((m) => (
          <div key={m.module_id} className="flex justify-between px-4 py-2.5 text-sm" data-testid={`grade-module-${m.module_id}`}>
            <span>{m.title}</span><span className="font-mono">{m.pct !== null ? `${m.pct}% · ` : ""}<b>{fmtNota(m.nota)}</b></span>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Cell label="Promedio módulos" nota={g.modules_avg_nota} pct={g.modules_avg_pct} testId="grade-modules-avg" />
        <Cell label="Examen final" nota={g.final_nota} pct={g.final_pct} testId="grade-final-exam" />
        <Cell label="Nota final curso" nota={g.overall_nota} pct={g.overall_pct} testId="grade-overall" strong />
      </div>
    </div>
  );
}

export default function CourseView() {
  const { id } = useParams();
  const { user } = useAuth();
  const [c, setC] = useState(null);
  const load = () => api.get(`/courses/${id}`).then((r) => setC(r.data));
  useEffect(() => { load(); }, [id]); // eslint-disable-line
  if (!c) return <p className="text-slate-500">Cargando…</p>;
  if (isStaff(user)) return <p>Vista de estudiante. <Link className="text-teal-700 underline" to={`/cursos/${id}/editar`}>Ir al editor</Link></p>;
  if (!c.enrollment) {
    const enroll = () => api.post(`/courses/${id}/enroll`).then(load).catch((e) => toast.error(errMsg(e)));
    return <><PageHeader title={c.title} subtitle={c.description} />{c.auto_enroll ? <Button onClick={enroll} data-testid="course-enroll-button">Matricularme</Button> : <p>Este curso requiere matrícula de la institución.</p>}</>;
  }
  const done = c.modules.filter((m) => m.completed).length;
  const pct = c.modules.length ? Math.round((done / c.modules.length) * 100) : 0;

  return (
    <>
      <PageHeader eyebrow={c.code || "Curso"} title={c.title} subtitle={c.description} />
      <div className="bg-white border rounded-xl p-5 mb-6" data-testid="module-flow-progress">
        <div className="flex justify-between text-sm mb-2"><span>{done} de {c.modules.length} módulos completados</span><b>{pct}%</b></div>
        <Progress value={pct} className="h-2.5" />
      </div>
      <div className="space-y-3">{c.modules.map((m, i) => <ModuleRow key={m.id} m={m} i={i} />)}</div>
      {c.grades && <Grades g={c.grades} />}
      <div className={`mt-6 rounded-xl p-6 flex flex-col sm:flex-row sm:items-center gap-4 ${c.final_unlocked ? "bg-[#0F172A] text-white" : "bg-slate-100 text-slate-500"}`} data-testid="final-exam-card">
        <Trophy className={c.final_unlocked ? "text-amber-400" : ""} />
        <div className="flex-1">
          <p className="font-semibold">Evaluación final del curso</p>
          <p className="text-sm opacity-80">{c.final_unlocked ? `${c.final_exam.question_count} preguntas · aprobación ${c.final_exam.pass_score}%` : "Se habilita al aprobar todos los exámenes de módulo."}</p>
        </div>
        {c.diploma_code ? (
          <Button asChild variant="secondary"><Link to={`/diploma/${c.diploma_code}`} data-testid="view-diploma-button"><Award size={16} className="mr-2" /> Ver diploma</Link></Button>
        ) : c.final_unlocked ? (
          <Button asChild><Link to={`/curso/${id}/final`} data-testid="start-final-exam-button">Rendir evaluación final</Link></Button>
        ) : <Lock />}
      </div>
    </>
  );
}
