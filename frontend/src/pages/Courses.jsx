import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Layers, Users, Upload } from "lucide-react";
import { uploadImage } from "@/pages/WebsiteAdmin";
import { api, errMsg } from "@/lib/api";
import { PageHeader, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export function CourseForm({ initial, onSave, submitLabel = "Guardar" }) {
  const [f, setF] = useState({ title: "", description: "", code: "", hours: 0, auto_enroll: false, published: true, price: 0, summary: "", modality: "", image_file_id: "", show_on_landing: false, ...(initial || {}) });
  const [preview, setPreview] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const onImage = (e) => { const file = e.target.files[0]; if (file) uploadImage(file).then((id) => { setF((x) => ({ ...x, image_file_id: id })); setPreview(URL.createObjectURL(file)); }).catch((er) => toast.error(errMsg(er))); };
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSave({ ...f, hours: Number(f.hours) || 0, price: Number(f.price) || 0 }); }} className="space-y-3 max-h-[75vh] overflow-y-auto pr-1">
      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2"><Label>Nombre del curso</Label><Input required value={f.title} onChange={set("title")} data-testid="course-title-input" /></div>
        <div><Label>Código / ramo</Label><Input value={f.code} onChange={set("code")} data-testid="course-code-input" /></div>
      </div>
      <div><Label>Descripción</Label><Textarea value={f.description} onChange={set("description")} data-testid="course-description-input" /></div>
      <div className="grid grid-cols-3 gap-3">
        <div><Label>Horas</Label><Input type="number" value={f.hours} onChange={set("hours")} data-testid="course-hours-input" /></div>
        <div><Label>Precio (CLP)</Label><Input type="number" min={0} value={f.price} onChange={set("price")} data-testid="course-price-input" /></div>
        <div><Label>Modalidad</Label><Input placeholder="Online" value={f.modality} onChange={set("modality")} data-testid="course-modality-input" /></div>
      </div>
      <div className="border rounded-lg p-3 space-y-3 bg-slate-50">
        <div className="flex items-center justify-between">
          <div><p className="text-sm font-medium">Mostrar en el sitio web</p><p className="text-xs text-slate-500">Aparece en la portada con botón “Inscríbete ahora”.</p></div>
          <Switch checked={f.show_on_landing} onCheckedChange={(v) => setF({ ...f, show_on_landing: v })} data-testid="course-landing-switch" />
        </div>
        <div><Label>Resumen para el sitio web</Label><Textarea rows={2} value={f.summary} onChange={set("summary")} data-testid="course-summary-input" /></div>
        <label className="flex items-center gap-3 cursor-pointer text-sm text-teal-600">
          <span className="h-16 w-24 rounded bg-white border overflow-hidden grid place-items-center">{preview || f.image_file_id ? <img src={preview || `${process.env.REACT_APP_BACKEND_URL}/api/files/${f.image_file_id}?auth=${localStorage.getItem("otec_token")}`} alt="" className="h-full w-full object-cover" /> : <Upload size={16} />}</span>
          {f.image_file_id ? "Cambiar imagen del curso" : "Subir imagen del curso"}
          <input type="file" accept="image/*" className="hidden" onChange={onImage} data-testid="course-image-input" />
        </label>
      </div>
      <div className="flex items-center justify-between border rounded-lg p-3">
        <div><p className="text-sm font-medium">Matrícula automática</p><p className="text-xs text-slate-500">Nuevos estudiantes quedan matriculados y pueden automatricularse.</p></div>
        <Switch checked={f.auto_enroll} onCheckedChange={(v) => setF({ ...f, auto_enroll: v })} data-testid="course-auto-enroll-switch" />
      </div>
      <div className="flex items-center justify-between border rounded-lg p-3">
        <p className="text-sm font-medium">Publicado</p>
        <Switch checked={f.published} onCheckedChange={(v) => setF({ ...f, published: v })} data-testid="course-published-switch" />
      </div>
      <Button type="submit" className="w-full" data-testid="course-save-button">{submitLabel}</Button>
    </form>
  );
}

export default function Courses() {
  const [courses, setCourses] = useState([]);
  const [open, setOpen] = useState(false);
  const load = () => api.get("/courses").then((r) => setCourses(r.data));
  useEffect(() => { load(); }, []);
  const create = (f) => api.post("/courses", f).then(() => { toast.success("Curso creado"); setOpen(false); load(); }).catch((e) => toast.error(errMsg(e)));

  return (
    <>
      <PageHeader eyebrow="Gestión académica" title="Cursos, ramos y módulos" subtitle="Crea cursos modulares con evaluaciones por módulo y evaluación final.">
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild><Button data-testid="courses-new-button"><Plus size={16} className="mr-2" /> Nuevo curso</Button></DialogTrigger>
          <DialogContent><DialogHeader><DialogTitle>Nuevo curso</DialogTitle></DialogHeader><CourseForm onSave={create} submitLabel="Crear curso" /></DialogContent>
        </Dialog>
      </PageHeader>
      {courses.length === 0 ? <Empty text="Todavía no hay cursos. Crea el primero." testId="courses-empty" /> : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {courses.map((c) => (
            <Link key={c.id} to={`/cursos/${c.id}/editar`} className="bg-white border rounded-xl p-6 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-[transform,box-shadow]" data-testid={`course-card-${c.id}`}>
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-slate-400">{c.code || "—"}</span>
                <div className="flex gap-1">
                  {c.auto_enroll && <Badge variant="secondary">Auto</Badge>}
                  {!c.published && <Badge variant="outline">Borrador</Badge>}
                </div>
              </div>
              <h3 className="text-lg font-semibold mt-2">{c.title}</h3>
              <p className="text-sm text-slate-500 line-clamp-2 mt-1">{c.description}</p>
              <div className="flex gap-4 mt-5 text-sm text-slate-600">
                <span className="flex items-center gap-1"><Layers size={14} /> {c.module_count} módulos</span>
                <span className="flex items-center gap-1"><Users size={14} /> {c.student_count} matriculados</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
