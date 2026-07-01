# Requirements: arduis

**Defined:** 2026-06-08
**Core Value:** Tirar a ideia "quero começar uma branch nova" e ter um agente de IA rodando numa worktree isolada em segundos — gerenciando N agentes em paralelo e sempre sabendo qual deles te espera.

## v1 Requirements

Requirements para o lançamento inicial (paralelismo simples). Cada um mapeia para fases do roadmap.

### Terminal (TERM)

- [x] **TERM-01**: Usuário tem um terminal VTE embutido rodando o shell do host (zsh) dentro do app

### Worktree / Core Loop (WT)

- [x] **WT-01**: Usuário cria uma worktree nova a partir de uma branch (nova ou existente) pela UI ("＋ Nova worktree")
- [x] **WT-02**: A worktree é criada via `git worktree add` no local/base configurados
- [x] **WT-03**: Um terminal abre no diretório da worktree nova com o agente padrão (`claude`) já rodando

### Paralelismo + Sidebar (PAR)

- [x] **PAR-01**: Usuário mantém várias worktrees abertas ao mesmo tempo, cada uma com seu terminal
- [x] **PAR-02**: Uma sidebar lista todas as worktrees; selecionar uma foca nela
- [x] **PAR-03**: Usuário troca entre worktrees pela UI e por atalhos estilo tmux

### Projetos (PROJ)

- [x] **PROJ-01**: Topbar lista múltiplos projetos multi-repo, alternáveis e persistidos entre execuções; trocar de projeto mantém os outros vivos ("both alive")

### Status / Atenção (STATUS)

- [x] **STATUS-01**: O app detecta "aguardando input" via hooks do Claude Code (`Notification`/`Stop` → state file)
- [x] **STATUS-02**: Indicador de status por worktree (rodando / aguardando / ocioso / pronto) na sidebar e no header do pane
- [x] **STATUS-03**: Notificação desktop (libnotify) + som opcional quando um agente entra em espera e a janela está fora de foco

### Agente (AGENT)

- [x] **AGENT-01**: Agente = comando configurável (default `claude`); `Ctrl+C` cai no shell para rodar outro agente

### UI — Aparência & Atalhos (UI)

- [x] **UI-01**: Keybindings configuráveis estilo tmux (`C-Space`, `C-h/j/k/l`, split `-`/`=`, zoom `z`)
- [x] **UI-02**: Temas de cor do app e dos terminais (paleta VTE + UI) — Dracula default, trocáveis

### Layout (LAYOUT)

- [x] **LAYOUT-01**: Layout livre de panes — dividir/arrastar como no tmux (em vez de grade fixa)

### Ambiente / Config (ENV)

- [x] **ENV-01**: `.arduis.toml` por repo é lido com defaults sensatos (funciona sem o arquivo)
- [x] **ENV-02**: Comandos de `setup` rodam na criação da worktree (via shell de login do host)

### Containers (CONT)

- [x] **CONT-01**: O app auto-detecta `docker-compose.yml`; integração de container é opcional
- [x] **CONT-02**: Containers isolados opt-in por worktree (`COMPOSE_PROJECT_NAME` único)
- [x] **CONT-03**: Compose-base vem da `main`; `docker-compose.override.yml` gerado com offset de porta auto-atribuído
- [x] **CONT-04**: As portas dos containers são exibidas em badges na UI
- [x] **CONT-05**: Teardown dos containers ao remover a worktree

### RAM / Recursos (RAM)

- [x] **RAM-01**: Usuário hiberna uma worktree (mata agente + para containers, mantém o diretório) e retoma depois
- [x] **RAM-02**: Limite configurável de agentes/containers ativos simultaneamente
- [x] **RAM-03**: Visibilidade de uso de RAM por worktree na UI
- [x] **RAM-04**: Suspender worktrees ociosas (ligado ao status idle)

### Review / Cleanup (REVIEW)

- [x] **REVIEW-01**: Usuário vê o diff (read-only) das mudanças de uma worktree
- [x] **REVIEW-02**: Usuário abre PR via `gh` (shell-out); o app lê o status do PR
- [x] **REVIEW-03**: "Concluir worktree" → remove a worktree (+ teardown de containers)

### Git Info (GIT)

- [x] **GIT-01**: O app lê e exibe branch + status de PR via git/`gh` (somente leitura)

### Distribuição (DIST)

- [x] **DIST-02**: Pacote nativo **AUR** (Arch), usando `vte4` do sistema — canal principal no Arch
- [x] **DIST-03**: Pacote nativo **`.deb`** (Ubuntu), usando `gir1.2-vte-3.91` do sistema — canal principal no Ubuntu
- [x] **DIST-04**: Roda em Ubuntu e Arch (GNOME, Wayland)

> **DIST-01 (Flatpak) movido pro v2** (ver abaixo). O pivô pra distribuição nativa elimina o sandbox e a ponte `flatpak-spawn --host`; o VTE vem dos repos oficiais (Ubuntu 0.76 / Arch 0.84), sem bundle.

## v2 Requirements

Adiados para depois. Rastreados, mas fora do roadmap atual.

### Distribuição (DIST)

- **DIST-01**: Flatpak como canal **secundário**, com VTE embutido — reintroduz a ponte `flatpak-spawn --host` via o `HostRunner` (que já nasce com esse caminho no v1, como no-op)

