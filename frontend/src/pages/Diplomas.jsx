import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Award, Check, X, Hourglass, CheckCheck, RefreshCw } from "lucide-react";
import { api, errMsg, fmtDay, fmtNota } from "@/lib/api";
import { useAuth, isStaff } from "@/context/AuthContext";
import { PageHeader, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export const STATUS = {
  pendiente: { label: "En aprobación", cls: "bg-amber-100 text-amber-800" },
  aprobado: { label: "Emitido", cls: "bg-emerald-100 text-emerald-800" },
  rechazado: { label: "Rechazado", cls: "bg-rose-100 text-rose-700" },
};
const statusOf = (d) => d.status || "aprobado";

function Badge({ d }) {
  const s = STATUS[statusOf(d)];
  return <span className={`text-xs rounded-full px-2 py-0.5 font-semibold ${s.cls}`} data-testid={`diploma-status-${d.code}`}>{s.label}</span>;
}

function Card({ d }) {
  return (
    <Link to={`/diploma/${d.code}`} className="diploma-paper border rounded-xl p-6 hover:shadow-md transition-shadow block" data-testid={`diploma-card-${d.code}`}>
      <div className="flex items-center justify-between"><Award className="text-amber-600" /><Badge d={d} /></div>
      <p className="font-semibold mt-3">{d.course_title}</p>
      <p className="text-sm text-slate-600">{d.student_name}</p>
      <p className="text-xs text-slate-500 mt-3 font-mono">{statusOf(d) === "aprobado" ? `${d.code} · ${fmtDay(d.approved_at || d.issued_at)}` : `Solicitado ${fmtDay(d.issued_at)}`}</p>
    </Link>
  );
}

function PendingRow({ d, canApprove, onDone, checked, onCheck }) {
  const [busy, setBusy] = useState(false);
  const approve = async () => {
    setBusy(true);
    try { await api.post(`/diplomas/${d.id}/approve`); toast.success("Certificado emitido y enviado al alumno"); onDone(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const reject = () => {
    const reason = window.prompt("Motivo del rechazo (opcional)");
    if (reason === null) return;
    api.post(`/diplomas/${d.id}/reject`, { reason }).then(() => { toast.success("Solicitud rechazada"); onDone(); }).catch((e) => toast.error(errMsg(e)));
  };
  return (
    <div className="p-4 flex flex-wrap items-center gap-4" data-testid={`certificate-request-${d.id}`}>
      {canApprove && <Checkbox checked={checked} onCheckedChange={onCheck} data-testid={`certificate-select-${d.id}`} />}
      <Hourglass size={18} className="text-amber-600" />
      <div className="flex-1 min-w-[200px]">
        <p className="font-medium">{d.student_name} {d.rut && <span className="text-xs text-slate-500">· {d.rut}</span>}</p>
        <p className="text-xs text-slate-500">{d.course_title} · nota final {fmtNota(d.nota_final)} · solicitado {fmtDay(d.issued_at)}</p>
        {d.status === "rechazado" && <p className="text-xs text-rose-600">Rechazado{d.reject_reason ? `: ${d.reject_reason}` : ""}</p>}
      </div>
      {canApprove ? (
        <div className="flex gap-2">
          <Button size="sm" onClick={approve} disabled={busy} data-testid={`certificate-approve-${d.id}`}><Check size={14} className="mr-1" /> {busy ? "Emitiendo…" : "Aprobar y emitir"}</Button>
          {d.status !== "rechazado" && <Button size="sm" variant="outline" onClick={reject} data-testid={`certificate-reject-${d.id}`}><X size={14} className="mr-1" /> Rechazar</Button>}
        </div>
      ) : <span className="text-xs text-slate-500">Solo el administrador aprueba</span>}
    </div>
  );
}

function BulkBar({ pending, selected, setSelected, onDone }) {
  const [busy, setBusy] = useState(false);
  const all = pending.length > 0 && selected.length === pending.length;
  const run = async () => {
    if (!window.confirm(`¿Aprobar y emitir ${selected.length} certificado(s)? Cada alumno recibirá su correo.`)) return;
    setBusy(true);
    try {
      const { data } = await api.post("/diplomas/approve-bulk", { ids: selected });
      toast.success(`${data.approved} certificado(s) emitidos y enviados`);
      if (data.errors.length) toast.error(`No se pudieron emitir: ${data.errors.join(", ")}`);
      setSelected([]);
      onDone();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3 bg-slate-50 rounded-t-xl border border-b-0" data-testid="certificate-bulk-bar">
      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <Checkbox checked={all} onCheckedChange={(v) => setSelected(v ? pending.map((d) => d.id) : [])} data-testid="certificate-select-all" /> Seleccionar todas
      </label>
      <span className="text-sm text-slate-500" data-testid="certificate-selected-count">{selected.length} seleccionada(s)</span>
      <Button size="sm" className="ml-auto" disabled={!selected.length || busy} onClick={run} data-testid="certificate-approve-selected">
        <CheckCheck size={14} className="mr-1" /> {busy ? "Emitiendo…" : `Aprobar seleccionados (${selected.length})`}
      </Button>
    </div>
  );
}

function IssuedItem({ d, canReissue, checked, onCheck, onDone }) {
  const [busy, setBusy] = useState(false);
  const reissue = async () => {
    if (!window.confirm(`¿Reemitir el certificado de ${d.student_name} con el diseño actual? El código ${d.code} quedará anulado.`)) return;
    setBusy(true);
    try { const { data } = await api.post(`/diplomas/${d.id}/reissue`); toast.success(`Reemitido con código ${data.code}`); onDone(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  if (!canReissue) return <Card d={d} />;
  return (
    <div className="space-y-2">
      <Card d={d} />
      <div className="flex items-center gap-2">
        <Checkbox checked={checked} onCheckedChange={onCheck} data-testid={`diploma-select-${d.id}`} />
        <Button size="sm" variant="outline" onClick={reissue} disabled={busy} data-testid={`diploma-reissue-${d.id}`}><RefreshCw size={14} className={`mr-1 ${busy ? "animate-spin" : ""}`} /> {busy ? "Reemitiendo…" : "Reemitir"}</Button>
      </div>
    </div>
  );
}

function ReissueBar({ issued, selected, setSelected, onDone }) {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (!window.confirm(`¿Reemitir ${selected.length} certificado(s) con el diseño actual? Los códigos anteriores quedarán anulados.`)) return;
    setBusy(true);
    try {
      const { data } = await api.post("/diplomas/reissue-bulk", { ids: selected });
      toast.success(`${data.reissued} certificado(s) reemitidos`);
      if (data.errors.length) toast.error(`No se pudieron reemitir: ${data.errors.join(", ")}`);
      setSelected([]); onDone();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3 mb-4 bg-slate-50 rounded-xl border" data-testid="diploma-reissue-bar">
      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <Checkbox checked={issued.length > 0 && selected.length === issued.length} onCheckedChange={(v) => setSelected(v ? issued.map((d) => d.id) : [])} data-testid="diploma-select-all" /> Seleccionar todos
      </label>
      <Button size="sm" className="ml-auto" disabled={!selected.length || busy} onClick={run} data-testid="diploma-reissue-selected"><RefreshCw size={14} className="mr-1" /> {busy ? "Reemitiendo…" : `Reemitir seleccionados (${selected.length})`}</Button>
    </div>
  );
}

function StaffView({ rows, canApprove, canReissue, reload }) {
  const [selected, setSelected] = useState([]);
  const [picked, setPicked] = useState([]);
  const pending = rows.filter((d) => statusOf(d) !== "aprobado");
  const issued = rows.filter((d) => statusOf(d) === "aprobado");
  return (
    <Tabs defaultValue="pending">
      <TabsList className="mb-6">
        <TabsTrigger value="pending" data-testid="diplomas-tab-pending">Solicitudes ({pending.length})</TabsTrigger>
        <TabsTrigger value="issued" data-testid="diplomas-tab-issued">Emitidos ({issued.length})</TabsTrigger>
      </TabsList>
      <TabsContent value="pending">
        {pending.length === 0 ? <Empty text="No hay solicitudes de certificado pendientes." testId="certificate-requests-empty" />
          : <>
            {canApprove && <BulkBar pending={pending} selected={selected.filter((id) => pending.some((d) => d.id === id))} setSelected={setSelected} onDone={reload} />}
            <div className={`bg-white border divide-y ${canApprove ? "rounded-b-xl" : "rounded-xl"}`}>{pending.map((d) => (
              <PendingRow key={d.id} d={d} canApprove={canApprove} onDone={reload} checked={selected.includes(d.id)}
                onCheck={(v) => setSelected(v ? [...selected, d.id] : selected.filter((x) => x !== d.id))} />
            ))}</div>
          </>}
      </TabsContent>
      <TabsContent value="issued">
        {issued.length === 0 ? <Empty text="Aún no hay certificados emitidos." testId="diplomas-empty" />
          : <>
            {canReissue && <ReissueBar issued={issued} selected={picked.filter((id) => issued.some((d) => d.id === id))} setSelected={setPicked} onDone={reload} />}
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">{issued.map((d) => <IssuedItem key={d.id} d={d} canReissue={canReissue} onDone={reload} checked={picked.includes(d.id)}
              onCheck={(v) => setPicked(v ? [...picked, d.id] : picked.filter((x) => x !== d.id))} />)}</div>
          </>}
      </TabsContent>
    </Tabs>
  );
}

export default function Diplomas() {
  const { user } = useAuth();
  const staff = isStaff(user);
  const [rows, setRows] = useState([]);
  const load = () => api.get(staff ? "/diplomas" : "/my/diplomas").then((r) => setRows(r.data));
  useEffect(() => { load(); }, [user]); // eslint-disable-line
  return (
    <>
      <PageHeader eyebrow="Certificación" title="Certificados" subtitle={staff ? "Aprueba las solicitudes de certificado de los alumnos que finalizaron su curso. Al aprobar, se genera el PDF y se envía al alumno por correo." : "Al finalizar un curso, tu certificado pasa a aprobación. Cuando se emite, lo recibes por correo y puedes descargarlo aquí."} />
      {staff ? <StaffView rows={rows} canApprove={user.role === "admin"} canReissue={!!user.is_super} reload={load} />
        : rows.length === 0 ? <Empty text="Aún no tienes certificados." testId="diplomas-empty" />
        : <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">{rows.map((d) => <Card key={d.id} d={d} />)}</div>}
    </>
  );
}
