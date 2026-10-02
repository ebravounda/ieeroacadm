import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ShieldCheck, ShieldX } from "lucide-react";
import { api, fmtDay, fmtNota } from "@/lib/api";

export default function VerifyDiploma() {
  const { code } = useParams();
  const [d, setD] = useState(null);
  const [invalid, setInvalid] = useState(false);
  useEffect(() => { api.get(`/public/verify/${code}`).then((r) => setD(r.data)).catch(() => setInvalid(true)); }, [code]);

  return (
    <div className="min-h-screen bg-[#0F172A] flex items-center justify-center p-6">
      <div className="bg-white rounded-2xl max-w-md w-full p-8 fade-up" data-testid="verify-diploma-card">
        {invalid ? (
          <div className="text-center" data-testid="verify-diploma-invalid">
            <ShieldX size={48} className="mx-auto text-rose-600" />
            <h1 className="text-2xl font-bold mt-4">Diploma no válido</h1>
            <p className="text-slate-500 mt-2">El código <span className="font-mono">{code}</span> no corresponde a ningún diploma emitido.</p>
          </div>
        ) : !d ? <p className="text-slate-500">Verificando…</p> : (
          <div data-testid="verify-diploma-valid">
            <ShieldCheck size={48} className="text-emerald-600" />
            <h1 className="text-2xl font-bold mt-4">Diploma verificado</h1>
            <p className="text-slate-500 text-sm">Emitido por {d.otec_name}</p>
            <dl className="mt-6 space-y-3 text-sm">
              <div><dt className="text-xs uppercase tracking-wider text-slate-500">Estudiante</dt><dd className="font-semibold text-lg" data-testid="verify-student-name">{d.student_name}</dd></div>
              {d.rut && <div><dt className="text-xs uppercase tracking-wider text-slate-500">RUT</dt><dd>{d.rut}</dd></div>}
              <div><dt className="text-xs uppercase tracking-wider text-slate-500">Curso</dt><dd className="font-semibold" data-testid="verify-course-title">{d.course_title}</dd></div>
              {d.nota_final && <div><dt className="text-xs uppercase tracking-wider text-slate-500">Nota final</dt><dd data-testid="verify-nota">{fmtNota(d.nota_final)}</dd></div>}
              <div><dt className="text-xs uppercase tracking-wider text-slate-500">Fecha de emisión</dt><dd>{fmtDay(d.issued_at)}</dd></div>
              <div><dt className="text-xs uppercase tracking-wider text-slate-500">Código</dt><dd className="font-mono">{d.code}</dd></div>
            </dl>
          </div>
        )}
      </div>
    </div>
  );
}
