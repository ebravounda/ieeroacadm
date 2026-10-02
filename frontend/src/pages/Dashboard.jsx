import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Users, BookOpen, Award, Activity, Bot, AlertTriangle, PlayCircle } from "lucide-react";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { api, errMsg, fmtNota } from "@/lib/api";
import { useAuth, isStaff } from "@/context/AuthContext";
import { PageHeader, StatCard, Empty } from "@/components/Common";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";

function StaffDashboard() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/analytics/overview").then((r) => setD(r.data)); }, []);
  if (!d) return <p className="text-slate-500">Cargando…</p>;
  return (
    <>
      <PageHeader eyebrow="Panel de gestión" title="Resumen institucional" subtitle="Acceso, permanencia y uso de IA de tus estudiantes en tiempo real." />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Estudiantes" value={d.students} icon={Users} testId="analytics-students-count" />
        <StatCard label="Activos hoy" value={d.active_today} icon={Activity} accent="text-indigo-700 bg-indigo-50" testId="analytics-active-today" />
        <StatCard label="Cursos" value={d.courses} icon={BookOpen} testId="analytics-courses-count" />
        <StatCard label="Diplomas emitidos" value={d.diplomas} icon={Award} accent="text-amber-700 bg-amber-50" testId="analytics-diplomas-count" />
      </div>
      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white border rounded-xl p-6 shadow-sm">
          <h3 className="text-lg font-semibold mb-4">Asistencia diaria a la plataforma (14 días)</h3>
          <div className="h-64" data-testid="analytics-daily-chart">
            <ResponsiveContainer>
              <AreaChart data={d.daily}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="date" fontSize={12} />
                <YAxis fontSize={12} allowDecimals={false} />
                <Tooltip />
                <Area type="monotone" dataKey="activos" name="Estudiantes activos" stroke="#11305C" fill="#DCE4F0" />
                <Area type="monotone" dataKey="minutos" name="Minutos totales" stroke="#FBAD17" fill="#FFF3D6" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="bg-[#0F172A] text-white rounded-xl p-6 flex flex-col">
          <div className="flex items-center gap-2 text-teal-300 text-xs uppercase tracking-wider"><Bot size={14} /> Detector de IA · Claude</div>
          <p className="mt-6 text-6xl font-heading font-extrabold" data-testid="analytics-ai-avg">{d.ai_avg}%</p>
          <p className="text-slate-400 text-sm mt-1">Promedio estimado de contenido generado por IA en respuestas abiertas</p>
          <div className="mt-auto pt-6 flex items-center gap-2 text-sm text-rose-300" data-testid="analytics-ai-high">
            <AlertTriangle size={16} /> {d.ai_high} entregas con riesgo alto (≥60%)
          </div>
          <Button asChild variant="secondary" className="mt-4"><Link to="/evaluaciones" data-testid="dashboard-go-submissions">Revisar evaluaciones</Link></Button>
        </div>
      </div>
    </>
  );
}

function CourseCard({ c }) {
  return (
    <Link to={`/curso/${c.id}`} className="group bg-white border rounded-xl p-6 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-[transform,box-shadow] block" data-testid={`my-course-${c.id}`}>
      <p className="text-xs font-mono text-slate-400">{c.code || "CURSO"}</p>
      <h3 className="text-lg font-semibold mt-1 group-hover:text-teal-700">{c.title}</h3>
      <p className="text-sm text-slate-500 mt-1 line-clamp-2">{c.description}</p>
      <div className="mt-5 flex justify-between text-xs text-slate-500 mb-1.5"><span>{c.completed_count}/{c.module_count} módulos</span><span>{c.progress}%</span></div>
      <Progress value={c.progress} className="h-2" />
      {c.final_passed && <p className="mt-3 text-xs font-semibold text-emerald-700 flex items-center gap-1"><Award size={14} /> Curso aprobado · Nota {fmtNota(c.grades?.overall_nota)}</p>}
      {!c.final_passed && c.grades?.modules_avg_nota && <p className="mt-3 text-xs text-slate-500">Promedio módulos: <b>{fmtNota(c.grades.modules_avg_nota)}</b></p>}
    </Link>
  );
}

function StudentDashboard({ user }) {
  const [mine, setMine] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const load = () => {
    api.get("/my/courses").then((r) => setMine(r.data));
    api.get("/courses").then((r) => setCatalog(r.data));
  };
  useEffect(load, []);
  const enroll = (id) => api.post(`/courses/${id}/enroll`).then(() => { toast.success("Matrícula realizada"); load(); }).catch((e) => toast.error(errMsg(e)));
  const available = catalog.filter((c) => c.auto_enroll && !mine.some((m) => m.id === c.id));

  return (
    <>
      <PageHeader eyebrow="Aula virtual" title={`Hola, ${user.nombre}`} subtitle="Completa cada módulo para desbloquear el siguiente. Al aprobar la evaluación final obtienes tu diploma." />
      <h3 className="text-lg font-semibold mb-4">Mis cursos</h3>
      {mine.length ? (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mb-12">{mine.map((c) => <CourseCard key={c.id} c={c} />)}</div>
      ) : <div className="mb-12"><Empty text="Aún no estás matriculado en ningún curso." testId="my-courses-empty" /></div>}
      {available.length > 0 && (
        <>
          <h3 className="text-lg font-semibold mb-4">Cursos con matrícula abierta</h3>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {available.map((c) => (
              <div key={c.id} className="bg-white border rounded-xl p-6" data-testid={`catalog-course-${c.id}`}>
                <h4 className="font-semibold">{c.title}</h4>
                <p className="text-sm text-slate-500 mt-1 line-clamp-2">{c.description}</p>
                <p className="text-xs text-slate-400 mt-3">{c.module_count} módulos · {c.hours} horas</p>
                <Button className="mt-4" size="sm" onClick={() => enroll(c.id)} data-testid={`catalog-enroll-${c.id}`}><PlayCircle size={14} className="mr-1" /> Matricularme</Button>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  return isStaff(user) ? <StaffDashboard /> : <StudentDashboard user={user} />;
}
