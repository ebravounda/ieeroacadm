import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileText, Video, Paperclip, Link2, Trash2, Upload, Download, ExternalLink, Presentation, ChevronUp, ChevronDown, Plus } from "lucide-react";
import { api, errMsg, fileUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export const MAT_ICON = { texto: FileText, video: Video, presentacion: Presentation, archivo: Paperclip, enlace: Link2 };
const MAT_LABEL = { texto: "Lectura", video: "Video", presentacion: "Presentación", archivo: "Documento", enlace: "Enlace" };
const ACCEPT = {
  video: ".mp4,.webm,.mov", presentacion: ".ppt,.pptx,.pdf",
  archivo: ".pdf,.ppt,.pptx,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.gif,.webp,.mp4,.webm,.mov,.mp3,.txt,.zip",
};
const uid = () => Math.random().toString(36).slice(2, 10);
export const DEFAULT_SECTION = { id: "general", title: "Contenidos", description: "" };

export function groupSections(sections, materials) {
  const secs = sections?.length ? sections : [DEFAULT_SECTION];
  const ids = secs.map((s) => s.id);
  return secs.map((s, k) => ({ ...s, items: (materials || []).filter((m) => m.section_id === s.id || (k === 0 && !ids.includes(m.section_id))) }));
}

function FileField({ m, onChange }) {
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
      <Upload size={14} /> {busy ? "Subiendo…" : m.file_name || (m.type === "video" ? "o sube un video MP4 (máx. 100 MB)" : "Seleccionar archivo (máx. 100 MB)")}
      <input type="file" className="hidden" onChange={upload} disabled={busy} data-testid={`material-file-input-${m.id}`} accept={ACCEPT[m.type] || ACCEPT.archivo} />
    </label>
  );
}

function IconBtn({ icon: Icon, ...p }) {
  return <Button type="button" size="icon" variant="ghost" {...p}><Icon size={16} /></Button>;
}

