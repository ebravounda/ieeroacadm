import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Award } from "lucide-react";
import { api, fmtDay } from "@/lib/api";
import { useAuth, isStaff } from "@/context/AuthContext";
import { PageHeader, Empty } from "@/components/Common";

export default function Diplomas() {
  const { user } = useAuth();
  const [rows, setRows] = useState([]);
  useEffect(() => { api.get(isStaff(user) ? "/diplomas" : "/my/diplomas").then((r) => setRows(r.data)); }, [user]);
  return (
    <>
      <PageHeader eyebrow="Certificación" title="Diplomas" subtitle="Cada diploma incluye un código QR que permite verificar su autenticidad públicamente." />
      {rows.length === 0 ? <Empty text="Aún no hay diplomas emitidos." testId="diplomas-empty" /> : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {rows.map((d) => (
            <Link key={d.id} to={`/diploma/${d.code}`} className="diploma-paper border rounded-xl p-6 hover:shadow-md transition-shadow" data-testid={`diploma-card-${d.code}`}>
              <Award className="text-amber-600" />
              <p className="font-semibold mt-3">{d.course_title}</p>
              <p className="text-sm text-slate-600">{d.student_name}</p>
              <p className="text-xs text-slate-500 mt-3 font-mono">{d.code} · {fmtDay(d.issued_at)}</p>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
