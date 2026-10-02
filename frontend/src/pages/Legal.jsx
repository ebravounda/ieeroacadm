import { useEffect } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

const CO = "IBERO ACADEMY SpA, RUT 78.486.869-9, con domicilio en la comuna de Providencia, Región Metropolitana de Santiago, Chile";
const MAIL = "[correo de contacto]";
const UPDATED = "2 de octubre de 2026";

const TERMS = {
  title: "Términos y Condiciones",
  sections: [
    ["1. Identificación", `El sitio web y la plataforma de aprendizaje IberoAcademy (en adelante, "la Plataforma") son operados por ${CO} (en adelante, "IberoAcademy"). Contacto: ${MAIL}. Estos términos se rigen por la Ley N° 19.496 sobre Protección de los Derechos de los Consumidores de Chile y, para usuarios residentes en España o la Unión Europea, por el Real Decreto Legislativo 1/2007 (Ley General para la Defensa de los Consumidores y Usuarios) y la Ley 34/2002 de Servicios de la Sociedad de la Información y de Comercio Electrónico (LSSI).`],
    ["2. Aceptación", "Al inscribirse, pagar un curso o usar la Plataforma, el usuario declara haber leído y aceptado estos Términos y Condiciones y la Política de Privacidad. Si no está de acuerdo, debe abstenerse de usar los servicios. La aceptación se registra en forma electrónica junto con la fecha y hora de la inscripción."],
    ["3. Servicios", "IberoAcademy ofrece cursos de capacitación en modalidad en línea y/o mixta, que pueden incluir módulos de contenido, materiales descargables, clases en vivo (Microsoft Teams o Google Meet), evaluaciones por módulo, examen final y emisión de certificados o diplomas. El contenido, duración, horas y precio de cada curso se informan en su ficha antes de la contratación."],
    ["4. Registro y cuenta", "El acceso se realiza con el correo electrónico del usuario mediante un código o enlace de ingreso. El usuario se obliga a entregar datos verdaderos, completos y actualizados (nombre, apellidos, RUT o documento de identidad y correo), y es responsable de la confidencialidad de su acceso. La cuenta es personal e intransferible."],
    ["5. Precios y pagos", "Los precios se expresan en pesos chilenos (CLP) e incluyen los impuestos que correspondan, salvo indicación en contrario. Los pagos se procesan a través de Flow (Flow S.A.), plataforma de pagos externa que acepta tarjetas de crédito, débito y transferencias. IberoAcademy no almacena datos de tarjetas. Una vez confirmado el pago, el acceso al curso se habilita automáticamente y se envía una confirmación al correo registrado."],
    ["6. Derecho de retracto y desistimiento", "Conforme al artículo 3 bis de la Ley N° 19.496, el consumidor en Chile puede retractarse de la compra dentro de los 10 días corridos siguientes a la contratación, comunicándolo a " + MAIL + ". Los usuarios residentes en la Unión Europea disponen de un plazo de 14 días naturales para desistir, salvo que hayan solicitado expresamente comenzar a acceder al contenido digital y reconocido la pérdida del derecho de desistimiento al iniciarlo (art. 103 m) del RDL 1/2007). Los reembolsos que procedan se realizarán por el mismo medio de pago dentro de los plazos legales."],
    ["7. Uso de la Plataforma y evaluaciones", "Los módulos se desbloquean en forma secuencial y pueden exigir un tiempo mínimo de permanencia. Las evaluaciones usan la escala de notas chilena de 1,0 a 7,0, con el porcentaje de aprobación que defina cada curso. El usuario se compromete a rendir sus evaluaciones en forma personal y honesta. Para resguardar la integridad académica, IberoAcademy puede analizar las respuestas escritas con herramientas de inteligencia artificial que estiman la probabilidad de texto generado por IA; este resultado es orientativo y la decisión final siempre la toma un docente."],
    ["8. Asistencia y registro de actividad", "La Plataforma registra el tiempo de conexión, el avance por módulo y la asistencia a clases en vivo, con fines académicos y de reporte a organismos de capacitación (OTEC / SENCE) cuando corresponda."],
    ["9. Certificados", "Al cumplir los requisitos del curso (aprobación de módulos y examen final), el usuario podrá obtener un certificado o diploma digital con un código QR verificable públicamente. La emisión está sujeta a revisión y aprobación administrativa. IberoAcademy podrá anular certificados obtenidos mediante fraude o suplantación."],
    ["10. Propiedad intelectual", "Todos los contenidos de la Plataforma (textos, presentaciones, videos, evaluaciones, logotipos y diseño) son de propiedad de IberoAcademy o de sus licenciantes y están protegidos por la Ley N° 17.336 de Propiedad Intelectual de Chile y la normativa española y europea aplicable. Se permite su uso solo para fines personales de estudio; queda prohibida su reproducción, distribución o comercialización sin autorización escrita."],
    ["11. Conductas prohibidas", "Está prohibido compartir el acceso con terceros, suplantar identidades, copiar o difundir evaluaciones, alterar el funcionamiento de la Plataforma o usarla con fines ilícitos. El incumplimiento podrá dar lugar a la suspensión de la cuenta, sin perjuicio de las acciones legales que correspondan."],
    ["12. Responsabilidad", "IberoAcademy procurará la disponibilidad continua de la Plataforma, pero no garantiza la ausencia de interrupciones por mantenimiento, fallas de terceros (proveedores de internet, pagos o videoconferencia) o fuerza mayor. Nada de lo dispuesto limita los derechos irrenunciables del consumidor."],
    ["13. Modificaciones", "IberoAcademy podrá actualizar estos términos. Los cambios se publicarán en esta página con su fecha de actualización y no afectarán las contrataciones ya realizadas."],
    ["14. Ley aplicable y reclamos", "Estos términos se rigen por las leyes de la República de Chile. El consumidor podrá recurrir a los tribunales competentes de su domicilio y al Servicio Nacional del Consumidor (SERNAC). Los consumidores residentes en la Unión Europea conservan la protección de las normas imperativas de su país de residencia y pueden usar la plataforma europea de resolución de litigios en línea (https://ec.europa.eu/consumers/odr)."],
  ],
};

