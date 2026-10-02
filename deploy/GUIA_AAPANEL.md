# Guía: publicar IberoAcademy en tu servidor aaPanel (iberoacademy.cl)

Requisitos del servidor: Ubuntu/Debian con aaPanel, 2 GB RAM mínimo, acceso SSH como root.

## 0. Obtener el código
En Emergent: botón **Save → Save to GitHub**. Luego en el servidor:
```bash
cd /www/wwwroot
git clone https://github.com/TU_USUARIO/TU_REPO.git iberoacademy
cd iberoacademy
```

## 1. Preparar el servidor
```bash
timedatectl set-timezone America/Santiago
apt update && apt install -y python3.11 python3.11-venv curl git
```
En **aaPanel → App Store** instala: **Nginx**, **MongoDB** (7.x), **Node.js version manager** (Node 20) y **PM2 Manager**.
Luego: `npm install -g yarn`

## 2. Cuentas externas (claves)
- **Resend** (correos): crea cuenta en resend.com → *Domains* → agrega `iberoacademy.cl` → copia los registros DNS (TXT/MX) en **Cloudflare** con la nube en **gris (DNS only)** → espera "Verified". Luego *API Keys* → crea una clave (`re_...`).
- **OpenAI** (análisis IA de exámenes): platform.openai.com/api-keys → crea clave (`sk-proj-...`) y carga saldo.
- **Flow.cl**: las claves se ingresan después, dentro de la plataforma (menú *Sitio web*).

## 3. Backend (FastAPI)
```bash
cd /www/wwwroot/iberoacademy/backend
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
mkdir -p /www/wwwroot/iberoacademy/storage
cp ../deploy/backend.env.example .env
nano .env        # completa tus claves y secretos
chmod 600 .env
```
Para generar los secretos: `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` (uno para JWT_SECRET y otro para WEBHOOK_CRON_SECRET).

Probar que arranca:
```bash
venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001
# en otra terminal: curl http://127.0.0.1:8001/api/public/landing  → debe responder JSON
```
Dejarlo siempre encendido con PM2:
```bash
pm2 start "venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001 --workers 1" --name iberoacademy-api
pm2 save && pm2 startup
```
> Usa `--workers 1`. El puerto 8001 NO debe abrirse en el firewall.

## 4. Frontend (React)
```bash
cd /www/wwwroot/iberoacademy/frontend
echo "REACT_APP_BACKEND_URL=https://iberoacademy.cl" > .env.production
yarn install
yarn build
```
Se genera la carpeta `frontend/build`.

## 5. Sitio en aaPanel + Nginx
1. **aaPanel → Website → Add site**: dominio `iberoacademy.cl` y `www.iberoacademy.cl`, PHP: *Static*.
2. **Config** del sitio: pega el contenido de `deploy/nginx_iberoacademy.conf` (reemplaza el `root` y los `location /`). Guarda.

## 6. Cloudflare + SSL
1. En Cloudflare → DNS: registro **A** `@` → IP de tu servidor, y **A** `www` → misma IP (nube naranja ✔).
2. Cloudflare → SSL/TLS → **Full (strict)**.
3. Cloudflare → SSL/TLS → **Origin Server → Create Certificate** (15 años). Copia el certificado y la clave privada.
4. aaPanel → sitio → **SSL → Other certificate**: pega certificado y clave → Guardar → activa **Force HTTPS**.
5. Abre https://iberoacademy.cl → debe verse la página principal.

## 7. Tareas automáticas (Cron)
aaPanel → **Cron → Add task → Shell script**: crea 3 tareas con las líneas de `deploy/crontab.txt` (reemplaza `TU_SECRETO`).
Probar una a mano:
```bash
curl -X POST https://iberoacademy.cl/api/cron/class-reminders -H "Authorization: Bearer TU_SECRETO" -H "Content-Type: application/json" -d '{}'
```

> **Nuevo:** las claves de Resend, OpenAI, Flow y el secreto del Cron también se pueden configurar desde el panel admin → **Integraciones** (tienen prioridad sobre el .env). Para el primer ingreso sí necesitas Resend en el .env (o configúralo apenas entres), porque el código de acceso llega por correo.

## 8. Primer ingreso
1. Entra a https://iberoacademy.cl/login con el correo de `ADMIN_EMAIL` → te llegará el código por correo (Resend).
2. **Configuración**: sube las 3 firmas y revisa la plantilla del diploma.
3. **Integraciones**: revisa Resend (envía un correo de prueba), OpenAI (Probar conexión), ingresa tus claves de Flow (primero *sandbox*, luego *producción*) y copia las 3 líneas del Cron en aaPanel.
4. Crea tus cursos, márcalos como publicados y "mostrar en landing".

## 9. Respaldos (recomendado)
aaPanel → Cron → *Backup database* (MongoDB) diario, y respaldo de la carpeta `/www/wwwroot/iberoacademy/storage` (ahí quedan PPT, PDF, plantillas y diplomas).

## Actualizar a una nueva versión
```bash
cd /www/wwwroot/iberoacademy && git pull
cd backend && source venv/bin/activate && pip install -r requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ && pm2 restart iberoacademy-api
cd ../frontend && yarn install && yarn build
```

## Problemas comunes
- **502 Bad Gateway**: el backend no está corriendo → `pm2 logs iberoacademy-api`.
- **No llega el código de ingreso**: dominio no verificado en Resend o `MAIL_FROM` no es `@iberoacademy.cl`.
- **Error 1014/525 de Cloudflare**: revisa que el SSL sea *Full (strict)* y que el certificado de origen esté instalado en aaPanel.
- **No suben archivos grandes**: confirma `client_max_body_size 500m;` en Nginx.
- **Página en blanco al recargar una ruta**: falta `try_files $uri $uri/ /index.html;`.
