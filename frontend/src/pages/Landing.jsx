import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Clock, Laptop, QrCode, Video, Briefcase, TrendingUp, CalendarCheck, ArrowRight, Menu, X, MapPin, Handshake } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

const B = process.env.REACT_APP_BACKEND_URL;
const img = (u) => (u?.startsWith("/api/") ? `${B}${u}` : u);
const clp = (n) => (n ? `$${Number(n).toLocaleString("es-CL")}` : "Gratis");
const DEFAULT_SLIDES = [
  { image_url: "/landing/slide4.jpg", title: "Capacítate online con IberoAcademy", subtitle: "Cursos 100% en línea, a tu ritmo y con certificado verificable." },
  { image_url: "/landing/slide2.jpg", title: "Potencia tu currículum", subtitle: "Suma competencias que las empresas valoran y destaca en tu próximo proceso de selección." },
  { image_url: "/landing/slide3.jpg", title: "Aprende desde donde estés", subtitle: "Módulos asincrónicos, clases en vivo por Teams o Meet y acompañamiento docente." },
];
const BENEFITS = [
  [Briefcase, "Mejora tu currículum", "Cada curso aprobado suma un certificado con nombre, nota y código QR que puedes adjuntar a tu CV y LinkedIn."],
  [TrendingUp, "Más oportunidades laborales", "Actualizar tus competencias te ayuda a postular a mejores cargos, ascender o cambiar de rubro."],
  [Laptop, "100% online", "Accede desde tu computador o celular, sin horarios rígidos ni traslados."],
  [Clock, "A tu ritmo", "Avanza módulo a módulo de forma asincrónica y retoma donde quedaste."],
  [Video, "Clases en vivo", "Sesiones por Microsoft Teams y Google Meet con tus docentes."],
  [QrCode, "Certificado verificable", "Cualquier empleador puede comprobar tu certificado escaneando su código QR."],
];
const FAQ = [
  ["¿Cómo me inscribo?", "Elige tu curso, presiona “Inscríbete ahora”, completa tus datos y paga de forma segura con Flow. Al confirmarse el pago quedas matriculado automáticamente."],
  ["¿Cómo ingreso a la plataforma?", "Ingresa con tu correo: te enviaremos un código de acceso de 6 dígitos cada vez que entres, sin contraseñas."],
  ["¿Cómo se evalúa?", "Cada módulo tiene un examen. Al aprobar todos los módulos rindes la evaluación final. Las notas van de 1,0 a 7,0."],
  ["¿Recibo un certificado?", "Sí. Al aprobar el curso recibes un certificado en PDF con tu nombre, nota final y un código QR de verificación."],
];

function Header() {
  const [open, setOpen] = useState(false);
  const links = [["#cursos", "Cursos"], ["#beneficios", "¿Por qué estudiar?"], ["#preguntas", "Preguntas frecuentes"]];
  return (
    <header className="fixed top-0 inset-x-0 z-50 backdrop-blur-xl bg-white/85 border-b">
      <div className="max-w-7xl mx-auto px-5 h-20 flex items-center gap-8">
        <a href="#inicio"><img src="/logo.png" alt="IberoAcademy" className="h-14 w-auto" data-testid="landing-logo" /></a>
        <nav className="hidden md:flex gap-7 text-sm font-medium text-slate-700">{links.map(([h, l]) => <a key={h} href={h} className="hover:text-teal-600 transition-colors">{l}</a>)}</nav>
        <div className="ml-auto hidden md:flex gap-2">
          <Button asChild variant="ghost"><Link to="/login" data-testid="landing-login-button">Ingresar</Link></Button>
          <Button asChild className="bg-teal-300 text-teal-900 hover:bg-teal-400"><a href="#cursos" data-testid="landing-header-cta">Inscríbete ahora</a></Button>
        </div>
        <button className="ml-auto md:hidden" onClick={() => setOpen(!open)} data-testid="landing-mobile-menu">{open ? <X /> : <Menu />}</button>
      </div>
      {open && <div className="md:hidden border-t bg-white px-5 py-4 flex flex-col gap-3">{links.map(([h, l]) => <a key={h} href={h} onClick={() => setOpen(false)}>{l}</a>)}<Link to="/login" className="font-semibold text-teal-600">Ingresar</Link></div>}
    </header>
  );
}

