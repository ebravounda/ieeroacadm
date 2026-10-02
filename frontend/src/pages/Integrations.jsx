import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Mail, Sparkles, CreditCard, Clock, Copy, RefreshCw } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FlowSettings } from "@/pages/WebsiteAdmin";

function Card({ icon: Icon, title, desc, active, id, children }) {
  return (
    <div className="bg-white border rounded-xl p-6 space-y-4" data-testid={`integration-${id}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3"><span className="h-10 w-10 rounded-lg bg-teal-50 text-teal-600 grid place-items-center shrink-0"><Icon size={18} /></span>
          <div><p className="font-semibold">{title}</p><p className="text-xs text-slate-500">{desc}</p></div></div>
        <span className={`text-xs font-semibold px-2.5 py-1 rounded-full whitespace-nowrap ${active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`} data-testid={`integration-${id}-status`}>{active ? "Activa" : "Sin configurar"}</span>
      </div>
      {children}
    </div>
  );
}

function SecretInput({ label, hint, value, onChange, testid }) {
  return <div><Label>{label} {hint && <span className="text-xs text-slate-500">(guardada {hint})</span>}</Label>
    <Input type="password" autoComplete="off" placeholder={hint ? "Dejar vacío para mantener" : "Pega tu clave"} value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} /></div>;
}

function EmailCard({ v, save }) {
  const [f, setF] = useState({ key: "", mail_from: v.mail_from, email_from_name: v.email_from_name });
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const test = () => { setBusy(true); api.post("/admin/integrations/test-email", { to }).then(() => toast.success(`Correo de prueba enviado a ${to}`)).catch((e) => toast.error(errMsg(e))).finally(() => setBusy(false)); };
  return (
    <Card icon={Mail} id="email" title="Correo (Resend)" desc="Códigos de ingreso, recordatorios, notas y diplomas. Clave en resend.com → API Keys; el dominio del remitente debe estar verificado." active={v.active}>
      <div className="grid sm:grid-cols-3 gap-4">
        <SecretInput label="API Key" hint={v.key_hint} value={f.key} onChange={(key) => setF({ ...f, key })} testid="resend-api-key" />
        <div><Label>Correo remitente</Label><Input placeholder="no-reply@iberoacademy.cl" value={f.mail_from} onChange={(e) => setF({ ...f, mail_from: e.target.value })} data-testid="resend-mail-from" /></div>
        <div><Label>Nombre remitente</Label><Input value={f.email_from_name} onChange={(e) => setF({ ...f, email_from_name: e.target.value })} data-testid="resend-from-name" /></div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => save({ resend_api_key: f.key, mail_from: f.mail_from, email_from_name: f.email_from_name }).then(() => setF({ ...f, key: "" }))} data-testid="resend-save">Guardar</Button>
        {v.key_hint && <Button variant="ghost" onClick={() => save({ clear: ["resend_api_key"] })} data-testid="resend-clear">Quitar clave</Button>}
        <div className="flex gap-2 ml-auto"><Input type="email" placeholder="correo@ejemplo.com" value={to} onChange={(e) => setTo(e.target.value)} className="w-56" data-testid="resend-test-to" />
          <Button variant="outline" disabled={!to || busy} onClick={test} data-testid="resend-test">{busy ? "Enviando…" : "Enviar prueba"}</Button></div>
      </div>
    </Card>
  );
}

function AiCard({ v, save }) {
  const [f, setF] = useState({ key: "", model: v.openai_model });
  const [busy, setBusy] = useState(false);
  const test = () => { setBusy(true); api.post("/admin/integrations/test-ai").then((r) => toast.success(`IA respondió correctamente (${r.data.percentage}% · ${r.data.level})`)).catch((e) => toast.error(errMsg(e))).finally(() => setBusy(false)); };
  return (
    <Card icon={Sparkles} id="ai" title="Inteligencia artificial (OpenAI)" desc="Detecta uso de IA en respuestas abiertas de exámenes. Clave en platform.openai.com/api-keys." active={v.active}>
      <div className="grid sm:grid-cols-2 gap-4">
        <SecretInput label="API Key" hint={v.key_hint} value={f.key} onChange={(key) => setF({ ...f, key })} testid="openai-api-key" />
        <div><Label>Modelo</Label><Input placeholder="ej. gpt-5.2" value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} data-testid="openai-model" /></div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => save({ openai_api_key: f.key, openai_model: f.model }).then(() => setF({ ...f, key: "" }))} data-testid="openai-save">Guardar</Button>
        {v.key_hint && <Button variant="ghost" onClick={() => save({ clear: ["openai_api_key"] })} data-testid="openai-clear">Quitar clave</Button>}
        <Button variant="outline" className="ml-auto" disabled={busy} onClick={test} data-testid="openai-test">{busy ? "Probando…" : "Probar conexión"}</Button>
      </div>
    </Card>
  );
}

function CronCard({ v, regen }) {
  const copy = (t) => navigator.clipboard.writeText(t).then(() => toast.success("Copiado"));
  return (
    <Card icon={Clock} id="cron" title="Tareas automáticas (Cron)" desc="Copia estas líneas en aaPanel → Cron (tipo Shell script). Si regeneras el secreto, debes actualizar las 3 tareas." active={v.active}>
      {v.lines.map((l, i) => (
        <div key={l.label}><p className="text-xs font-semibold text-slate-600 mb-1">{l.label}</p>
          <div className="flex gap-2"><code className="flex-1 text-xs bg-slate-50 border rounded-lg p-2.5 break-all" data-testid={`cron-line-${i}`}>{l.line}</code>
            <Button size="icon" variant="outline" onClick={() => copy(l.line)} data-testid={`cron-copy-${i}`}><Copy size={14} /></Button></div></div>
      ))}
      <Button variant="outline" onClick={() => window.confirm("¿Generar un nuevo secreto? Las tareas actuales dejarán de funcionar hasta actualizarlas.") && regen()} data-testid="cron-regenerate"><RefreshCw size={14} className="mr-1" /> {v.active ? "Regenerar secreto" : "Generar secreto"}</Button>
    </Card>
  );
}

export default function Integrations() {
  const [v, setV] = useState(null);
  const load = () => api.get("/admin/integrations").then((r) => setV(r.data));
  useEffect(() => { load(); }, []);
  const save = (body) => api.put("/admin/integrations", body).then((r) => { setV(r.data); toast.success("Integración guardada"); }).catch((e) => { toast.error(errMsg(e)); throw e; });
  const regen = () => api.post("/admin/integrations/cron-secret").then((r) => { setV(r.data); toast.success("Nuevo secreto generado"); }).catch((e) => toast.error(errMsg(e)));
  if (!v) return null;
  return (
    <div className="max-w-4xl space-y-6" data-testid="integrations-page">
      <PageHeader eyebrow="Administración" title="Integraciones y APIs" subtitle="Configura aquí las claves de los servicios externos. Lo guardado en este panel tiene prioridad sobre el archivo .env del servidor." />
      <EmailCard v={v.email} save={save} />
      <AiCard v={v.ai} save={save} />
      <Card icon={CreditCard} id="payments" title="Pagos (Flow.cl)" desc={`Ambiente actual: ${v.payments.flow_env === "production" ? "Producción" : "Sandbox"}`} active={v.payments.active}>
        <FlowSettings embedded onSaved={load} />
      </Card>
      <CronCard v={v.cron} regen={regen} />
    </div>
  );
}
