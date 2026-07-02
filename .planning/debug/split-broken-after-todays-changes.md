---
status: awaiting_human_verify
trigger: "split de terminal quebrou hoje: pane original renderiza à esquerda, resto preto, 2 handles de paned visíveis colados no meio-direita"
created: 2026-07-02T15:40:00
updated: 2026-07-02T16:45:00
---

## Current Focus

hypothesis: Regressão exposta por restore-on-boot (2e1aaf7): árvore Gtk.Paned aninhada construída de uma vez (boot restore OU split) assenta numa extensão TRANSIENTE; GTK4 coalesce o notify::max-position final; o tick de 1145132 PARA no 1o frame com maxp>1 (extensão transiente) -> posição degenerada -> black hole que só cura no resize (assinatura documentada). NÃO é causado pelo tick em si (reactive-only reproduz idêntico) — o tick é insuficiente, não a causa.
test: Fix = tick re-aplica até max-position ESTÁVEL por N frames (não parar no 1o maxp>1) + sanitização defensiva de ratio degenerado no load.
expecting: 3-leaf continua limpo (sem regressão) em broadway + suite verde.
next_action: Aplicar fix em _init_paned_position + layout_store.tree_from_dict; rodar suite.

## Symptoms

expected: Split cria dois panes visíveis, cada um com terminal renderizando.
actual: Após split só o pane original renderiza (esquerda ~1/3); resto preto; 2 handles de paned colados no meio-direita.
errors: Não coletados ainda.
reproduction: Determinístico ao fazer split agora. Funcionava antes de hoje.
started: Hoje. Suspeitos: commit 1145132 (tick callback em _init_paned_position, _learned_ratio guard) + hunks uncommitted "quick 260702-kzo" (empty state em _reflect_layout, _split_active_pane, _close_terminal, _make_empty_state).

## Eliminated

- hypothesis: Ratio envenenado persistido em layouts.json
  evidence: ~/.config/arduis/layouts.json tem apenas ratios 0.5 (limpos). Nenhum ratio degenerado persistido.
  timestamp: 2026-07-02T15:45:00
- hypothesis: Uncommitted empty-state hunks (260702-kzo) quebram o rebuild de árvore com panes reais
  evidence: Diff mostra que a branch empty-state só dispara quando model.root is None; o caminho normal de split (root != None, focused visível) é IDÊNTICO ao anterior: model.split(...) -> _reflect_layout() -> _build_widget(model.root). Uncommitted não altera split path.
  timestamp: 2026-07-02T15:50:00

## Evidence

- timestamp: 2026-07-02T15:50:00
  checked: git show 1145132 -- src/arduis/window.py (diff completo do commit suspeito)
  found: A ÚNICA mudança funcional no caminho de renderização de split é (1) o novo add_tick_callback(_tick) em _init_paned_position que chama _apply() a cada frame até o 1o maxp>1 e então se remove; (2) _learned_ratio guard (só afeta drag-learning). O _apply reativo (notify::max-position) é logicamente idêntico à versão que funcionava.
  implication: O tick é candidato, mas precisa ser testado empiricamente.

