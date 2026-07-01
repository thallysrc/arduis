# arduis

## What This Is

arduis é um app desktop GNOME **lightweight** (Linux: Ubuntu + Arch) que orquestra
**vários agentes de IA (Claude Code) em paralelo** — cada um na sua **git worktree**, com
**terminais reais embutidos (VTE)**. É a resposta Linux e terminal-cêntrica ao
BridgeMind/BridgeSpace (que só existe no Mac). Para devs que vivem no terminal/tmux e usam
agentes de IA intensamente; usável solo e **instalável facilmente por um time** (pacotes
nativos `.deb` + AUR).

## Core Value

Tirar a ideia "quero começar uma branch nova" e ter um **agente de IA rodando numa worktree
isolada em segundos** — gerenciando N agentes em paralelo e **sempre sabendo qual deles te
espera**.

## Current State

**v1.0 MVP shipped 2026-07-01** (tag `v1.0`). 13 fases (9 planejadas + 4 corretivas inseridas), 52 planos, 320 commits em 23 dias, ~14.2k LOC Python, **448 testes verdes**. Auditoria do milestone: PASSED (33/33 requisitos, 14/14 seams de integração, 7/7 fluxos E2E) com 4 aceitações de risco registradas (UAT visual das fases 03–08 e UAT de hardware da fase 9 — fechadas por decisão explícita do PO sem execução ao vivo; contrato de reabertura em `.planning/milestones/v1.0-MILESTONE-AUDIT.md`).

O app: topbar multi-projeto ("both alive"), task cross-repo = worktrees + symlinks espelhando a raiz, 2 terminais VTE por task (agente + shell) em layout livre, atenção hooks-first ("quem te espera"), temas trocáveis, `.arduis.toml` com trust gate, containers compose isolados opt-in, review read-only + conclude com clean-gate, empacotado como `.deb` (0 erros lintian) + PKGBUILD.

**Pendências v1.1:** publicar (AUR push + hospedar .deb + CI), confirmar oportunisticamente os itens risk-accepted em uso real.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- [x] **v1.0 — todos os 33 requisitos v1 entregues** (TERM, WT, PAR, PROJ, STATUS, AGENT, UI, LAYOUT, ENV, CONT, RAM, REVIEW, GIT, DIST-02/03/04) — arquivo completo com outcomes em `.planning/milestones/v1.0-REQUIREMENTS.md`. Itens de UAT ao vivo fechados por aceitação de risco (2026-06-15 hardware / 2026-07-01 visual).

