# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-07-01 (código completo 2026-06-15; fechamento formal + auditoria 2026-07-01)
**Phases:** 13 (9 planejadas + 4 corretivas inseridas) | **Plans:** 52 | **Commits:** 320 em 23 dias

### What Was Built
- App GNOME nativo (GTK4/libadwaita + VTE) que orquestra N agentes Claude Code em paralelo, cada um em worktree isolada, com terminais reais embutidos — "branch nova → agente rodando em segundos"
- Topbar multi-projeto "both alive" + task cross-repo (worktrees + symlinks espelhando a raiz multi-repo)
- Atenção hooks-first ("quem te espera"): hook Claude Code → state file → dots + libnotify, com auto-suspend opt-in
- Containers compose isolados opt-in por task (`COMPOSE_PROJECT_NAME` + `ports: !override` + probe de portas)
- Review read-only (diff VTE, PR via gh) + "Concluir task" com clean-gate nunca-`--force`
- Empacotamento nativo: `.deb` (lintian 0 erros) + PKGBUILD; 448 testes; ~14.2k LOC Python

### What Worked
- **Camada de domínio GTK-free primeiro, GTK como glue depois** — quase toda fase nasceu com módulos stdlib puros unit-testados (worktree/attention/compose/review/themes) e só então o wiring no window.py; o pytest ficou rápido (2.3s p/ 448) e headless
- **Smokes broadway headless** para provar mecanismo GTK sem display — destravou debug (paned-collapse) e verificação de fases
- **Fases corretivas decimais (03.1–03.4)** absorveram dois erros de nível do topbar sem quebrar o trunk
- **Quick tasks GSD** para o code review pós-milestone (t37/trz/tzk/buk) — 4 fixes cross-project com testes de regressão em 2 dias

### What Was Inefficient
- **O nível do topbar foi errado DUAS vezes** (03.2 D-06 nome-só → 03.3 chips de repo → 03.4 multi-projeto). Lição: decisões de nível de UI merecem um mockup-check com o PO antes de planejar
- **UAT humano acumulou como dívida** (8 fases human_needed) até ser fechado em lote por aceitação de risco — gates ao vivo deviam ser executados por fase, ou declarados risk-accepted mais cedo
- Artefatos de status (traceability, checkboxes do ROADMAP) dessincronizaram do disco e precisaram de reconciliação na auditoria

### Patterns Established
- HostRunner seam (no-op nativo) como único ponto de execução host — reancoragem do Flatpak v2 pré-paga
- Teardown como invariante: todo caminho (hibernate, conclude, app-exit) mata pgids + desce containers; "no orphans" testado
- Trust gate hash-based (modelo direnv) para comandos commitados no repo
- Aceitação de risco explícita e documentada (status `accepted` + contrato de reabertura) para gates humanos que o PO decide não executar

### Key Lessons
1. Provar destrutividade headless contra git REAL (smoke com repo de verdade) dá confiança suficiente para o PO aceitar pular o UAT visual — mas o registro do risco precisa ser explícito e reabrível
2. `docker compose` override CONCATENA arrays: a tag `!override` é obrigatória para substituir `ports` — achado que só apareceu testando contra disco real
3. `Gtk.Paned` aninhado não pode ser posicionado one-shot no map — dirigir por `notify::max-position` com ratio aprendido
4. Codar pro piso de API (VTE 0.76) desde o dia 1 evitou qualquer branch por distro

### Cost Observations
- Model mix: profile "quality" — executor opus, planners/researchers fable, checkers sonnet
- Notable: 4 fases corretivas (~30% do total de fases) vieram de decisões de nível de UI, não de bugs de código

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 13 | 52 | Baseline: domínio GTK-free + smokes broadway + fases corretivas decimais + risk-accepted closure de gates humanos |

### Cumulative Quality

| Milestone | Tests | Zero-Dep Additions |
|-----------|-------|--------------------|
| v1.0 | 448 | 0 (stdlib + stack GNOME do sistema apenas) |

### Top Lessons (Verified Across Milestones)

1. (v1.0) Domínio GTK-free testado primeiro; GTK como glue — a suíte inteira roda em segundos sem display
2. (v1.0) Decisões de nível/estrutura de UI validar com mockup + PO antes de planejar — correções custaram 4 fases decimais
