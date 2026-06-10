# Arduis — Motivação

> *Fortis in arduis* — "Forte nas dificuldades". `arduis` é o nome artístico do projeto.

Este documento é a **base de tudo**. Captura por que o projeto existe e quais são
as restrições inegociáveis. Tudo o que for decidido depois deve servir a isto.

## Quem sou e como trabalho

- Vivo dentro do **tmux**. Troco de terminal/janela com altíssima fluência.
- **Os meus atalhos importam mais do que a ferramenta em si.** Qualquer solução
  precisa respeitar / não atrapalhar o muscle-memory que já tenho no tmux.
- Edito texto às vezes no **neovim**.
- Uso o **Claude (Claude Code)** intensamente para resolver problemas do dia a dia.
- Configuro Jira, GitHub etc. **na mão** — isso está **fora do escopo**. A ferramenta
  só deve *ler* informação via `git` e `gh` (GitHub CLI), nunca gerenciar credenciais.

### Setup atual (contexto técnico)
- tmux: prefix remapeado para `C-Space`, base-index 1, panes navegados com `C-h/j/k/l`
  (estilo vim), split com `-` e `=`, mouse on, status bar no topo (tema dracula),
  extended-keys on (Shift+Enter pro Claude Code), `allow-passthrough on`.
- shell: zsh.
- Padrão de uso observado: uma sessão tmux com várias janelas, **múltiplos `claude`
  rodando em paralelo** no mesmo projeto (ex.: backend, frontend, panes separados).

## O problema

A **automação das janelas do terminal** hoje é manual e repetitiva. Quero
**iniciar uma branch/worktree nova rapidamente** e ter o ambiente de trabalho
(janelas, panes, agentes, containers) montado para mim.

O objetivo central é **tornar o gerenciamento de vários agentes em paralelo mais
fácil** — múltiplos agentes trabalhando em **worktrees diferentes**, podendo
compartilhar (ou não) os mesmos containers da aplicação. (A ser discutido.)

## A visão

Uma versão **Linux** da experiência do **BridgeMind / BridgeSpace** (que só existe
para Mac): um **app desktop GNOME** que orquestra vários agentes em paralelo.

- **App gráfico próprio (GTK4 + libadwaita)** com **terminais reais embutidos via VTE**
  (o mesmo motor do GNOME Terminal) rodando `claude`/`zsh` dentro de cada pane. NÃO se
  constrói um emulador de terminal do zero — embute-se o VTE.
- **Continua centrado no terminal:** o app é, no fundo, uma grade de terminais com
  orquestração por cima — e **respeita meus atalhos** (keybindings configuráveis no
  padrão tmux que já uso: `C-Space`, `C-h/j/k/l`, etc.).
- **Lightweight e instalável** — distribuição **nativa**: **`.deb`** (Ubuntu) + **AUR**
  (Arch), usando o **VTE do sistema** (sem sandbox, sem bundle). Snap está descartado
  (confinamento atrapalha uma ferramenta que dirige docker/git).
- **Fácil de instalar na máquina de OUTROS devs** (não é só ferramenta pessoal — é de
  time): `apt install` (Ubuntu) ou pacote AUR (Arch), dependendo do VTE/GTK/libadwaita
  já presentes na distro. Docker **não** é caminho de distribuição de app desktop (é p/
  serviços) — instinto confirmado.
- Sem reinventar gestão de credenciais: usa `git` e `gh` para obter informação.

> Decisão de caminho: avaliamos (A) app GTK próprio com VTE embutido vs. (B) só
> orquestrar um terminal pronto (kitty) via remote-control. **Escolhido o caminho A**
> pelo visual rico (sidebar com status dos agentes, badges de container) e por ser um
> app instalável de verdade. (kitty não pode ser embutido como widget, ainda mais no
> Wayland; por isso não vira o motor interno.)

### Estrutura da interface — 3 níveis (modelo aprovado)

A navegação tem **três níveis**, de cima para baixo:

1. **Topbar = repositórios (projetos).** Posso ter **vários repositórios git abertos ao
   mesmo tempo** e alternar entre eles na barra superior. Cada repositório é um projeto.
2. **Sidebar = worktrees** do repositório selecionado. Lista as worktrees daquele repo
   (com status); selecionar uma foca/abre essa worktree.
