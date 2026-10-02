import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Video, Trash2, ExternalLink, Users, ClipboardList, Download, Award } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { useAuth, isStaff } from "@/context/AuthContext";
import { PageHeader, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const STATUS = {
  en_vivo: { label: "En vivo", cls: "bg-rose-100 text-rose-700" },
  programada: { label: "Programada", cls: "bg-indigo-50 text-indigo-700" },
  finalizada: { label: "Finalizada", cls: "bg-slate-100 text-slate-500" },
};

function NewClassDialog({ onDone }) {
  const [open, setOpen] = useState(false);
  const [courses, setCourses] = useState([]);
  const [f, setF] = useState({ course_id: "", title: "", platform: "teams", url: "", start_at: "", end_at: "" });
  useEffect(() => { if (open) api.get("/courses").then((r) => setCourses(r.data)); }, [open]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault();
    try {
      await api.post("/live-classes", { ...f, start_at: new Date(f.start_at).toISOString(), end_at: new Date(f.end_at).toISOString() });
      toast.success("Clase programada"); setOpen(false); onDone();
    } catch (err) { toast.error(errMsg(err)); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button data-testid="live-classes-new-button"><Plus size={16} className="mr-2" /> Programar clase</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Nueva clase en vivo</DialogTitle></DialogHeader>
        <form onSubmit={save} className="space-y-3">
          <div><Label>Curso</Label>
            <Select value={f.course_id} onValueChange={(v) => setF({ ...f, course_id: v })}>
              <SelectTrigger data-testid="live-class-course-select"><SelectValue placeholder="Selecciona curso" /></SelectTrigger>
              <SelectContent>{courses.map((c) => <SelectItem key={c.id} value={c.id}>{c.title}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label>Título</Label><Input required value={f.title} onChange={set("title")} data-testid="live-class-title-input" /></div>
          <div><Label>Plataforma</Label>
            <Select value={f.platform} onValueChange={(v) => setF({ ...f, platform: v })}>
              <SelectTrigger data-testid="live-class-platform-select"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="teams">Microsoft Teams</SelectItem><SelectItem value="meet">Google Meet</SelectItem></SelectContent>
            </Select>
          </div>
          <div><Label>Enlace de la reunión</Label><Input required type="url" placeholder="https://teams.microsoft.com/…" value={f.url} onChange={set("url")} data-testid="live-class-url-input" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Inicio</Label><Input required type="datetime-local" value={f.start_at} onChange={set("start_at")} data-testid="live-class-start-input" /></div>
            <div><Label>Término</Label><Input required type="datetime-local" value={f.end_at} onChange={set("end_at")} data-testid="live-class-end-input" /></div>
          </div>
          <Button type="submit" className="w-full" disabled={!f.course_id} data-testid="live-class-save-button">Guardar</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function exportAttendance(data) {
  const c = data.class;
  const head = ["Curso", "Clase", "Plataforma", "Fecha inicio", "Estudiante", "RUT", "Correo", "Asistencia", "Hora de ingreso"];
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = data.rows.map((r) => [c.course_title, c.title, c.platform === "teams" ? "Teams" : "Meet", fmtDate(c.start_at), r.student_name, r.rut, r.email, r.present ? "Presente" : "Ausente", r.joined_at ? fmtDate(r.joined_at) : ""].map(esc).join(";"));
  const blob = new Blob(["\ufeff" + [head.map(esc).join(";"), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `asistencia_${c.title.replace(/\W+/g, "_")}_${c.start_at.slice(0, 10)}.csv`;
  a.click();
}

function AttendanceDialog({ classId }) {
  const [data, setData] = useState(null);
  const load = (open) => open && api.get(`/live-classes/${classId}/attendance`).then((r) => setData(r.data)).catch((e) => toast.error(errMsg(e)));
  return (
    <Dialog onOpenChange={load}>
      <DialogTrigger asChild><Button variant="outline" data-testid={`live-class-attendance-${classId}`}><ClipboardList size={16} className="mr-2" /> Asistencia</Button></DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Lista de asistencia</DialogTitle></DialogHeader>
        {!data ? <p className="text-slate-500 text-sm">Cargando…</p> : (
          <div data-testid="attendance-dialog">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div><p className="font-semibold">{data.class.title}</p><p className="text-xs text-slate-500">{data.class.course_title} · {fmtDate(data.class.start_at)}</p></div>
              <div className="flex items-center gap-3">
                <span className="text-sm font-mono" data-testid="attendance-summary">{data.present}/{data.total} presentes</span>
                <Button size="sm" onClick={() => exportAttendance(data)} disabled={!data.rows.length} data-testid="attendance-export-csv"><Download size={14} className="mr-1" /> Descargar CSV</Button>
              </div>
            </div>
            {data.rows.length === 0 ? <p className="text-sm text-slate-500">No hay estudiantes matriculados en este curso.</p> : (
              <div className="border rounded-lg divide-y">
                {data.rows.map((r) => (
                  <div key={r.email} className="flex items-center gap-3 px-4 py-2.5 text-sm" data-testid="attendance-row">
                    <div className="flex-1 min-w-0"><p className="font-medium truncate">{r.student_name}</p><p className="text-xs text-slate-500 truncate">{r.rut ? `${r.rut} · ` : ""}{r.email}</p></div>
                    <span className="text-xs text-slate-500">{r.joined_at ? new Date(r.joined_at).toLocaleTimeString("es-CL", { timeStyle: "short" }) : ""}</span>
                    <span className={`text-xs rounded-full px-2 py-0.5 font-semibold ${r.present ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{r.present ? "Presente" : "Ausente"}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ClassCard({ c, staff, onChange }) {
  const st = STATUS[c.status];
  const nav = useNavigate();
  const certificate = () => api.post(`/live-classes/${c.id}/certificate`).then((r) => nav(`/certificado-asistencia/${r.data.code}`)).catch((e) => toast.error(errMsg(e)));
  const join = () => api.post(`/live-classes/${c.id}/join`).then((r) => window.open(r.data.url, "_blank", "noopener")).catch((e) => toast.error(errMsg(e)));
  const del = () => window.confirm("¿Eliminar clase?") && api.delete(`/live-classes/${c.id}`).then(onChange);
  return (
    <div className={`bg-white border rounded-xl p-5 flex flex-col sm:flex-row sm:items-center gap-4 ${c.status === "en_vivo" ? "border-rose-300 shadow-md" : ""}`} data-testid={`live-class-${c.id}`}>
      <div className={`h-11 w-11 rounded-lg grid place-items-center ${c.platform === "teams" ? "bg-indigo-50 text-indigo-700" : "bg-emerald-50 text-emerald-700"}`}><Video size={20} /></div>
      <div className="flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="font-semibold">{c.title}</p>
          <span className={`text-xs rounded-full px-2 py-0.5 font-semibold flex items-center gap-1 ${st.cls}`} data-testid={`live-class-status-${c.id}`}>
            {c.status === "en_vivo" && <span className="live-dot h-1.5 w-1.5 rounded-full bg-rose-600" />}{st.label}
          </span>
        </div>
        <p className="text-xs text-slate-500 mt-1">{c.course_title} · {c.platform === "teams" ? "Microsoft Teams" : "Google Meet"} · {fmtDate(c.start_at)} – {new Date(c.end_at).toLocaleTimeString("es-CL", { timeStyle: "short" })}</p>
        {staff && <p className="text-xs text-slate-500 mt-1 flex items-center gap-1"><Users size={12} /> {c.attendees} asistentes registrados</p>}
      </div>
      {(c.status === "en_vivo" || staff) && (
        <Button onClick={join} className={c.status === "en_vivo" ? "bg-rose-600 hover:bg-rose-700" : ""} variant={c.status === "en_vivo" ? "default" : "outline"} data-testid={`live-class-open-${c.id}`}>
          <ExternalLink size={16} className="mr-2" /> Abrir clase
        </Button>
      )}
      {!staff && c.attended && c.status === "finalizada" && (
        <Button variant="outline" onClick={certificate} data-testid={`live-class-certificate-${c.id}`}><Award size={16} className="mr-2" /> Certificado de asistencia</Button>
      )}
      {staff && <AttendanceDialog classId={c.id} />}
      {staff && <Button size="icon" variant="ghost" onClick={del} data-testid={`live-class-delete-${c.id}`}><Trash2 size={16} /></Button>}
    </div>
  );
}

export default function LiveClasses() {
  const { user } = useAuth();
  const staff = isStaff(user);
  const [rows, setRows] = useState([]);
  const load = () => api.get("/live-classes").then((r) => setRows(r.data));
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, []);
  const order = { en_vivo: 0, programada: 1, finalizada: 2 };
  const sorted = [...rows].sort((a, b) => order[a.status] - order[b.status]);

  return (
    <>
      <PageHeader eyebrow="Sincrónico" title="Clases en vivo" subtitle="Sesiones por Microsoft Teams y Google Meet. El botón “Abrir clase” se habilita cuando la clase está en línea y registra tu asistencia.">
        {staff && <NewClassDialog onDone={load} />}
      </PageHeader>
      {sorted.length === 0 ? <Empty text="No hay clases programadas." testId="live-classes-empty" /> : (
        <div className="space-y-3">{sorted.map((c) => <ClassCard key={c.id} c={c} staff={staff} onChange={load} />)}</div>
      )}
    </>
  );
}