function MaterialItem({ m, i, n, update, remove, move }) {
  const Icon = MAT_ICON[m.type];
  return (
    <div className="border rounded-lg p-4 bg-white space-y-2" data-testid={`material-${m.id}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1"><Icon size={14} /> {i + 1}. {MAT_LABEL[m.type]}</span>
        <div className="flex">
          <IconBtn icon={ChevronUp} disabled={i === 0} onClick={() => move(-1)} data-testid={`material-up-${m.id}`} />
          <IconBtn icon={ChevronDown} disabled={i === n - 1} onClick={() => move(1)} data-testid={`material-down-${m.id}`} />
          <IconBtn icon={Trash2} onClick={remove} data-testid={`material-remove-${m.id}`} />
        </div>
      </div>
      <Input placeholder="Título del contenido" value={m.title} onChange={(e) => update({ title: e.target.value })} data-testid={`material-title-${m.id}`} />
      {m.type === "texto" && <Textarea rows={5} placeholder="Contenido de la lectura" value={m.body} onChange={(e) => update({ body: e.target.value })} data-testid={`material-body-${m.id}`} />}
      {(m.type === "video" || m.type === "enlace") && <Input placeholder={m.type === "video" ? "URL de YouTube o Vimeo" : "https://…"} value={m.url}
        onChange={(e) => update({ url: e.target.value, ...(e.target.value ? { file_id: "", file_name: "", content_type: "" } : {}) })} data-testid={`material-url-${m.id}`} />}
      {["video", "presentacion", "archivo"].includes(m.type) && <FileField m={m} onChange={(p) => update({ ...p, ...(m.type === "video" ? { url: "" } : {}) })} />}
      {m.type !== "texto" && <Input placeholder="Instrucciones (opcional)" value={m.body} onChange={(e) => update({ body: e.target.value })} data-testid={`material-instructions-${m.id}`} />}
    </div>
  );
}

function SectionCard({ g, k, total, setG, moveG, removeG }) {
  const addItem = (type) => setG({ items: [...g.items, { id: uid(), type, title: "", body: "", url: "", file_id: "", file_name: "", content_type: "" }] });
  const moveItem = (i, d) => { const it = [...g.items]; [it[i], it[i + d]] = [it[i + d], it[i]]; setG({ items: it }); };
  return (
    <div className="border-2 border-slate-200 rounded-xl p-4 bg-slate-50 space-y-3" data-testid={`section-${k}`}>
      <div className="flex items-center gap-2">
        <span className="text-xs font-bold text-teal-700 whitespace-nowrap">SECCIÓN {k + 1}</span>
        <Input className="bg-white font-semibold" placeholder="Título de la sección" value={g.title} onChange={(e) => setG({ title: e.target.value })} data-testid={`section-title-${k}`} />
        <IconBtn icon={ChevronUp} disabled={k === 0} onClick={() => moveG(-1)} data-testid={`section-up-${k}`} />
        <IconBtn icon={ChevronDown} disabled={k === total - 1} onClick={() => moveG(1)} data-testid={`section-down-${k}`} />
        <IconBtn icon={Trash2} disabled={total === 1} onClick={removeG} data-testid={`section-remove-${k}`} />
      </div>
      <Input className="bg-white" placeholder="Descripción de la sección (opcional)" value={g.description} onChange={(e) => setG({ description: e.target.value })} data-testid={`section-description-${k}`} />
      {g.items.map((m, i) => (
        <MaterialItem key={m.id} m={m} i={i} n={g.items.length} move={(d) => moveItem(i, d)}
          update={(p) => setG({ items: g.items.map((x, j) => (j === i ? { ...x, ...p } : x)) })}
          remove={() => setG({ items: g.items.filter((_, j) => j !== i) })} />
      ))}
      <div className="flex gap-2 flex-wrap">
        {Object.keys(MAT_LABEL).map((t) => {
          const Icon = MAT_ICON[t];
          return <Button key={t} type="button" variant="outline" size="sm" className="bg-white" onClick={() => addItem(t)} data-testid={`section-${k}-add-${t}`}><Icon size={14} className="mr-1" /> {MAT_LABEL[t]}</Button>;
        })}
      </div>
    </div>
  );
}

export function SectionsEditor({ sections, materials, onChange }) {
  const groups = groupSections(sections, materials);
  const emit = (gs) => onChange({ sections: gs.map(({ items, ...s }) => s), materials: gs.flatMap((g) => g.items.map((m) => ({ ...m, section_id: g.id }))) });
  const moveG = (k, d) => { const gs = [...groups]; [gs[k], gs[k + d]] = [gs[k + d], gs[k]]; emit(gs); };
  const removeG = (k) => window.confirm(`¿Eliminar la sección "${groups[k].title}" y sus ${groups[k].items.length} contenido(s)?`) && emit(groups.filter((_, j) => j !== k));
  return (
    <div className="space-y-4" data-testid="sections-editor">
      {groups.map((g, k) => (
        <SectionCard key={g.id} g={g} k={k} total={groups.length} moveG={(d) => moveG(k, d)} removeG={() => removeG(k)}
          setG={(p) => emit(groups.map((x, j) => (j === k ? { ...x, ...p } : x)))} />
      ))}
      <Button type="button" variant="outline" onClick={() => emit([...groups, { id: uid(), title: `Sección ${groups.length + 1}`, description: "", items: [] }])} data-testid="section-add"><Plus size={14} className="mr-1" /> Agregar sección</Button>
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

const OFFICE_RE = /\.(pptx?|docx?|xlsx?)$/i;

function OfficeViewer({ m }) {
  const [src, setSrc] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    api.get(`/files/${m.file_id}/viewer-url`)
      .then((r) => setSrc(`https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(r.data.url)}`))
      .catch(() => setFailed(true));
  }, [m.file_id]);
  if (failed) return null;
  if (!src) return <div className="h-[480px] rounded-lg border bg-slate-50 grid place-items-center text-sm text-slate-400">Cargando presentación…</div>;
  return <iframe title={m.title} src={src} className="w-full h-[520px] rounded-lg border bg-white" allowFullScreen data-testid={`material-office-viewer-${m.id}`} />;
}

export function MaterialBody({ m }) {
  if (m.type === "texto") return <div className="whitespace-pre-wrap leading-relaxed text-slate-700">{m.body}</div>;
  const instr = m.body && <p className="text-sm text-slate-600 mb-3">{m.body}</p>;
  if (m.type === "video" && !m.file_id) return <>{instr}<div className="aspect-video rounded-lg overflow-hidden bg-black"><iframe title={m.title} src={embedUrl(m.url)} className="w-full h-full" allowFullScreen /></div></>;
  if (m.type === "enlace") return <>{instr}<a href={m.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-teal-700 hover:underline"><ExternalLink size={14} /> Abrir enlace</a></>;
  if (!m.file_id) return <p className="text-sm text-slate-400">Archivo no disponible</p>;
  const url = fileUrl(m.file_id);
  const ct = m.content_type || "";
  let preview = null;
  if (ct.startsWith("image/")) preview = <img src={url} alt={m.title} className="max-h-[480px] rounded-lg border" />;
  else if (ct.startsWith("video/")) preview = <video src={url} controls className="w-full rounded-lg bg-black" />;
  else if (ct.startsWith("audio/")) preview = <audio src={url} controls className="w-full" />;
  else if (ct === "application/pdf") preview = <iframe title={m.title} src={url} className="w-full h-[520px] rounded-lg border" />;
  else if (OFFICE_RE.test(m.file_name || "")) preview = <OfficeViewer m={m} />;
  return (
    <>
      {instr}
      {preview}
      <a href={url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex items-center gap-1 text-sm text-teal-700 hover:underline" data-testid={`material-download-${m.id}`}><Download size={14} /> Descargar {m.file_name}</a>
    </>
  );
}
