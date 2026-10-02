import { useState } from "react";
import { toast } from "sonner";
import { FileText, Video, Paperclip, Link2, Trash2, Upload, Download, ExternalLink } from "lucide-react";
import { api, errMsg, fileUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export const MAT_ICON = { texto: FileText, video: Video, archivo: Paperclip, enlace: Link2 };
const MAT_LABEL = { texto: "Lectura", video: "Video (URL)", archivo: "Archivo (PDF, PPT, imagen, video…)", enlace: "Enlace externo" };
const uid = () => Math.random().toString(36).slice(2, 10);

function FileField({ m, onChange, i }) {
  const [busy, setBusy] = useState(false);
  const upload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/files", fd);
      onChange({ file_id: data.id, file_name: data.file_name, content_type: data.content_type, title: m.title || data.file_name });
      toast.success("Archivo subido");
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <label className="flex items-center gap-2 text-sm text-teal-700 cursor-pointer">
      <Upload size={14} /> {busy ? "Subiendo…" : m.file_name || "Seleccionar archivo (máx. 100 MB)"}
      <input type="file" className="hidden" onChange={upload} disabled={busy} data-testid={`material-file-input-${i}`}
        accept=".pdf,.ppt,.pptx,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.gif,.webp,.mp4,.webm,.mov,.mp3,.txt,.zip" />
    </label>
  );
}

export function MaterialsEditor({ materials, onChange }) {
  const update = (i, patch) => onChange(materials.map((m, j) => (j === i ? { ...m, ...patch } : m)));
  const add = (type) => onChange([...materials, { id: uid(), type, title: "", body: "", url: "", file_id: "", file_name: "", content_type: "" }]);
  return (
    <div className="space-y-3" data-testid="materials-editor">
      {materials.map((m, i) => {
        const Icon = MAT_ICON[m.type];
        return (
          <div key={m.id} className="border rounded-lg p-4 bg-slate-50 space-y-2" data-testid={`material-${i}`}>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1"><Icon size={14} /> Tarea {i + 1} · {MAT_LABEL[m.type]}</span>
              <Button type="button" size="icon" variant="ghost" onClick={() => onChange(materials.filter((_, j) => j !== i))} data-testid={`material-remove-${i}`}><Trash2 size={16} /></Button>
            </div>
            <Input placeholder="Título de la tarea / material" value={m.title} onChange={(e) => update(i, { title: e.target.value })} data-testid={`material-title-${i}`} />
            {m.type === "texto" && <Textarea rows={5} placeholder="Contenido de la lectura" value={m.body} onChange={(e) => update(i, { body: e.target.value })} data-testid={`material-body-${i}`} />}
            {(m.type === "video" || m.type === "enlace") && <Input placeholder="https://…" value={m.url} onChange={(e) => update(i, { url: e.target.value })} data-testid={`material-url-${i}`} />}
            {m.type === "archivo" && <FileField m={m} i={i} onChange={(p) => update(i, p)} />}
            {m.type !== "texto" && <Input placeholder="Instrucciones (opcional)" value={m.body} onChange={(e) => update(i, { body: e.target.value })} data-testid={`material-instructions-${i}`} />}
          </div>
        );
      })}
      <div className="flex gap-2 flex-wrap">
        {Object.keys(MAT_LABEL).map((t) => {
          const Icon = MAT_ICON[t];
          return <Button key={t} type="button" variant="outline" size="sm" onClick={() => add(t)} data-testid={`material-add-${t}`}><Icon size={14} className="mr-1" /> {t === "archivo" ? "Archivo" : MAT_LABEL[t].split(" ")[0]}</Button>;
        })}
      </div>
    </div>
  );
}

export function embedUrl(url) {
  const yt = url.match(/(?:youtu\.be\/|v=|embed\/)([\w-]{11})/);
  if (yt) return `https://www.youtube.com/embed/${yt[1]}`;
  const vm = url.match(/vimeo\.com\/(\d+)/);
  if (vm) return `https://player.vimeo.com/video/${vm[1]}`;
  return url;
}

export function MaterialBody({ m }) {
  if (m.type === "texto") return <div className="whitespace-pre-wrap leading-relaxed text-slate-700">{m.body}</div>;
  const instr = m.body && <p className="text-sm text-slate-600 mb-3">{m.body}</p>;
  if (m.type === "video") return <>{instr}<div className="aspect-video rounded-lg overflow-hidden bg-black"><iframe title={m.title} src={embedUrl(m.url)} className="w-full h-full" allowFullScreen /></div></>;
  if (m.type === "enlace") return <>{instr}<a href={m.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-teal-700 hover:underline"><ExternalLink size={14} /> Abrir enlace</a></>;
  if (!m.file_id) return <p className="text-sm text-slate-400">Archivo no disponible</p>;
  const url = fileUrl(m.file_id);
  const ct = m.content_type || "";
  let preview = null;
  if (ct.startsWith("image/")) preview = <img src={url} alt={m.title} className="max-h-[480px] rounded-lg border" />;
  else if (ct.startsWith("video/")) preview = <video src={url} controls className="w-full rounded-lg bg-black" />;
  else if (ct.startsWith("audio/")) preview = <audio src={url} controls className="w-full" />;
  else if (ct === "application/pdf") preview = <iframe title={m.title} src={url} className="w-full h-[520px] rounded-lg border" />;
  return (
    <>
      {instr}
      {preview}
      <a href={url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex items-center gap-1 text-sm text-teal-700 hover:underline" data-testid={`material-download-${m.id}`}><Download size={14} /> Descargar {m.file_name}</a>
    </>
  );
}
