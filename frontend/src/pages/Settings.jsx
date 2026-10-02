import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Upload, Eye } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function SignatureUpload({ label, value, onChange, testId }) {
  const onFile = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.type !== "image/png") return toast.error("La firma debe ser un archivo PNG");
    if (file.size > 1024 * 1024) return toast.error("Máximo 1 MB");
    const r = new FileReader();
    r.onload = () => onChange(r.result);
    r.readAsDataURL(file);
  };
  return (
    <div className="border rounded-xl p-4 bg-white">
      <Label>{label}</Label>
      <div className="h-28 my-3 rounded-lg bg-slate-50 border border-dashed grid place-items-center" data-testid={`${testId}-preview`}>
        {value ? <img src={value} alt={label} className="max-h-24 object-contain" /> : <span className="text-xs text-slate-400">Sin firma</span>}
      </div>
      <label className="inline-flex items-center gap-2 text-sm text-teal-700 cursor-pointer hover:underline">
        <Upload size={14} /> Subir PNG
        <input type="file" accept="image/png" className="hidden" onChange={onFile} data-testid={`${testId}-input`} />
      </label>
    </div>
  );
}

const LAYOUT_FIELDS = [
  ["text_x", "Texto: margen izquierdo %"], ["text_w", "Texto: ancho %"], ["name_y", "Nombre: altura %"],
  ["course_y", "Curso: altura %"], ["sign_y", "Firmas: altura %"], ["sign_x", "Firmas: inicio %"],
  ["sign_w", "Firmas: ancho total %"], ["qr_x", "QR: posición horizontal %"], ["qr_y", "QR: posición vertical %"], ["qr_size", "QR: tamaño %"],
];

function TemplateCard({ s, setS, onPreview }) {
  const [busy, setBusy] = useState(false);
  const tpl = s.cert_template || {};
  const layout = s.cert_layout || {};
  const upload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!/\.(png|jpe?g|pdf)$/i.test(file.name)) return toast.error("La plantilla debe ser PNG, JPG o PDF");
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/files", fd);
      setS({ ...s, cert_template: { file_id: data.id, file_name: data.file_name, content_type: data.content_type } });
      toast.success("Plantilla cargada. Guarda la configuración y revisa la vista previa.");
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  const setLayout = (k, v) => setS({ ...s, cert_layout: { ...layout, [k]: v === "" ? undefined : Number(v) } });
  return (
    <div className="bg-white border rounded-xl p-6 mb-6 space-y-4" data-testid="settings-certificate-template">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-semibold">Plantilla del certificado</p>
          <p className="text-sm text-slate-500" data-testid="settings-template-name">{tpl.file_id ? `Plantilla propia: ${tpl.file_name}` : "Usando la plantilla IberoAcademy (diseño del ZIP adaptado)"}</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <label className="inline-flex items-center gap-2 text-sm border rounded-md px-3 h-9 cursor-pointer hover:bg-slate-50">
            <Upload size={14} /> {busy ? "Subiendo…" : "Subir plantilla (PNG, JPG o PDF)"}
            <input type="file" accept=".png,.jpg,.jpeg,.pdf" className="hidden" onChange={upload} disabled={busy} data-testid="settings-template-input" />
          </label>
          {tpl.file_id && <Button variant="ghost" size="sm" onClick={() => setS({ ...s, cert_template: {} })} data-testid="settings-template-reset">Usar plantilla IberoAcademy</Button>}
          <Button variant="outline" size="sm" onClick={onPreview} data-testid="settings-certificate-preview"><Eye size={14} className="mr-1" /> Vista previa PDF</Button>
        </div>
      </div>
      <p className="text-xs text-slate-500">La plantilla debe ser solo el fondo (sin nombres ni textos de ejemplo). La plataforma escribe el nombre del alumno, el curso, las tres firmas, el QR y el código de aprobación.</p>
      <details>
        <summary className="text-sm text-teal-700 cursor-pointer">Ajustar posiciones (para plantillas propias)</summary>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mt-3">
          {LAYOUT_FIELDS.map(([k, label]) => (
            <div key={k}><Label className="text-xs">{label}</Label><Input type="number" step="0.5" placeholder="auto" value={layout[k] ?? ""} onChange={(e) => setLayout(k, e.target.value)} data-testid={`settings-layout-${k}`} /></div>
          ))}
          <div><Label className="text-xs">Alineación</Label>
            <select className="h-9 w-full border rounded-md px-2 text-sm" value={layout.align || "left"} onChange={(e) => setS({ ...s, cert_layout: { ...layout, align: e.target.value } })} data-testid="settings-layout-align">
              <option value="left">Izquierda</option><option value="center">Centrada</option>
            </select>
          </div>
        </div>
      </details>
    </div>
  );
}

export default function Settings() {
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/settings").then((r) => setS(r.data)); }, []);
  if (!s) return <p className="text-slate-500">Cargando…</p>;
  const set = (k) => (e) => setS({ ...s, [k]: e.target.value });
  const save = () => api.put("/settings", s).then((r) => { setS(r.data); toast.success("Configuración guardada"); }).catch((e) => toast.error(errMsg(e)));
  const preview = async () => {
    try {
      await api.put("/settings", s);
      const r = await api.post("/settings/certificate-preview", {}, { responseType: "blob" });
      window.open(URL.createObjectURL(new Blob([r.data], { type: "application/pdf" })), "_blank");
    } catch (e) { toast.error("No se pudo generar la vista previa. Revisa la plantilla."); }
  };

  return (
    <div className="max-w-3xl">
      <PageHeader eyebrow="Institución" title="Configuración del certificado" subtitle="Plantilla del certificado, autoridades y firmas en PNG (idealmente con fondo transparente)." />
      <TemplateCard s={s} setS={setS} onPreview={preview} />
      <div className="bg-white border rounded-xl p-6 space-y-4 mb-6">
        <div><Label>Nombre de la OTEC</Label><Input value={s.otec_name} onChange={set("otec_name")} data-testid="settings-otec-name" /></div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div><Label>Nombre del Rector(a)</Label><Input value={s.rector_name} onChange={set("rector_name")} data-testid="settings-rector-name" /></div>
          <div><Label>Nombre del Vicerrector(a)</Label><Input value={s.vicerrector_name} onChange={set("vicerrector_name")} data-testid="settings-vicerrector-name" /></div>
          <div><Label>Nombre de la Directora Académica</Label><Input value={s.directora_name} onChange={set("directora_name")} data-testid="settings-directora-name" /></div>
        </div>
      </div>
      <div className="grid sm:grid-cols-3 gap-4 mb-6">
        <SignatureUpload label="Firma Rector(a)" value={s.rector_signature} onChange={(v) => setS({ ...s, rector_signature: v })} testId="settings-rector-signature" />
        <SignatureUpload label="Firma Vicerrector(a)" value={s.vicerrector_signature} onChange={(v) => setS({ ...s, vicerrector_signature: v })} testId="settings-vicerrector-signature" />
        <SignatureUpload label="Firma Directora Académica" value={s.directora_signature} onChange={(v) => setS({ ...s, directora_signature: v })} testId="settings-directora-signature" />
      </div>
      <Button onClick={save} data-testid="settings-save-button">Guardar configuración</Button>
    </div>
  );
}
