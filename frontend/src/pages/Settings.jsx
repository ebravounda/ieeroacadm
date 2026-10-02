import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Upload } from "lucide-react";
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

export default function Settings() {
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/settings").then((r) => setS(r.data)); }, []);
  if (!s) return <p className="text-slate-500">Cargando…</p>;
  const set = (k) => (e) => setS({ ...s, [k]: e.target.value });
  const save = () => api.put("/settings", s).then((r) => { setS(r.data); toast.success("Configuración guardada"); }).catch((e) => toast.error(errMsg(e)));

  return (
    <div className="max-w-3xl">
      <PageHeader eyebrow="Institución" title="Configuración del diploma" subtitle="Nombre de la OTEC, autoridades y firmas en PNG (idealmente con fondo transparente)." />
      <div className="bg-white border rounded-xl p-6 space-y-4 mb-6">
        <div><Label>Nombre de la OTEC</Label><Input value={s.otec_name} onChange={set("otec_name")} data-testid="settings-otec-name" /></div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div><Label>Nombre del Rector(a)</Label><Input value={s.rector_name} onChange={set("rector_name")} data-testid="settings-rector-name" /></div>
          <div><Label>Nombre del Vicerrector(a)</Label><Input value={s.vicerrector_name} onChange={set("vicerrector_name")} data-testid="settings-vicerrector-name" /></div>
        </div>
      </div>
      <div className="grid sm:grid-cols-2 gap-4 mb-6">
        <SignatureUpload label="Firma Rector(a)" value={s.rector_signature} onChange={(v) => setS({ ...s, rector_signature: v })} testId="settings-rector-signature" />
        <SignatureUpload label="Firma Vicerrector(a)" value={s.vicerrector_signature} onChange={(v) => setS({ ...s, vicerrector_signature: v })} testId="settings-vicerrector-signature" />
      </div>
      <Button onClick={save} data-testid="settings-save-button">Guardar configuración</Button>
    </div>
  );
}
