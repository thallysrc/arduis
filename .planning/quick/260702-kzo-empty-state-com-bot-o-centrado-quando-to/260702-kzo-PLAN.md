---
phase: quick-260702-kzo
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/arduis/window.py
  - tests/test_window_empty_state.py
autonomous: true
requirements: [QUICK-260702-KZO]

must_haves:
  truths:
    - "Fechar o último pane de um workspace mostra um empty state centrado (Adw.StatusPage) com botão '+ Novo terminal' — nunca uma área preta sem saída"
    - "Clicar no botão (ou apertar Enter — ele nasce focado) cria um pane novo rodando o agente padrão (claude) no workspace ATUAL, pelo mesmo fluxo do split"
    - "O keybinding de split (C-Space = / -) também recupera um canvas vazio (roota um leaf novo em vez de no-op)"
    - "Mudanças uncommitted não relacionadas (attention/scanner/hook) permanecem intactas no working tree"
  artifacts:
    - path: "src/arduis/window.py"
      provides: "_make_empty_state(), branch root-if-empty em _split_active_pane, branch empty-state em _reflect_layout, _close_terminal permanece no workspace"
      contains: "Adw.StatusPage"
    - path: "tests/test_window_empty_state.py"
      provides: "Regressão GTK-free: root-if-empty, close-last-pane fica no workspace, _reflect_layout escolhe o empty state"
      min_lines: 40
  key_links:
    - from: "botão '+ Novo terminal' (clicked)"
      to: "_split_active_pane(None, ...)"
      via: "callback do botão"
      pattern: "_split_active_pane\\(None"
    - from: "_split_active_pane (model vazio)"
      to: "_spawn_into(..., kind=\"agent\")"
      via: "mesmo fluxo do split (make_terminal → make_leaf → root → reflect → TerminalRecord → spawn)"
      pattern: "kind=\"agent\""
    - from: "_reflect_layout (model.root is None)"
      to: "_make_empty_state"
      via: "set_child no _canvas_slot"
      pattern: "_make_empty_state"
---

<objective>
Empty state recuperável no canvas do workspace: quando o layout do workspace ativo fica
sem panes (todos fechados, ou restore vazio), a área central hoje vira um `Gtk.Box`
vazio/preto sem caminho de volta (referência: workspace "caramelo" inteiro preto).
Substituir esse placeholder por um `Adw.StatusPage` centrado com botão "+ Novo terminal"
que cria um pane novo rodando o agente padrão (claude) no workspace atual — reutilizando
EXATAMENTE o fluxo que o split usa (`_split_active_pane` → `_spawn_into(kind="agent")`).

Purpose: nunca deixar o usuário sem caminho de recuperação no canvas (app keyboard-driven).
Output: `_make_empty_state()` + `_split_active_pane` rootável + `_close_terminal` que
permanece no workspace + teste de regressão GTK-free.

**GIT / WORKING TREE (CRÍTICO):** o working tree tem ~1000 linhas de mudanças uncommitted
de OUTRA task em andamento (attention/prompt-scanner/hook): `src/arduis/attention.py`,
`src/arduis/hooks/arduis_hook.py`, `data/meson.build`, `tests/test_attention.py`,
`tests/test_hook_script.py`, `tests/test_prompt_scan.py`, `tests/test_window_sidebar_selection.py`,
`data/icons/...` E hunks dentro do próprio `src/arduis/window.py` (`_dialog_on_screen`,
`_setup_attention`, `_apply_state_file`, regiões de prompt-scan). NÃO tocar, NÃO reverter,
NÃO reformatar esses hunks. Edite window.py só nas regiões desta task.
**NÃO COMMITAR ao final** — window.py está entrelaçado com a task em andamento e um commit
misturaria os dois trabalhos. Deixe o working tree dirty e liste no summary exatamente
quais hunks/arquivos pertencem a esta quick task para o usuário commitar.
</objective>

<context>
@src/arduis/window.py (6004 linhas — ler só as regiões citadas nas tasks)
@src/arduis/layout.py (LayoutModel/LeafNode/SplitNode — não precisa mudar)
@tests/test_window_conclude.py (padrão bare-window `ArduisWindow.__new__` + monkeypatch)

