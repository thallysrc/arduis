# Restyle visual do arduis — estilo "parallel-code"

## Contexto

O usuário quer melhorar o visual do arduis. Desde 2026-06-18 a diretriz é usar
**parallel-code** (github.com/johannesjo/parallel-code) como referência visual/de layout —
copiar aparência e comportamento de botões **apenas para features que o arduis já tem**,
sem introduzir features novas (sem diff panel, notes, prompt bar, steps, stats novas, arena).

Decisões tomadas com o usuário nesta sessão:
1. **Adotar o visual do parallel-code** (não polir o mockup Dracula v1, não híbrido).
2. **Projetos migram do topbar para a sidebar** (seção PROJECTS, como no pc), desfazendo os chips da fase 3.4.

Tradução visual: paleta quase-preta sóbria, panes como **cards/"ilhas"** arredondados com
gap entre eles, sidebar seccionada (PROJECTS / + Nova task / TASKS / TIPS + stats),
headerbar minimalista, foco por cor de borda. O visual entra como **novo tema default
"Parallel Dark"** no sistema de temas existente; os 4 temas atuais continuam selecionáveis
(a estrutura — cards, gaps, seções — é independente de tema; só cores vêm do `Theme`).

## Arquivos críticos

- `src/arduis/window.py` — `_build_css` (:148), `_make_leaf` (:1252), `_build_sidebar` (:1476), `_build_project_tabs` (:2448), `_build_hint_bar` (:2100), `_build_widget`/Paned (:4442), montagem do `__init__` (:456-482), headerbar (:410-454)
- `src/arduis/themes.py` — dataclass `Theme` (:29), registry `THEMES` (:109), `get_theme` (:117)
- `src/arduis/appconfig.py` — `_DEFAULT_THEME` (:16)
- Testes a atualizar: `tests/smoke/test_project_switch_smoke.py`, `tests/smoke/test_project_lifecycle_smoke.py`, `tests/test_themes.py`, `tests/test_appconfig.py`, `tests/smoke/test_theme_switch_smoke.py`

## Design

### Tema (themes.py / appconfig.py)
- Adicionar ao dataclass `Theme` (frozen; defaults no final): `card: str | None = None`,
  `border: str | None = None`, `canvas: str | None = None`. Fallbacks resolvidos em
  `_build_css` (`card→surface`, `border→surface`, `canvas→bg`) — os 4 temas atuais não mudam.
- Novo tema `PARALLEL_DARK` (slug `"parallel-dark"`): bg/card `#16181d`, fg `#d8dce3`,
  surface `#111318`, border `#2a2d33`, canvas `#0d0f12`, accent `#4d9fff` (azul),
  branch `#e6e9ef` (neutro), dots verde/laranja/azul/cinza estilo GitHub-dark,
  palette ANSI 16 correspondente. O menu de temas itera `THEMES.items()` — aparece de graça.
- Flip do default por último: `get_theme` fallback → PARALLEL_DARK; `_DEFAULT_THEME = "parallel-dark"`.
  Migração implícita: quem gravou tema explicitamente via `write_theme` mantém a escolha.

### Cards ("ilhas") — CSS + _make_leaf
- `.arduis-leaf { background: {card}; border: 1px solid {border}; border-radius: 10px; }`;
  foco troca só a **cor** da borda (hoje adiciona borda → pulo de 1px; corrigir).
- `leaf.set_overflow(Gtk.Overflow.HIDDEN)` em `_make_leaf` para clipar o VTE nos cantos arredondados.
- Header do card transparente (card dá o fundo), padding `0 12px`, `border-bottom: 1px solid {border}`.
- Botões do header (⊟ ⊞ ✕, handlers existentes intocados): `opacity: 0.55`, hover `1`.
- Reordenar header: **dot · título · badge · spacer · ações** — o `pane_dot` já existe (:1280-1285), só muda de posição.

### Gaps entre cards — Gtk.Paned
- `paned.add_css_class("arduis-split")` em `_build_widget` (:4442);
  `.arduis-split > separator { background: transparent; min-width/height: 12px; border: none; }`
  — gap de 12px que continua arrastável (`set_wide_handle(True)` mantém a hit-area);
  `_init_paned_position` é ratio-based, não quebra.
- `_canvas_slot` (Gtk.Frame, :467): classe `.arduis-canvas { border: none; background: {canvas}; }`
  + margens de 12px. Manter o Frame (menos invasivo que trocar o widget).

