import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, CheckCircle2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth, isStaff } from "@/context/AuthContext";
import { PageHeader } from "@/components/Common";
import ExamRunner, { ExamResult } from "@/components/ExamRunner";
import { Button } from "@/components/ui/button";

function embedUrl(url) {
  const yt = url.match(/(?:youtu\.be\/|v=)([\w-]{11})/);
  if (yt) return `https://www.youtube.com/embed/${yt[1]}`;
  const vm = url.match(/vimeo\.com\/(\d+)/);
  if (vm) return `https://player.vimeo.com/video/${vm[1]}`;
  return url;
}

export default function ModuleView() {
  const { id } = useParams();
  const { user } = useAuth();
  const [m, setM] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [retry, setRetry] = useState(0);
  const load = () => api.get(`/modules/${id}`).then((r) => setM(r.data)).catch((e) => setError(errMsg(e)));
  useEffect(() => { setResult(null); load(); }, [id]); // eslint-disable-line

  if (error) return <div className="bg-white border rounded-xl p-8" data-testid="module-locked-message"><p className="font-semibold">{error}</p><Link to="/" className="text-teal-700 text-sm">Volver</Link></div>;
  if (!m) return <p className="text-slate-500">Cargando…</p>;
  const hasQuiz = m.quiz?.questions?.length > 0;
  const back = isStaff(user) ? `/cursos/${m.course_id}/editar` : `/curso/${m.course_id}`;
  const markDone = () => api.post(`/modules/${id}/complete`).then(() => { toast.success("Módulo completado"); load(); }).catch((e) => toast.error(errMsg(e)));

  return (
    <div className="max-w-3xl">
      <Link to={back} className="text-sm text-slate-500 flex items-center gap-1 mb-4 hover:text-slate-800" data-testid="module-back-link"><ArrowLeft size={14} /> Volver al curso</Link>
      <PageHeader eyebrow={`Módulo ${m.order}`} title={m.title} subtitle={m.description} />
      {m.video_url && <div className="aspect-video rounded-xl overflow-hidden bg-black mb-6"><iframe title="video" src={embedUrl(m.video_url)} className="w-full h-full" allowFullScreen data-testid="module-video" /></div>}
      <article className="bg-white border rounded-xl p-6 sm:p-8 whitespace-pre-wrap leading-relaxed text-slate-700 mb-8" data-testid="module-content">{m.content || "Sin contenido."}</article>
      {m.completed && <p className="mb-6 flex items-center gap-2 text-emerald-700 font-medium" data-testid="module-completed-badge"><CheckCircle2 size={18} /> Módulo completado</p>}
      {!isStaff(user) && !hasQuiz && !m.completed && <Button onClick={markDone} data-testid="module-mark-complete-button">Marcar como completado</Button>}
      {!isStaff(user) && hasQuiz && (
        <>
          <h3 className="text-xl font-semibold mb-4">Evaluación del módulo</h3>
          {result ? (
            <ExamResult result={result}>
              {result.passed ? <Button asChild><Link to={back} data-testid="module-continue-button">Continuar al siguiente módulo</Link></Button>
                : <Button variant="outline" onClick={() => { setResult(null); setRetry(retry + 1); }} data-testid="module-retry-button">Reintentar</Button>}
            </ExamResult>
          ) : <ExamRunner key={retry} quiz={m.quiz} submitUrl={`/modules/${id}/submit`} onResult={(r) => { setResult(r); load(); }} />}
        </>
      )}
    </div>
  );
}
