import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Download, Hourglass, XCircle } from "lucide-react";
import { api, errMsg, fmtDay, fmtNota } from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function DiplomaView() {
  const { code } = useParams();
  const [d, setD] = useState(null);
  const [pdfUrl, setPdfUrl] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let url;
    api.get(`/diplomas/${code}`).then(async (r) => {
      setD(r.data);
      if ((r.data.status || "aprobado") === "aprobado") {
        const pdf = await api.get(`/diplomas/${code}/pdf`, { responseType: "blob" });
        url = URL.createObjectURL(new Blob([pdf.data], { type: "application/pdf" }));
        setPdfUrl(url);
      }
    }).catch((e) => setError(errMsg(e)));
    return () => url && URL.revokeObjectURL(url);
  }, [code]);

  if (error) return <p data-testid="diploma-error">{error}</p>;
  if (!d) return <p className="text-slate-500">Cargando…</p>;
  const status = d.status || "aprobado";

  if (status !== "aprobado") {
    const pending = status === "pendiente";
    return (
      <div className="max-w-xl bg-white border rounded-xl p-8" data-testid="diploma-pending">
        {pending ? <Hourglass className="text-amber-600" /> : <XCircle className="text-rose-600" />}
        <h2 className="text-2xl font-bold mt-3">{pending ? "Certificado en aprobación" : "Solicitud rechazada"}</h2>
        <p className="text-slate-600 mt-2">
          {pending ? <>¡Felicidades por completar <b>{d.course_title}</b>! Tu certificado está siendo revisado por la institución. Te avisaremos por correo cuando sea emitido.</>
            : <>La solicitud de certificado para <b>{d.course_title}</b> fue rechazada{d.reject_reason ? `: ${d.reject_reason}` : "."} Contacta a la institución.</>}
        </p>
        <p className="text-sm text-slate-500 mt-4">Nota final: <b>{fmtNota(d.nota_final)}</b> · Solicitado el {fmtDay(d.issued_at)}</p>
        <Link to="/diplomas" className="text-teal-700 text-sm mt-4 inline-block">Volver a certificados</Link>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="text-2xl font-bold" data-testid="diploma-course-title">{d.course_title}</h1>
          <p className="text-sm text-slate-500" data-testid="diploma-student-name">{d.student_name} · Código de aprobación <span className="font-mono font-semibold" data-testid="diploma-code">{d.code}</span></p>
        </div>
        {pdfUrl && <Button asChild><a href={pdfUrl} download={`certificado_${d.code}.pdf`} data-testid="diploma-download-button"><Download size={16} className="mr-2" /> Descargar PDF</a></Button>}
      </div>
      {pdfUrl ? <iframe title="Certificado" src={pdfUrl} className="w-full h-[75vh] rounded-xl border bg-white" data-testid="diploma-document" />
        : <p className="text-slate-500">Cargando certificado…</p>}
    </div>
  );
}
