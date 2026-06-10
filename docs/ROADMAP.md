# Arduis — Roadmap em Degraus (v1)

> Método: **Accelerate / DORA** — small batches, trunk-based, entrega contínua.
> Cada degrau é uma **fatia vertical instalável e usável**. Nada pela metade.
> `main` sempre funcionando. Objetivo: **dogfooding cedo** (usar o arduis pra construir o arduis).

Base: ver `docs/MOTIVATION.md` (a âncora) e os mockups em `docs/mockup/`.

---

## Stack (decidido)

| Camada | Escolha | Porquê |
|---|---|---|
| Linguagem | **Python + PyGObject** ✅ (confirmado) | protótipo rápido, mínimo de deps, ecossistema GNOME |
| UI | **GTK4 + libadwaita** | nativo GNOME (Ubuntu + Arch) |
| Terminal | **VTE** (`Vte.Terminal`) | mesmo motor do GNOME Terminal; não se faz emulador do zero |
| Config | **TOML** (`tomllib` na stdlib p/ ler) | edição à mão agradável, zero dep p/ parsear |
| Integrações | shell-out p/ `git`, `gh`, `docker compose` | sem reinventar credenciais |
| Distribuição | **Flatpak** principal; **AUR + .deb** nativos | 1 build cobre os dois; nativo fura sandbox |
| Ambiente dev | **Flatpak + GNOME SDK** (`org.gnome.Sdk`) | inclui `Vte-3.91` (GTK4 VTE não vem no apt do Ubuntu 24.04); dev == distribuição |

**Modelo de agente:** um pane = terminal VTE rodando `zsh`; o arduis auto-executa o
agente padrão (`claude`). `Ctrl+C` cai no shell → roda qualquer outro agente. Agente = comando.

**Containers:** isolamento **opt-in por worktree**; compose-base vem da **`main`**;
`COMPOSE_PROJECT_NAME` único + `docker-compose.override.yml` gerado com **offset de porta
auto-atribuído** (mostrado na UI); seed/migrations via comandos de `setup`. Default `off`.

---

## `.arduis.toml` (esboço — por repositório)

```toml
[agents]
default = "claude"
claude  = "claude"
codex   = "codex"          # plugável no futuro
shell   = "zsh"

[worktree]
base      = "main"         # branch base p/ novas worktrees
location  = "../"          # onde criar (sibling do repo)
setup     = []             # ex.: ["npm install", "cp .env.example .env", "make migrate", "make seed"]

[containers]
compose_from = "main"      # ambiente sempre baseado no trunk
default_mode = "off"       # "off" | "isolated"
port_offset  = 1000        # passo do offset entre worktrees
```

---

## Degraus da v1 (paralelismo simples)

> Cada degrau lista **Objetivo · Escopo mínimo · Definition of Done (DoD)**.

### Degrau 1 — Um terminal de verdade numa janela
- **Objetivo:** fundação GTK + VTE funcionando.
- **Escopo:** janela GTK4/libadwaita com **1 terminal VTE** rodando seu `zsh` (suas configs, cores).
- **DoD:** `arduis` abre uma janela e você tem um shell funcional dentro. Roda localmente (`make run`).

### Degrau 2 — Nova worktree → terminal já na pasta (o core loop)
- **Objetivo:** o coração do produto, mínimo.
- **Escopo:** botão **＋ Nova worktree** → pergunta a branch (nova/existente) → `git worktree add` →
  abre VTE na pasta da worktree → auto-roda o agente padrão (`claude`).
- **DoD:** num repo, clico, digito a branch, e ganho um terminal com `claude` rodando na worktree nova.

### Degrau 3 — Várias worktrees lado a lado + sidebar
- **Objetivo:** paralelismo de verdade.
- **Escopo:** sidebar listando worktrees; clicar foca; múltiplas colunas/panes (shell do layout v2).
- **DoD:** tenho N worktrees abertas, vejo na sidebar e troco entre elas.

### Degrau 4 — Status: quem me espera
- **Objetivo:** resolver a dor da bolinha laranja.
- **Escopo:** detectar estado (rodando / **aguardando input** / ocioso / pronto) lendo a saída do VTE
  → bolinha de status na sidebar e no header do pane.
- **DoD:** quando um `claude` para esperando resposta, o ponto fica laranja e eu acho na hora.

### Degrau 5 — Trocar de agente + atalhos tmux
- **Objetivo:** respeitar meu muscle-memory.
- **Escopo:** keybindings configuráveis (`C-Space n`, `C-h/j/k/l`, split `-`/`=`, zoom `z`);
  `Ctrl+C` → shell → outro agente; temas (Dracula default).
- **DoD:** meus atalhos do tmux funcionam; troco de agente por pane sem fricção.

### Degrau 6 — Setup ao criar worktree (`.arduis.toml`)
- **Objetivo:** worktree nasce "pronta pra trabalhar".
- **Escopo:** ler `.arduis.toml`; rodar `setup = [...]` na criação (npm install, cp .env, migrate, seed).
  Vazio = não faz nada. Defaults sensatos sem config.
- **DoD:** worktree nova roda meu setup automaticamente; configurável por repo.

### Degrau 7 — Containers isolados (opt-in)
- **Objetivo:** ambiente isolado por worktree p/ projetos grandes (a coisa que mais sinto falta).
- **Escopo:** detectar `docker-compose.yml`; toggle "isolated" por worktree; gerar override com
  **offset de porta auto**; compose-base da `main`; mostrar portas na UI (badge); **teardown** ao remover.
- **DoD:** ligo isolado numa worktree → sobe instâncias próprias em portas auto, exibidas nos badges;
  remover a worktree derruba os containers.

### Degrau 8 — Fechar o ciclo: review + cleanup
- **Objetivo:** terminar uma worktree sem deixar lixo.
- **Escopo:** ver diff (ou abrir PR via `gh`); ação "concluir worktree" → remove worktree + teardown containers.
- **DoD:** termino → abro PR via `gh` → arduis limpa worktree e containers.

### Degrau 9 — Empacotamento instalável
- **Objetivo:** `install` de verdade nos dois distros.
- **Escopo:** manifesto **Flatpak** (Flathub) + **AUR** (PKGBUILD) + **.deb**.
- **DoD:** instalo o arduis numa máquina limpa (Ubuntu e Arch) e ele roda.

---

## Trilha opcional — Swarm (Fase 2, só se eu quiser, degrau a degrau)

Princípio roubado do BridgeMind: **posse exclusiva de arquivo** (conflito eliminado por construção).
Eu construo **encanamento, não IA** (o Coordinator é só um Claude com prompt + tools).

1. Agentes leem um arquivo compartilhado de contexto. *(trivial)*
2. Board de tarefas manual na sidebar. *(fácil)*
3. Agentes **leem** as tarefas. *(fácil)*
4. **Coordinator** (Claude c/ prompt) escreve o board a partir de um objetivo. *(médio)*
5. Posse exclusiva de arquivo + Builders pegam tarefas. *(médio)*
6. Expor via **MCP** em vez de arquivo solto. *(médio)*
7. Reviewer automático + sequência de dependências. *(difícil)*

> Posso **parar em qualquer degrau** e ainda ter produto coerente.

---

## Fora de escopo (v1)
- Gestão de credenciais / Jira / criação de issues (faço na mão; `gh`/`git` só leem info).
- Construir um emulador de terminal (embute-se VTE).
- Swarm coordenado (é a Fase 2 opcional).
- Editor de código embutido (uso neovim; reavaliar depois).
