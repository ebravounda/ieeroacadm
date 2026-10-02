import { useEffect, useState } from "react";
import { toast } from "sonner";
import { UserPlus, Upload } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

function CourseSelect({ courses, value, onChange, testId, allowNone = true }) {
  return (
    <Select value={value || "none"} onValueChange={(v) => onChange(v === "none" ? null : v)}>
      <SelectTrigger data-testid={testId}><SelectValue placeholder="Curso" /></SelectTrigger>
      <SelectContent>
        {allowNone && <SelectItem value="none">Sin matrícula</SelectItem>}
        {courses.map((c) => <SelectItem key={c.id} value={c.id}>{c.title}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

function NewUserDialog({ courses, onDone }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ email: "", nombre: "", apellidos: "", rut: "", role: "estudiante", course_id: null });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault();
    try { await api.post("/users", f); toast.success("Usuario creado"); setOpen(false); onDone(); }
    catch (err) { toast.error(errMsg(err)); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button data-testid="students-new-button"><UserPlus size={16} className="mr-2" /> Matrícula manual</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Nuevo usuario</DialogTitle></DialogHeader>
        <form onSubmit={save} className="grid grid-cols-2 gap-3">
          <div><Label>Nombres</Label><Input required value={f.nombre} onChange={set("nombre")} data-testid="new-user-nombre" /></div>
          <div><Label>Apellidos</Label><Input required value={f.apellidos} onChange={set("apellidos")} data-testid="new-user-apellidos" /></div>
          <div className="col-span-2"><Label>Correo</Label><Input type="email" required value={f.email} onChange={set("email")} data-testid="new-user-email" /></div>
          <div><Label>RUT</Label><Input value={f.rut} onChange={set("rut")} data-testid="new-user-rut" /></div>
          <div><Label>Rol</Label>
            <Select value={f.role} onValueChange={(v) => setF({ ...f, role: v })}>
              <SelectTrigger data-testid="new-user-role"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="estudiante">Estudiante</SelectItem>
                <SelectItem value="docente">Docente</SelectItem>
                <SelectItem value="admin">Administrador</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {f.role === "estudiante" && <div className="col-span-2"><Label>Matricular en curso</Label><CourseSelect courses={courses} value={f.course_id} onChange={(v) => setF({ ...f, course_id: v })} testId="new-user-course" /></div>}
          <Button type="submit" className="col-span-2 mt-2" data-testid="new-user-save">Guardar</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ImportDialog({ courses, onDone }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("email,nombre,apellidos,rut\n");
  const [course, setCourse] = useState(null);
  const [result, setResult] = useState(null);
  const onFile = (e) => { const file = e.target.files[0]; if (file) file.text().then(setText); };
  const run = async () => {
    try { const { data } = await api.post("/users/import", { csv_text: text, course_id: course }); setResult(data); toast.success(`${data.created} estudiantes matriculados`); onDone(); }
    catch (err) { toast.error(errMsg(err)); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); setResult(null); }}>
      <DialogTrigger asChild><Button variant="outline" data-testid="students-import-button"><Upload size={16} className="mr-2" /> Matrícula masiva (CSV)</Button></DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Matrícula automatizada por CSV</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-500">Columnas: email, nombre, apellidos, rut. Los estudiantes se crean y se matriculan automáticamente.</p>
        <Input type="file" accept=".csv,text/csv" onChange={onFile} data-testid="import-file-input" />
        <Textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} className="font-mono text-xs" data-testid="import-csv-textarea" />
        <CourseSelect courses={courses} value={course} onChange={setCourse} testId="import-course-select" />
        <Button onClick={run} data-testid="import-run-button">Importar y matricular</Button>
        {result && <div className="text-sm" data-testid="import-result"><p className="font-semibold">{result.created} creados</p>{result.errors.map((e) => <p key={e} className="text-rose-600">{e}</p>)}</div>}
      </DialogContent>
    </Dialog>
  );
}

function EnrollDialog({ user, courses, onDone }) {
  const [course, setCourse] = useState(null);
  const run = () => api.post("/enrollments", { user_id: user.id, course_id: course }).then(() => { toast.success("Matriculado"); onDone(); }).catch((e) => toast.error(errMsg(e)));
  return (
    <Dialog>
      <DialogTrigger asChild><Button size="sm" variant="outline" data-testid={`enroll-user-${user.id}`}>Matricular</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Matricular a {user.nombre} {user.apellidos}</DialogTitle></DialogHeader>
        <CourseSelect courses={courses} value={course} onChange={setCourse} allowNone={false} testId="enroll-course-select" />
        <Button disabled={!course} onClick={run} data-testid="enroll-confirm-button">Confirmar matrícula</Button>
      </DialogContent>
    </Dialog>
  );
}

export default function Students() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [courses, setCourses] = useState([]);
  const [q, setQ] = useState("");
  const load = () => { api.get("/users").then((r) => setUsers(r.data)); api.get("/courses").then((r) => setCourses(r.data)); };
  useEffect(load, []);
  const toggle = (u) => api.put(`/users/${u.id}`, { active: !u.active }).then(load);
  const rows = users.filter((u) => `${u.nombre} ${u.apellidos} ${u.email} ${u.rut}`.toLowerCase().includes(q.toLowerCase()));
  const isAdmin = me.role === "admin";

  return (
    <>
      <PageHeader eyebrow="Ingreso y matrícula" title="Estudiantes y usuarios" subtitle="Matricula manualmente, importa listados CSV o habilita la automatrícula en los cursos.">
        {isAdmin && <><ImportDialog courses={courses} onDone={load} /><NewUserDialog courses={courses} onDone={load} /></>}
      </PageHeader>
      <Input placeholder="Buscar por nombre, correo o RUT…" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-sm mb-4 bg-white" data-testid="students-search-input" />
      <div className="bg-white border rounded-xl overflow-x-auto">
        <Table data-testid="students-table">
          <TableHeader><TableRow><TableHead>Nombre</TableHead><TableHead>Correo</TableHead><TableHead>RUT</TableHead><TableHead>Rol</TableHead><TableHead>Último acceso</TableHead><TableHead className="text-right">Acciones</TableHead></TableRow></TableHeader>
          <TableBody>
            {rows.map((u) => (
              <TableRow key={u.id} data-testid={`student-row-${u.id}`}>
                <TableCell className="font-medium">{u.nombre} {u.apellidos}</TableCell>
                <TableCell>{u.email}</TableCell>
                <TableCell className="font-mono text-xs">{u.rut || "—"}</TableCell>
                <TableCell><Badge variant={u.active ? "secondary" : "destructive"}>{u.role}{!u.active && " · inactivo"}</Badge></TableCell>
                <TableCell className="text-xs text-slate-500">{fmtDate(u.last_login)}</TableCell>
                <TableCell className="text-right space-x-2 whitespace-nowrap">
                  {u.role === "estudiante" && <EnrollDialog user={u} courses={courses} onDone={load} />}
                  {isAdmin && u.id !== me.id && <Button size="sm" variant="ghost" onClick={() => toggle(u)} data-testid={`toggle-user-${u.id}`}>{u.active ? "Desactivar" : "Activar"}</Button>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}
