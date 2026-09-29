#!/bin/bash
set -eu

install -D -o root -g root -m 0644 \
    /.temp_assets/fastfetch/config.jsonc /etc/fastfetch/config.jsonc
install -D -o root -g root -m 0644 \
    /.temp_assets/fastfetch/persisos.txt /usr/share/fastfetch/persisos.txt

if ! grep -Fq '# PersisOS Fastfetch' /etc/bash.bashrc; then
    cat >> /etc/bash.bashrc <<'EOF'

# PersisOS Fastfetch
if [[ $- == *i* && -t 1 && -z ${PERSISOS_FASTFETCH_SHOWN:-} ]] &&
   command -v fastfetch >/dev/null 2>&1; then
    export PERSISOS_FASTFETCH_SHOWN=1
    fastfetch --config /etc/fastfetch/config.jsonc || true
fi
EOF
fi