const PRIVACY = {
  title: "Política de Privacidad",
  sections: [
    ["1. Responsable del tratamiento", `${CO}. Correo de contacto para asuntos de privacidad: ${MAIL}. Esta política se ajusta a la Ley N° 19.628 sobre Protección de la Vida Privada y a la Ley N° 21.719 que la moderniza (Chile), al Reglamento (UE) 2016/679 General de Protección de Datos (RGPD) y a la Ley Orgánica 3/2018 de Protección de Datos Personales y garantía de los derechos digitales (LOPDGDD, España).`],
    ["2. Datos que recopilamos", "Datos de identificación y contacto (nombre, apellidos, RUT o documento de identidad, correo electrónico); datos académicos (inscripciones, avance, tiempo de conexión, asistencia a clases en vivo, respuestas a evaluaciones, calificaciones y certificados); datos de pago (monto, estado y número de orden; los datos de tarjeta los trata exclusivamente Flow); y datos técnicos (dirección IP, navegador y registros de acceso)."],
    ["3. Finalidades", "a) Gestionar la inscripción, el acceso y la prestación de los cursos; b) procesar pagos y emitir comprobantes; c) evaluar el aprendizaje y emitir certificados verificables; d) enviar comunicaciones del servicio (códigos de acceso, recordatorios de clases, avisos de inactividad, resultados); e) cumplir obligaciones legales y de reporte a organismos de capacitación (OTEC / SENCE); f) resguardar la integridad académica y la seguridad de la Plataforma."],
    ["4. Base de licitud", "Ejecución del contrato de prestación de servicios educativos (art. 6.1.b RGPD); cumplimiento de obligaciones legales (art. 6.1.c RGPD); interés legítimo en la integridad académica y seguridad (art. 6.1.f RGPD); y consentimiento del titular cuando sea necesario, que puede retirarse en cualquier momento. En Chile, el tratamiento se basa en el consentimiento del titular y en las demás fuentes de licitud previstas en la ley."],
    ["5. Uso de inteligencia artificial", "Las respuestas escritas de las evaluaciones pueden ser analizadas por un servicio de inteligencia artificial para estimar la probabilidad de que hayan sido generadas por IA. No se adoptan decisiones basadas únicamente en tratamiento automatizado: el resultado es una referencia para el docente, quien revisa y decide. El titular puede solicitar intervención humana y expresar su punto de vista."],
    ["6. Destinatarios y encargados", "Compartimos datos solo con proveedores necesarios para prestar el servicio, bajo contratos de confidencialidad: procesador de pagos (Flow), servicios de alojamiento y almacenamiento en la nube, envío de correos electrónicos, videoconferencia (Microsoft Teams / Google Meet) y análisis con IA. Además, con organismos públicos cuando la ley lo exija. Los certificados pueden ser verificados por terceros mediante su código QR, mostrando solo nombre, curso, fecha y validez."],
    ["7. Transferencias internacionales", "Algunos proveedores pueden estar ubicados fuera de Chile o del Espacio Económico Europeo (por ejemplo, en Estados Unidos). En esos casos se aplican garantías adecuadas, como cláusulas contractuales tipo aprobadas por la Comisión Europea o decisiones de adecuación."],
    ["8. Plazo de conservación", "Los datos se conservan mientras exista la relación con el usuario y, después, durante los plazos necesarios para cumplir obligaciones legales, tributarias y de capacitación, y para permitir la verificación de los certificados emitidos. Luego se eliminan o anonimizan."],
    ["9. Derechos del titular", `El titular puede ejercer sus derechos de acceso, rectificación, supresión (cancelación), oposición, portabilidad, limitación del tratamiento y bloqueo, escribiendo a ${MAIL} e indicando su nombre y documento de identidad. Responderemos dentro de los plazos legales (un mes en la UE, prorrogable según el RGPD; y los plazos de la ley chilena). Si considera que sus derechos no han sido atendidos, puede reclamar ante la Agencia de Protección de Datos Personales de Chile o ante la Agencia Española de Protección de Datos (www.aepd.es).`],
    ["10. Seguridad", "Aplicamos medidas técnicas y organizativas razonables para proteger los datos: conexiones cifradas (HTTPS), acceso restringido por roles, sesiones protegidas y proveedores con estándares de seguridad reconocidos. En caso de una vulneración que afecte sus datos, se notificará a la autoridad y a los afectados cuando la ley lo exija."],
    ["11. Cookies", "La Plataforma usa solo cookies técnicas imprescindibles para mantener la sesión iniciada y el funcionamiento del sitio. No usamos cookies publicitarias ni de seguimiento de terceros."],
    ["12. Menores de edad", "Los cursos están dirigidos a mayores de 18 años. Si un menor desea inscribirse, debe contar con la autorización de su padre, madre o representante legal (en España, el consentimiento propio solo es válido desde los 14 años, art. 7 LOPDGDD)."],
    ["13. Cambios a esta política", "Podemos actualizar esta política. Publicaremos la versión vigente en esta página con su fecha de actualización."],
  ],
};

