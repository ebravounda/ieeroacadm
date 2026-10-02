#!/usr/bin/env bash
# Instala/actualiza IberoAcademy en aaPanel (Nginx). Uso: sudo bash instalar.sh
set -e
APP=/www/wwwroot/iberoacademy
DOM=iberoacademy.cl
PORT=8001
NGX=/www/server/nginx/sbin/nginx
VHOST=/www/server/panel/vhost/nginx/$DOM.conf
CERT=/www/server/panel/vhost/cert/$DOM
ok(){ echo -e "\e[32m✔ $1\e[0m"; }
err(){ echo -e "\e[31m✘ $1\e[0m"; exit 1; }

[ "$(id -u)" = 0 ] || err "Ejecuta como root: sudo -i"
[ -d $APP/backend ] || err "No existe $APP (clona el repositorio primero)"
[ -x $NGX ] || err "No encuentro Nginx de aaPanel en $NGX (¿usas OpenLiteSpeed?)"

echo "== 1/6 MongoDB (Docker, puerto 27022)"
if docker ps -a --format '{{.Names}}' | grep -qx iberoacademy-mongo; then docker start iberoacademy-mongo >/dev/null
else docker run -d --name iberoacademy-mongo --restart unless-stopped -p 127.0.0.1:27022:27017 -v iberoacademy-mongo-data:/data/db mongo:7 >/dev/null; sleep 8; fi
ok "MongoDB listo"

echo "== 2/6 Backend"
cd $APP/backend
[ -d venv ] || python3 -m venv venv
[ -f requirements-server.txt ] || grep -viE "^(emergentintegrations|litellm|black|flake8|isort|mypy|mypy_extensions|pytest|pytest-xdist|pycodestyle|pyflakes|mccabe|pathspec|pytokens|librt|ast_serialize|execnet|iniconfig|pluggy)( |=|@)" requirements.txt > requirements-server.txt
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r requirements-server.txt
mkdir -p $APP/storage
if [ ! -f .env ]; then
cat > .env <<ENVF
MONGO_URL=mongodb://127.0.0.1:27022
DB_NAME=iberoacademy
CORS_ORIGINS=https://$DOM,https://www.$DOM
JWT_SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
WEBHOOK_CRON_SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))")
ADMIN_EMAIL=ed0.2580@gmail.com
EMAIL_FROM_NAME=IberoAcademy
RESEND_API_KEY=re_PEGA_TU_CLAVE
MAIL_FROM=no-reply@$DOM
LOCAL_STORAGE_DIR=$APP/storage
ENVF
fi
chmod 600 .env
pm2 delete iberoacademy-api >/dev/null 2>&1 || true
pm2 start $APP/backend/venv/bin/uvicorn --name iberoacademy-api --cwd $APP/backend --interpreter none -- server:app --host 127.0.0.1 --port $PORT --workers 1 >/dev/null
pm2 save >/dev/null
pm2 startup systemd -u root --hp /root >/dev/null 2>&1 || true
sleep 8
curl -sf http://127.0.0.1:$PORT/api/ >/dev/null || { pm2 logs iberoacademy-api --lines 30 --nostream; err "El backend no responde"; }
ok "Backend online en 127.0.0.1:$PORT"

echo "== 3/6 Frontend (3-5 min)"
cd $APP/frontend
echo "REACT_APP_BACKEND_URL=https://$DOM" > .env.production
yarn install --silent --network-timeout 600000
NODE_OPTIONS=--max-old-space-size=2048 yarn build >/tmp/ibero_build.log 2>&1 || { tail -30 /tmp/ibero_build.log; err "Falló la compilación"; }
[ -f build/index.html ] || err "No se generó build/index.html"
ok "Frontend compilado"

echo "== 4/6 Certificado SSL"
mkdir -p $CERT
if [ ! -s $CERT/fullchain.pem ] || [ ! -s $CERT/privkey.pem ]; then
  openssl req -x509 -nodes -newkey rsa:2048 -days 3650 -subj "/CN=$DOM" \
    -addext "subjectAltName=DNS:$DOM,DNS:www.$DOM" -keyout $CERT/privkey.pem -out $CERT/fullchain.pem 2>/dev/null
  ok "Certificado autofirmado creado (Cloudflare SSL debe estar en 'Full')"
else ok "Usando certificado existente"; fi

echo "== 5/6 Nginx"
[ -f $VHOST ] && cp $VHOST $VHOST.bak.$(date +%s)
cat > $VHOST <<NGINX
server {
    listen 80;
    listen 443 ssl;
    server_name $DOM www.$DOM;
    root $APP/frontend/build;
    index index.html;
    ssl_certificate $CERT/fullchain.pem;
    ssl_certificate_key $CERT/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 500m;

    location /api/ {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
    location / { try_files \$uri \$uri/ /index.html; }

    access_log /www/wwwlogs/$DOM.log;
    error_log /www/wwwlogs/$DOM.error.log;
}
NGINX
$NGX -t || err "Configuración de Nginx inválida (se guardó respaldo en $VHOST.bak.*)"
$NGX -s reload
ok "Sitio $DOM configurado"

echo "== 6/6 Tareas automáticas (cron)"
SECRET=$(grep ^WEBHOOK_CRON_SECRET= $APP/backend/.env | cut -d= -f2-)
H="-H 'Authorization: Bearer $SECRET' -H 'Content-Type: application/json' -d '{}'"
( crontab -l 2>/dev/null | grep -v "$DOM/api/cron" || true
  echo "*/15 * * * * curl -s -X POST https://$DOM/api/cron/class-reminders $H >/dev/null"
  echo "0 10 * * * curl -s -X POST https://$DOM/api/cron/inactivity-alerts $H >/dev/null"
  echo "0 8 * * 1 curl -s -X POST https://$DOM/api/cron/weekly-report $H >/dev/null" ) | crontab -
ok "Cron instalado"

echo; echo "== Verificación"
curl -sk https://127.0.0.1/api/ -H "Host: $DOM"; echo
curl -sk https://127.0.0.1/ -H "Host: $DOM" | grep -o "<title>[^<]*</title>" || true
grep -q "re_PEGA_TU_CLAVE" $APP/backend/.env && echo -e "\e[33m⚠ Falta tu clave de Resend: nano $APP/backend/.env y luego pm2 restart iberoacademy-api\e[0m"
echo; ok "Listo. En Cloudflare → SSL/TLS usa modo 'Full'. Abre https://$DOM"
