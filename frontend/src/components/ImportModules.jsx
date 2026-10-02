import { useState } from "react";
import { toast } from "sonner";
import { FileInput } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export function ImportModulesDialog({ courseId, onDone }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [prev, setPrev] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = (dry_run) => {
    setBusy(true);
    return api.post(`/courses/${courseId}/import-modules`, { text, dry_run })
      .then((r) => {
        if (dry_run) return setPrev(r.data.modules);
        toast.success(`${r.data.created} módulos importados`); setOpen(false); setText(""); setPrev(null); onDone();
      })
      .catch((e) => toast.error(errMsg(e))).finally(() => setBusy(false));
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setPrev(null); }}>
      <DialogTrigger asChild><Button variant="outline" data-testid="import-modules-button"><FileInput size={16} className="mr-2" /> Importar módulos desde texto</Button></DialogTrigger>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Importar módulos completos</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-500">Pega el programa del curso (por ejemplo, el generado con ChatGPT). Cada <b>MÓDULO N</b> se crea como módulo; cada <b>Lección</b>, <b>Actividad</b>, <b>Recursos</b> o <b>Video</b> se crea como sección con su contenido. Las evaluaciones no se importan: agrégalas después en cada módulo. Los enlaces (https://…) se crean como video o enlace.</p>
        <Textarea rows={14} value={text} onChange={(e) => { setText(e.target.value); setPrev(null); }} placeholder={"MÓDULO 1\nTítulo del módulo\nObjetivo del módulo\n…\nLección 1. …"} className="font-mono text-xs" data-testid="import-modules-text" />
        {prev && (
          <div className="border rounded-lg p-4 bg-slate-50 space-y-2 text-sm" data-testid="import-modules-preview">
            <p className="font-semibold">Se crearán {prev.length} módulos:</p>
            {prev.map((m, i) => (
              <div key={i}><p className="font-medium">{i + 1}. {m.title} <span className="text-xs text-slate-500">· {m.sections.length} secciones · {m.contents} contenidos</span></p>
                <p className="text-xs text-slate-500 pl-4">{m.sections.join(" · ")}</p></div>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <Button variant="outline" disabled={busy || text.length < 20} onClick={() => run(true)} data-testid="import-modules-preview-button">Vista previa</Button>
          <Button disabled={busy || !prev} onClick={() => run(false)} data-testid="import-modules-confirm">{busy ? "Importando…" : "Importar al curso"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
