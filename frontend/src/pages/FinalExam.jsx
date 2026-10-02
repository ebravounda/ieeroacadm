import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Award } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import ExamRunner, { ExamResult } from "@/components/ExamRunner";
import { Button } from "@/components/ui/button";

export default function FinalExam() {
  const { id } = useParams();
  const [exam, setExam] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => { api.get(`/courses/${id}/final-exam`).then((r) => setExam(r.data)).catch((e) => setError(errMsg(e))); }, [id]);

  if (error) return <div className="bg-white border rounded-xl p-8" data-testid="final-exam-locked"><p className="font-semibold">{error}</p><Link to={`/curso/${id}`} className="text-teal-700 text-sm">Volver al curso</Link></div>;
  if (!exam) return <p className="text-slate-500">Cargando…</p>;
  const shown = result || (["en_revision"].includes(exam.last_submission?.status) || exam.final_passed ? exam.last_submission : null);

  return (
    <div className="max-w-3xl">
      <PageHeader eyebrow="Evaluación final" title={exam.course_title} subtitle={`Aprobación con ${exam.pass_score}%. Tu nota final será el promedio entre el promedio de tus módulos y este examen.`} />
      {shown ? (
        <ExamResult result={shown}>
          {(result?.passed || exam.final_passed) && <Button asChild><Link to={`/curso/${id}`} data-testid="final-back-course">Ver nota final y diploma</Link></Button>}
          {result?.passed === false && <Button variant="outline" onClick={() => { setResult(null); setRetry(retry + 1); }} data-testid="final-retry-button">Reintentar</Button>}
          {result?.diploma_code && <Button asChild variant="secondary"><Link to={`/diploma/${result.diploma_code}`} data-testid="final-view-diploma"><Award size={16} className="mr-2" /> Ver mi diploma</Link></Button>}
        </ExamResult>
      ) : exam.questions.length ? (
        <ExamRunner key={retry} quiz={exam} submitUrl={`/courses/${id}/final-exam/submit`} onResult={setResult} />
      ) : <p>El curso aún no tiene evaluación final configurada.</p>}
    </div>
  );
}
