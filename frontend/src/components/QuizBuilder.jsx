import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const uid = () => Math.random().toString(36).slice(2, 10);

export default function QuizBuilder({ quiz, onChange, prefix }) {
  const qs = quiz.questions || [];
  const update = (i, patch) => onChange({ ...quiz, questions: qs.map((q, j) => (j === i ? { ...q, ...patch } : q)) });
  const add = (type) => onChange({ ...quiz, questions: [...qs, { id: uid(), type, text: "", options: type === "mc" ? ["", ""] : [], correct: type === "mc" ? 0 : null }] });
  const remove = (i) => onChange({ ...quiz, questions: qs.filter((_, j) => j !== i) });

  return (
    <div className="space-y-4" data-testid={`${prefix}-quiz-builder`}>
      <div className="flex items-center gap-3">
        <Label>Nota mínima de aprobación (%)</Label>
        <Input type="number" className="w-24" value={quiz.pass_score} onChange={(e) => onChange({ ...quiz, pass_score: Number(e.target.value) })} data-testid={`${prefix}-pass-score`} />
      </div>
      {qs.map((q, i) => (
        <div key={q.id} className="border rounded-lg p-4 bg-slate-50 space-y-3" data-testid={`${prefix}-question-${i}`}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Pregunta {i + 1} · {q.type === "mc" ? "Alternativas" : "Respuesta abierta (análisis IA)"}</span>
            <Button type="button" size="icon" variant="ghost" onClick={() => remove(i)} data-testid={`${prefix}-remove-question-${i}`}><Trash2 size={16} /></Button>
          </div>
          <Textarea placeholder="Enunciado" value={q.text} onChange={(e) => update(i, { text: e.target.value })} data-testid={`${prefix}-question-text-${i}`} />
          {q.type === "mc" && (
            <div className="space-y-2">
              {q.options.map((o, k) => (
                <div key={k} className="flex items-center gap-2">
                  <input type="radio" checked={q.correct === k} onChange={() => update(i, { correct: k })} data-testid={`${prefix}-q${i}-correct-${k}`} />
                  <Input value={o} placeholder={`Alternativa ${k + 1}`} onChange={(e) => update(i, { options: q.options.map((x, z) => (z === k ? e.target.value : x)) })} data-testid={`${prefix}-q${i}-option-${k}`} />
                </div>
              ))}
              <Button type="button" size="sm" variant="ghost" onClick={() => update(i, { options: [...q.options, ""] })} data-testid={`${prefix}-q${i}-add-option`}>+ Alternativa</Button>
            </div>
          )}
        </div>
      ))}
      <div className="flex gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => add("mc")} data-testid={`${prefix}-add-mc`}><Plus size={14} className="mr-1" /> Alternativas</Button>
        <Button type="button" variant="outline" size="sm" onClick={() => add("open")} data-testid={`${prefix}-add-open`}><Plus size={14} className="mr-1" /> Respuesta abierta</Button>
      </div>
    </div>
  );
}
