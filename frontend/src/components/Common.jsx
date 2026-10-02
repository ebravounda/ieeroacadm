export function PageHeader({ eyebrow, title, subtitle, children }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
      <div>
        {eyebrow && <p className="text-xs font-semibold uppercase tracking-wider text-teal-700 mb-2">{eyebrow}</p>}
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-2 text-slate-600 max-w-2xl">{subtitle}</p>}
      </div>
      {children && <div className="flex gap-2 flex-wrap">{children}</div>}
    </div>
  );
}

export function StatCard({ label, value, icon: Icon, accent = "text-teal-700 bg-teal-50", testId }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow" data-testid={testId}>
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</p>
        {Icon && <span className={`h-8 w-8 rounded-lg grid place-items-center ${accent}`}><Icon size={16} /></span>}
      </div>
      <p className="mt-3 text-3xl font-heading font-bold text-slate-900">{value}</p>
    </div>
  );
}

export function AiBadge({ value, testId }) {
  if (value === null || value === undefined) return <span className="text-xs text-slate-400" data-testid={testId}>—</span>;
  const cls = value >= 60 ? "bg-rose-100 text-rose-800 border-rose-200" : value >= 30 ? "bg-amber-100 text-amber-800 border-amber-200" : "bg-emerald-100 text-emerald-800 border-emerald-200";
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold font-mono ${cls}`} data-testid={testId}>{value}% IA</span>;
}

export function Empty({ text, testId }) {
  return <div className="border border-dashed border-slate-300 rounded-xl p-10 text-center text-slate-500 bg-white" data-testid={testId}>{text}</div>;
}