<interfaces>
Pontos exatos do código (verificados no working tree atual):

- `_split_active_pane(self, focused_tid: str, orientation: str = "h")` — window.py ~linha 4286.
  Fluxo: resolve sid/model → cwd/label (workspace vs main) → `_next_term_id(sid)` →
  `_make_terminal()` + connect("child-exited", `_on_worktree_term_exited`) →
  `_make_leaf(new_tid, label, terminal, badge_label="claude")` → registra em
  `_leaf_by_sid`/`_term_by_sid` → `model.split(focused_tid, new_tid, orientation)` →
  `_reflect_layout()` → `workspace.terminals.append(TerminalRecord(new_tid, "agent"))` +
  `_spawn_into(terminal, cwd, workspace, new_tid, kind="agent")` (ou spawn sem record no
  main) → `_schedule_layout_save()`.

- Precedente do "root se vazio" já existe em `_open_diff_leaf` (~linha 4391):
  `model.root = LeafNode(diff_tid); model.focused_id = diff_tid; model.touch(diff_tid)`.
  `LeafNode` já está importado em window.py.

- `_reflect_layout` (~linha 5296): quando `model is None or model.root is None` faz
  `self._canvas_slot.set_child(self._build_widget(None))` → `Gtk.Box` vazio (o "preto").
  `_active_layout()` (~linha 735) retorna None sem projeto (bootstrap).

- `_close_terminal` (~linha 1918): quando `not model.visible_ids()` faz
  `self._swap_workspace(_MAIN_SID)` — se o main também estiver vazio, canvas preto sem saída.
  `_MAIN_SID = "main"` (linha 119).

- Keymap split (~linha 3000): `self._split_active_pane(model.focused_id, action[1])` —
  com model vazio `focused_id` é None; hoje `model.split` no-opa silenciosamente.

