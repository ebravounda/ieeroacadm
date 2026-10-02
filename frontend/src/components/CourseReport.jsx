import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, FileSpreadsheet } from "lucide-react";
import { api, errMsg, fmtDate, fmtDay, fmtNota } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const COLS = [
  ["Apellidos", (r) => r.apellidos], ["Nombres", (r) => r.nombre], ["RUT", (r) => r.rut], ["Correo", (r) => r.email],
  ["Fecha matrícula", (r) => fmtDay(r.enrolled_at)], ["Tipo matrícula", (r) => r.method],
  ["Último acceso", (r) => (r.last_access ? fmtDate(r.last_access) : "")], ["Días conectado al curso", (r) => r.days_attended],
  ["Permanencia en el curso (min)", (r) => r.total_minutes], ["Días en plataforma (total)", (r) => r.platform_days],
  ["Permanencia en plataforma (min, total)", (r) => r.platform_minutes], ["Clases en vivo asistidas", (r) => `${r.live_attended}/${r.live_total}`],
  ["% asistencia clases", (r) => (r.live_pct ?? "")], ["Módulos aprobados", (r) => `${r.modules_done}/${r.modules_total}`],
  ["% avance", (r) => r.progress], ["Nota promedio módulos", (r) => fmtNota(r.modules_avg_nota)],
  ["Nota examen final", (r) => fmtNota(r.final_nota)], ["Nota final curso", (r) => fmtNota(r.overall_nota)],
  ["Estado", (r) => r.status], ["Fecha aprobación", (r) => (r.completed_at ? fmtDay(r.completed_at) : "")],
];

function exportCsv(data) {
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const meta = [`Curso;${esc(data.course.title)}`, `Código;${esc(data.course.code)}`, `Horas;${data.course.hours}`, `Generado;${esc(fmtDate(data.generated_at))}`, ""];
  const lines = data.rows.map((r) => COLS.map(([, f]) => esc(f(r))).join(";"));
  const blob = new Blob(["\ufeff" + [...meta, COLS.map(([h]) => esc(h)).join(";"), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `reporte_otec_${(data.course.code || data.course.title).replace(/\W+/g, "_")}_${data.generated_at.slice(0, 10)}.csv`;
  a.click();
}

export default function CourseReport({ courseId }) {
  const [data, setData] = useState(null);
  useEffect(() => { api.get(`/courses/${courseId}/report`).then((r) => setData(r.data)).catch((e) => toast.error(errMsg(e))); }, [courseId]);
  if (!data) return <p className="text-slate-500">Generando reporte…</p>;
  const s = data.summary;

  return (
    <div className="space-y-4" data-testid="course-report">
      <div className="bg-white border rounded-xl p-5 flex flex-wrap items-center gap-4">
        <FileSpreadsheet className="text-teal-700" />
        <div className="flex-1 min-w-[200px]">
          <p className="font-semibold">Reporte OTEC / SENCE</p>
          <p className="text-xs text-slate-500">{s.students} matriculados · {s.approved} aprobados · {s.live_classes} clases en vivo · generado {fmtDate(data.generated_at)}</p>
        </div>
        <Button onClick={() => exportCsv(data)} disabled={!data.rows.length} data-testid="course-report-export"><Download size={16} className="mr-2" /> Descargar reporte (CSV)</Button>
      </div>
      <div className="bg-white border rounded-xl overflow-x-auto">
        <Table>
          <TableHeader><TableRow>
            <TableHead>Estudiante</TableHead><TableHead className="text-right">Días en curso</TableHead><TableHead className="text-right">Permanencia en curso</TableHead>
            <TableHead className="text-right">Clases</TableHead><TableHead className="text-right">Módulos</TableHead>
            <TableHead className="text-right">Prom. mód.</TableHead><TableHead className="text-right">Ex. final</TableHead><TableHead className="text-right">Nota final</TableHead><TableHead>Estado</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {data.rows.length === 0 && <TableRow><TableCell colSpan={9} className="text-center text-slate-500">Sin estudiantes matriculados.</TableCell></TableRow>}
            {data.rows.map((r) => (
              <TableRow key={r.email} data-testid="course-report-row">
                <TableCell><p className="font-medium">{r.student_name}</p><p className="text-xs text-slate-500">{r.rut ? `${r.rut} · ` : ""}{r.email}</p></TableCell>
                <TableCell className="text-right font-mono">{r.days_attended}</TableCell>
                <TableCell className="text-right font-mono" data-testid="course-report-minutes">{r.total_minutes} min<p className="text-[10px] text-slate-400">{r.platform_minutes} min total</p></TableCell>
                <TableCell className="text-right font-mono">{r.live_attended}/{r.live_total}</TableCell>
                <TableCell className="text-right font-mono">{r.modules_done}/{r.modules_total}</TableCell>
                <TableCell className="text-right font-mono">{fmtNota(r.modules_avg_nota)}</TableCell>
                <TableCell className="text-right font-mono">{fmtNota(r.final_nota)}</TableCell>
                <TableCell className="text-right font-mono font-bold">{fmtNota(r.overall_nota)}</TableCell>
                <TableCell><span className={`text-xs rounded-full px-2 py-0.5 font-semibold ${r.status === "Aprobado" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{r.status}</span></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
