#!/usr/bin/env bash
# 用 sslip.io 为 VPS 公网 IP 申请临时 HTTPS 证书（Let's Encrypt 正规证书）
# 用法: sudo ./setup-ssl-ip.sh
#       sudo ./setup-ssl-ip.sh 123.45.67.89
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_PORT="${APP_PORT:-8000}"

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 运行: sudo ./setup-ssl-ip.sh"
  exit 1
fi

PUBLIC_IP="${1:-}"
if [ -z "$PUBLIC_IP" ]; then
  echo "正在获取公网 IP..."
  PUBLIC_IP="$(curl -sS --max-time 10 ifconfig.me || curl -sS --max-time 10 icanhazip.com || true)"
fi
if [ -z "$PUBLIC_IP" ]; then
  echo "无法自动获取 IP，请手动指定: sudo ./setup-ssl-ip.sh 你的公网IP"
  exit 1
fi

SSL_HOST="${PUBLIC_IP//./-}.sslip.io"

echo "========================================"
echo "  临时 HTTPS（sslip.io）"
echo "========================================"
echo "  公网 IP:     $PUBLIC_IP"
echo "  临时域名:    $SSL_HOST"
echo "  后端端口:    $APP_PORT"
echo "========================================"

echo "[1/5] 检查 DNS..."
RESOLVED="$(dig +short "$SSL_HOST" @8.8.8.8 | tail -1)"
if [ "$RESOLVED" != "$PUBLIC_IP" ]; then
  echo "警告: $SSL_HOST 当前解析为 [$RESOLVED]，期望 [$PUBLIC_IP]"
  echo "      若 sslip.io 不可用，可改用 nip.io: ${PUBLIC_IP}.nip.io"
else
  echo "      DNS 正常: $SSL_HOST -> $PUBLIC_IP"
fi

echo "[2/5] 安装 nginx / certbot..."
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx dnsutils curl

echo "[3/5] 配置 Nginx..."
cat > /etc/nginx/sites-available/gadinan << EOF
server {
    listen 80;
    server_name ${SSL_HOST};

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        client_max_body_size 20M;
    }
}
EOF

ln -sf /etc/nginx/sites-available/gadinan /etc/nginx/sites-enabled/gadinan
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl reload nginx

echo "[4/5] 申请 Let's Encrypt 证书..."
certbot --nginx -d "$SSL_HOST" --non-interactive --agree-tos --register-unsafely-without-email --redirect

echo "[5/5] 完成"
echo ""
echo "  手机访问: https://${SSL_HOST}"
echo "  确保阿里云安全组已放行 80、443"
echo ""
echo "  域名 gardinan.xyz 生效后，再执行:"
echo "  certbot --nginx -d gardinan.xyz -d www.gardinan.xyz"
echo "  并修改 /etc/nginx/sites-available/gadinan 的 server_name"
echo "========================================"
