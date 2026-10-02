import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Bot, RefreshCw, Copy, Eye, Clock } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { PageHeader, AiBadge, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";

function Detail({ sub, onReanalyze, busy }) {
  const ai = sub.ai_analysis;
  const per = Object.fromEntries((ai?.answers || []).map((a) => [a.question_id, a]));
  return (
    <div className="space-y-5 mt-4" data-testid="ai-detector-detail">
      <div className="bg-[#0F172A] text-white rounded-xl p-5">
        <p className="text-xs uppercase tracking-wider text-teal-300 flex items-center gap-1"><Bot size={14} /> Análisis Claude</p>
        {ai ? (
          <>
            <p className="text-4xl font-heading font-extrabold mt-2" data-testid="ai-detector-percentage">{ai.percentage}%</p>
            <Progress value={ai.percentage} className="h-2 mt-2 bg-slate-700" />
            <p className="text-sm text-slate-300 mt-3">{ai.summary}</p>
          </>
        ) : <p className="mt-2 text-sm text-slate-300">Estado: {sub.ai_status}</p>}
        <Button size="sm" variant="secondary" className="mt-4" disabled={busy} onClick={onReanalyze} data-testid="ai-detector-reanalyze"><RefreshCw size={14} className={`mr-1 ${busy ? "animate-spin" : ""}`} /> Reanalizar</Button>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div className="border rounded-lg p-3"><Eye size={14} className="mx-auto mb-1" /><b className="text-lg">{sub.behavior.tab_switches}</b><p>cambios de pestaña</p></div>
        <div className="border rounded-lg p-3"><Copy size={14} className="mx-auto mb-1" /><b className="text-lg">{sub.behavior.paste_events}</b><p>textos pegados</p></div>
        <div className="border rounded-lg p-3"><Clock size={14} className="mx-auto mb-1" /><b className="text-lg">{Math.round(sub.behavior.duration_sec / 60)}</b><p>minutos</p></div>
      </div>
      {sub.questions.filter((q) => q.type === "open").map((q) => (
        <div key={q.id} className="border rounded-lg p-4">
          <div className="flex justify-between gap-2"><p className="text-sm font-semibold">{q.text}</p><AiBadge value={per[q.id]?.percentage} /></div>
          <p className="text-sm text-slate-700 mt-2 bg-slate-50 rounded p-3 whitespace-pre-wrap">{sub.answers[q.id] || "(sin respuesta)"}</p>
          {per[q.id]?.reasoning && <p className="text-xs text-slate-500 mt-2">{per[q.id].reasoning}</p>}
        </div>
      ))}
    </div>
  );
}

export default function Submissions() {
  const [subs, setSubs] = useState([]);
  const [sel, setSel] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/submissions").then((r) => setSubs(r.data));
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);
  const reanalyze = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/submissions/${sel.id}/analyze`); setSel({ ...sel, ...data }); load(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader eyebrow="Evaluaciones" title="Entregas y detección de IA" subtitle="Cada respuesta abierta es analizada por Claude para estimar el porcentaje de contenido generado con IA." />
      {subs.length === 0 ? <Empty text="Aún no hay evaluaciones rendidas." testId="submissions-empty" /> : (
        <div className="bg-white border rounded-xl divide-y" data-testid="submissions-list">
          {subs.map((s) => (
            <button key={s.id} onClick={() => setSel(s)} className="w-full text-left p-4 flex flex-wrap items-center gap-4 hover:bg-slate-50 transition-colors" data-testid={`submission-row-${s.id}`}>
              <div className="flex-1 min-w-[200px]"><p className="font-medium">{s.student_name}</p><p className="text-xs text-slate-500">{s.course_title} · {s.module_title} · {fmtDate(s.created_at)}</p></div>
              <span className={`text-sm font-mono font-semibold ${s.passed ? "text-emerald-700" : "text-rose-600"}`}>{s.score}%</span>
              {s.ai_status === "completado" ? <AiBadge value={s.ai_analysis.percentage} testId={`submission-ai-${s.id}`} /> : <span className="text-xs text-slate-400" data-testid={`submission-ai-${s.id}`}>IA: {s.ai_status}</span>}
            </button>
          ))}
        </div>
      )}
      <Sheet open={!!sel} onOpenChange={(o) => !o && setSel(null)}>
        <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
          {sel && <><SheetHeader><SheetTitle>{sel.student_name}</SheetTitle><p className="text-sm text-slate-500">{sel.course_title} · {sel.module_title} · Nota {sel.score}%</p></SheetHeader><Detail sub={sel} onReanalyze={reanalyze} busy={busy} /></>}
        </SheetContent>
      </Sheet>
    </>
  );
}
