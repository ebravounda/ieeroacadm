import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Trash2, Pencil, Lock } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/Common";
import QuizBuilder from "@/components/QuizBuilder";
import { MaterialsEditor } from "@/components/Materials";
import CourseReport from "@/components/CourseReport";
import { CourseForm } from "@/pages/Courses";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const EMPTY_MODULE = { title: "", description: "", content: "", video_url: "", min_minutes: 0, materials: [], quiz: { questions: [], pass_score: 75 } };

function ModuleDialog({ open, onClose, initial, onSave }) {
  const [m, setM] = useState(EMPTY_MODULE);
  useEffect(() => { if (open) setM(initial ? { ...EMPTY_MODULE, ...initial, materials: initial.materials || [] } : EMPTY_MODULE); }, [open, initial]);
  const set = (k) => (e) => setM({ ...m, [k]: e.target.value });
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>{initial ? "Editar módulo" : "Nuevo módulo"}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Título</Label><Input value={m.title} onChange={set("title")} data-testid="module-title-input" /></div>
          <div><Label>Descripción breve</Label><Input value={m.description} onChange={set("description")} data-testid="module-description-input" /></div>
          <div><Label>Introducción del módulo</Label><Textarea rows={4} value={m.content} onChange={set("content")} data-testid="module-content-input" /></div>
          <div className="flex items-center gap-3">
            <Label>Tiempo mínimo en el módulo antes del examen (minutos)</Label>
            <Input type="number" min={0} className="w-24" value={m.min_minutes ?? 0} onChange={(e) => setM({ ...m, min_minutes: Math.max(0, Number(e.target.value) || 0) })} data-testid="module-min-minutes-input" />
            <span className="text-xs text-slate-500">0 = sin mínimo</span>
          </div>
          <h4 className="font-semibold pt-3">Material y tareas del módulo</h4>
          <p className="text-xs text-slate-500 -mt-2">Lecturas, videos, presentaciones PPT, PDF, imágenes o enlaces. El estudiante debe completar todas las tareas para rendir el examen.</p>
          <MaterialsEditor materials={m.materials} onChange={(materials) => setM({ ...m, materials })} />
          <h4 className="font-semibold pt-3">Examen del módulo</h4>
          <p className="text-xs text-slate-500 -mt-2">Si el estudiante reprueba, debe repetir las tareas del módulo. Sin preguntas, el módulo se completa al terminar las tareas.</p>
          <QuizBuilder quiz={m.quiz} onChange={(quiz) => setM({ ...m, quiz })} prefix="module" />
          <Button className="w-full" disabled={!m.title} onClick={() => onSave(m)} data-testid="module-save-button">Guardar módulo</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ModulesTab({ course, reload }) {
  const [editing, setEditing] = useState(null);
  const save = async (m) => {
    try {
      if (editing === "new") await api.post(`/courses/${course.id}/modules`, m);
      else await api.put(`/modules/${editing.id}`, m);
      toast.success("Módulo guardado"); setEditing(null); reload();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const del = (id) => window.confirm("¿Eliminar módulo?") && api.delete(`/modules/${id}`).then(reload);
  return (
    <div className="space-y-3">
      {course.modules.map((m, i) => (
        <div key={m.id} className="bg-white border rounded-xl p-5 flex items-center gap-4" data-testid={`editor-module-${i}`}>
          <span className="h-10 w-10 rounded-lg bg-teal-50 text-teal-700 font-heading font-bold grid place-items-center">{i + 1}</span>
          <div className="flex-1 min-w-0">
            <p className="font-semibold">{m.title}</p>
            <p className="text-xs text-slate-500">{m.materials?.length || 0} tareas · {m.quiz?.questions?.length || 0} preguntas · aprobación {m.quiz?.pass_score ?? 75}% {m.min_minutes > 0 && `· mín. ${m.min_minutes} min `}{i > 0 && <>· <Lock size={10} className="inline" /> requiere módulo {i}</>}</p>
          </div>
          <Button size="icon" variant="ghost" onClick={() => setEditing(m)} data-testid={`edit-module-${i}`}><Pencil size={16} /></Button>
          <Button size="icon" variant="ghost" onClick={() => del(m.id)} data-testid={`delete-module-${i}`}><Trash2 size={16} /></Button>
        </div>
      ))}
      <Button onClick={() => setEditing("new")} data-testid="add-module-button"><Plus size={16} className="mr-2" /> Agregar módulo</Button>
      <ModuleDialog open={!!editing} initial={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSave={save} />
    </div>
  );
}

function FinalExamTab({ course }) {
  const [quiz, setQuiz] = useState(course.final_exam);
  const save = () => api.put(`/courses/${course.id}/final-exam`, quiz).then(() => toast.success("Evaluación final guardada")).catch((e) => toast.error(errMsg(e)));
  return (
    <div className="bg-white border rounded-xl p-6 space-y-4">
      <p className="text-sm text-slate-500">Se habilita cuando el estudiante aprueba todos los exámenes de módulo. Nota final del curso = promedio entre el promedio de los módulos y el examen final (escala 1,0 a 7,0). Al aprobarla se emite el diploma.</p>
      <QuizBuilder quiz={quiz} onChange={setQuiz} prefix="final" />
      <Button onClick={save} data-testid="final-exam-save-button">Guardar evaluación final</Button>
    </div>
  );
}

function EnrollmentsTab({ courseId }) {
  const [rows, setRows] = useState([]);
  const { user } = useAuth();
  const load = () => api.get(`/courses/${courseId}/enrollments`).then((r) => setRows(r.data));
  useEffect(() => { load(); }, [courseId]); // eslint-disable-line
  const remove = (id) => window.confirm("¿Quitar matrícula?") && api.delete(`/enrollments/${id}`).then(load);
  return (
    <div className="bg-white border rounded-xl divide-y" data-testid="course-enrollments">
      {rows.length === 0 && <p className="p-6 text-slate-500">Sin estudiantes matriculados.</p>}
      {rows.map((r) => (
        <div key={r.id} className="p-4 flex items-center gap-4">
          <div className="flex-1"><p className="font-medium">{r.student_name}</p><p className="text-xs text-slate-500">{r.email} · matrícula {r.method} · {fmtDate(r.enrolled_at)}</p></div>
          <div className="w-40"><Progress value={r.progress} className="h-2" /><p className="text-xs text-slate-500 mt-1">{r.progress}% {r.final_passed && "· Aprobado"}</p></div>
          {user.role === "admin" && <Button size="sm" variant="ghost" onClick={() => remove(r.id)} data-testid={`remove-enrollment-${r.id}`}>Quitar</Button>}
        </div>
      ))}
    </div>
  );
}

export default function CourseEditor() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const [course, setCourse] = useState(null);
  const load = () => api.get(`/courses/${id}`).then((r) => setCourse(r.data));
  useEffect(() => { load(); }, [id]); // eslint-disable-line
  if (!course) return <p className="text-slate-500">Cargando…</p>;
  const saveInfo = (f) => api.put(`/courses/${id}`, f).then(() => { toast.success("Curso actualizado"); load(); }).catch((e) => toast.error(errMsg(e)));
  const del = () => window.confirm("¿Eliminar curso completo?") && api.delete(`/courses/${id}`).then(() => nav("/cursos"));

  return (
    <>
      <PageHeader eyebrow={course.code || "Curso"} title={course.title} subtitle={course.description}>
        {user.role === "admin" && <Button variant="outline" onClick={del} data-testid="course-delete-button"><Trash2 size={16} className="mr-2" /> Eliminar</Button>}
      </PageHeader>
      <Tabs defaultValue="modules">
        <TabsList className="mb-6">
          <TabsTrigger value="modules" data-testid="tab-modules">Módulos</TabsTrigger>
          <TabsTrigger value="final" data-testid="tab-final">Evaluación final</TabsTrigger>
          <TabsTrigger value="students" data-testid="tab-students">Matriculados</TabsTrigger>
          <TabsTrigger value="report" data-testid="tab-report">Reporte OTEC</TabsTrigger>
          <TabsTrigger value="info" data-testid="tab-info">Datos del curso</TabsTrigger>
        </TabsList>
        <TabsContent value="modules"><ModulesTab course={course} reload={load} /></TabsContent>
        <TabsContent value="final"><FinalExamTab course={course} /></TabsContent>
        <TabsContent value="students"><EnrollmentsTab courseId={id} /></TabsContent>
        <TabsContent value="report"><CourseReport courseId={id} /></TabsContent>
        <TabsContent value="info"><div className="bg-white border rounded-xl p-6 max-w-xl"><CourseForm initial={{ title: course.title, description: course.description, code: course.code, hours: course.hours, auto_enroll: course.auto_enroll, published: course.published, price: course.price || 0, summary: course.summary || "", modality: course.modality || "", image_file_id: course.image_file_id || "", show_on_landing: !!course.show_on_landing }} onSave={saveInfo} /></div></TabsContent>
      </Tabs>
    </>
  );
}