- [x] **Terminal real embutido (VTE) rodando o shell do host** — janela GTK4/libadwaita com um terminal VTE rodando `zsh -l -i` do host via PTY nativo direto (sem `flatpak-spawn`), atrás do seam no-op `HostRunner`; paleta Dracula owned pelo app, Ctrl+C/Ctrl+Z+`fg`, decode de exit-status, teardown sem órfãos e copy/paste (Ctrl+Shift+C/V). *Validado na Fase 1: Terminal (2026-06-09, aceite manual #1–#4/#6 + 15 testes).* A parte "agente rodando" da linha Active correspondente chega na Fase 2.
- [x] **Core loop**: "Nova worktree" → cria worktree + agente (`claude`) rodando num terminal real, em segundos — botão `+New worktree` num `Adw.TabView`, diálogo type-or-pick de branch, `git worktree add` async (off the GTK loop) na dir irmã a partir da default branch auto-detectada, terminal VTE com `claude` alimentado como bytes; branch já em uso foca a aba/aborta sem `--force`; `+` desabilita fora de repo git; hibernar mata o grupo de processos e mantém a dir, resume relança. Nasce a camada de domínio GTK-free (`worktree.py`, `SessionStore`) + o seam `swarm/`. *Validado na Fase 2: Core Loop (2026-06-09, aceite manual SC#2/#3/#4 + D-03 + 25 testes; WT-01/02/03, RAM-01).*

- [x] **N agentes em paralelo, cada um na sua worktree, com worktree = workspace de terminais** — cada worktree possui seu próprio LayoutModel e nasce com 2 terminais (agente `claude` + shell); o canvas mostra UM worktree por vez e a sidebar troca o workspace inteiro (tmux: panes = terminais, windows = worktrees); C-Space h/j/k/l move entre terminais, n/p/número troca workspaces; RAM somada por worktree; hibernar mata todos os grupos de processos do worktree e resume relança o layout default; fechar a janela não deixa órfãos. *Validado na Fase 03.1: worktree-as-terminal-workspace (2026-06-10, UAT manual aprovado após 2 rodadas de fix + 55 testes; PAR-01/02/03, LAYOUT-01, RAM-02/03 re-targeted).*

### Active

<!-- Hipóteses até serem entregues e validadas. (v1.0 entregou tudo; candidatos v1.1 abaixo) -->
- [ ] **Publishing**: push do PKGBUILD pro AUR + hospedar o `.deb` (GitHub Releases / apt repo) + CI de build+lint por push
- [ ] Confirmação oportunista dos itens risk-accepted (UAT visual 03–08, hardware install 09) em uso real — reabrir como gap se falhar
- [ ] **DIST-01 (Flatpak)** — canal secundário v2, reativa o caminho `flatpak-spawn` do HostRunner
- [ ] **PERSIST-01** — reatar agentes vivos após reabrir o app (camada tmux/abduco)
- [ ] **STATUS-04** — fallback de scraping para agentes não-Claude

### Out of Scope

<!-- Limites explícitos, com razão, para não re-adicionar. -->

- Gestão de credenciais / Jira / criação de issues — feito na mão; git/`gh` só *leem* info
- Construir emulador de terminal do zero — embute-se o **VTE**
- Editor de código embutido — usa-se **neovim**
- **Swarm coordenado** (papéis Coordinator/Builder/Scout/Reviewer + mailbox + MCP) — Fase 2 OPCIONAL, não v1
- **Snap** como canal principal — confinamento atrapalha uma ferramenta que dirige docker/git/ssh
- macOS / Windows — apenas **Linux + GNOME**
- Trocar Python por Rust por causa de RAM — gargalo está nos agentes/containers, não na GUI

## Context

- **Ambiente:** Ubuntu 24.04 + Arch Linux, GNOME, Wayland. Instalados: flatpak 1.14.6,
  flatpak-builder 1.4.2, GNOME Platform/Sdk **50** (user), Python 3.12, `gh`, `tmux`,
  `nvim`, docker (snap), cargo/rust.
- **VTE pra GTK4 vem dos repos oficiais**: Ubuntu 24.04 tem `gir1.2-vte-3.91` **0.76** no
  `main` (verificado em 2026-06-08); Arch tem `vte4` **0.84** no `extra`. Pacotes nativos usam
  o VTE do sistema — **sem compilar/bundle**. Codar pro piso da API 0.76 cobre a Fase 1 e o
  OSC 133 da Fase 4.
- **Inspiração:** BridgeMind/BridgeSpace (Mac). Mockups visuais **APROVADOS** em
  `docs/mockup/` — v1 (Dracula, grade 2×2) e v2 estilo BridgeSpace (charcoal + accent,
  command-blocks tipo Warp, room tabs Command/Swarm/Review, rail de agentes, mini-kanban).
- **Contexto rico prévio:** `docs/MOTIVATION.md` (documento-base) e `docs/ROADMAP.md`
  (roadmap em degraus + esquema do `.arduis.toml` + trilha de swarm).
- **Rascunho NÃO-commitado do Degrau 1** existe (`src/main.py`, `data/*`). Com o pivô pra
  nativo, o manifesto Flatpak (`io.github.thallys.Arduis.yml`) e o `dev.sh` ficam **obsoletos**
  (precisam de um script de run/build nativo); o `main.py` serve de base, mas **perde o
  `flatpak-spawn`** — passa a spawnar o `zsh` direto.
- **Usuário:** tmux-cêntrico, keyboard-driven, heavy Claude Code user; valoriza mínimo de
  dependências e manutenção solo. App-id placeholder: `io.github.thallys.Arduis`.

## Constraints

- **Plataforma**: Linux + GNOME, **Ubuntu E Arch** — regra inegociável
- **Tech stack**: Python + PyGObject + GTK4 + libadwaita + VTE (Vte-3.91); config TOML; shell-out para git/gh/docker compose
- **Distribuição**: **nativa** — `.deb` (Ubuntu) + AUR (Arch), usando o VTE do sistema; Flatpak fora do v1; Snap não
- **UX**: centrado no terminal; respeita keybindings estilo tmux
- **Performance/Memória**: lightweight, com **gestão de RAM de primeira classe**
- **Método**: Accelerate/DORA — degraus pequenos, instaláveis e usáveis; trunk-based; entrega contínua; `main` sempre funcionando; dogfooding cedo
- **Escopo**: credenciais/Jira fora; só leitura de git/gh

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| App desktop GTK4 + VTE (caminho A) vs. orquestrar kitty (caminho B) | Visual rico (sidebar com status, badges) + app instalável de verdade; kitty não embute como widget no Wayland | ✓ Good — v1.0 shipped nesse caminho; VTE embutido provou sidebar/dots/badges |
| Python (PyGObject) vs. Vala/Rust | Protótipo rápido, mínimo de deps, manutenção solo; RAM não é gargalo da GUI | ✓ Good — 14k LOC, 448 testes, zero deps além do stack GNOME |
| VTE do sistema (Ubuntu 0.76 / Arch 0.84), sem compilar | Disponível nos repos oficiais dos dois; bundle só era necessário por causa do Flatpak | ✓ 2026-06-08 — piso 0.76 segurou as duas distros |
| **Nativo (`.deb` Ubuntu + AUR Arch); Flatpak fora do v1; Snap não** | Flatpak forçaria sandbox → todo o risco do `flatpak-spawn --host`. Ubuntu 24.04 já tem GTK4-VTE 0.76 no `main` e Arch tem `vte4` 0.84 → nativo usa o VTE do sistema sem bundle e o PTY roda **direto** (igual BridgeMind). Snap confina demais | ✓ 2026-06-08 — `.deb` builda com 0 erros lintian; PKGBUILD parseia; HostRunner no-op guardado por teste |
| Containers isolados **opt-in**, compose-base da `main`, porta auto | Isolar projeto grande por worktree sem custo de RAM por padrão; ambiente baseado no trunk | ✓ Good — v1.0 Fase 7; achado-chave: tag `ports: !override` (override puro concatena) |
| Agente = comando configurável (Ctrl+C troca) | Flexibilidade (claude/codex/aider/shell) sem integração profunda | ✓ Good — v1.0 Fase 5 (`[agent] command` + re-feed C-Space a) |
| MVP = paralelismo simples; swarm = Fase 2 opcional | Evolução constante e visível (Accelerate); swarm monolítico mataria o momentum | ✓ Good — v1 shipped sem swarm; seams (SessionStore GTK-free, AgentSpec) preservados |
| Gestão de RAM como requisito de 1ª classe | Custo real vem de agentes (Node) + containers isolados, não do app | ✓ Good — poll ~2s, caps, hibernate/auto-suspend, teardown garantido em todos os caminhos |
| Isolamento por TASK (set de worktrees cross-repo), não por worktree | Projeto real é multi-repo; compose na raiz; duplicação atômica do stack | ✓ Good — pivô 03.2, sustentou 03.4 e Fase 7 |
| Fechar UAT humano por aceitação de risco (hardware 09, visual 03–08) | PO preferiu ship a bloquear no gate manual; toda a lógica provada headless | — Revisit em uso real; contrato de reabertura no audit |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-01 after v1.0 milestone — **🚢 v1.0 MVP SHIPPED & ARCHIVED** (tag `v1.0`; audit PASSED 33/33; arquivos em `.planning/milestones/`). Histórico narrativo completo das fases preservado abaixo.*

<details>
<summary>Histórico de evolução por fase (v1.0)</summary>

*2026-06-15 — **🎉 MILESTONE v1 COMPLETE (13/13 fases).** Phase 9 (Packaging .deb + AUR) complete: arduis agora é instalável nativamente. Build system = **meson** (fonte única `project(version:'1.0.0')`): instala o pacote `arduis` em purelib via `python.install_sources(preserve_path)` (incl. `hooks/arduis_hook.py` como package-data pro `importlib.resources`), um launcher `bin/arduis` gerado SEM o sys.path-hack do dev, e os assets XDG (.desktop/.metainfo/ícone SVG). **`.deb`** (`debian/` via `dh --buildsystem=meson`, `Architecture: all`, deps exatas do CLAUDE.md, `debhelper-compat (= 13)`, `3.0 (native)`) **builda de verdade** — `arduis_1.0.0_all.deb`, lintian 0 erros (1 warning benigno no-manual-page). **AUR** (`PKGBUILD` `arch=('any')`, deps Arch exatas, `arch-meson`+`meson install --destdir`, SEM `.install` — pacman refresca caches; override do D-05 por RESEARCH). Ícone SVG gerado; metainfo ganhou homepage + `<release 1.0.0>` (antes falhava `appstreamcli validate`). HostRunner confirmado no-op nativo (sem flatpak-spawn vivo, SC-4). Verificação: **4/4 critérios**, automated gate 7/7 (suíte 436, .deb builda+linta, validações, PKGBUILD parseia); DIST-02/03/04 fechados. **UAT de hardware (instalar limpo em Ubuntu+Arch sob Wayland real) ACEITO PELO PO sem testar** (risco explícito, registrado em 09-HUMAN-UAT.md status:accepted). Entrega = definições que buildam local (publish AUR + hospedar .deb = manual/v1.1; Flatpak = v2). Anterior — Phase 03.4 (topbar = multi-PROJECT switcher, INSERTED corrective) complete: corrige o nível do topbar que o GSD errou DUAS vezes (03.2 D-06 nome-só, depois 03.3 chips-de-repo). Agora o topbar lista **vários PROJETOS** (cada um uma raiz multi-repo: Livon-Saude, KarveLabs), trocáveis e **"both alive"** (trocar de projeto NÃO mata os terminais/agentes/containers dos outros — pattern de unparent do `_reflect_layout` um nível acima, sem `Gtk.Stack`). "Abrir projeto" (`Gtk.FileDialog.select_folder`) registra a raiz e **lembra a lista** num `projects.json` (stdlib json, atômico temp+rename, em `$XDG_CONFIG_HOME/arduis/`; tomllib continua read-only). Os repos membros saíram do topbar e voltaram pro diálogo "Nova task" (D-12). Arquitetura: modelo GTK-free `Project` (root + member_repos + SessionStore próprio + bundle de mapas de widget por projeto) atrás de um `ProjectRegistry`, substituindo os singletons do `window.py`. 3 bugs concretos fechados: cap conta a UNIÃO entre projetos (D-09), `_on_close_request` itera `registry.all()` com o compose-name de CADA projeto (D-11, zero órfãos cross-projeto), e `project_term_id` (sha1 do root) namespaceia os 4 status-file sites pra branches homônimas não vazarem status (A3). **Gap G-1 achado no dogfooding e corrigido (`4a93988`):** abrir um repo único mostrava canvas vazio — `_switch_project` não semeava o shell scratch do projeto recém-aberto, e `_open_project`/`_init_projects` pulavam o fallback degenerado de repo-único; `_resolve_members()` + seed-on-switch resolveram. Verificação: 6/6 critérios, **427 testes**, UI-SPEC aprovado, security ASVS-L1 nos 5 planos; smokes headless lifecycle 9/9 + switch 5/5. UAT vivo aprovado pelo PO. **Roadmap: 12/13 fases completas — falta SÓ a Phase 9 (Packaging .deb+AUR), o gate de hardware.** Anterior — Phase 8 (review-cleanup) complete: fecha o loop de trabalho e o de recursos. Diff read-only (`review.py` GTK-free: `git --no-pager diff` num leaf VTE com `set_input_enabled(False)`, por repo via "Ver diff ▸"); status de branch+PR na subline via git/`gh` read-only + THROTTLED (`review_cache.py` TTL git 30s/gh 120s + debounce `_pr_busy`, sem poll); `gh.py` (argv + parse + degrade gracioso: gh ausente→"gh ausente", exit-4→"gh não autenticado"); "Abrir PR" = `gh pr create --web` (a ÚNICA escrita sancionada); `run_git_async` ganhou `cwd=` (D-07). **"Concluir task" — o teardown seguro (a segurança da fase):** ordem FIXA (mata agentes → desce containers → clean-gate `git status --porcelain` ALL-OR-NOTHING que RECUSA se qualquer repo está sujo → `git worktree remove` SEM `--force` → prune → unlink só dos symlinks com guarda `islink`, nunca `rmtree` → drop do store). D-10 intacto: remove só as worktrees da task, nunca os repos fonte, branches ou alvos de symlink. Verificação: 4/4 automatizados (406 testes), security 18/18 ameaças; `test_window_conclude.py` trava a ordem+recusa+no-force (stubbed) e `test_review_cleanup_smoke.py` prova contra git REAL (limpa remove e source/branch sobrevivem; suja recusa sem --force; alvo de symlink sobrevive). UAT vivo (5 itens) em 08-HUMAN-UAT.md. **Roadmap: 10/11 fases completas. Falta só a Phase 9 (Packaging .deb+AUR) — gate de hardware (instalação limpa em Ubuntu E Arch sob Wayland real) + depende do UAT vivo; é o ponto de parada do autopilot.** Anterior — Phase 7 (opt-in-isolated-containers) complete: stacks docker-compose isoladas POR TASK, opt-in (default OFF), docker no host via HostRunner async. Base = UM `docker-compose.yml` na raiz (espelhado na pasta da task pela 03.2); `compose.py` (GTK-free) lê os serviços via `docker compose config --format json`, gera o `docker-compose.override.yml` que REESCREVE a lista de portas via a tag **`ports: !override`** (achado live: override puro CONCATENA e re-binda a porta base — a tag substitui), com `COMPOSE_PROJECT_NAME=arduis-<branch>` único e offset de porta probed-livre (retry + cap). `containerstate.py` persiste projeto+portas+on/off em `<task_dir>/arduis.container.toml`; `docker_service.py` é o wrapper async (clone do run_git_async). No `window.py`: toggle no menu da task (só aparece se há compose), badges de porta no `pack_end` (chips da 03.3 no pack_start), teardown `down --remove-orphans --volumes` SEMPRE escopado ao `arduis-*` da task — canal SEPARADO do killpg dos agentes — em hibernate (async) + app-exit (síncrono c/ timeout), e reconcile conservador de órfãos `arduis-*` no startup (só sinaliza, nunca `down -v` automático). Verificação: 5/6 automatizados (344 testes), security 16/16 ameaças (ASVS L2); smoke `tests/test_compose_smoke.py` 8/8 provou em disco a tag `!override` + porta-offset + base-ausente, todos os argv, probe bump+cap, state round-trip. UAT vivo (5 critérios; precisa de host docker real — 29.3.1 presente) em 07-HUMAN-UAT.md. **Roadmap: 9/11 fases completas; faltam 8 (Review+Cleanup) e 9 (Packaging .deb+AUR).** Anterior — Phase 03.3 (topbar-repo-chips, INSERTED corretiva) complete: corrige a divergência que o PO apontou — o GSD (D-06 da 03.2) tinha achatado o topbar para só o nome do projeto, contra o mockup aprovado que mostra os repos como chips. Agora o topbar renderiza **um chip toggleável por repo membro** (bolinha de status reusando o CSS dos dots), o conjunto ligado **semeia a seleção de repos da "Nova task"** (override por task preservado), e a task ativa reflete nos chips; overflow `+N` acima de 6. **Fix obrigatório junto (D-04, supersede o Pitfall-1 da 03.2):** `detect_member_repos` passou a contar só subpastas com `.git` DIRETÓRIO — exclui worktrees vinculadas (`.git` arquivo); o Livon-Saude real resolve 2 repos, não 22. Topbar packado no pack_start, pack_end/título reservados para os badges de container da Fase 7. Verificação: 5/5 critérios automatizados (336 testes), security 8/8; smoke headless broadway 8/8 (incl. o gate "2 repos não 22" com fixture de 20 worktrees). UAT vivo (6 itens) em 03.3-HUMAN-UAT.md. **Fase 7 (containers) está com o domínio pronto (compose/state/docker_service, 07-01/02/03) e PAUSADA antes do 07-04** — retomando agora. Anterior — Phase 6 (per-worktree-setup-via-arduis-toml) complete: uma worktree nova nasce "pronta pra trabalhar". `repoconfig.py` (GTK-free, tolerante) lê o `.arduis.toml` POR REPO (`[setup] commands=[...]`; ausente/inválido = no-op estrito — funciona sem o arquivo) e `setup_feed_bytes` monta `cd '<worktree>' &&\n<cmds>` (single-quote no path, newline-join não `&&`-chain). Na CRIAÇÃO da task (nunca no resume), `_run_repo_setups` roda cada repo: alimenta os comandos no terminal SHELL (`t1`, nunca o agente `t0`) através do `zsh -l -i` durável (shims nvm/asdf/mise resolvem de graça). **Trust gate** (a peça de segurança — é RCE de comando commitado no repo): hash sha256 do CONTEÚDO dos comandos (`trust.py`), fail-closed, persistido atômico em `~/.config/arduis/trusted_setups.toml`; um `Adw.AlertDialog` consolidado mostra os comandos EXATOS antes de rodar ("Confiar e rodar"/"Pular"), repos já confiados rodam em silêncio, e um `.arduis.toml` alterado (hash novo) re-pergunta (modelo direnv-allow). Controle = consentimento informado + hash, não sandbox (risco aceito, documentado). Verificação: 9/9 automatizados (274 testes), security 14/14 ameaças; smoke headless broadway 7/7 provou no-op-ausente, untrusted-primeiro, trusted→feed-silencioso-no-t1 (agente nunca alimentado), setup-alterado-re-pergunta, trust list real intocada. UAT vivo (5 itens; o gate de segurança é o diálogo mostrar os comandos exatos antes de executar) pendente em 06-HUMAN-UAT.md. Anterior — Phase 5 (agent-swap-tmux-keybindings-themes) complete: o agente virou **comando configurável** (`[agent] command` no `~/.config/arduis/arduis.toml`, default `claude`, parseado com shlex) alimentado no zsh durável — Ctrl+C cai no shell e `C-Space a` re-injeta o agente sem respawn (segunda swarm seam fechada). O prefixo C-Space + os chords (split `-`/`=`, zoom `z`, foco `h/j/k/l`, prefixo) viraram **configuráveis** via `[keys]` sobre o keymap GTK-free, sem redesenhar a máquina capture-phase. **Temas trocáveis em runtime** (UI-02): registro GTK-free `themes.py` com 4 temas dark (Dracula default + Nord + Solarized Dark + Gruvbox Dark), cada um definindo a paleta VTE de 16 cores + fg/bg/cursor E as cores de UI; menu "Tema" no header troca em runtime (provider substituído-não-empilhado, todo VTE vivo re-colorido, terminais nascem no tema ativo) e persiste via writer atômico section-preserving (sem tomli-w). Critério 3 (atalhos app-scoped sob Wayland real) é verificação, não código novo — o controller capture-phase é propagação interna do app, não um grab do compositor. Verificação: 3/4 wiring verdes (240 testes), security 11/11 ameaças; smoke headless broadway 9/9 provou troca-de-tema (substitui provider, born-in-theme), feed configurado e dispatch de binding, `~/.config/arduis` real intocado. UAT vivo (5 itens; criterion-3 sob `$XDG_SESSION_TYPE=wayland` é o gate) pendente em 05-HUMAN-UAT.md. Anterior — Phase 4 (attention-detection-who-s-waiting) complete: the Core Value pillar ("qual agente te espera") shipped HOOKS-FIRST. arduis instala (com consentimento, merge aditivo que nunca destrói os hooks do usuário) um hook stdlib env-guarded do Claude Code que é no-op fora do arduis; ele escreve state files atômicos por terminal em `$XDG_RUNTIME_DIR/arduis/status`, observados por `Gio.FileMonitor` (só GLib loop). Máquina de 5 estados (running/waiting/ready/idle/ended) a partir de 7 eventos; `notification_type` distingue permission_prompt de idle_prompt (o `waiting` nunca é rebaixado por idade/idle — Pitfall 2). Dots de status na sidebar (agregado por task) e no header do pane (por terminal): laranja=waiting, verde=running, ciano=ready, cinza-esverdeado=idle. Notificação libnotify só em waiting+desfocado (replace-id por terminal). RAM-04: auto-suspend opt-in (`~/.config/arduis/arduis.toml` `[attention] auto_suspend_minutes`, default OFF) que cavalga a máquina de hibernate sem órfãos e retoma com `claude --continue`; running/waiting nunca são mortos em nenhuma idade. Modo degradado (consentimento recusado): bell + activity-timeout, sem auto-suspend. Decisão registrada: SessionStart→ready (CONTEXT dizia running) — flag [UAT-D03] para observação ao vivo. Verificação: 9/10 automatizados verdes (172 testes), security 24/24 ameaças fechadas; smoke headless 13/13 provou consent-safety (~/.claude real intocado), pipeline hook→arquivo→dot, cleanup e auto-suspend. UAT vivo (10 itens, criterion-3 "sem falso-laranja em redraw do TUI" é o gate) pendente em 04-HUMAN-UAT.md. Anterior — Phase 03.2 (projects-and-cross-repo-tasks) complete: level 1 pivoted from "topbar = repo" to **projeto = pasta raiz multi-repo** e **task = unidade de trabalho cross-repo**. Criar task escolhe 1+ repos, cria worktree branch-nomeada em cada e materializa uma pasta de task espelhando a raiz (worktrees com nomes dos repos + symlinks RELATIVOS do resto) — tooling do projeto roda verbatim dentro da task. Sidebar lista TASKS; hibernate/RAM/cap/teardown re-targeted para task. Scan de startup em `../<root>-tasks/` (disco = fonte de verdade, sem state file); "fechar repositório" mata só os grupos daquele repo (arduis nunca deleta do disco). **Decisões de UAT que substituíram o plano:** (a) workspace da task abre com UM par de 2 terminais (claude sobre zsh) na RAIZ da pasta da task — não uma coluna por repo (grade 2×6 inutilizável num projeto real de 6 repos); usuário adiciona terminais via splits; (b) clicar numa task hibernada NAVEGA para um card "Retomar task" explícito — navegar nunca spawna; resume passa pelo cap gate; (c) conflito de ref-namespace do git (branch `feat` vs `feat/...`) abortado com mensagem clara em pt-BR e task zumbi removida quando todos os repos falham. Verificação: 9/9 must-haves automatizados, 88 testes; UAT vivo parcial (4 itens pendentes em 03.2-HUMAN-UAT.md). Anterior — Phase 03.1 (worktree-as-terminal-workspace) complete: the canvas now shows ONE worktree's terminals at a time (workspace), cada worktree com LayoutModel próprio + 2 terminais default (agente + shell); sidebar troca o workspace inteiro; C-Space re-targeted (h/j/k/l = terminais, n/p/número = workspaces); RAM somada por worktree; hibernate/resume/close sem órfãos; menu "Layout" pré-pivô removido. UAT manual aprovado após 2 rodadas de fix (colapso de Gtk.Paned aninhado resolvido empiricamente via broadway headless). Anterior — Phase 3 (Parallel Worktrees + Sidebar + RAM Groundwork) complete: sidebar bound to SessionStore + nested GtkPaned canvas (no tabs), GTK-free LayoutModel, C-Space tmux prefix, ~2s /proc RAM poll + footer, active-agent cap on +New. UAT: main shell now opens in the launch repo root (D-07 revised) + repo name in sidebar + empty-repo guard. NEXT-PHASE IDEA captured: "worktree = workspace of up to 2 terminals" (sidebar switches workspaces) — a redesign of the current shared-canvas / focus-or-swap model, to be designed via discuss→plan. (Phase 2: "+New worktree" → worktree + `claude` in seconds. Phase 1: embedded VTE host-shell terminal behind the no-op HostRunner seam.)*

</details>
