---
task: 260702-kzo
title: Empty state com botão centrado quando o workspace fica sem panes
type: quick
status: complete
committed: false
files_modified:
  - src/arduis/window.py
  - tests/test_window_empty_state.py
requirements: [QUICK-260702-KZO]
---

# Quick 260702-kzo: Empty state recuperável no canvas — Summary

Canvas de workspace sem panes agora renderiza um `Adw.StatusPage` centrado com botão
"+ Novo terminal" (nasce focado) em vez de um `Gtk.Box` preto sem saída. O botão/Enter e
o keybinding de split (`C-Space =`/`-`) recuperam o canvas vazio rootando um leaf novo pelo
MESMO fluxo do split (`_split_active_pane` → `_spawn_into(kind="agent")` → agente claude no
workspace atual). Fechar o último pane permanece no workspace mostrando o empty state.

## O que mudou

Quatro edições cirúrgicas em `src/arduis/window.py` (todas com comentário `quick 260702-kzo`
para localização) + um novo arquivo de teste GTK-free.

### 1. `_split_active_pane` — rootável em canvas vazio
- Assinatura: `focused_tid: str` → `focused_tid: str | None`.
- Docstring estendida (bloco "Empty-state recovery").
- Nova branch antes do spawn: se `model.root is None or focused_tid is None or not
  model.is_visible(focused_tid)` → roota o leaf novo (`model.root = LeafNode(new_tid)`,
  `focused_id`, `touch`) — mesmo padrão degenerado de `_open_diff_leaf`; senão `model.split(...)`.
- Todo o resto (TerminalRecord "agent" + `_spawn_into(kind="agent")` + `_schedule_layout_save`)
  fica intacto — é o que garante "mesmo fluxo do split".
- Bônus sem mudança de código: `C-Space =`/`-` passa `model.focused_id` (None num model
  vazio) → cai na mesma recuperação por teclado.

### 2. `_make_empty_state()` — novo método (antes de `_build_widget`)
- `Adw.StatusPage` (`utilities-terminal-symbolic`, "Nenhum terminal aberto") com
  `Adw.ButtonContent` ("+ Novo terminal", `suggested-action`/`pill`, centrado).
- `clicked` → `self._split_active_pane(None, "h")`.
- `GLib.idle_add(btn.grab_focus)` — app keyboard-driven (Enter/Space ativa direto).
- Sem API nova além do floor: `Adw.StatusPage`/`Adw.ButtonContent` existem desde libadwaita 1.0;
  nenhuma API VTE nova (floor 0.76 preservado).

### 3. `_reflect_layout` — escolhe empty state vs placeholder neutro
- `model is None` (bootstrap sem projeto) → `_build_widget(None)` (Gtk.Box neutro, como antes).
- `model.root is None` (workspace ativo sem panes) → `_make_empty_state()` — nunca canvas preto.

### 4. `_close_terminal` — permanece no workspace no último pane
- Docstring atualizada (Failure 2 agora é o empty state, não o swap para main).
- Bloco `if not model.visible_ids():` — trocado `self._swap_workspace(_MAIN_SID)` por
  `self._reflect_layout(); self._schedule_layout_save(); return` (o reflect mostra o empty state).

### 5. `tests/test_window_empty_state.py` — novo (regressão GTK-free, 4 testes)
Padrão bare-window (`ArduisWindow.__new__`) com helpers de GTK/spawn monkeypatchados:
- `test_split_none_on_empty_model_roots_leaf_and_spawns_agent`
- `test_split_on_nonempty_model_uses_split_path`
- `test_close_last_pane_stays_in_workspace`
- `test_reflect_layout_picks_empty_state_vs_placeholder`

Nota de implementação: `_leaf_by_sid`/`_term_by_sid` são `@property` read-only (views do bundle
de mapas por projeto), então o teste NÃO os atribui — mutação/leitura direta do dict vazio lazy.

## Resultado dos testes

```
pytest tests/test_window_empty_state.py tests/test_layout.py \
       tests/test_window_conclude.py tests/test_workspace_layout.py
→ 27 passed (4 novos verdes; layout/close/workspace sem regressão)
```
Venv: `/tmp/arduis-venv-kzo` (`python3 -m venv --system-site-packages` + `pip install pytest`),
rodado com `PYTHONPATH=src`. Sanidade de import: `python3 -c "import arduis.window"` OK.

## Commit desta task (o usuário commita separado — NADA foi commitado)

**CRÍTICO:** o working tree tem ~1000 linhas uncommitted de OUTRA task em andamento
(attention/prompt-scanner/hook). Esta quick task NÃO foi commitada de propósito, pois
`src/arduis/window.py` está entrelaçado com aquela task. Nenhum hunk de attention/scan foi
tocado (cada Edit casou uma região única; todos os meus hunks carregam o comentário
`quick 260702-kzo`).

Hunks/arquivos que pertencem a ESTA task (commitar isolado da task de attention):

- `src/arduis/window.py` — SOMENTE as 4 regiões marcadas `quick 260702-kzo`:
  - `_split_active_pane` (assinatura + docstring + branch root-if-empty)
  - `_make_empty_state` (método novo, antes de `_build_widget`)
  - `_reflect_layout` (branches model-None vs root-None)
  - `_close_terminal` (docstring + bloco "empty workspace" permanece no workspace)
- `tests/test_window_empty_state.py` — arquivo novo inteiro.

Como o `window.py` mistura os dois trabalhos, o commit isolado exige `git add -p`
selecionando apenas os hunks `260702-kzo` (o `tests/test_window_empty_state.py` pode ir
inteiro com `git add`).

Sugestão de mensagem:
`feat(window): recoverable empty state (Adw.StatusPage + '+ Novo terminal') on empty workspace canvas`

## Smoke manual pendente (não bloqueante)

```
gtk4-broadwayd :5 &
GDK_BACKEND=broadway BROADWAY_DISPLAY=:5 ./run.sh
# fechar todos os panes de um workspace → StatusPage centrado aparece
# Enter/click no botão → pane novo com claude no workspace atual
```

## Self-Check: PASSED
- `src/arduis/window.py` contém `_make_empty_state` — FOUND (import + `hasattr` OK).
- `tests/test_window_empty_state.py` — FOUND (4 testes verdes).
- Suite alvo (empty_state/layout/conclude/workspace_layout) — 27 passed, 0 regressão.
- Nenhum commit feito (working tree deixado dirty por design).
