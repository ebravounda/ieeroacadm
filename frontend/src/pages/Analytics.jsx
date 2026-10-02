import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { api, fmtDate, fmtNota } from "@/lib/api";
import { PageHeader, AiBadge } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const COLS = ["nombre", "apellidos", "email", "rut", "last_login", "logins", "days_attended", "total_minutes", "courses", "progress", "avg_score", "avg_nota", "ai_avg"];

function exportCsv(rows) {
  const csv = [COLS.join(","), ...rows.map((r) => COLS.map((c) => `"${r[c] ?? ""}"`).join(","))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = "analitica_estudiantes.csv";
  a.click();
}

export default function Analytics() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  useEffect(() => { api.get("/analytics/students").then((r) => setRows(r.data)); }, []);
  const list = rows.filter((r) => `${r.nombre} ${r.apellidos} ${r.email}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <PageHeader eyebrow="Analítica" title="Acceso, permanencia y progreso" subtitle="Asistencia (días con conexión), tiempo de permanencia, ingresos, avance y uso estimado de IA por estudiante.">
        <Button variant="outline" onClick={() => exportCsv(rows)} data-testid="analytics-export-button"><Download size={16} className="mr-2" /> Exportar CSV</Button>
      </PageHeader>
      <Input placeholder="Buscar estudiante…" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-sm mb-4 bg-white" data-testid="analytics-search-input" />
      <div className="bg-white border rounded-xl overflow-x-auto">
        <Table data-testid="analytics-students-table">
          <TableHeader><TableRow>
            <TableHead>Estudiante</TableHead><TableHead>Último acceso</TableHead><TableHead className="text-right">Ingresos</TableHead>
            <TableHead className="text-right">Días asistidos</TableHead><TableHead className="text-right">Permanencia</TableHead>
            <TableHead>Avance</TableHead><TableHead className="text-right">Logro prom.</TableHead><TableHead className="text-right">Nota prom.</TableHead><TableHead>Uso IA</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {list.map((r) => (
              <TableRow key={r.id} data-testid={`analytics-row-${r.id}`}>
                <TableCell><p className="font-medium">{r.nombre} {r.apellidos}</p><p className="text-xs text-slate-500">{r.email}</p></TableCell>
                <TableCell className="text-xs">{fmtDate(r.last_login)}</TableCell>
                <TableCell className="text-right font-mono">{r.logins}</TableCell>
                <TableCell className="text-right font-mono">{r.days_attended}</TableCell>
                <TableCell className="text-right font-mono">{r.total_minutes} min</TableCell>
                <TableCell className="min-w-[120px]"><Progress value={r.progress} className="h-2" /><span className="text-xs text-slate-500">{r.progress}% · {r.courses} cursos</span></TableCell>
                <TableCell className="text-right font-mono">{r.avg_score ?? "—"}{r.avg_score != null && "%"}</TableCell>
                <TableCell className="text-right font-mono font-semibold" data-testid={`analytics-nota-${r.id}`}>{fmtNota(r.avg_nota)}</TableCell>
                <TableCell><AiBadge value={r.ai_avg} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}
