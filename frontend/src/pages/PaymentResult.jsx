import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Hourglass, XCircle } from "lucide-react";
import { api } from "@/lib/api";

export default function PaymentResult() {
  const [params] = useSearchParams();
  const [p, setP] = useState(null);
  const id = params.get("orden");
  useEffect(() => {
    if (!id) return setP({ status: "error" });
    const load = () => api.get(`/public/payments/${id}`).then((r) => setP(r.data)).catch(() => setP({ status: "error" }));
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [id]);
  const ok = p?.status === "pagado";
  const pending = p?.status === "pendiente";
  const Icon = ok ? CheckCircle2 : pending ? Hourglass : XCircle;
  return (
    <div className="min-h-screen bg-[#0A2449] grid place-items-center p-6">
      <div className="bg-white rounded-2xl max-w-md w-full p-8 text-center fade-up" data-testid="payment-result-card">
        <img src="/logo.png" alt="IberoAcademy" className="h-16 mx-auto mb-6" />
        {!p ? <p className="text-slate-500">Consultando tu pago…</p> : (
          <>
            <Icon size={48} className={`mx-auto ${ok ? "text-emerald-600" : pending ? "text-amber-500" : "text-rose-600"}`} />
            <h1 className="text-2xl font-bold mt-4" data-testid="payment-result-status">{ok ? "¡Inscripción confirmada!" : pending ? "Pago en proceso" : "No se completó el pago"}</h1>
            {p.course_title && <p className="text-slate-600 mt-2">{p.course_title}</p>}
            <p className="text-sm text-slate-500 mt-4">
              {ok ? `Te enviamos un correo a ${p.email}. Ingresa a la plataforma con ese correo para comenzar.`
                : pending ? "Estamos esperando la confirmación de Flow. Esta página se actualiza sola."
                : "Puedes intentarlo nuevamente desde nuestra página de cursos."}
            </p>
            <Link to={ok ? "/login" : "/#cursos"} className="mt-6 inline-flex w-full justify-center rounded-lg bg-[#11305C] text-white font-semibold py-3 hover:bg-[#0A2449]" data-testid="payment-result-action">{ok ? "Ingresar a mi curso" : "Volver a los cursos"}</Link>
          </>
        )}
      </div>
    </div>
  );
}