- timestamp: 2026-07-02T16:00:00
  checked: Repro headless real (gtk4-broadwayd :7) do app arduis real, monkeypatch de _init_paned_position em 3 variantes (current/tick, reactive_only pre-1145132, width_based) — probe da geometria dos Gtk.Paned.
  found: TODAS as 3 variantes produzem o MESMO paned degenerado (PANED#3 w=289 mas max-position=538). reactive_only (pré-1145132) reproduz IDÊNTICO ao current.
  implication: 1145132 / o tick NÃO é a causa (nem a cura). ELIMINADO como causa raiz.

- timestamp: 2026-07-02T16:05:00
  checked: git log --since hoje; ancestralidade de 1145132.
  found: TODO o stack de persistência de layout aterrissou HOJE 13:15-13:22 (4e0f0a7..2e1aaf7): serialização recursiva, save/load layouts.json, learn/apply ratios, e RESTORE-ON-BOOT (2e1aaf7). 1145132 (15:00) veio depois como tentativa de fix do black-hole.
  implication: Antes de hoje o boot abria 1 pane (sem paned). Hoje o boot RESTAURA uma árvore aninhada — é isso que expõe deterministicamente a fragilidade de posição de paned aninhado. "Funcionava antes de hoje" = não havia restore de árvore aninhada no boot.

- timestamp: 2026-07-02T16:15:00
  checked: Probe do modelo runtime + variação de tamanho de janela; _MIN_PANE_W=240 por leaf; monitor broadway limitado a 1024x768 (canvas ~672px).
  found: Árvore 3-leaf que CABE (720px) renderiza LIMPA (BAD_COUNT=0) em todas as variantes. Só a árvore 5-leaf (precisa ~1200px, não cabe em 672px) degenera — PANED#3 fica com max-position=538 num paned de 289px = inconsistência de measure/allocate do GTK por OVERFLOW dos filhos (cada filho pede ~287px, paned só tem 289px). Nenhuma lógica de posição corrige overflow físico.
  implication: broadway (máx 1024px) NÃO reproduz o bug do usuário (janela grande, árvore que cabe). O degradado 5-leaf é artefato de overflow do broadway pequeno, não o cenário do usuário. Reprodução headless fiel do timing do compositor real é inviável aqui.

## Resolution

root_cause: |
  Regressão exposta pela feature restore-on-boot (2e1aaf7, hoje). O boot passou a
  RECONSTRUIR uma árvore Gtk.Paned ANINHADA de uma só vez (antes o boot abria 1 pane
  sem paned). Paneds aninhados construídos de uma vez passam por extensões TRANSIENTES
  durante a alocação multi-pass; o GTK4 coalesce o notify::max-position final, então o
  paned pode assentar na extensão real SEM re-notify. O tick de _init_paned_position
  (1145132) PARA no PRIMEIRO frame com max-position>1 — que para uma árvore recém-construída
  no boot é frequentemente uma extensão transiente — aplica posição = transiente*ratio,
  marca settled e se auto-remove; a extensão real chega sem notify e o caminho reativo
  nunca re-aplica -> split degenerado (um filho ~0 = black hole) que "só cura no resize"
  (a assinatura documentada nos debugs anteriores split-black-pane-hole e
  paned-collapse-3-terminals). O tick NÃO é a causa (reactive-only reproduz idêntico);
  o tick era insuficiente para o timing de boot-restore.
  NOTA de honestidade: broadway (máx 1024px) não reproduz o cenário de janela grande do
  usuário; a causa raiz é inferida da assinatura documentada + do que mudou hoje + do código.
  A correção é estritamente mais robusta que o tick atual e não pode regredir o caso que
  funciona (verificado: 3-leaf permanece limpo).
fix: |
  1. src/arduis/window.py _init_paned_position: o tick re-aplica a posição proporcional a
     cada frame até que max-position esteja ESTÁVEL (dentro de tolerância) por N frames
     consecutivos — em vez de parar no PRIMEIRO max-position>1. Isso garante que a aplicação
     final aterrisse na alocação assentada, independentemente do coalescing do notify,
     matando a classe "só cura no resize" tanto no split quanto no boot-restore. Caminho
     reativo mantido para resizes; budget de segurança mantido; drag-learning intacto.
  2. src/arduis/layout_store.py tree_from_dict: sanitização defensiva — ratio degenerado
     persistido (<=0.02 ou >=0.98) é normalizado para 0.5 no load, para que um layouts.json
     envenenado nunca produza um black hole resistente a resize.
verification: |
  - Suite completa: 549 passed (era 547 + 2 novos testes de sanitização). Zero falhas.
  - test_paned_ratio_guard.py continua verde (drag-learning intacto).
  - Broadway no-regression: árvore 3-leaf que cabe continua LIMPA com o fix (BAD_COUNT=0,
    ambos paneds proporcionais).
  - PENDENTE: verificação humana no compositor real (janela grande) — broadway não
    reproduz o timing real, então a cura do black-hole de boot-restore precisa ser
    confirmada pelo usuário fazendo boot com layout multi-pane salvo + split ao vivo.
files_changed: [src/arduis/window.py, src/arduis/layout_store.py, tests/test_layout_store.py]
