import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const uid = () => Math.random().toString(36).slice(2, 10);
const TYPE_LABEL = { single: "Alternativas (una correcta)", mc: "Alternativas (una correcta)", multiple: "Selección múltiple (varias correctas)", open: "Desarrollo (corrige el docente)" };

function Options({ q, i, prefix, update }) {
  const multi = q.type === "multiple";
  const isCorrect = (k) => (multi ? (q.correct_multi || []).includes(k) : q.correct === k);
  const toggle = (k) => {
    if (!multi) return update(i, { correct: k });
    const cur = q.correct_multi || [];
    update(i, { correct_multi: cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k] });
  };
  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-500">Marca {multi ? "todas las alternativas correctas" : "la alternativa correcta"}.</p>
      {q.options.map((o, k) => (
        <div key={k} className="flex items-center gap-2">
          <input type={multi ? "checkbox" : "radio"} checked={isCorrect(k)} onChange={() => toggle(k)} data-testid={`${prefix}-q${i}-correct-${k}`} />
          <Input value={o} placeholder={`Alternativa ${k + 1}`} onChange={(e) => update(i, { options: q.options.map((x, z) => (z === k ? e.target.value : x)) })} data-testid={`${prefix}-q${i}-option-${k}`} />
        </div>
      ))}
      <Button type="button" size="sm" variant="ghost" onClick={() => update(i, { options: [...q.options, ""] })} data-testid={`${prefix}-q${i}-add-option`}>+ Alternativa</Button>
    </div>
  );
}

export default function QuizBuilder({ quiz, onChange, prefix }) {
  const qs = quiz.questions || [];
  const update = (i, patch) => onChange({ ...quiz, questions: qs.map((q, j) => (j === i ? { ...q, ...patch } : q)) });
  const add = (type) => onChange({ ...quiz, questions: [...qs, { id: uid(), type, text: "", options: type === "open" ? [] : ["", ""], correct: type === "single" ? 0 : null, correct_multi: [] }] });
  const remove = (i) => onChange({ ...quiz, questions: qs.filter((_, j) => j !== i) });

  return (
    <div className="space-y-4" data-testid={`${prefix}-quiz-builder`}>
      <div className="flex items-center gap-3">
        <Label>Porcentaje de aprobación (%)</Label>
        <Input type="number" min={1} max={100} className="w-24" value={quiz.pass_score} onChange={(e) => onChange({ ...quiz, pass_score: Number(e.target.value) })} data-testid={`${prefix}-pass-score`} />
        <span className="text-xs text-slate-500">equivale a nota 4,0</span>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Label>Preguntas por alumno</Label>
        <Input type="number" min={1} className="w-24" value={quiz.draw_count ?? 10} onChange={(e) => onChange({ ...quiz, draw_count: Math.max(1, Number(e.target.value) || 1) })} data-testid={`${prefix}-draw-count`} />
        <span className="text-xs text-slate-500" data-testid={`${prefix}-bank-info`}>Banco: {qs.length} preguntas · cada alumno recibe {Math.min(quiz.draw_count ?? 10, qs.length)} al azar con alternativas mezcladas{qs.length <= (quiz.draw_count ?? 10) && qs.length > 0 ? " (agrega más preguntas al banco para que cada alumno reciba preguntas distintas)" : ""}</span>
      </div>
      {qs.map((q, i) => (
        <div key={q.id} className="border rounded-lg p-4 bg-slate-50 space-y-3" data-testid={`${prefix}-question-${i}`}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Pregunta {i + 1} · {TYPE_LABEL[q.type]}</span>
            <Button type="button" size="icon" variant="ghost" onClick={() => remove(i)} data-testid={`${prefix}-remove-question-${i}`}><Trash2 size={16} /></Button>
          </div>
          <Textarea placeholder="Enunciado" value={q.text} onChange={(e) => update(i, { text: e.target.value })} data-testid={`${prefix}-question-text-${i}`} />
          {q.type !== "open" && <Options q={q} i={i} prefix={prefix} update={update} />}
        </div>
      ))}
      <div className="flex gap-2 flex-wrap">
        <Button type="button" variant="outline" size="sm" onClick={() => add("single")} data-testid={`${prefix}-add-single`}><Plus size={14} className="mr-1" /> Alternativas</Button>
        <Button type="button" variant="outline" size="sm" onClick={() => add("multiple")} data-testid={`${prefix}-add-multiple`}><Plus size={14} className="mr-1" /> Selección múltiple</Button>
        <Button type="button" variant="outline" size="sm" onClick={() => add("open")} data-testid={`${prefix}-add-open`}><Plus size={14} className="mr-1" /> Desarrollo</Button>
      </div>
    </div>
  );
}
