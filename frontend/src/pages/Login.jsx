import { useState } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { toast } from "sonner";
import { GraduationCap, Mail, ArrowLeft } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";

const HERO = "https://images.unsplash.com/photo-1758270705290-62b6294dd044?crop=entropy&cs=srgb&fm=jpg&q=85&w=1400";

function RequestForm({ onSent }) {
  const [mode, setMode] = useState("login");
  const [f, setF] = useState({ email: "", nombre: "", apellidos: "", rut: "" });
  const [loading, setLoading] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (mode === "login") await api.post("/auth/request-code", { email: f.email });
      else await api.post("/auth/register", f);
      toast.success("Te enviamos un código a tu correo");
      onSent(f.email);
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4" data-testid="otp-login-request-form">
      <div className="flex bg-slate-100 rounded-lg p-1 text-sm">
        {[["login", "Ingresar"], ["register", "Matricularme"]].map(([k, l]) => (
          <button type="button" key={k} onClick={() => setMode(k)} data-testid={`otp-login-tab-${k}`}
            className={`flex-1 py-2 rounded-md transition-colors ${mode === k ? "bg-white shadow-sm font-semibold" : "text-slate-500"}`}>{l}</button>
        ))}
      </div>
      {mode === "register" && (
        <div className="grid grid-cols-2 gap-3">
          <div><Label>Nombres</Label><Input required value={f.nombre} onChange={set("nombre")} data-testid="register-nombre-input" /></div>
          <div><Label>Apellidos</Label><Input required value={f.apellidos} onChange={set("apellidos")} data-testid="register-apellidos-input" /></div>
          <div className="col-span-2"><Label>RUT / Documento</Label><Input value={f.rut} onChange={set("rut")} data-testid="register-rut-input" /></div>
        </div>
      )}
      <div>
        <Label>Correo electrónico</Label>
        <Input type="email" required value={f.email} onChange={set("email")} placeholder="tu@correo.cl" data-testid="otp-login-email-input" />
      </div>
      <Button type="submit" className="w-full h-11" disabled={loading} data-testid="otp-login-send-code-button">
        <Mail size={16} className="mr-2" /> {loading ? "Enviando…" : "Enviar código de verificación"}
      </Button>
    </form>
  );
}

function VerifyForm({ email, onBack }) {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const nav = useNavigate();

  const verify = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/auth/verify-code", { email, code });
      login(data.token, data.user);
      nav("/");
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setLoading(false);
    }
  };

  const resend = () => api.post("/auth/request-code", { email }).then(() => toast.success("Código reenviado")).catch((e) => toast.error(errMsg(e)));

  return (
    <div className="space-y-5" data-testid="otp-login-verify-form">
      <button onClick={onBack} className="text-sm text-slate-500 flex items-center gap-1 hover:text-slate-800" data-testid="otp-login-back-button"><ArrowLeft size={14} /> Cambiar correo</button>
      <p className="text-sm text-slate-600">Ingresa el código de 6 dígitos enviado a <b>{email}</b></p>
      <InputOTP maxLength={6} value={code} onChange={setCode} data-testid="otp-login-code-input">
        <InputOTPGroup>{[0, 1, 2, 3, 4, 5].map((i) => <InputOTPSlot key={i} index={i} className="h-12 w-12 text-lg" />)}</InputOTPGroup>
      </InputOTP>
      <Button className="w-full h-11" disabled={code.length < 6 || loading} onClick={verify} data-testid="otp-login-verify-button">
        {loading ? "Verificando…" : "Ingresar a la plataforma"}
      </Button>
      <button onClick={resend} className="text-sm text-teal-700 hover:underline" data-testid="otp-login-resend-button">Reenviar código</button>
    </div>
  );
}

export default function Login() {
  const { user } = useAuth();
  const [email, setEmail] = useState(null);
  if (user) return <Navigate to="/" replace />;
  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      <div className="hidden lg:block relative">
        <img src={HERO} alt="Estudiantes" className="absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-[#0F172A]/70" />
        <div className="relative h-full flex flex-col justify-end p-14 text-white">
          <p className="text-xs uppercase tracking-[0.2em] text-teal-300 mb-4">Organismo Técnico de Capacitación</p>
          <h1 className="text-5xl font-extrabold leading-tight max-w-lg">Aprende a tu ritmo, certifica tu avance.</h1>
          <p className="mt-4 text-slate-300 max-w-md">Cursos modulares, clases en vivo por Teams y Google Meet, evaluaciones y diplomas verificables con código QR.</p>
        </div>
      </div>
      <div className="flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-sm fade-up">
          <div className="flex items-center gap-3 mb-10">
            <div className="h-10 w-10 rounded-lg bg-teal-600 grid place-items-center text-white"><GraduationCap size={22} /></div>
            <span className="font-heading text-xl font-bold">IberoAcademy</span>
          </div>
          <h2 className="text-2xl font-bold mb-1">Bienvenido</h2>
          <p className="text-slate-500 text-sm mb-6">Accede sin contraseña con un código enviado a tu correo.</p>
          {email ? <VerifyForm email={email} onBack={() => setEmail(null)} /> : <RequestForm onSent={setEmail} />}
        </div>
      </div>
    </div>
  );
}
