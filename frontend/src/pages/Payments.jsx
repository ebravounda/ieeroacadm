import { useEffect, useState } from "react";
import { toast } from "sonner";
import { RefreshCw, Send, CheckCircle2, Link2, Plus } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { PageHeader, StatCard, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const ST = { pagado: "bg-emerald-100 text-emerald-700", pendiente: "bg-amber-100 text-amber-800", rechazado: "bg-rose-100 text-rose-700", anulado: "bg-slate-100 text-slate-500" };
const clp = (n) => `$${Number(n || 0).toLocaleString("es-CL")}`;

function NewLinkDialog({ onDone }) {
  const [open, setOpen] = useState(false);
  const [users, setUsers] = useState([]);
  const [courses, setCourses] = useState([]);
  const [f, setF] = useState({ user_id: "", course_id: "" });
  useEffect(() => { if (open) { api.get("/users?role=estudiante").then((r) => setUsers(r.data)); api.get("/courses").then((r) => setCourses(r.data.filter((c) => c.price > 0))); } }, [open]);
  const send = () => api.post("/payments/send-link", f).then(() => { toast.success("Link de pago enviado por correo"); setOpen(false); onDone(); }).catch((e) => toast.error(errMsg(e)));
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button data-testid="payments-new-link"><Plus size={16} className="mr-2" /> Enviar link de pago</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Enviar link de pago</DialogTitle></DialogHeader>
        <Select value={f.user_id} onValueChange={(v) => setF({ ...f, user_id: v })}><SelectTrigger data-testid="payments-link-student"><SelectValue placeholder="Estudiante" /></SelectTrigger>
          <SelectContent>{users.map((u) => <SelectItem key={u.id} value={u.id}>{u.nombre} {u.apellidos} · {u.email}</SelectItem>)}</SelectContent></Select>
        <Select value={f.course_id} onValueChange={(v) => setF({ ...f, course_id: v })}><SelectTrigger data-testid="payments-link-course"><SelectValue placeholder="Curso con precio" /></SelectTrigger>
          <SelectContent>{courses.map((c) => <SelectItem key={c.id} value={c.id}>{c.title} · {clp(c.price)}</SelectItem>)}</SelectContent></Select>
        <Button disabled={!f.user_id || !f.course_id} onClick={send} data-testid="payments-link-send">Generar y enviar</Button>
      </DialogContent>
    </Dialog>
  );
}

export default function Payments() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("todos");
  const load = () => api.get("/payments").then((r) => setRows(r.data));
  useEffect(() => { load(); }, []);
  const act = (p, path, msg) => api.post(path, path.endsWith("send-link") ? { payment_id: p.id } : {}).then(() => { toast.success(msg); load(); }).catch((e) => toast.error(errMsg(e)));
  const list = rows.filter((r) => (filter === "todos" || r.status === filter) && `${r.student_name} ${r.email} ${r.course_title} ${r.order}`.toLowerCase().includes(q.toLowerCase()));
  const paid = rows.filter((r) => r.status === "pagado");

  return (
    <>
      <PageHeader eyebrow="Finanzas" title="Pagos" subtitle="Inscripciones pagadas con Flow, pagos pendientes y envío de links de pago."><NewLinkDialog onDone={load} /></PageHeader>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Recaudado" value={clp(paid.reduce((a, r) => a + r.amount, 0))} testId="payments-total" />
        <StatCard label="Pagados" value={paid.length} testId="payments-paid-count" />
        <StatCard label="Pendientes" value={rows.filter((r) => r.status === "pendiente").length} testId="payments-pending-count" />
        <StatCard label="Rechazados / anulados" value={rows.filter((r) => ["rechazado", "anulado"].includes(r.status)).length} />
      </div>
      <div className="flex flex-wrap gap-3 mb-4">
        <Input placeholder="Buscar por alumno, correo, curso u orden…" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-sm bg-white" data-testid="payments-search" />
        <Select value={filter} onValueChange={setFilter}><SelectTrigger className="w-44 bg-white" data-testid="payments-filter"><SelectValue /></SelectTrigger>
          <SelectContent>{["todos", "pagado", "pendiente", "rechazado", "anulado"].map((s) => <SelectItem key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</SelectItem>)}</SelectContent></Select>
      </div>
      {list.length === 0 ? <Empty text="No hay pagos registrados." testId="payments-empty" /> : (
        <div className="bg-white border rounded-xl divide-y" data-testid="payments-list">
          {list.map((p) => (
            <div key={p.id} className="p-4 flex flex-wrap items-center gap-4" data-testid={`payment-row-${p.id}`}>
              <div className="flex-1 min-w-[220px]">
                <p className="font-medium">{p.student_name} <span className="text-xs text-slate-500">· {p.email}</span></p>
                <p className="text-xs text-slate-500">{p.course_title} · orden <span className="font-mono">{p.order}</span> · {fmtDate(p.created_at)}{p.manual && " · registrado manualmente"}</p>
              </div>
              <b className="font-mono">{clp(p.amount)}</b>
              <span className={`text-xs rounded-full px-2 py-0.5 font-semibold ${ST[p.status]}`} data-testid={`payment-status-${p.id}`}>{p.status}</span>
              {p.status !== "pagado" && (
                <div className="flex gap-1">
                  {p.checkout_url && <Button size="icon" variant="ghost" title="Copiar link" onClick={() => navigator.clipboard.writeText(p.checkout_url).then(() => toast.success("Link copiado"))} data-testid={`payment-copy-${p.id}`}><Link2 size={16} /></Button>}
                  {p.checkout_url && <Button size="icon" variant="ghost" title="Consultar en Flow" onClick={() => act(p, `/payments/${p.id}/refresh`, "Estado actualizado")} data-testid={`payment-refresh-${p.id}`}><RefreshCw size={16} /></Button>}
                  <Button size="sm" variant="outline" onClick={() => act(p, "/payments/send-link", "Link de pago enviado")} data-testid={`payment-send-link-${p.id}`}><Send size={14} className="mr-1" /> Enviar link</Button>
                  <Button size="sm" variant="ghost" onClick={() => window.confirm("¿Registrar como pagado (por ejemplo transferencia) y matricular al alumno?") && act(p, `/payments/${p.id}/mark-paid`, "Pago registrado y alumno matriculado")} data-testid={`payment-mark-paid-${p.id}`}><CheckCircle2 size={14} className="mr-1" /> Marcar pagado</Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
