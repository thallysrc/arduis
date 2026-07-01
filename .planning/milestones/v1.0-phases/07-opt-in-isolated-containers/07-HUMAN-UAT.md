---
status: partial
phase: 07-opt-in-isolated-containers
source: [07-05-PLAN.md]
started: 2026-06-14T11:01:23-03:00
updated: 2026-06-14T11:01:23-03:00
---

## Current Test

[awaiting human testing on a real docker host]

## Tests

### 1. Criterion 1 — auto-detect compose + opt-in per task (default OFF)
expected: Num projeto cujo root tem `docker-compose.yml`, o menu da task (botão direito) mostra "Isolar containers"; sem compose, não aparece. Default é OFF (nenhum container sobe sozinho).
result: passed headless para a detecção/argv (confirmação ao vivo pendente) — wiring presente (`_docker_available`/`_compose_path`/`win.toggle_isolation`). Ao vivo: confirmar o item de menu aparece só quando há compose.

### 2. Criterion 2 — stack própria, COMPOSE_PROJECT_NAME persistido, override `!override` da main
expected: Ligar isolamento → sobe stack própria (`arduis-<branch>`), gera `docker-compose.override.yml` na pasta da task reescrevendo TODA a lista de `ports` (tag `!override`), base lida da main.
result: passed headless para a geração (LIVE REQUIRED para a stack real) — smoke `tests/test_compose_smoke.py` provou em disco: override contém `ports: !override` + porta com offset (`9080:80`) e NÃO a base (`8080:80`); COMPOSE_PROJECT_NAME persistido (round-trip). Ao vivo: confirmar `docker compose ps` mostra a stack isolada.

### 3. Criterion 3 — portas probed livres (offset + retry) + badges na UI
expected: Portas do host são testadas livres antes do `up` (offset determinístico + retry em colisão); as portas resolvidas aparecem como badges (`db :5433`) no topbar/task.
result: passed headless para a lógica (LIVE para os badges) — smoke provou bump do task inteiro em colisão + cap (`PortAssignmentError`). Ao vivo: provocar uma colisão de porta real e ver o badge com a porta resolvida.

### 4. Criterion 4 — teardown ao remover + reconcile de órfãos no startup
expected: Desligar/hibernar/concluir uma task → `docker compose down --remove-orphans --volumes`; relançar após um crash → o arduis detecta stacks `arduis-*` órfãs e oferece limpeza (conservador, sem `down -v` automático).
result: passed headless para os argv + canal de teardown separado do killpg (LIVE para o efeito real) — `_container_down` (hibernate async + app-exit síncrono) e `_reconcile_orphans` presentes. Ao vivo: hibernar uma task isolada e confirmar `docker ps` sem os containers dela; matar o app e relançar para ver o reconcile.

### 5. Criterion 5 — tudo via HostRunner; snap-docker Ubuntu + native Arch
expected: Toda chamada `docker compose` passa pelo HostRunner async; funciona no snap-docker (Ubuntu) e docker nativo (Arch). Arquivos compose sob `$HOME` (snap não lê fora do $HOME).
result: passed headless para o caminho (LIVE para o ambiente real) — argv list-form via `docker_service.run_compose_async`; D-09 ($HOME) respeitado nos smokes. Ao vivo: confirmar `up`/`down` reais no host (docker 29.3.1 presente).

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

(Note: toda a lógica testável headless — override `!override` em disco, todos os argv, probe+cap, state round-trip — está provada por `tests/test_compose_smoke.py` (8/8). O que falta é SÓ confirmável num host docker real: a stack subir isolada, os badges com portas resolvidas, o teardown/reconcile efetivos. Docker 29.3.1 está no host, então dá pra testar de verdade.)

## Gaps