function Hero({ slides }) {
  const list = slides.length ? slides : DEFAULT_SLIDES;
  const [i, setI] = useState(0);
  useEffect(() => { const t = setInterval(() => setI((x) => (x + 1) % list.length), 6000); return () => clearInterval(t); }, [list.length]);
  const go = (d) => setI((i + d + list.length) % list.length);
  return (
    <section id="inicio" className="relative h-[88vh] min-h-[560px] mt-20 overflow-hidden bg-teal-900" data-testid="landing-hero-slider">
      {list.map((s, k) => (
        <div key={k} className={`absolute inset-0 transition-opacity duration-1000 ${k === i ? "opacity-100" : "opacity-0"}`}>
          {s.image_url && <img src={img(s.image_url)} alt="" className={`h-full w-full object-cover transition-transform duration-[7000ms] ${k === i ? "scale-105" : "scale-100"}`} />}
          <div className="absolute inset-0 bg-gradient-to-r from-[#0A2449]/90 via-[#0A2449]/60 to-transparent" />
          <div className="absolute inset-0 max-w-7xl mx-auto px-5 flex flex-col justify-center">
            <p className="text-teal-300 uppercase tracking-[0.25em] text-xs font-semibold mb-4">IberoAcademy · Capacitación online</p>
            <h1 className="text-white text-4xl sm:text-5xl lg:text-6xl font-extrabold max-w-2xl leading-tight" data-testid={`landing-slide-title-${k}`}>{s.title}</h1>
            <p className="text-slate-200 text-lg mt-5 max-w-xl">{s.subtitle}</p>
            <div className="mt-8 flex gap-3 flex-wrap">
              <Button asChild size="lg" className="bg-teal-300 text-teal-900 hover:bg-teal-400 h-12 px-8"><a href="#cursos" data-testid="landing-hero-cta">Ver cursos <ArrowRight size={18} className="ml-2" /></a></Button>
              <Button asChild size="lg" variant="outline" className="h-12 px-8 bg-transparent text-white border-white/50 hover:bg-white/10 hover:text-white"><Link to="/login">Ya soy alumno</Link></Button>
            </div>
          </div>
        </div>
      ))}
      <div className="absolute bottom-8 inset-x-0 max-w-7xl mx-auto px-5 flex items-center gap-3">
        <button onClick={() => go(-1)} className="h-10 w-10 rounded-full border border-white/40 text-white grid place-items-center hover:bg-white/10" data-testid="landing-slide-prev"><ChevronLeft size={18} /></button>
        <button onClick={() => go(1)} className="h-10 w-10 rounded-full border border-white/40 text-white grid place-items-center hover:bg-white/10" data-testid="landing-slide-next"><ChevronRight size={18} /></button>
        <div className="flex gap-2 ml-3">{list.map((_, k) => <button key={k} onClick={() => setI(k)} className={`h-1.5 rounded-full transition-all ${k === i ? "w-10 bg-teal-300" : "w-5 bg-white/40"}`} data-testid={`landing-slide-dot-${k}`} />)}</div>
      </div>
    </section>
  );
}