### Persistência (PERSIST)

- **PERSIST-01**: Reatar agentes vivos após fechar/reabrir o app inteiro (não só a janela) — exige camada host (tmux/abduco)

### Status (STATUS)

- **STATUS-04**: Fallback de scraping da saída do terminal para detectar status de agentes não-Claude (codex/aider)

### Swarm (SWARM) — Fase 2 opcional, degrau a degrau

- **SWARM-01**: Arquivo de contexto compartilhado entre agentes
- **SWARM-02**: Board de tarefas manual na sidebar
- **SWARM-03**: Agentes leem as tarefas do board
- **SWARM-04**: Agente Coordinator escreve o board a partir de um objetivo
- **SWARM-05**: Posse exclusiva de arquivo + Builders pegam tarefas
- **SWARM-06**: Estado exposto via MCP (em vez de arquivo solto)
- **SWARM-07**: Reviewer automático + sequência de dependências

## Out of Scope

Explicitamente excluído. Documentado para evitar scope creep.

| Feature | Reason |
|---------|--------|
| Gestão de credenciais / Jira / criação de issues | Feito na mão; git/`gh` só leem info. Superfície de segurança + escopo explode |
| Construir emulador de terminal do zero | Escopo gigante; embute-se o VTE (motor do GNOME Terminal) |
| Editor de código embutido | Compete com o neovim que o usuário já usa; superfície enorme |
| Containers always-on por worktree (modelo Sculptor) | 0,5–2 GB cada → mata a promessa lightweight; viola constraint de RAM |
| autoyes/yolo auto-accept por default | Perigoso pra ferramenta de time; se entrar, opt-in por sessão, nunca default |
| Comentários inline no diff que o agente lê / UI de PR no app | arduis é read-only em git/gh; escrever de volta = integração profunda |
| Acesso mobile/web remoto | Superfície de rede/auth; foge da tese desktop-GNOME |
| Snap como canal principal | Confinamento quebra ferramenta que dirige docker/git/ssh |
| macOS / Windows | Apenas Linux + GNOME |
| Reescrever em Rust por causa de RAM | Gargalo está nos agentes/containers, não na GUI |

## Traceability

Qual fase cobre qual requisito. Cada requisito v1 mapeia para exatamente uma fase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TERM-01 | Phase 1 | Complete |
| WT-01 | Phase 2 | Complete |
| WT-02 | Phase 2 | Complete |
| WT-03 | Phase 2 | Complete |
| RAM-01 | Phase 2 | Complete |
| PAR-01 | Phase 3 | Complete (UAT pending) |
| PAR-02 | Phase 3 | Complete (UAT pending) |
| PAR-03 | Phase 3 | Complete (UAT pending) |
| LAYOUT-01 | Phase 3 | Complete (UAT pending) |
| RAM-02 | Phase 3 | Complete (UAT pending) |
| RAM-03 | Phase 3 | Complete (UAT pending) |
| PROJ-01 | Phase 03.4 | Complete |
| STATUS-01 | Phase 4 | Complete (UAT pending) |
| STATUS-02 | Phase 4 | Complete (UAT pending) |
| STATUS-03 | Phase 4 | Complete (UAT pending) |
| RAM-04 | Phase 4 | Complete (UAT pending) |
| AGENT-01 | Phase 5 | Complete (UAT pending) |
| UI-01 | Phase 5 | Complete (UAT pending) |
| UI-02 | Phase 5 | Complete (UAT pending) |
| ENV-01 | Phase 6 | Complete (UAT pending) |
| ENV-02 | Phase 6 | Complete (UAT pending) |
| CONT-01 | Phase 7 | Complete (UAT pending) |
| CONT-02 | Phase 7 | Complete (UAT pending) |
| CONT-03 | Phase 7 | Complete (UAT pending) |
| CONT-04 | Phase 7 | Complete (UAT pending) |
| CONT-05 | Phase 7 | Complete (UAT pending) |
| REVIEW-01 | Phase 8 | Complete (UAT pending) |
| REVIEW-02 | Phase 8 | Complete (UAT pending) |
| REVIEW-03 | Phase 8 | Complete (UAT pending) |
| GIT-01 | Phase 8 | Complete (UAT pending) |
| DIST-02 | Phase 9 | Complete |
| DIST-03 | Phase 9 | Complete |
| DIST-04 | Phase 9 | Complete (hardware UAT PO-accepted as open risk) |
| ~~DIST-01~~ (Flatpak) | v2 | Deferred |

**Nota cross-cutting:** RAM management é tecido entre as fases — RAM-01 (agent-half) na Phase 2, RAM-02/03 (ResourceMonitor + visibilidade + caps) na Phase 3, RAM-04 (auto-suspend) na Phase 4; a metade de containers amadurece na Phase 7. Cada RAM-REQ é "owned" por uma única fase (acima), mas a feature evolui ao longo do roadmap.

**Coverage:**
- v1 requirements: 33 total (DIST-01/Flatpak movido pro v2)
- Mapped to phases: 33 ✓
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-08*
*Last updated: 2026-06-15 — PROJ-01 adicionado (Phase 03.4 corretiva: topbar = multi-projeto switcher "both alive" + persistência)*
