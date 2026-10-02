import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Upload, ExternalLink } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export async function uploadImage(file) {
  if (!file.type.startsWith("image/")) throw new Error("Debe ser una imagen (JPG, PNG o WEBP)");
  const fd = new FormData();
  fd.append("file", file);
  return (await api.post("/files", fd)).data.id;
}

function Slides() {
  const [slides, setSlides] = useState([]);
  useEffect(() => { api.get("/admin/landing").then((r) => setSlides(r.data.slides)); }, []);
  const upd = (i, p) => setSlides(slides.map((s, j) => (j === i ? { ...s, ...p } : s)));
  const onFile = (i) => (e) => e.target.files[0] && uploadImage(e.target.files[0]).then((id) => upd(i, { image_file_id: id, preview: URL.createObjectURL(e.target.files[0]) })).catch((er) => toast.error(errMsg(er)));
  const save = () => api.put("/admin/landing", { slides: slides.map(({ preview, ...s }) => s) }).then(() => toast.success("Slider guardado")).catch((e) => toast.error(errMsg(e)));
  return (
    <div className="bg-white border rounded-xl p-6 space-y-4" data-testid="website-slides">
      <div className="flex justify-between items-center"><div><p className="font-semibold">Slider de la portada</p><p className="text-xs text-slate-500">Si no agregas slides, se muestran 3 imágenes por defecto.</p></div>
        <Button size="sm" variant="outline" asChild><a href="/" target="_blank" rel="noreferrer"><ExternalLink size={14} className="mr-1" /> Ver sitio</a></Button></div>
      {slides.map((s, i) => (
        <div key={s.id || i} className="border rounded-lg p-4 grid sm:grid-cols-[160px_1fr_auto] gap-4 items-start" data-testid={`website-slide-${i}`}>
          <label className="aspect-video rounded-lg bg-slate-100 grid place-items-center cursor-pointer overflow-hidden text-xs text-slate-500">
            {s.preview || s.image_file_id ? <img src={s.preview || `${process.env.REACT_APP_BACKEND_URL}/api/files/${s.image_file_id}?auth=${localStorage.getItem("otec_token")}`} alt="" className="h-full w-full object-cover" /> : <span className="flex items-center gap-1"><Upload size={14} /> Imagen</span>}
            <input type="file" accept="image/*" className="hidden" onChange={onFile(i)} data-testid={`website-slide-image-${i}`} />
          </label>
          <div className="space-y-2"><Input placeholder="Título" value={s.title} onChange={(e) => upd(i, { title: e.target.value })} data-testid={`website-slide-title-${i}`} /><Input placeholder="Texto" value={s.subtitle} onChange={(e) => upd(i, { subtitle: e.target.value })} data-testid={`website-slide-subtitle-${i}`} /></div>
          <Button size="icon" variant="ghost" onClick={() => setSlides(slides.filter((_, j) => j !== i))} data-testid={`website-slide-remove-${i}`}><Trash2 size={16} /></Button>
        </div>
      ))}
      <div className="flex gap-2"><Button variant="outline" onClick={() => setSlides([...slides, { title: "", subtitle: "", image_file_id: "" }])} data-testid="website-slide-add"><Plus size={14} className="mr-1" /> Agregar slide</Button><Button onClick={save} data-testid="website-slides-save">Guardar slider</Button></div>
    </div>
  );
}

function FlowSettings() {
  const [s, setS] = useState(null);
  const [secret, setSecret] = useState("");
  useEffect(() => { api.get("/admin/payment-settings").then((r) => setS(r.data)); }, []);
  if (!s) return null;
  const save = () => api.put("/admin/payment-settings", { flow_env: s.flow_env, flow_api_key: s.flow_api_key, flow_secret_key: secret || null }).then((r) => { setS(r.data); setSecret(""); toast.success("Credenciales de Flow guardadas"); }).catch((e) => toast.error(errMsg(e)));
  return (
    <div className="bg-white border rounded-xl p-6 space-y-4" data-testid="website-flow-settings">
      <div><p className="font-semibold">Pagos con Flow.cl</p><p className="text-xs text-slate-500">Obtén tus claves en Flow → Mi cuenta → Datos. Sandbox: sandbox.flow.cl · Producción: www.flow.cl</p></div>
      <div className="flex gap-2">{[["sandbox", "Sandbox (pruebas)"], ["production", "Producción (cobros reales)"]].map(([v, l]) => (
        <button key={v} onClick={() => setS({ ...s, flow_env: v })} className={`px-4 py-2 rounded-lg border text-sm ${s.flow_env === v ? "bg-teal-600 text-white border-teal-600" : "hover:bg-slate-50"}`} data-testid={`flow-env-${v}`}>{l}</button>))}</div>
      <div className="grid sm:grid-cols-2 gap-4">
        <div><Label>API Key</Label><Input value={s.flow_api_key} onChange={(e) => setS({ ...s, flow_api_key: e.target.value })} data-testid="flow-api-key" /></div>
        <div><Label>Secret Key {s.secret_set && <span className="text-xs text-slate-500">(guardada {s.secret_hint})</span>}</Label><Input type="password" placeholder={s.secret_set ? "Dejar vacío para mantener" : "Pega tu secret key"} value={secret} onChange={(e) => setSecret(e.target.value)} data-testid="flow-secret-key" /></div>
      </div>
      <Button onClick={save} data-testid="flow-settings-save">Guardar credenciales</Button>
    </div>
  );
}

export default function WebsiteAdmin() {
  return (
    <div className="max-w-4xl space-y-6">
      <PageHeader eyebrow="Sitio web" title="Portada y pagos" subtitle="Administra el slider de iberoacademy.cl y las credenciales de Flow. Los cursos se publican desde Cursos y módulos → Datos del curso." />
      <Slides />
      <FlowSettings />
    </div>
  );
}