export default function Legal({ doc }) {
  const d = doc === "privacidad" ? PRIVACY : TERMS;
  useEffect(() => { window.scrollTo(0, 0); document.title = `${d.title} · IberoAcademy`; }, [d]);
  return (
    <div className="min-h-screen bg-slate-50" data-testid={`legal-page-${doc}`}>
      <header className="bg-white border-b">
        <div className="max-w-4xl mx-auto px-5 h-20 flex items-center justify-between">
          <Link to="/" data-testid="legal-home-link"><img src="/logo.png" alt="IberoAcademy" className="h-14" /></Link>
          <Link to="/" className="text-sm text-teal-600 flex items-center gap-1 hover:underline" data-testid="legal-back-link"><ArrowLeft size={14} /> Volver al inicio</Link>
        </div>
      </header>
      <main className="max-w-4xl mx-auto px-5 py-14">
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-teal-600">Información legal</p>
        <h1 className="text-4xl sm:text-5xl font-extrabold text-slate-900 mt-2" data-testid="legal-title">{d.title}</h1>
        <p className="text-sm text-slate-500 mt-3">Última actualización: {UPDATED}</p>
        <div className="bg-white rounded-2xl border shadow-sm p-6 sm:p-10 mt-10 space-y-8">
          {d.sections.map(([t, body]) => (
            <section key={t}>
              <h2 className="text-base md:text-lg font-bold text-slate-900">{t}</h2>
              <p className="text-sm sm:text-base text-slate-600 leading-relaxed mt-2">{body}</p>
            </section>
          ))}
        </div>
        <div className="flex gap-6 mt-8 text-sm">
          <Link to="/terminos" className="text-teal-600 hover:underline" data-testid="legal-link-terminos">Términos y Condiciones</Link>
          <Link to="/privacidad" className="text-teal-600 hover:underline" data-testid="legal-link-privacidad">Política de Privacidad</Link>
        </div>
      </main>
    </div>
  );
}
