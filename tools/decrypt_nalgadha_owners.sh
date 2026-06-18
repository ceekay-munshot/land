#!/usr/bin/env bash
# Decrypt the Nalgadha owner-names file locally (needs the NALGADHA_KEY you set as a repo secret).
#
#   tools/decrypt_nalgadha_owners.sh 'YOUR_NALGADHA_KEY'
#
# Output: nalgadha_owners.json (PLAINTEXT — it's gitignored; keep it off any public place).
set -euo pipefail
KEY="${1:?Pass your NALGADHA_KEY as the first argument}"
IN="${2:-web/data/nalgadha_owners.json.enc}"
OUT="${3:-nalgadha_owners.json}"
openssl enc -d -aes-256-cbc -pbkdf2 -in "$IN" -out "$OUT" -pass pass:"$KEY"
echo "decrypted -> $OUT"
python3 -c "import json;print(len(json.load(open('$OUT'))),'gatas with owner names')" 2>/dev/null || true
