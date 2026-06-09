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

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- [x] **Terminal real embutido (VTE) rodando o shell do host** — janela GTK4/libadwaita com um terminal VTE rodando `zsh -l -i` do host via PTY nativo direto (sem `flatpak-spawn`), atrás do seam no-op `HostRunner`; paleta Dracula owned pelo app, Ctrl+C/Ctrl+Z+`fg`, decode de exit-status, teardown sem órfãos e copy/paste (Ctrl+Shift+C/V). *Validado na Fase 1: Terminal (2026-06-09, aceite manual #1–#4/#6 + 15 testes).* A parte "agente rodando" da linha Active correspondente chega na Fase 2.
- [x] **Core loop**: "Nova worktree" → cria worktree + agente (`claude`) rodando num terminal real, em segundos — botão `+New worktree` num `Adw.TabView`, diálogo type-or-pick de branch, `git worktree add` async (off the GTK loop) na dir irmã a partir da default branch auto-detectada, terminal VTE com `claude` alimentado como bytes; branch já em uso foca a aba/aborta sem `--force`; `+` desabilita fora de repo git; hibernar mata o grupo de processos e mantém a dir, resume relança. Nasce a camada de domínio GTK-free (`worktree.py`, `SessionStore`) + o seam `swarm/`. *Validado na Fase 2: Core Loop (2026-06-09, aceite manual SC#2/#3/#4 + D-03 + 25 testes; WT-01/02/03, RAM-01).*

### Active

<!-- Hipóteses até serem entregues e validadas. -->
- [ ] N agentes em **paralelo**, cada um na sua git worktree
- [ ] Terminais reais embutidos via **VTE**, rodando o shell/agente **do host** (zsh, claude, git)
- [ ] **Agente = comando configurável**; default `claude`; `Ctrl+C` cai no shell e troca de agente
- [ ] Detecção de status **"te espera"** (destaque visual quando um agente para aguardando input)
- [ ] **Sidebar de worktrees** com status por worktree (rodando / aguardando / ocioso / pronto)
- [ ] **Containers isolados opt-in** por worktree (compose-base da `main`; `COMPOSE_PROJECT_NAME` único; `docker-compose.override.yml` com offset de porta auto; teardown ao remover)
- [ ] **`.arduis.toml` por repo** (comandos de `setup`, agentes, config de containers, base/location da worktree)
- [ ] **Gestão de RAM**: hibernar worktree (mata agente + para containers, mantém diretório); limite configurável de agentes/containers ativos; visibilidade de RAM por worktree na UI; suspender ociosos; teardown garantido
- [ ] **Keybindings estilo tmux** configuráveis; tema **Dracula** default (temas trocáveis)
- [ ] Ler info de **git/gh** (branch, status de PR) — somente leitura
- [ ] **Review + cleanup**: ver diff / abrir PR via `gh`; concluir worktree remove worktree + containers
- [ ] **Instalável**: pacotes **nativos** — `.deb` (Ubuntu) + **AUR** (Arch), usando o VTE do sistema; Flatpak fora do v1

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
| App desktop GTK4 + VTE (caminho A) vs. orquestrar kitty (caminho B) | Visual rico (sidebar com status, badges) + app instalável de verdade; kitty não embute como widget no Wayland | — Pending |
| Python (PyGObject) vs. Vala/Rust | Protótipo rápido, mínimo de deps, manutenção solo; RAM não é gargalo da GUI | — Pending |
| VTE do sistema (Ubuntu 0.76 / Arch 0.84), sem compilar | Disponível nos repos oficiais dos dois; bundle só era necessário por causa do Flatpak | ✓ 2026-06-08 |
| **Nativo (`.deb` Ubuntu + AUR Arch); Flatpak fora do v1; Snap não** | Flatpak forçaria sandbox → todo o risco do `flatpak-spawn --host`. Ubuntu 24.04 já tem GTK4-VTE 0.76 no `main` e Arch tem `vte4` 0.84 → nativo usa o VTE do sistema sem bundle e o PTY roda **direto** (igual BridgeMind). Snap confina demais | ✓ 2026-06-08 |
| Containers isolados **opt-in**, compose-base da `main`, porta auto | Isolar projeto grande por worktree sem custo de RAM por padrão; ambiente baseado no trunk | — Pending |
| Agente = comando configurável (Ctrl+C troca) | Flexibilidade (claude/codex/aider/shell) sem integração profunda | — Pending |
| MVP = paralelismo simples; swarm = Fase 2 opcional | Evolução constante e visível (Accelerate); swarm monolítico mataria o momentum | — Pending |
| Gestão de RAM como requisito de 1ª classe | Custo real vem de agentes (Node) + containers isolados, não do app | — Pending |

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
*Last updated: 2026-06-09 — Phase 3 (Parallel Worktrees + Sidebar + RAM Groundwork) complete: sidebar bound to SessionStore + nested GtkPaned canvas (no tabs), GTK-free LayoutModel, C-Space tmux prefix, ~2s /proc RAM poll + footer, active-agent cap on +New. UAT: main shell now opens in the launch repo root (D-07 revised) + repo name in sidebar + empty-repo guard. NEXT-PHASE IDEA captured: "worktree = workspace of up to 2 terminals" (sidebar switches workspaces) — a redesign of the current shared-canvas / focus-or-swap model, to be designed via discuss→plan. (Phase 2: "+New worktree" → worktree + `claude` in seconds. Phase 1: embedded VTE host-shell terminal behind the no-op HostRunner seam.)*
