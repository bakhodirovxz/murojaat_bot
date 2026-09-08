#!/usr/bin/env bash
# Serverda botni o'rnatish. Bir marta ishga tushiriladi:
#     bash install.sh
set -e
cd "$(dirname "$0")"

echo "==> Virtual muhit yaratilmoqda (.venv)"
python3 -m venv .venv || {
    echo "python3-venv o'rnatilmagan bo'lishi mumkin. Buni bajaring:"
    echo "    sudo apt install -y python3-venv"
    exit 1
}

echo "==> Kutubxonalar o'rnatilmoqda"
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
    cp .env.example .env
    echo "==> .env yaratildi — uni to'ldiring: nano .env"
else
    echo "==> .env allaqachon bor, tegilmadi"
fi

mkdir -p files matrix_store

echo
echo "Tayyor. Endi:"
echo "    nano .env                            # sozlamalarni to'ldiring"
echo "    .venv/bin/python check_server.py     # umumiy tekshiruv"
echo "    .venv/bin/python check_mysql.py      # MySQL tekshiruvi (DB_TYPE=mysql bo'lsa)"
echo "    .venv/bin/python bot.py              # qo'lda ishga tushirish"
