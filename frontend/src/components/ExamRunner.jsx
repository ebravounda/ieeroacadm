import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ShieldAlert, Hourglass } from "lucide-react";
import { api, errMsg, fmtNota } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

function Choice({ q, i, value, onChange }) {
  const multi = q.type === "multiple";
  const sel = multi ? value || [] : value;
  const isOn = (k) => (multi ? sel.includes(k) : String(sel) === String(k));
  const pick = (k) => onChange(multi ? (isOn(k) ? sel.filter((x) => x !== k) : [...sel, k]) : k);
  return (
    <div className="space-y-2">
      {multi && <p className="text-xs text-slate-500">Selecciona todas las alternativas correctas.</p>}
      {q.options.map((o, k) => (
        <label key={k} className={`flex items-center gap-3 border rounded-lg px-3 py-2.5 cursor-pointer transition-colors ${isOn(k) ? "border-teal-600 bg-teal-50" : "hover:bg-slate-50"}`}>
          <input type={multi ? "checkbox" : "radio"} name={q.id} checked={isOn(k)} onChange={() => pick(k)} data-testid={`exam-q${i}-option-${k}`} />
          <span className="text-sm">{o}</span>
        </label>
      ))}
    </div>
  );
}

const BLOCKED_KEYS = ["c", "x", "a", "p", "s", "u"];

function useCopyGuard(enabled, stats) {
  useEffect(() => {
    if (!enabled) return;
    const block = (e) => { e.preventDefault(); stats.current.copy += 1; toast.warning("Copiar contenido del examen final no está permitido"); };
    const key = (e) => {
      const k = (e.key || "").toLowerCase();
      if ((e.ctrlKey || e.metaKey) && BLOCKED_KEYS.includes(k)) block(e);
      else if (k === "printscreen") { navigator.clipboard?.writeText("").catch(() => {}); block(e); }
    };
    const evs = ["copy", "cut", "contextmenu", "dragstart", "selectstart"];
    const sel = (e) => (e.type !== "selectstart" || e.target?.tagName !== "TEXTAREA") && block(e);
    evs.forEach((ev) => document.addEventListener(ev, sel));
    document.addEventListener("keydown", key, true);
    return () => { evs.forEach((ev) => document.removeEventListener(ev, sel)); document.removeEventListener("keydown", key, true); };
  }, [enabled, stats]);
}

export default function ExamRunner({ quiz, submitUrl, onResult, protect = false }) {
  const [answers, setAnswers] = useState({});
  const [sending, setSending] = useState(false);
  const stats = useRef({ tab: 0, paste: 0, copy: 0, start: Date.now() });
  useCopyGuard(protect, stats);

  useEffect(() => {
    const vis = () => document.visibilityState === "hidden" && (stats.current.tab += 1);
    document.addEventListener("visibilitychange", vis);
    return () => document.removeEventListener("visibilitychange", vis);
  }, []);

  const submit = async () => {
    setSending(true);
    try {
      const { data } = await api.post(submitUrl, {
        answers, tab_switches: stats.current.tab, paste_events: stats.current.paste, copy_attempts: stats.current.copy,
        duration_sec: Math.round((Date.now() - stats.current.start) / 1000),
      });
      onResult(data);
    } catch (e) { toast.error(errMsg(e)); }
    finally { setSending(false); }
  };

  return (
    <div className={`space-y-5 ${protect ? "select-none [&_textarea]:select-text exam-protected" : ""}`} data-testid="exam-runner">
      {protect && <p className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-3" data-testid="exam-copy-protected-notice">Examen protegido: no se puede copiar, seleccionar ni imprimir el contenido. Los intentos de copia quedan registrados.</p>}
      <div className="flex items-start gap-2 text-xs text-slate-600 bg-amber-50 border border-amber-200 rounded-lg p-3">
        <ShieldAlert size={16} className="text-amber-600 shrink-0" />
        Aprobación: {quiz.pass_score}% (nota 4,0). Se registran cambios de pestaña, texto pegado y tiempo. Las respuestas de desarrollo se analizan con IA y las corrige el docente.
      </div>
      {quiz.questions.map((q, i) => (
        <div key={q.id} className="bg-white border rounded-xl p-5" data-testid={`exam-question-${i}`}>
          <p className="font-medium mb-3"><span className="text-teal-700 font-mono mr-2">{i + 1}.</span>{q.text}</p>
          {q.type === "open" ? (
            <Textarea rows={5} value={answers[q.id] || ""} onPaste={() => (stats.current.paste += 1)}
              onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} placeholder="Desarrolla tu respuesta con tus propias palabras…" data-testid={`exam-q${i}-open`} />
          ) : <Choice q={q} i={i} value={answers[q.id]} onChange={(v) => setAnswers({ ...answers, [q.id]: v })} />}
        </div>
      ))}
      <Button onClick={submit} disabled={sending} className="h-11 px-8" data-testid="exam-submit-button">{sending ? "Enviando…" : "Enviar evaluación"}</Button>
    </div>
  );
}

export function ExamResult({ result, children }) {
  if (result.status === "en_revision") {
    return (
      <div className="rounded-xl p-6 border bg-indigo-50 border-indigo-200" data-testid="exam-result">
        <Hourglass className="text-indigo-600" />
        <p className="font-semibold mt-2" data-testid="exam-result-status">Evaluación enviada · en revisión</p>
        <p className="text-sm text-slate-600 mt-1">Tu examen tiene preguntas de desarrollo. El docente las corregirá y verás aquí tu nota.</p>
        <div className="mt-4 flex gap-2 flex-wrap">{children}</div>
      </div>
    );
  }
  return (
    <div className={`rounded-xl p-6 border ${result.passed ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200"}`} data-testid="exam-result">
      <p className="text-xs uppercase tracking-wider font-semibold text-slate-500" data-testid="exam-result-attempt">Resultado{result.attempt ? ` · Intento ${result.attempt}` : ""}</p>
      <div className="flex items-end gap-6 mt-1">
        <div><p className="text-4xl font-heading font-extrabold" data-testid="exam-result-nota">{fmtNota(result.nota)}</p><p className="text-xs text-slate-500">Nota</p></div>
        <div><p className="text-2xl font-heading font-bold text-slate-600" data-testid="exam-result-score">{result.score}%</p><p className="text-xs text-slate-500">Logro</p></div>
      </div>
      <p className="mt-2 text-sm" data-testid="exam-result-status">{result.passed ? "¡Aprobado!" : `No aprobado (requiere ${result.pass_score}%).`}</p>
      {result.feedback && <p className="mt-2 text-sm text-slate-600">Comentario del docente: {result.feedback}</p>}
      <div className="mt-4 flex gap-2 flex-wrap">{children}</div>
    </div>
  );
}
