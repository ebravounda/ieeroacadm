import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Save, Send, Eye, Link2, FlaskConical } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const VARS = ["nombre", "apellidos", "email", "curso", "enlace"];
const AUD = [["students", "Todos los estudiantes"], ["all", "Todos los usuarios"], ["course", "Alumnos de un curso"], ["inactive", "Estudiantes inactivos"]];
const EMPTY = { id: null, name: "", subject: "", body: "" };

function TemplateList({ list, current, pick }) {
  return (
    <div className="bg-white border rounded-xl p-3 space-y-1 h-fit" data-testid="templates-list">
      <Button variant="outline" size="sm" className="w-full mb-2" onClick={() => pick(EMPTY)} data-testid="template-new"><Plus size={14} className="mr-1" /> Nueva plantilla</Button>
      {list.map((t) => (
        <button key={t.id} onClick={() => pick(t)} className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${current === t.id ? "bg-teal-600 text-white" : "hover:bg-slate-50"}`} data-testid={`template-item-${t.id}`}>{t.name}</button>
      ))}
    </div>
  );
}

function Audience({ a, setA, courses }) {
  return (
    <div className="grid sm:grid-cols-[1fr_1fr] gap-3">
      <div><Label>Destinatarios</Label>
        <select className="w-full h-10 border rounded-md px-3 text-sm bg-white" value={a.type} onChange={(e) => setA({ ...a, type: e.target.value })} data-testid="audience-type">
          {AUD.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
      {a.type === "course" && <div><Label>Curso</Label>
        <select className="w-full h-10 border rounded-md px-3 text-sm bg-white" value={a.course_id || ""} onChange={(e) => setA({ ...a, course_id: e.target.value })} data-testid="audience-course">
          <option value="">Selecciona…</option>{courses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}</select></div>}
      {a.type === "inactive" && <div><Label>Sin ingresar hace (días)</Label><Input type="number" min={1} value={a.days} onChange={(e) => setA({ ...a, days: Number(e.target.value) })} data-testid="audience-days" /></div>}
    </div>
  );
}

function History({ items }) {
  return (
    <div className="bg-white border rounded-xl p-6" data-testid="campaigns-history">
      <p className="font-semibold mb-3">Historial de envíos</p>
      {items.length === 0 ? <p className="text-sm text-slate-500">Aún no hay envíos.</p> : (
        <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left text-slate-500 border-b"><th className="py-2">Fecha</th><th>Asunto</th><th>Destinatarios</th><th>Enviados</th><th>Fallidos</th><th>Estado</th></tr></thead>
          <tbody>{items.map((c) => <tr key={c.id} className="border-b last:border-0" data-testid={`campaign-${c.id}`}><td className="py-2 whitespace-nowrap">{new Date(c.created_at).toLocaleString("es-CL")}</td><td>{c.subject}</td><td>{AUD.find(([v]) => v === c.audience.type)?.[1]}</td><td>{c.sent}/{c.total}</td><td>{c.failed}</td><td>{c.status}</td></tr>)}</tbody></table></div>)}
    </div>
  );
}

export default function Messages() {
  const [list, setList] = useState([]);
  const [t, setT] = useState(EMPTY);
  const [a, setA] = useState({ type: "students", course_id: "", days: 7 });
  const [courses, setCourses] = useState([]);
  const [prev, setPrev] = useState(null);
  const [testTo, setTestTo] = useState("");
  const [hist, setHist] = useState([]);
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);
  const load = () => api.get("/admin/templates").then((r) => { setList(r.data); return r.data; });
  const loadHist = () => api.get("/admin/messages/campaigns").then((r) => setHist(r.data));
  useEffect(() => { load().then((d) => d[0] && setT(d[0])); api.get("/courses").then((r) => setCourses(r.data)); loadHist(); const i = setInterval(loadHist, 8000); return () => clearInterval(i); }, []);
  useEffect(() => { setPrev(null); }, [t.subject, t.body, a]);
  const insert = (txt) => { const el = ref.current; const s = el?.selectionStart ?? t.body.length; setT({ ...t, body: t.body.slice(0, s) + txt + t.body.slice(el?.selectionEnd ?? s) }); };
  const addLink = () => { const url = window.prompt("URL del enlace (https://...)"); if (!url) return; const txt = window.prompt("Texto del enlace", "Ver más") || "Ver más"; insert(`[${txt}](${url})`); };
  const msg = { subject: t.subject, body: t.body, audience: { ...a, course_id: a.course_id || null } };
  const save = () => (t.id ? api.put(`/admin/templates/${t.id}`, t) : api.post("/admin/templates", t)).then((r) => { setT({ ...t, id: r.data.id }); load(); toast.success("Plantilla guardada"); }).catch((e) => toast.error(errMsg(e)));
  const del = () => window.confirm(`¿Eliminar la plantilla "${t.name}"?`) && api.delete(`/admin/templates/${t.id}`).then(() => { load().then((d) => setT(d[0] || EMPTY)); toast.success("Plantilla eliminada"); });
  const preview = () => api.post("/admin/messages/preview", msg).then((r) => setPrev(r.data)).catch((e) => toast.error(errMsg(e)));
  const test = () => api.post("/admin/messages/test", { ...msg, to: testTo }).then(() => toast.success(`Prueba enviada a ${testTo}`)).catch((e) => toast.error(errMsg(e)));
  const send = async () => {
    try {
      const p = (await api.post("/admin/messages/preview", msg)).data; setPrev(p);
      if (!p.count) return toast.error("No hay destinatarios para esta selección");
      if (!window.confirm(`¿Enviar "${p.subject}" a ${p.count} destinatario(s)?`)) return;
      setBusy(true); await api.post("/admin/messages/send", msg); toast.success("Envío iniciado. Puedes seguir el avance en el historial."); loadHist();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="max-w-6xl space-y-6" data-testid="messages-page">
      <PageHeader eyebrow="Comunicaciones" title="Mensajes masivos" subtitle="Crea plantillas y envía correos a tus alumnos. Usa variables para personalizar cada mensaje." />
      <div className="grid lg:grid-cols-[220px_1fr] gap-6">
        <TemplateList list={list} current={t.id} pick={setT} />
        <div className="bg-white border rounded-xl p-6 space-y-4" data-testid="template-editor">
          <div className="grid sm:grid-cols-2 gap-3">
            <div><Label>Nombre de la plantilla</Label><Input value={t.name} onChange={(e) => setT({ ...t, name: e.target.value })} data-testid="template-name" /></div>
            <div><Label>Asunto</Label><Input value={t.subject} onChange={(e) => setT({ ...t, subject: e.target.value })} data-testid="template-subject" /></div>
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-1.5 mb-1.5"><Label className="mr-2">Mensaje</Label>
              {VARS.map((v) => <button key={v} onClick={() => insert(`{${v}}`)} className="text-xs px-2 py-1 rounded-md bg-slate-100 hover:bg-slate-200" data-testid={`insert-var-${v}`}>{`{${v}}`}</button>)}
              <button onClick={addLink} className="text-xs px-2 py-1 rounded-md bg-teal-50 text-teal-700 hover:bg-teal-100 flex items-center gap-1" data-testid="insert-link"><Link2 size={12} /> Enlace</button></div>
            <Textarea ref={ref} rows={12} value={t.body} onChange={(e) => setT({ ...t, body: e.target.value })} data-testid="template-body" />
            <p className="text-xs text-slate-500 mt-1">Deja una línea en blanco entre párrafos. Enlaces: [texto](https://...). {"{enlace}"} = acceso a la plataforma.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={save} disabled={!t.name || !t.subject || !t.body} data-testid="template-save"><Save size={14} className="mr-1" /> Guardar plantilla</Button>
            {t.id && <Button variant="ghost" onClick={del} data-testid="template-delete"><Trash2 size={14} className="mr-1" /> Eliminar</Button>}
          </div>
          <div className="border-t pt-4 space-y-4">
            <Audience a={a} setA={setA} courses={courses} />
            <div className="flex flex-wrap gap-2 items-center">
              <Button variant="outline" onClick={preview} disabled={!t.subject || !t.body} data-testid="message-preview"><Eye size={14} className="mr-1" /> Vista previa</Button>
              <Input type="email" placeholder="tu@correo.cl" value={testTo} onChange={(e) => setTestTo(e.target.value)} className="w-56" data-testid="message-test-to" />
              <Button variant="outline" onClick={test} disabled={!testTo || !t.body} data-testid="message-test"><FlaskConical size={14} className="mr-1" /> Enviar prueba</Button>
              <Button onClick={send} disabled={busy || !t.subject || !t.body} className="ml-auto bg-teal-300 text-teal-900 hover:bg-teal-400" data-testid="message-send"><Send size={14} className="mr-1" /> {busy ? "Enviando…" : "Enviar a destinatarios"}</Button>
            </div>
            {prev && <div data-testid="message-preview-box"><p className="text-sm mb-2"><b>{prev.count}</b> destinatario(s) · Asunto: <b>{prev.subject}</b></p>
              <iframe title="preview" srcDoc={prev.html} className="w-full h-96 border rounded-lg bg-white" data-testid="message-preview-frame" /></div>}
          </div>
        </div>
      </div>
      <History items={hist} />
    </div>
  );
}
