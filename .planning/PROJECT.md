# arduis

## What This Is

arduis é um app desktop GNOME **lightweight** (Linux: Ubuntu + Arch) que orquestra
**vários agentes de IA (Claude Code) em paralelo** — cada um na sua **git worktree**, com
**terminais reais embutidos (VTE)**. É a resposta Linux e terminal-cêntrica ao
BridgeMind/BridgeSpace (que só existe no Mac). Para devs que vivem no terminal/tmux e usam
agentes de IA intensamente; usável solo e **instalável facilmente por um time** (Flatpak).

## Core Value

Tirar a ideia "quero começar uma branch nova" e ter um **agente de IA rodando numa worktree
isolada em segundos** — gerenciando N agentes em paralelo e **sempre sabendo qual deles te
espera**.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Hipóteses até serem entregues e validadas. -->

- [ ] **Core loop**: "Nova worktree" → cria worktree + monta ambiente + agente rodando num terminal real, em segundos
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
- [ ] **Instalável**: **Flatpak** principal (`flatpak install` para outros devs), **AUR + .deb** nativos

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
- **VTE não vem no runtime do GNOME nem no apt do Ubuntu 24.04** → é **compilado dentro do
  app** via flatpak-builder: VTE 0.84.0 (+ deps `fast_float` v8.2.8 e `simdutf` v7.7.1).
- **Inspiração:** BridgeMind/BridgeSpace (Mac). Mockups visuais **APROVADOS** em
  `docs/mockup/` — v1 (Dracula, grade 2×2) e v2 estilo BridgeSpace (charcoal + accent,
  command-blocks tipo Warp, room tabs Command/Swarm/Review, rail de agentes, mini-kanban).
- **Contexto rico prévio:** `docs/MOTIVATION.md` (documento-base) e `docs/ROADMAP.md`
  (roadmap em degraus + esquema do `.arduis.toml` + trilha de swarm).
- **Rascunho NÃO-commitado do Degrau 1** existe (`io.github.thallys.Arduis.yml`,
  `src/main.py`, `data/*`, `dev.sh`) — tratar como rascunho a validar, não como verdade.
- **Usuário:** tmux-cêntrico, keyboard-driven, heavy Claude Code user; valoriza mínimo de
  dependências e manutenção solo. App-id placeholder: `io.github.thallys.Arduis`.

## Constraints

- **Plataforma**: Linux + GNOME, **Ubuntu E Arch** — regra inegociável
- **Tech stack**: Python + PyGObject + GTK4 + libadwaita + VTE (Vte-3.91); config TOML; shell-out para git/gh/docker compose
- **Distribuição**: Flatpak principal (instalação fácil pro time); AUR + .deb nativos; Snap não
- **UX**: centrado no terminal; respeita keybindings estilo tmux
- **Performance/Memória**: lightweight, com **gestão de RAM de primeira classe**
- **Método**: Accelerate/DORA — degraus pequenos, instaláveis e usáveis; trunk-based; entrega contínua; `main` sempre funcionando; dogfooding cedo
- **Escopo**: credenciais/Jira fora; só leitura de git/gh

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| App desktop GTK4 + VTE (caminho A) vs. orquestrar kitty (caminho B) | Visual rico (sidebar com status, badges) + app instalável de verdade; kitty não embute como widget no Wayland | — Pending |
| Python (PyGObject) vs. Vala/Rust | Protótipo rápido, mínimo de deps, manutenção solo; RAM não é gargalo da GUI | — Pending |
| VTE compilado no app via flatpak-builder | VTE não vem no runtime GNOME nem no apt Ubuntu 24.04 | — Pending |
| Flatpak principal (+ AUR/.deb), Snap não | 1 build cobre Ubuntu+Arch; instalação fácil pro time; Snap confina demais p/ ferramenta que dirige docker/git | — Pending |
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
*Last updated: 2026-06-08 after initialization*
