---
status: accepted
phase: 08-review-cleanup
source: [08-06-PLAN.md]
started: 2026-06-15T08:42:17-03:00
updated: 2026-07-01
---

## Current Test

[User accepted closure 2026-07-01 WITHOUT running the live UAT — explicit risk acceptance
("não quero testar, modo yolo"). All logic + destructive safety are proven headless
(order/dirty-refusal/no-force/D-10 against real git; 448 tests green). Items 1-5 remain to
confirm live whenever the app is used for real; reopen as gap closure if any fails.
Same precedent as Phase 9 hardware UAT (PO risk acceptance, 09-HUMAN-UAT.md).]

## Tests

### 1. Read-only diff (REVIEW-01)
expected: Botão direito numa task → "Ver diff ▸ <repo>" → abre um pane com `git diff` colorido, READ-ONLY (não dá pra digitar nele). Por repo.
result: passed headless para o mecanismo (live pendente) — leaf VTE com `set_input_enabled(False)` + `git --no-pager diff cwd=worktree`. Ao vivo: confirmar cor + read-only no display.

### 2. PR + branch status (GIT-01/REVIEW-02)
expected: A subline da task mostra branch (ahead/behind) + status do PR; "Atualizar status" força releitura; leituras throttled (cache TTL git 30s/gh 120s), sem poll. gh ausente/não-autenticado → mostra "gh ausente"/"gh não autenticado", não quebra.
result: passed headless para parse/degrade/throttle (live pendente) — confirmar a subline real num repo com PR aberto e o degrade com `gh auth logout`.

### 3. Abrir PR (REVIEW-02, a ÚNICA escrita permitida)
expected: "Abrir PR" → `gh pr create --web` abre o navegador no fluxo de criar PR; depois força releitura do status.
result: [pending — live] — argv `gh pr create --web` wired (nunca executado em teste). Confirmar que abre o navegador.

### 4. [O GATE] Concluir task — teardown seguro (REVIEW-03, criterion 4)
expected: Botão direito → "Concluir task" → diálogo destrutivo (avisa: remove as worktrees, MANTÉM branch + repos fonte). Ao confirmar numa task LIMPA: mata os agentes → desce containers (se isolada) → remove as worktrees (sem --force) → prune → limpa os symlinks da pasta da task → some da sidebar. Os repos FONTE e as branches sobrevivem.
result: passed headless para a lógica (live REQUIRED) — `tests/test_window_conclude.py` (ordem + recusa) + `tests/test_review_cleanup_smoke.py` (git real: limpa remove, source/branch sobrevivem). Ao vivo: concluir uma task real e confirmar no disco.

### 5. [O GATE] Concluir RECUSA árvore suja (criterion 4 — a segurança)
expected: Numa task com mudanças NÃO commitadas em qualquer repo → "Concluir" BLOQUEIA (diálogo lista os repos sujos), NADA é removido, nenhuma worktree some. Nunca usa --force.
result: passed headless (live pendente) — provado em git real (remove sem --force falha em árvore suja) + no state machine (zero remove argv quando sujo). Ao vivo: sujar um repo, tentar concluir, confirmar o bloqueio.

## Summary

total: 5
passed: 0
issues: 0
pending: 0
skipped: 5 (risk-accepted by user 2026-07-01 — yolo closure; confirm opportunistically in real use)
blocked: 0

(Note: toda a lógica + a segurança destrutiva estão provadas headless [order/dirty-refusal/no-force/D-10 contra git real]; falta só a confirmação visual no display + gh/PR reais. git 2.43 + gh 2.93 autenticado estão no host.)

## Gaps