function EnrollDialog({ course, onClose }) {
  const [f, setF] = useState({ nombre: "", apellidos: "", rut: "", email: "", accept_terms: false });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/public/checkout", { ...f, course_id: course.id });
      if (data.checkout_url) window.location.assign(data.checkout_url);
      else window.location.assign(`/pago/resultado?orden=${data.order_id}`);
    } catch (err) { toast.error(errMsg(err)); setBusy(false); }
  };
  return (
    <Dialog open={!!course} onOpenChange={(o) => !o && onClose()}>
      <DialogContent aria-describedby={undefined}>
        <DialogHeader><DialogTitle>Inscripción: {course?.title}</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-2 gap-3" data-testid="landing-enroll-form">
          <div><Label>Nombres</Label><Input required value={f.nombre} onChange={set("nombre")} data-testid="enroll-nombre" /></div>
          <div><Label>Apellidos</Label><Input required value={f.apellidos} onChange={set("apellidos")} data-testid="enroll-apellidos" /></div>
          <div><Label>RUT</Label><Input value={f.rut} onChange={set("rut")} data-testid="enroll-rut" /></div>
          <div><Label>Correo</Label><Input type="email" required value={f.email} onChange={set("email")} data-testid="enroll-email" /></div>
          <div className="col-span-2 flex items-center justify-between bg-slate-50 rounded-lg p-3 mt-1"><span className="text-sm text-slate-600">Total a pagar</span><b className="text-xl" data-testid="enroll-total">{clp(course?.price)}</b></div>
          <label className="col-span-2 flex items-start gap-2 text-sm text-slate-600 cursor-pointer">
            <input type="checkbox" required checked={f.accept_terms} onChange={(e) => setF({ ...f, accept_terms: e.target.checked })} className="mt-0.5 h-4 w-4 accent-[#11305C]" data-testid="enroll-accept-terms" />
            <span>Acepto los <a href="/terminos" target="_blank" rel="noreferrer" className="text-teal-600 underline">Términos y Condiciones</a> y la <a href="/privacidad" target="_blank" rel="noreferrer" className="text-teal-600 underline">Política de Privacidad</a>.</span>
          </label>
          <Button type="submit" disabled={busy || !f.accept_terms} className="col-span-2 h-11" data-testid="enroll-submit">{busy ? "Procesando…" : course?.price ? "Ir a pagar con Flow" : "Confirmar inscripción"}</Button>
          <p className="col-span-2 text-xs text-slate-500 text-center">Pago seguro con Flow: tarjetas de crédito, débito y transferencias.</p>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Courses({ courses, onEnroll }) {
  return (
    <section id="cursos" className="max-w-7xl mx-auto px-5 py-24">
      <p className="text-xs font-semibold uppercase tracking-[0.25em] text-teal-600">Oferta académica</p>
      <h2 className="text-3xl sm:text-4xl font-extrabold mt-2 mb-10 text-slate-900">Nuestros cursos</h2>
      {courses.length === 0 ? <p className="text-slate-500" data-testid="landing-courses-empty">Muy pronto publicaremos nuestros cursos.</p> : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-7">
          {courses.map((c) => (
            <article key={c.id} className="group bg-white rounded-2xl border overflow-hidden shadow-sm hover:shadow-xl hover:-translate-y-1 transition-[transform,box-shadow] duration-300 flex flex-col" data-testid={`landing-course-${c.id}`}>
              <div className="aspect-[16/10] bg-teal-50 overflow-hidden">{c.image_url ? <img src={img(c.image_url)} alt={c.title} className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-500" /> : <div className="h-full grid place-items-center"><img src="/logo.png" alt="" className="h-20 opacity-60" /></div>}</div>
              <div className="p-6 flex flex-col flex-1">
                <div className="flex gap-2 text-xs text-slate-500 mb-2">{c.hours > 0 && <span className="flex items-center gap-1"><Clock size={12} /> {c.hours} horas</span>}{c.modality && <span>· {c.modality}</span>}</div>
                <h3 className="text-lg font-bold text-slate-900">{c.title}</h3>
                <p className="text-sm text-slate-600 mt-2 line-clamp-3 flex-1">{c.summary || c.description}</p>
                <div className="flex items-center justify-between mt-6">
                  <span className="text-2xl font-extrabold text-teal-600" data-testid={`landing-course-price-${c.id}`}>{clp(c.price)}</span>
                  <Button onClick={() => onEnroll(c)} className="bg-teal-300 text-teal-900 hover:bg-teal-400" data-testid={`landing-enroll-${c.id}`}>Inscríbete ahora</Button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

const PARTNERS = [["aws", "Amazon Web Services"], ["tramilex", "Tramilex"], ["goroky", "GoRoky"], ["openfactura", "Openfactura"], ["inmo-tramilex", "Inmo Tramilex"]];
const COUNTRIES = ["Chile", "España", "México", "Honduras", "Perú"];

function Partners() {
  return (
    <section id="alianzas" className="bg-slate-50 border-y py-24" data-testid="landing-partners">
      <div className="max-w-7xl mx-auto px-5">
        <div className="grid lg:grid-cols-[1fr_1.4fr] gap-10 items-end mb-12">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.25em] text-teal-600 flex items-center gap-2"><Handshake size={14} /> Alianzas estratégicas</p>
            <h2 className="text-3xl sm:text-4xl font-extrabold mt-2 text-slate-900">Respaldados por grandes empresas</h2>
          </div>
          <div>
            <p className="text-slate-600">Contamos con alianzas estratégicas con grandes empresas en Chile, España, México, Honduras y Perú, que fortalecen nuestra formación y conectan a nuestros estudiantes con el mundo laboral.</p>
            <div className="flex flex-wrap gap-2 mt-4" data-testid="landing-partner-countries">
              {COUNTRIES.map((c) => <span key={c} className="inline-flex items-center gap-1 text-xs font-semibold text-teal-900 bg-white border rounded-full px-3 py-1.5"><MapPin size={12} className="text-teal-600" />{c}</span>)}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 sm:gap-6">
          {PARTNERS.map(([k, n]) => (
            <div key={k} className="group bg-white rounded-2xl border h-32 sm:h-36 p-5 sm:p-6 flex items-center justify-center overflow-hidden shadow-sm hover:shadow-lg hover:-translate-y-1 transition-[transform,box-shadow] duration-300" data-testid={`landing-partner-${k}`}>
              <img src={`/partners/${k}.png`} alt={n} loading="lazy" className="max-h-full max-w-full object-contain mix-blend-multiply group-hover:scale-105 transition-transform duration-300" />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Benefits() {
  return (
    <section id="beneficios" className="bg-teal-900 text-white py-24">
      <div className="max-w-7xl mx-auto px-5">
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-teal-300">¿Por qué estudiar con nosotros?</p>
        <h2 className="text-3xl sm:text-4xl font-extrabold mt-2 max-w-2xl">Un curso hoy es una ventaja en tu currículum mañana</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 mt-12">
          {BENEFITS.map(([Icon, t, d]) => (
            <div key={t} className="rounded-2xl border border-white/10 bg-white/5 p-6 hover:bg-white/10 transition-colors">
              <span className="h-11 w-11 rounded-xl bg-teal-300 text-teal-900 grid place-items-center"><Icon size={20} /></span>
              <h3 className="font-bold text-lg mt-4">{t}</h3>
              <p className="text-slate-300 text-sm mt-2">{d}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function Landing() {
  const [data, setData] = useState({ slides: [], courses: [] });
  const [selected, setSelected] = useState(null);
  useEffect(() => { api.get("/public/landing").then((r) => setData(r.data)); }, []);
  return (
    <div className="bg-white">
      <Header />
      <Hero slides={data.slides} />
      <section className="max-w-7xl mx-auto px-5 -mt-12 relative z-10 grid sm:grid-cols-3 gap-4">
        {[[CalendarCheck, "Inscripción inmediata", "Paga en línea y comienza el mismo día"], [Laptop, "Aula virtual", "Contenidos, tareas y exámenes en un solo lugar"], [QrCode, "Certificado con QR", "Verificable por cualquier empleador"]].map(([Icon, t, d]) => (
          <div key={t} className="bg-white rounded-2xl shadow-lg border p-6 flex gap-4 items-start"><Icon className="text-teal-300 shrink-0" /><div><p className="font-bold">{t}</p><p className="text-sm text-slate-500">{d}</p></div></div>
        ))}
      </section>
      <Courses courses={data.courses} onEnroll={setSelected} />
      <Partners />
      <Benefits />
      <section id="preguntas" className="max-w-3xl mx-auto px-5 py-24">
        <h2 className="text-3xl font-extrabold mb-8 text-slate-900">Preguntas frecuentes</h2>
        <Accordion type="single" collapsible data-testid="landing-faq">
          {FAQ.map(([q, a], k) => <AccordionItem key={q} value={`q${k}`}><AccordionTrigger className="text-left">{q}</AccordionTrigger><AccordionContent className="text-slate-600">{a}</AccordionContent></AccordionItem>)}
        </Accordion>
      </section>
      <footer className="bg-[#061A38] text-slate-400 py-12">
        <div className="max-w-7xl mx-auto px-5 flex flex-col sm:flex-row gap-6 justify-between items-start sm:items-center">
          <div className="bg-white rounded-xl p-2"><img src="/logo.png" alt="IberoAcademy" className="h-12" /></div>
          <div className="text-sm"><p>© {new Date().getFullYear()} IBERO ACADEMY SpA · RUT 78.486.869-9</p><p className="text-xs mt-1">Providencia, Región Metropolitana, Chile</p></div>
          <nav className="flex flex-col sm:flex-row gap-3 sm:gap-6 text-sm">
            <Link to="/terminos" className="hover:text-white" data-testid="footer-terms-link">Términos y Condiciones</Link>
            <Link to="/privacidad" className="hover:text-white" data-testid="footer-privacy-link">Política de Privacidad</Link>
            <Link to="/login" className="text-teal-300 hover:underline">Acceso alumnos y docentes</Link>
          </nav>
        </div>
      </footer>
      <EnrollDialog course={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