- LayoutModel (layout.py): `split()`, `close_leaf()`, `visible_ids()`, `touch()`,
  `focused_id`; `LeafNode(session_id)`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Empty state (Adw.StatusPage) + _split_active_pane rootável em canvas vazio</name>
  <files>src/arduis/window.py</files>
  <behavior>
    - `_split_active_pane(None)` (ou tid ausente do model) com model vazio ROOTA um leaf
      novo em vez de no-opar: model.root = LeafNode(new_tid), focused_id = new_tid,
      touch(new_tid); resto do fluxo idêntico (TerminalRecord + _spawn_into kind="agent").
    - `_reflect_layout` com model existente mas root None mostra o empty state; sem
      workspace ativo (bootstrap, model None) mantém o Gtk.Box neutro atual.
    - `_close_terminal` do ÚLTIMO pane permanece no workspace atual (empty state é a
      recuperação) — não faz mais `_swap_workspace(_MAIN_SID)`.
  </behavior>
  <action>
    Quatro edições cirúrgicas em src/arduis/window.py (não tocar hunks de attention/scan):

    1. `_split_active_pane`: mudar assinatura para `focused_tid: str | None` e trocar a
       linha `model.split(focused_tid, new_tid, orientation)` por:
       ```python
       if model.root is None or focused_tid is None or not model.is_visible(focused_tid):
           # Canvas vazio (todos os panes fechados): roota o leaf novo — mesmo
           # padrão degenerado de _open_diff_leaf. Recuperação do empty state.
           model.root = LeafNode(new_tid)
           model.focused_id = new_tid
           model.touch(new_tid)
       else:
           model.split(focused_tid, new_tid, orientation)
       ```
       Todo o resto do método fica intacto (é ele que garante "mesmo fluxo do split":
       _make_terminal → _make_leaf → maps → _reflect_layout → TerminalRecord/agent →
       _spawn_into → _schedule_layout_save). Atualizar a docstring (1-2 linhas).
       Bônus automático: o keybinding C-Space =/- (linha ~3000 passa model.focused_id,
       que é None num model vazio) vira caminho de recuperação por teclado sem mudança lá.

    2. Novo método `_make_empty_state(self) -> Gtk.Widget` (perto de _build_widget):
       ```python
       def _make_empty_state(self) -> Gtk.Widget:
           """Canvas vazio recuperável: StatusPage centrado com '+ Novo terminal'."""
           btn = Gtk.Button()
           content = Adw.ButtonContent(
               icon_name="list-add-symbolic", label="Novo terminal"
           )
           btn.set_child(content)
           btn.add_css_class("suggested-action")
           btn.add_css_class("pill")
           btn.set_halign(Gtk.Align.CENTER)
           btn.connect("clicked", lambda *_: self._split_active_pane(None, "h"))
           page = Adw.StatusPage(
               icon_name="utilities-terminal-symbolic",
               title="Nenhum terminal aberto",
               description="Crie um pane novo com o agente padrão (claude) neste workspace",
           )
           page.set_child(btn)
           # App keyboard-driven: Enter/Space ativa direto (idle: precisa estar mapeado).
           GLib.idle_add(btn.grab_focus)
           return page
       ```
       Adw.StatusPage e Adw.ButtonContent existem desde libadwaita 1.0 — dentro do floor.
       Nenhuma API VTE nova (floor 0.76 preservado).

    3. `_reflect_layout` (~linha 5314): trocar o branch vazio por:
       ```python
       model = self._active_layout()
       if model is None:
           self._canvas_slot.set_child(self._build_widget(None))
           return
       if model.root is None:
           # Workspace sem panes: empty state recuperável (nunca canvas preto).
           self._canvas_slot.set_child(self._make_empty_state())
           return
       ```
       (model None = bootstrap sem projeto → placeholder neutro continua; model existente
       vazio = workspace real → empty state.)

    4. `_close_terminal` (~linha 1970): trocar o bloco
       `if not model.visible_ids(): self._swap_workspace(_MAIN_SID); ...` por permanecer
       no workspace: `self._reflect_layout(); self._schedule_layout_save(); return`
       (o _reflect_layout agora mostra o empty state — o comentário "Failure 2" deve ser
       atualizado: o empty state É a nova garantia de canvas nunca-em-branco).

    Sanidade rápida sem display: `python3 -c "import arduis.window"` (import é module-level
    safe, ver docstring de test_window_conclude.py) rodando do toplevel com PYTHONPATH=src.
  </action>
  <verify>
    <automated>cd /home/thallysrc/Projects/arduis && PYTHONPATH=src python3 -c "import arduis.window as W; assert hasattr(W.ArduisWindow, '_make_empty_state')"</automated>
  </verify>
  <done>window.py importa; _make_empty_state existe; _split_active_pane aceita None e roota; _close_terminal do último pane não troca mais para o main; hunks de attention/scan intocados (git diff confere).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Regressão GTK-free (bare-window) para os 3 comportamentos novos</name>
  <files>tests/test_window_empty_state.py</files>
  <behavior>
    - Test 1: `_split_active_pane(None)` num model vazio roota LeafNode(new_tid),
      focused_id == new_tid, workspace.terminals ganha TerminalRecord kind "agent",
      `_spawn_into` chamado com kind="agent".
    - Test 2: `_split_active_pane(tid_focado)` num model COM leaf continua usando
      model.split (2 leaves visíveis depois) — regressão do caminho normal.
    - Test 3: `_close_terminal` do último pane NÃO chama `_swap_workspace`; chama
      `_reflect_layout` e `_schedule_layout_save`; model.visible_ids() == [].
    - Test 4: `_reflect_layout` com model existente e root None faz
      `_canvas_slot.set_child(<sentinela de _make_empty_state>)`; com model None usa
      `_build_widget(None)` (placeholder neutro).
  </behavior>
  <action>
    Criar tests/test_window_empty_state.py seguindo o padrão bare-window de
    tests/test_window_conclude.py: `win = W.ArduisWindow.__new__(W.ArduisWindow)` (sem
    __init__/GTK) + monkeypatch dos helpers que tocam GTK/spawn:
    `_make_terminal`/`_make_leaf` → sentinelas `object()`; `_spawn_into`,
    `_reflect_layout`, `_schedule_layout_save`, `_swap_workspace`, `_teardown_pgid`,
    `_refresh_main_row_attention` → gravadores em lista `calls`; `_next_term_id` →
    lambda determinística. Atribuir direto `win._leaf_by_sid = {}`, `win._term_by_sid = {}`,
    `win._main_split_info = {}`, `win._dialog_on_screen = set()`,
    `win._active_workspace_sid = "feat"` e um layout via `LayoutModel` real de
    arduis.layout (monkeypatch `_workspace_layout`/`_active_layout` para devolvê-lo).
    Para o store: stub com `.get(sid)` devolvendo um `Workspace` real de arduis.session
    (como test_window_conclude faz). Para o Test 4, stub `win._canvas_slot` com
    `set_child`/`get_child` gravadores e monkeypatch `_make_empty_state`/`_build_widget`
    para sentinelas.

    Rodar: criar venv `python3 -m venv --system-site-packages /tmp/arduis-venv-kzo &&
    /tmp/arduis-venv-kzo/bin/pip install -q pytest` (pytest não está no site-packages do
    sistema; --system-site-packages é obrigatório para o gi importar). Se testes de
    OUTROS arquivos dirty (attention/prompt_scan) falharem, IGNORAR — pertencem à task em
    andamento; não consertar nem tocar.

    NÃO commitar nada ao final (ver objective). No summary, listar os hunks desta task:
    src/arduis/window.py (_split_active_pane / _make_empty_state / _reflect_layout /
    _close_terminal) + tests/test_window_empty_state.py.
  </action>
  <verify>
    <automated>cd /home/thallysrc/Projects/arduis && /tmp/arduis-venv-kzo/bin/pytest tests/test_window_empty_state.py tests/test_layout.py tests/test_window_conclude.py tests/test_workspace_layout.py -x -q</automated>
  </verify>
  <done>4 testes novos verdes; test_layout/test_window_conclude/test_workspace_layout continuam verdes (sem regressão nos caminhos de split/close existentes); nada commitado.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| nenhum novo | O botão dispara o MESMO caminho de spawn já existente (`_split_active_pane` → `_spawn_into`, argv em lista via HostRunner). Nenhum input do usuário entra em argv/shell; nenhum arquivo/rede novo. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-kzo-01 | E (Elevation) | spawn via botão do empty state | accept | Reusa fluxo de spawn existente sem parâmetros novos controláveis pelo usuário; argv construído internamente como lista. |
