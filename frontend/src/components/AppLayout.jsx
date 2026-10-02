import { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { ListChecks, LayoutDashboard, Users, BookOpen, ClipboardCheck, BarChart3, Video, Settings, Award, LogOut, Menu } from "lucide-react";
import { useAuth, isStaff } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

const NAV = [
  { to: "/", label: "Inicio", icon: LayoutDashboard, roles: ["admin", "docente", "estudiante"] },
  { to: "/mi-avance", label: "Mi avance", icon: ListChecks, roles: ["estudiante"] },
  { to: "/estudiantes", label: "Estudiantes", icon: Users, roles: ["admin", "docente"] },
  { to: "/cursos", label: "Cursos y módulos", icon: BookOpen, roles: ["admin", "docente"] },
  { to: "/evaluaciones", label: "Evaluaciones e IA", icon: ClipboardCheck, roles: ["admin", "docente"] },
  { to: "/analitica", label: "Analítica", icon: BarChart3, roles: ["admin", "docente"] },
  { to: "/clases", label: "Clases en vivo", icon: Video, roles: ["admin", "docente", "estudiante"] },
  { to: "/diplomas", label: "Diplomas", icon: Award, roles: ["admin", "docente", "estudiante"] },
  { to: "/configuracion", label: "Configuración", icon: Settings, roles: ["admin"] },
];

function contextOf(path) {
  const c = path.match(/^\/curso\/([^/]+)/);
  if (c) return { course_id: c[1] };
  const m = path.match(/^\/modulo\/([^/]+)/);
  return m ? { module_id: m[1] } : {};
}

function useHeartbeat() {
  const { pathname } = useLocation();
  const path = useRef(pathname);
  path.current = pathname;
  useEffect(() => {
    const beat = () => document.visibilityState === "visible" && api.post("/activity/heartbeat", contextOf(path.current)).catch(() => {});
    beat();
    const t = setInterval(beat, 60000);
    return () => clearInterval(t);
  }, []);
}

export default function AppLayout({ children }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  useHeartbeat();
  const items = NAV.filter((n) => n.roles.includes(user.role));

  return (
    <div className="min-h-screen flex">
      <aside className={`fixed lg:sticky top-0 z-40 h-screen w-64 shrink-0 bg-[#0F172A] text-slate-300 flex flex-col transition-transform duration-200 ${open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`} data-testid="sidebar">
        <div className="px-5 py-5 flex items-center gap-3 border-b border-slate-800">
          <div className="h-12 w-12 rounded-lg bg-white grid place-items-center p-1 shrink-0"><img src="/logo.png" alt="IberoAcademy" className="max-h-full max-w-full object-contain" data-testid="sidebar-logo" /></div>
          <div>
            <p className="font-heading font-bold text-white leading-tight">IberoAcademy</p>
            <p className="text-[11px] uppercase tracking-wider text-slate-500">{isStaff(user) ? "Gestión" : "Aula virtual"}</p>
          </div>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)}
              data-testid={`nav-${to === "/" ? "inicio" : to.slice(1)}`}
              className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${isActive ? "bg-teal-600/15 text-teal-300" : "hover:bg-slate-800 hover:text-white"}`}>
              <Icon size={18} /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-slate-800">
          <p className="text-sm text-white truncate" data-testid="sidebar-user-name">{user.nombre} {user.apellidos}</p>
          <p className="text-xs text-slate-500 truncate mb-3">{user.email} · {user.role}</p>
          <Button variant="ghost" size="sm" className="w-full justify-start text-slate-400 hover:text-white hover:bg-slate-800" data-testid="logout-button"
            onClick={async () => { await logout(); nav("/login"); }}>
            <LogOut size={16} className="mr-2" /> Cerrar sesión
          </Button>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="flex-1 min-w-0">
        <header className="lg:hidden sticky top-0 z-20 backdrop-blur-md bg-white/80 border-b px-4 py-3 flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => setOpen(true)} data-testid="mobile-menu-button"><Menu /></Button>
          <img src="/logo.png" alt="IberoAcademy" className="h-8 w-auto" />
          <span className="font-heading font-bold">IberoAcademy</span>
        </header>
        <main className="p-5 sm:p-8 lg:p-10 max-w-7xl fade-up">{children}</main>
      </div>
    </div>
  );
}
