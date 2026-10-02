import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth, isStaff } from "@/context/AuthContext";
import AppLayout from "@/components/AppLayout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Students from "@/pages/Students";
import Courses from "@/pages/Courses";
import CourseEditor from "@/pages/CourseEditor";
import CourseView from "@/pages/CourseView";
import ModuleView from "@/pages/ModuleView";
import FinalExam from "@/pages/FinalExam";
import Submissions from "@/pages/Submissions";
import Analytics from "@/pages/Analytics";
import LiveClasses from "@/pages/LiveClasses";
import Settings from "@/pages/Settings";
import Diplomas from "@/pages/Diplomas";
import MyProgress from "@/pages/MyProgress";
import AttendanceCertificate, { VerifyAttendance } from "@/pages/AttendanceCertificate";
import Landing from "@/pages/Landing";
import PaymentResult from "@/pages/PaymentResult";
import Payments from "@/pages/Payments";
import WebsiteAdmin from "@/pages/WebsiteAdmin";
import Legal from "@/pages/Legal";
import Integrations from "@/pages/Integrations";

function Home() {
  const { user } = useAuth();
  if (user === null) return <div className="p-10 text-slate-500">Cargando…</div>;
  return user ? <AppLayout><Dashboard /></AppLayout> : <Landing />;
}
import DiplomaView from "@/pages/DiplomaView";
import VerifyDiploma from "@/pages/VerifyDiploma";

function Protected({ children, staff, admin }) {
  const { user } = useAuth();
  if (user === null) return <div className="p-10 text-slate-500" data-testid="auth-loading">Cargando…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (staff && !isStaff(user)) return <Navigate to="/" replace />;
  if (admin && user.role !== "admin") return <Navigate to="/" replace />;
  return <AppLayout>{children}</AppLayout>;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/verificar/:code" element={<VerifyDiploma />} />
          <Route path="/verificar-asistencia/:code" element={<VerifyAttendance />} />
          <Route path="/certificado-asistencia/:code" element={<Protected><AttendanceCertificate /></Protected>} />
          <Route path="/" element={<Home />} />
          <Route path="/terminos" element={<Legal doc="terminos" />} />
          <Route path="/privacidad" element={<Legal doc="privacidad" />} />
          <Route path="/pago/resultado" element={<PaymentResult />} />
          <Route path="/pagos" element={<Protected staff><Payments /></Protected>} />
          <Route path="/integraciones" element={<Protected admin><Integrations /></Protected>} />
          <Route path="/sitio-web" element={<Protected admin><WebsiteAdmin /></Protected>} />
          <Route path="/estudiantes" element={<Protected staff><Students /></Protected>} />
          <Route path="/cursos" element={<Protected staff><Courses /></Protected>} />
          <Route path="/cursos/:id/editar" element={<Protected staff><CourseEditor /></Protected>} />
          <Route path="/curso/:id" element={<Protected><CourseView /></Protected>} />
          <Route path="/modulo/:id" element={<Protected><ModuleView /></Protected>} />
          <Route path="/curso/:id/final" element={<Protected><FinalExam /></Protected>} />
          <Route path="/evaluaciones" element={<Protected staff><Submissions /></Protected>} />
          <Route path="/analitica" element={<Protected staff><Analytics /></Protected>} />
          <Route path="/clases" element={<Protected><LiveClasses /></Protected>} />
          <Route path="/configuracion" element={<Protected admin><Settings /></Protected>} />
          <Route path="/mi-avance" element={<Protected><MyProgress /></Protected>} />
          <Route path="/diplomas" element={<Protected><Diplomas /></Protected>} />
          <Route path="/diploma/:code" element={<Protected><DiplomaView /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster richColors position="top-right" />
    </AuthProvider>
  );
}

export default App;
