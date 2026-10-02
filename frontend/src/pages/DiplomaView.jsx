import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { QRCodeSVG } from "qrcode.react";
import { Printer } from "lucide-react";
import { api, errMsg, fmtDay, fmtNota } from "@/lib/api";
import { Button } from "@/components/ui/button";

function Signature({ img, name, role }) {
  return (
    <div className="text-center w-48 sm:w-56">
      <div className="h-16 flex items-end justify-center">{img && <img src={img} alt={role} className="max-h-16 object-contain" />}</div>
      <div className="border-t border-slate-400 mt-1 pt-1">
        <p className="text-sm font-semibold">{name || "—"}</p>
        <p className="text-[11px] uppercase tracking-wider text-slate-500">{role}</p>
      </div>
    </div>
  );
}

export default function DiplomaView() {
  const { code } = useParams();
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.get(`/diplomas/${code}`).then((r) => setD(r.data)).catch((e) => setError(errMsg(e))); }, [code]);
  if (error) return <p data-testid="diploma-error">{error}</p>;
  if (!d) return <p className="text-slate-500">Cargando…</p>;
  const s = d.settings;
  const verifyUrl = `${window.location.origin}/verificar/${d.code}`;

  return (
    <div>
      <div className="flex justify-end mb-4"><Button onClick={() => window.print()} data-testid="diploma-print-button"><Printer size={16} className="mr-2" /> Imprimir / Guardar PDF</Button></div>
      <div id="diploma-print" className="diploma-paper relative aspect-[1.414/1] w-full max-w-5xl mx-auto shadow-xl border-[10px] border-double border-teal-800/70 p-6 sm:p-12 flex flex-col text-slate-900" data-testid="diploma-document">
        <div className="text-center">
          <p className="text-xs sm:text-sm uppercase tracking-[0.35em] text-teal-800 font-semibold" data-testid="diploma-otec-name">{s.otec_name}</p>
          <h1 className="mt-3 sm:mt-6 text-3xl sm:text-5xl font-extrabold tracking-tight" style={{ fontFamily: "Plus Jakarta Sans" }}>Diploma</h1>
          <p className="mt-3 sm:mt-6 text-sm text-slate-600">Se otorga el presente diploma a</p>
          <p className="mt-2 text-2xl sm:text-4xl font-heading font-bold text-teal-900" data-testid="diploma-student-name">{d.student_name}</p>
          {d.rut && <p className="text-sm text-slate-600 mt-1">RUT {d.rut}</p>}
          <p className="mt-3 sm:mt-5 text-sm text-slate-600">por haber aprobado satisfactoriamente el curso</p>
          <p className="mt-1 text-lg sm:text-2xl font-semibold" data-testid="diploma-course-title">{d.course_title}</p>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">{d.nota_final ? <span data-testid="diploma-nota">Nota final {fmtNota(d.nota_final)} · </span> : ""}{d.hours ? `${d.hours} horas cronológicas · ` : ""}Emitido el {fmtDay(d.issued_at)}</p>
        </div>
        <div className="mt-auto flex items-end justify-between gap-4">
          <Signature img={s.rector_signature} name={s.rector_name} role="Rector(a)" />
          <div className="text-center" data-testid="diploma-qr">
            <QRCodeSVG value={verifyUrl} size={92} level="M" bgColor="transparent" />
            <p className="text-[10px] font-mono mt-1">Código: {d.code}</p>
          </div>
          <Signature img={s.vicerrector_signature} name={s.vicerrector_name} role="Vicerrector(a)" />
        </div>
      </div>
    </div>
  );
}
