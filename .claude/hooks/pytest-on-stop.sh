#!/usr/bin/env bash
# Stop hook (Claude Code): garante que a suite pytest está verde antes de o
# turno terminar, sempre que arquivos .py de src/ ou tests/ mudaram desde a
# última execução verde. Bloqueia o stop com o output do pytest em caso de
# falha, para o modelo corrigir antes de encerrar.
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 0

INPUT=$(cat 2>/dev/null || true)
STOP_ACTIVE=$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)

GREEN_STAMP="$ROOT/.claude/.pytest-green.stamp"
RED_STAMP="$ROOT/.claude/.pytest-red.stamp"

# Hash do conteúdo de todos os .py em src/ e tests/ (ordem estável).
HASH=$( (find src tests -name '*.py' -type f -print0 2>/dev/null | sort -z | xargs -0 sha256sum 2>/dev/null) | sha256sum | cut -d' ' -f1)

# Nada mudou desde a última suite verde → sai silencioso e barato.
if [ -f "$GREEN_STAMP" ] && [ "$(cat "$GREEN_STAMP")" = "$HASH" ]; then
  exit 0
fi

# Anti-loop: se já bloqueamos com exatamente este código e o modelo parou de
# novo sem mudar nada, não bloqueia de novo — só avisa o usuário.
if [ "$STOP_ACTIVE" = "true" ] && [ -f "$RED_STAMP" ] && [ "$(cat "$RED_STAMP")" = "$HASH" ]; then
  jq -n '{systemMessage: "⚠ pytest continua falhando e o código não mudou — hook liberou o stop para evitar loop. Rode a suite manualmente."}'
  exit 0
fi

PYTEST=""
for cand in "$ROOT/.venv/bin/pytest" /tmp/arduis-venv/bin/pytest; do
  if [ -x "$cand" ]; then PYTEST="$cand"; break; fi
done
if [ -z "$PYTEST" ]; then
  jq -n '{systemMessage: "⚠ hook de testes: pytest não encontrado (.venv/bin/pytest ou /tmp/arduis-venv) — a suite NÃO rodou neste stop."}'
  exit 0
fi

OUT=$("$PYTEST" 2>&1)
STATUS=$?

if [ $STATUS -eq 0 ]; then
  printf '%s' "$HASH" > "$GREEN_STAMP"
  rm -f "$RED_STAMP"
  SUMMARY=$(printf '%s' "$OUT" | tail -1)
  jq -n --arg s "✓ suite pytest verde (hook pós-mudança): $SUMMARY" '{systemMessage: $s}'
  exit 0
fi

printf '%s' "$HASH" > "$RED_STAMP"
TAIL=$(printf '%s' "$OUT" | tail -40)
jq -n --arg r "A suite pytest FALHOU após mudanças em src/ ou tests/. Corrija os testes antes de encerrar o turno. Últimas linhas do output:

$TAIL" '{decision: "block", reason: $r}'
exit 0
