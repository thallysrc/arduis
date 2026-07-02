# Persistência de layout de terminais entre reinícios do app

**Data:** 2026-07-02
**Status:** Design — aguardando revisão do usuário

## Problema

Ao fechar e reabrir o arduis, o workspace principal ("arduis") perde todo o
arranjo de painéis. Na imagem #3 o usuário tinha um grid 2×2 (1 `zsh` + 3
`claude`); ao reabrir (imagem #4) sobrou apenas um único `zsh`. O usuário quer
que o arranjo volte idêntico ao da imagem #3.

## Causa-raiz (confirmada no código)

O layout ao vivo — a árvore de splits por workspace e o `kind` (agent/shell) de
cada painel — **existe apenas em memória**. Nada disso é persistido:

1. `window.py::_open_shell_leaf()` reconstrói o workspace principal como **um
   único leaf** `main:t0` (zsh). Os splits abertos pelo usuário nunca são relidos.
2. Painéis extras do workspace principal **não viram `TerminalRecord`** — ficam
   num dict volátil `_main_split_info` (comentário no código: "main workspace has
   no store workspace — spawn plain, no record to write").
3. Os `LayoutModel` por workspace (`self._layouts`) e os ratios dos `Gtk.Paned`
   (closures de `_init_paned_position`) vivem só em memória.
4. Único estado persistido hoje: `projects.json` (raízes de projeto +
   `last_active`), via `projects_store.py`. Não há `layouts.json`.
5. No fechamento, `_on_close_request` mata todos os grupos PTY (SIGHUP→SIGKILL) —
   "no orphans" é barra dura do projeto. Processos **não** podem sobreviver ao
   fechamento sem uma camada tipo tmux/abduco.

## Decisão de semântica (aprovada pelo usuário)

**Opção A — restaurar arranjo + retomar conversas (respawn).** Reconstruir o
grid idêntico (mesmos splits, mesmo agent/shell, mesmo cwd); shells nascem novos;
painéis `claude` reabrem com `claude --continue`, retomando a conversa anterior.
Processos são novos — não se mantém processo vivo (Opção B, tmux/abduco, foi
descartada por conflitar com "no-orphans" e RAM-first).

## Decisão de escopo (assumida — CONFIRMAR)

**Principal sobe automaticamente; worktrees lembram o layout no resume.**

- Só o workspace principal (`_MAIN_SID`) respawna o grid completo no boot.
- Workspaces de worktree continuam hibernando no boot (RAM-first / D-11), mas ao
  receberem *resume* sobem com o layout customizado salvo — não mais o par default.
- Descartado: "tudo sobe no boot" (fura RAM-first; vários `claude` no arranque).

> O usuário estava ausente quando esta pergunta foi feita; seguimos o julgamento
> recomendado. Reconfirmar na revisão deste spec.

## Arquitetura

Um único arquivo de estado novo, no padrão já provado de `projects_store.py`.

### Componente 1 — `src/arduis/layout_store.py` (novo, GTK-free)

Responsabilidade única: ler/escrever `~/.config/arduis/layouts.json`. Importa
`NO gi`. Espelha `projects_store.py`: escrita atômica (`mkstemp` no mesmo dir →
`os.replace`), leitura tolerante (json ruim / não-dict / arquivo ausente →
snapshot vazio; uma entrada ruim nunca aborta o load).

A (de)serialização recursiva da árvore de layout mora **aqui** (o módulo já
conhece as formas `LeafNode`/`SplitNode`), mantendo `layout.py` como lógica pura.

Formato de `layouts.json`:

```json
{
  "version": 1,
  "projects": {
    "<project-root-abs>": {
      "workspaces": {
        "<sid>": {
          "focused_id": "main:t2",
          "tree": {
            "split": "h", "ratio": 0.5,
            "start": { "leaf": "main:t0" },
            "end":   { "split": "v", "ratio": 0.5,
                       "start": { "leaf": "main:t1" },
                       "end":   { "leaf": "main:t2" } }
          },
          "leaves": {
            "main:t0": { "kind": "shell", "cwd": "/home/u/Projects/arduis" },
            "main:t1": { "kind": "agent", "cwd": "/home/u/Projects/arduis" },
            "main:t2": { "kind": "agent", "cwd": "/home/u/Projects/arduis" }
          }
        }
      }
    }
  }
}
```

API pública:

- `save_layouts(path: str, snapshot: dict) -> None` — escrita atômica best-effort.
- `load_layouts(path: str) -> dict` — load tolerante; retorna `{"projects": {}}`
  em qualquer falha.
- `tree_to_dict(node) -> dict | None` / `tree_from_dict(d) -> Node | None` —
  (de)serialização recursiva de `LeafNode`/`SplitNode` (com `ratio`).

`kind`/`cwd` são o mínimo necessário. `badge` **não** é salvo — é derivado
(`"zsh"` para shell, `"claude"` para agent). `focused_id` é salvo para restaurar
o anel de foco.

### Componente 2 — `src/arduis/layout.py` (alteração mínima)

Adicionar **um** campo ao `SplitNode`:

```python
@dataclass
class SplitNode:
    orientation: str
    start: "LeafNode | SplitNode"
    end: "LeafNode | SplitNode"
    ratio: float = 0.5   # fração do split; aprendida no drag, persistida
```

Default `0.5` mantém toda construção posicional existente funcionando. Nenhuma
outra lógica muda.

### Componente 3 — `src/arduis/window.py` (integração)

**Wiring do ratio em `_init_paned_position`:** o `SplitNode` correspondente é
passado ao helper; o closure `_learn` (drag do usuário) grava `node.ratio` e
`_apply` lê `node.ratio` em vez da constante local `0.5`. Assim a árvore
serializada já carrega as proporções sem estado paralelo.

**Salvar — `_snapshot_layouts() -> dict`:** varre `self._registry.all()` ×
workspaces; para cada `sid` com `LayoutModel`, monta `{tree, focused_id, leaves}`.
Fonte de `kind`/`cwd`:
- workspace principal → `_main_split_info` (+ `main:t0` = shell no `_repo_root`);
- workspaces reais → `Workspace.terminals` / `repos[*].terminals` + `_workspace_root_cwd`.

Gatilhos de save:
- `_on_close_request` (antes do teardown — teardown intacto);
- debounce (~500 ms via `GLib.timeout_add`) ao fim de `_split_active_pane` e
  `_close_terminal`, para resistir a crash.

**Restaurar principal — `_open_shell_leaf`:** cria `main:t0` (zsh) como hoje — ele
**continua sendo o shell primário que fecha a janela** ao sair. Se houver layout
salvo para `_MAIN_SID` com mais de um leaf: seta `model.root` = árvore
desserializada; reusa o terminal de `main:t0`; para cada **outro** leaf, cria
widget + `_spawn_into(cwd, kind)`. Painéis `agent` recebem
`agentconfig.resume_feed_bytes(cmd)` (`claude --continue`) — mesmo caminho do
auto-suspend. Popula `_term_by_sid`/`_leaf_by_sid`/`_main_split_info` para os
painéis restaurados.

**Restaurar worktree — `_resume_workspace`:** se existe layout salvo para o `sid`,
reconstrói dele (árvore + spawns com `resume_feed_bytes`); senão, mantém o
`_build_workspace_terminals` default atual.

**Helper compartilhado — `_restore_layout(sid, saved, primary_tid=None)`:**
centraliza a reconstrução da árvore + spawn dos leaves, usado pelos dois pontos
acima. `primary_tid` (só o principal) marca o leaf já criado que não deve ser
respawnado.

## Tolerância a falhas (padrão D-06 já existente)

- Worktree concluída/apagada → `cwd` inexistente → workspace pulado, sem crash.
- `term_id` salvos populam `_term_by_sid` no restore → `_next_term_id` não colide.
- `layouts.json` corrompido / dir ausente → degrada para "sem layout salvo" (=
  comportamento atual).
- `claude --continue` sem histórico prévio: mesmo comportamento já aceito no
  auto-suspend (reusa `resume_feed_bytes`).

## Invariantes preservados

- Teardown "no-orphans" inalterado — só adicionamos um snapshot **antes** dele.
- `main:t0` permanece o shell primário cujo exit fecha a janela.
- `layout.py` e `layout_store.py` continuam GTK-free e unit-testáveis.
- RAM-first: worktrees não sobem sozinhas no boot.

## Testes (seguindo `test_projects_persist.py` / `test_layout.py`)

- **`tests/test_layout_store.py`** (novo):
  - round-trip `save_layouts`/`load_layouts`;
  - load tolerante: json inválido, arquivo ausente, não-dict → `{"projects": {}}`;
  - escrita atômica: falha no meio não corrompe o arquivo existente;
  - `tree_to_dict`/`tree_from_dict` recursivo, com `ratio` preservado.
- **`tests/test_layout.py`** (extensão): `SplitNode.ratio` sobrevive a
  split/collapse; default `0.5` não quebra construção posicional.
- Restauração de nível-window (GTK) fica como checklist de aceitação manual
  (abrir grid 2×2 no principal → fechar → reabrir → grid idêntico, agents com
  conversa retomada), coerente com o padrão de testes GUI do projeto.

## Fora de escopo (YAGNI)

- Manter processos vivos entre reinícios (Opção B / tmux / abduco).
- Auto-subir worktrees no boot.
- Persistir `badge` (derivado de `kind`).
- Persistir posição/tamanho da janela ou largura da sidebar (não pedido).