3. **Workspace = a worktree selecionada**, exibindo seus **terminais**. **Apenas uma
   worktree fica visível por vez** — selecionar outra na sidebar troca o workspace inteiro.

- **Terminais por worktree:** o padrão é **2** (ex.: um `claude` + um shell — meu hábito
  backend/frontend), lado a lado. **Não é limite rígido** — posso abrir mais quando
  precisar; 2 é só o default.
- Os terminais são VTE embutidos; layout e atalhos seguem o padrão tmux (`C-Space`,
  `C-h/j/k/l`, split, etc.).

> Isto **refina/supersede** a ideia anterior de "grade 2×2 de worktrees" (mockup v1):
> os panes do workspace são os **terminais de UMA worktree**, não várias worktrees lado
> a lado. Repos vivem no topbar; worktrees na sidebar; terminais no workspace.

## Restrições inegociáveis (REGRAS)

1. **Roda em Linux com GNOME** — tem que funcionar tanto no **Ubuntu** quanto no
   **Arch Linux** com GNOME. Isto é uma regra, não uma preferência.
2. **Centrado no terminal.** Terminais VTE embutidos; respeita meus atalhos (estilo tmux).
3. **Lightweight e instalável** — pacotes **nativos**: `.deb` (Ubuntu) + AUR (Arch).
4. Integração com **git branch / worktree** e **GitHub CLI** apenas para leitura de info.
5. Gestão de Jira/GitHub/credenciais está **fora do escopo**.

## Decisões tomadas

- **Caminho A**: app desktop GNOME (GTK4 + libadwaita) com terminais **VTE** embutidos.
- Distribuição: **nativa** — `.deb` (Ubuntu) + AUR (Arch), via VTE do sistema; Snap
  descartado. (Decidido 2026-06-08; sem sandbox — o app fala direto com o host.)
- Referência visual **APROVADA**: `docs/mockup/` — v1 (Dracula, grade 2×2) e
  v2 estilo BridgeSpace (charcoal + accent, command-blocks tipo Warp, room tabs
  Command/Swarm/Review, rail de agentes, mini-kanban). Elementos validados: sidebar de
  worktrees com status, command-blocks, badges de container shared/isolated, status bar
  tmux-like. Dracula vira um tema entre vários.
- **Gestão de memória (RAM) é requisito de primeira classe.** O custo NÃO está no app
  (GTK4+VTE é leve, ~dezenas de MB) nem na linguagem (Python vs Rust = ruído); está nos
  **agentes** (cada `claude`/Node ~100–300 MB) e, sobretudo, nos **containers isolados**
  (0,5–2 GB por worktree). Por isso o arduis deve: (a) **hibernar** worktree (mata agente
  + para containers, mantém o diretório) e retomar; (b) **limite configurável** de
  agentes/containers simultâneos; (c) **visibilidade de RAM por worktree/agente/container
  na UI**; (d) suspender ociosos; (e) **teardown garantido** ao fechar/remover; (f)
  compartilhado como default. NÃO trocar Python por Rust por RAM — o gargalo não está aí.

## Em aberto (a discutir)

- ~~**Linguagem**~~ → **DECIDIDO: Python (PyGObject)** (protótipo rápido, mínimo de deps).
- **Containers** (DECIDIDO): isolamento **por worktree, opt-in** (não toda vez). Quando
  ligado, sobe instância própria e isolada via `COMPOSE_PROJECT_NAME` único (nomes/redes/
  volumes separados → banco vazio e isolado de graça) + **`docker-compose.override.yml`
  gerado** com **offset de porta** por worktree, exibido na UI (badge tipo `db :5433`).
  O compose-base vem **sempre da `main`** (ambiente baseado no trunk, não da branch).
  Default = `off`. A criar dados: migrations/seed via comandos de `setup`.
  Em aberto: portas auto-atribuídas vs. fixas previsíveis.
- ~~**Layout** dos panes: grade fixa vs. livre~~ → **RESOLVIDO** pelo modelo de 3 níveis
  (ver "Estrutura da interface"): os panes do workspace são os **terminais de UMA
  worktree** (default 2, sem limite rígido), com split estilo tmux — não várias worktrees
  numa grade. Repos no topbar, worktrees na sidebar.
- Features além do MVP: diff/review embutido, kanban de cards, pane de logs do container.