### Sidebar seccionada (substitui chips do topbar + hint bar)
```
Gtk.Box vertical .arduis-sidebar (largura 248 → 264)
├── "PROJECTS" .arduis-section-title  + botão "+" flat (reusa _on_open_project_clicked)
├── _projects_box (ListBox em ScrolledWindow curto): dot + nome (set_text, guard T-03.4-07)
│   + ✕ inline (reusa _remove_project); ativo = 600 + fundo card; right-click = menu existente
├── "+ Nova task" .arduis-new-task-btn  ← mover self._new_btn do headerbar (mesmo atributo/handler)
├── "TASKS" .arduis-section-title
├── ScrolledWindow (vexpand) > _listbox existente  ← _rebuild_sidebar/_make_row intocados
└── footer: "TIPS" + labels de atalhos + _degraded_hint_btn + _footer_label
```
- **Manter o nome `_build_project_tabs`** (monkeypatchado por nome em `test_window_projects.py`);
  reescrever só o corpo para renderizar rows em `_projects_box`. Remover `_chip_bar` do
  headerbar (:425-430), overflow `+N` e `_MAX_VISIBLE_CHIPS` (lista vertical rola).
- Hint bar inferior é absorvida pela seção TIPS; remover `outer.append(self._build_hint_bar())` (:473).
- **Bug fixes de tema embutidos**: hints usam `_FOCUS_RING` hardcoded (:2109) e
  `_update_footer` usa `_DOT_ACTIVE` hardcoded (~:4380) → trocar por classes CSS
  theme-sourced (`.arduis-hint-key`, `.arduis-footer-count`).
- Headerbar final: título `Adw.WindowTitle` + menu de temas; CSS flat (`background: {surface}`).

### Classes CSS
- Manter (referenciadas por lógica/testes): `.arduis-dot-*`, `.arduis-row-*`, `.arduis-badge`,
  `.arduis-branch`, `.arduis-leaf`, `.arduis-pane-header`, `.arduis-hint-key`, `.arduis-footer-count`, `.arduis-sidebar`.
- Novas: `.arduis-split`, `.arduis-canvas`, `.arduis-section-title`, `.arduis-project-row`,
  `.arduis-new-task-btn`, `.arduis-sidebar-footer`.
- Remover: `.arduis-chip-bar`, `.arduis-chip`, `.arduis-chip-active`, `.arduis-tab-label-active`, `.arduis-hintbar`.

## Degraus de implementação (cada um instalável, commit próprio)

| # | Degrau | Risco | Quebra testes? |
|---|--------|-------|----------------|
| 1 | Campos `card/border/canvas` no Theme + fallbacks no `_build_css` (zero mudança visual) | Baixo | Não |
| 2 | Registrar PARALLEL_DARK (selecionável; default ainda Dracula) | Baixo | Só se houver pin de contagem de temas |
| 3 | Card restyle: radius+borda+overflow hidden, header transparente, botões dim, foco por cor, dot antes do título | Médio | Não |
| 4 | Gaps: separator transparente 12px + `.arduis-canvas` + margens | Médio | Não |
| 5 | Sidebar seccionada: títulos, ScrolledWindow no `_listbox`, `_new_btn` para a sidebar, largura 264 | Baixo-médio | Não |
| 6 | PROJECTS na sidebar: corpo novo de `_build_project_tabs`, ✕ inline, remover `_chip_bar`/overflow | Alto | Sim: `test_project_switch_smoke.py`, `test_project_lifecycle_smoke.py` (introspecção da chip bar → `_projects_box`) |
| 7 | TIPS+footer na sidebar; remover hint bar; fix cores hardcoded | Baixo | Não |
| 8 | Flip default → parallel-dark | Baixo | Sim: `test_themes.py:42-50`, `test_appconfig.py`, `test_theme_switch_smoke.py` |
| 9 | Polish: headerbar flat, tipografia, paddings finos | Baixo | Não |

Degraus 6 e 8 são os únicos com churn de testes — isolar em commits próprios.

## Verificação

- **Suíte**: pytest via venv em /tmp com `--system-site-packages` (padrão do projeto).
  `test_window_projects.py` monkeypatcha `_build_project_tabs`/`_rebuild_sidebar` por nome — nomes preservados.
- **Visual headless por degrau**: `gtk4-broadwayd :95 &` +
  `GDK_BACKEND=broadway BROADWAY_DISPLAY=:95 python -m arduis`, inspecionar no browser:
  cards/gaps (arrastar separators, split/zoom/fechar, foco), sidebar (trocar projeto,
  criar task, remover projeto), troca de temas (Parallel Dark ↔ Dracula).
- Comparar screenshot broadway com `scratchpad/pc-overview.png` (referência baixada).

## Processo

Execução deve rodar via GSD (CLAUDE.md): sugerido `/gsd-quick` por degrau ou inserir uma
fase decimal via `/gsd-insert-phase` para o restyle completo, mantendo commits atômicos por degrau.
