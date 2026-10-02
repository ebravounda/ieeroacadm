import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { QRCodeSVG } from "qrcode.react";
import { Printer, ShieldCheck, ShieldX } from "lucide-react";
import { api, errMsg, fmtDay } from "@/lib/api";
import { Button } from "@/components/ui/button";

const hour = (iso) => new Date(iso).toLocaleTimeString("es-CL", { timeStyle: "short" });

export default function AttendanceCertificate() {
  const { code } = useParams();
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.get(`/attendance-certificates/${code}`).then((r) => setD(r.data)).catch((e) => setError(errMsg(e))); }, [code]);
  if (error) return <p data-testid="attendance-cert-error">{error}</p>;
  if (!d) return <p className="text-slate-500">Cargando…</p>;
  const verifyUrl = `${window.location.origin}/verificar-asistencia/${d.code}`;

  return (
    <div>
      <div className="flex justify-end mb-4"><Button onClick={() => window.print()} data-testid="attendance-cert-print"><Printer size={16} className="mr-2" /> Imprimir / Guardar PDF</Button></div>
      <div id="diploma-print" className="diploma-paper aspect-[1.414/1] w-full max-w-4xl mx-auto shadow-xl border-[6px] border-teal-800/60 p-6 sm:p-12 flex flex-col text-slate-900" data-testid="attendance-cert-document">
        <div className="text-center">
          <p className="text-xs sm:text-sm uppercase tracking-[0.35em] text-teal-800 font-semibold">{d.otec_name}</p>
          <h1 className="mt-3 sm:mt-6 text-2xl sm:text-4xl font-extrabold tracking-tight">Certificado de asistencia</h1>
          <p className="mt-4 sm:mt-6 text-sm text-slate-600">Se certifica que</p>
          <p className="mt-2 text-xl sm:text-3xl font-heading font-bold text-teal-900" data-testid="attendance-cert-student">{d.student_name}</p>
          {d.rut && <p className="text-sm text-slate-600 mt-1">RUT {d.rut}</p>}
          <p className="mt-3 sm:mt-5 text-sm text-slate-600">asistió a la clase en vivo</p>
          <p className="mt-1 text-lg sm:text-2xl font-semibold" data-testid="attendance-cert-class">{d.class_title}</p>
          <p className="text-sm text-slate-600 mt-1">del curso {d.course_title}</p>
          <p className="text-xs sm:text-sm text-slate-500 mt-2">{fmtDay(d.start_at)} · {hour(d.start_at)} – {hour(d.end_at)} ({d.duration_min} min) · {d.platform} · ingreso {hour(d.joined_at)}</p>
        </div>
        <div className="mt-auto flex items-end justify-between">
          <p className="text-[11px] text-slate-500">Emitido el {fmtDay(d.issued_at)}</p>
          <div className="text-center" data-testid="attendance-cert-qr">
            <QRCodeSVG value={verifyUrl} size={84} level="M" bgColor="transparent" />
            <p className="text-[10px] font-mono mt-1">Código: {d.code}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export function VerifyAttendance() {
  const { code } = useParams();
  const [d, setD] = useState(null);
  const [invalid, setInvalid] = useState(false);
  useEffect(() => { api.get(`/public/verify-attendance/${code}`).then((r) => setD(r.data)).catch(() => setInvalid(true)); }, [code]);
  return (
    <div className="min-h-screen bg-[#0F172A] flex items-center justify-center p-6">
      <div className="bg-white rounded-2xl max-w-md w-full p-8 fade-up" data-testid="verify-attendance-card">
        {invalid ? (
          <div className="text-center" data-testid="verify-attendance-invalid">
            <ShieldX size={48} className="mx-auto text-rose-600" />
            <h1 className="text-2xl font-bold mt-4">Certificado no válido</h1>
            <p className="text-slate-500 mt-2">El código <span className="font-mono">{code}</span> no corresponde a ningún certificado emitido.</p>
          </div>
        ) : !d ? <p className="text-slate-500">Verificando…</p> : (
          <div data-testid="verify-attendance-valid">
            <ShieldCheck size={48} className="text-emerald-600" />
            <h1 className="text-2xl font-bold mt-4">Asistencia verificada</h1>
            <p className="text-slate-500 text-sm">Emitido por {d.otec_name}</p>
            <dl className="mt-6 space-y-3 text-sm">
              <div><dt className="text-xs uppercase tracking-wider text-slate-500">Estudiante</dt><dd className="font-semibold text-lg">{d.student_name}</dd></div>
              {d.rut && <div><dt className="text-xs uppercase tracking-wider text-slate-500">RUT</dt><dd>{d.rut}</dd></div>}
              <div><dt className="text-xs uppercase tracking-wider text-slate-500">Clase</dt><dd className="font-semibold">{d.class_title}</dd></div>
              <div><dt className="text-xs uppercase tracking-wider text-slate-500">Curso</dt><dd>{d.course_title}</dd></div>
              <div><dt className="text-xs uppercase tracking-wider text-slate-500">Fecha</dt><dd>{fmtDay(d.start_at)} · {hour(d.start_at)} – {hour(d.end_at)} · {d.platform}</dd></div>
              <div><dt className="text-xs uppercase tracking-wider text-slate-500">Código</dt><dd className="font-mono">{d.code}</dd></div>
            </dl>
          </div>
        )}
      </div>
    </div>
  );
}
