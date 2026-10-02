import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ShieldAlert } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export default function ExamRunner({ quiz, submitUrl, onResult }) {
  const [answers, setAnswers] = useState({});
  const [sending, setSending] = useState(false);
  const stats = useRef({ tab: 0, paste: 0, start: Date.now() });

  useEffect(() => {
    const vis = () => document.visibilityState === "hidden" && (stats.current.tab += 1);
    document.addEventListener("visibilitychange", vis);
    return () => document.removeEventListener("visibilitychange", vis);
  }, []);

  const submit = async () => {
    setSending(true);
    try {
      const { data } = await api.post(submitUrl, {
        answers, tab_switches: stats.current.tab, paste_events: stats.current.paste,
        duration_sec: Math.round((Date.now() - stats.current.start) / 1000),
      });
      onResult(data);
    } catch (e) { toast.error(errMsg(e)); }
    finally { setSending(false); }
  };

  return (
    <div className="space-y-5" data-testid="exam-runner">
      <div className="flex items-start gap-2 text-xs text-slate-600 bg-amber-50 border border-amber-200 rounded-lg p-3">
        <ShieldAlert size={16} className="text-amber-600 shrink-0" />
        Esta evaluación registra cambios de pestaña, texto pegado y tiempo. Las respuestas abiertas se analizan con IA para estimar el porcentaje de contenido generado por inteligencia artificial.
      </div>
      {quiz.questions.map((q, i) => (
        <div key={q.id} className="bg-white border rounded-xl p-5" data-testid={`exam-question-${i}`}>
          <p className="font-medium mb-3"><span className="text-teal-700 font-mono mr-2">{i + 1}.</span>{q.text}</p>
          {q.type === "mc" ? (
            <div className="space-y-2">
              {q.options.map((o, k) => (
                <label key={k} className={`flex items-center gap-3 border rounded-lg px-3 py-2.5 cursor-pointer transition-colors ${String(answers[q.id]) === String(k) ? "border-teal-600 bg-teal-50" : "hover:bg-slate-50"}`}>
                  <input type="radio" name={q.id} checked={String(answers[q.id]) === String(k)} onChange={() => setAnswers({ ...answers, [q.id]: k })} data-testid={`exam-q${i}-option-${k}`} />
                  <span className="text-sm">{o}</span>
                </label>
              ))}
            </div>
          ) : (
            <Textarea rows={5} value={answers[q.id] || ""} onPaste={() => (stats.current.paste += 1)}
              onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} placeholder="Escribe tu respuesta con tus propias palabras…" data-testid={`exam-q${i}-open`} />
          )}
        </div>
      ))}
      <Button onClick={submit} disabled={sending} className="h-11 px-8" data-testid="exam-submit-button">{sending ? "Enviando…" : "Enviar evaluación"}</Button>
    </div>
  );
}

export function ExamResult({ result, children }) {
  return (
    <div className={`rounded-xl p-6 border ${result.passed ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200"}`} data-testid="exam-result">
      <p className="text-xs uppercase tracking-wider font-semibold text-slate-500">Resultado</p>
      <p className="text-4xl font-heading font-extrabold mt-1" data-testid="exam-result-score">{result.score}%</p>
      <p className="mt-1 text-sm" data-testid="exam-result-status">{result.passed ? "¡Aprobado!" : `No aprobado. Necesitas ${result.pass_score}% y responder todas las preguntas abiertas.`}</p>
      <div className="mt-4 flex gap-2 flex-wrap">{children}</div>
    </div>
  );
}