</threat_model>

<verification>
- `pytest tests/test_window_empty_state.py tests/test_layout.py tests/test_window_conclude.py tests/test_workspace_layout.py -x` verde no venv /tmp.
- `git diff src/arduis/window.py` mostra APENAS as 4 regiões desta task além dos hunks
  pré-existentes de attention/scan (que devem estar byte-idênticos ao estado inicial).
- Smoke manual opcional (não bloqueante): `gtk4-broadwayd :5 &` +
  `GDK_BACKEND=broadway BROADWAY_DISPLAY=:5 ./run.sh`, fechar todos os panes de um
  workspace → StatusPage centrado aparece → Enter/click cria pane com claude.
</verification>

<success_criteria>
- Canvas de workspace vazio renderiza Adw.StatusPage com botão "+ Novo terminal" focado
  (nunca Gtk.Box preto quando há workspace ativo).
- Botão/Enter e o keybinding de split criam um pane agente (claude) no workspace atual
  pelo fluxo existente de split (TerminalRecord "agent" + _spawn_into kind="agent" +
  _schedule_layout_save).
- Fechar o último pane permanece no workspace mostrando o empty state.
- Suite de layout/close existente sem regressão; mudanças uncommitted alheias intactas;
  NENHUM commit feito (entrega dirty documentada no summary).
</success_criteria>

<output>
Após completar, criar `.planning/quick/260702-kzo-empty-state-com-bot-o-centrado-quando-to/260702-kzo-SUMMARY.md`
listando: hunks/arquivos desta task (para o usuário commitar separado da task de
attention em andamento), resultado dos testes, e o smoke manual pendente.
</output>
