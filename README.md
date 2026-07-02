# arduis

arduis é um app desktop GNOME **lightweight** (Linux: Ubuntu + Arch) que orquestra
**vários agentes de IA (Claude Code) em paralelo** — cada um na sua **git worktree**, com
**terminais reais embutidos (VTE)**. É a resposta Linux e terminal-cêntrica ao
BridgeMind/BridgeSpace.

**Core value:** tirar a ideia "quero começar uma branch nova" e ter um **agente de IA
rodando numa worktree isolada em segundos** — gerenciando N agentes em paralelo e
**sempre sabendo qual deles te espera**.

The app is 100% pure Python on the **system** GNOME stack (PyGObject + GTK4 +
libadwaita + VTE-3.91). It uses the distro's VTE — **never** a bundled or `pip`-installed
one — and ships as **native packages only** in v1: a `.deb` for Ubuntu and an AUR
`PKGBUILD` for Arch. There is **no Flatpak and no Snap** in v1 (Flatpak is deferred to v2).

## Agente de voz (opcional)

Botão de microfone no header (ou `C-Space v`): fale um prompt em inglês, fique em
silêncio ~1,5s e o arduis transcreve localmente (whisper.cpp), **cria um pane novo no
workspace ativo e roda `claude '<prompt>'` direto** (handsfree). Cada prompt falado fica
num histórico persistente (popover ao lado do mic) com replay de um clique.

Requisitos (a feature degrada com um toast se faltarem):

- GStreamer plugins-good (captura de microfone) — `gstreamer1.0-plugins-good` (Ubuntu) /
  `gst-plugins-good` (Arch)
- `whisper-cli` + um modelo ggml — Arch: `pacman -S whisper.cpp`; Ubuntu: compile o
  [whisper.cpp](https://github.com/ggml-org/whisper.cpp). Modelo:
  `curl -Lo ~/.local/share/arduis/models/ggml-base.en.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin`

Configuração (`~/.config/arduis/arduis.toml`, tudo opcional):

```toml
[voice]
command = "whisper-cli"                                   # binário (pode embutir flags)
model = "~/.local/share/arduis/models/ggml-base.en.bin"
language = "en"
silence_ms = 1500            # silêncio que encerra a fala
silence_threshold_db = -40.0 # limiar RMS de "falando"
max_seconds = 60             # teto de gravação
history_max = 200            # tamanho do histórico
```

## Packaging / Install

Both packages are thin wrappers over a single [meson](https://mesonbuild.com) build
definition (`meson.build`). The app is architecture-independent (pure Python), so the
`.deb` is `Architecture: all` and the AUR package is `arch=('any')`. Runtime dependencies
are the **system** GNOME libraries — installing the package pulls them in; nothing comes
from `pip`.

> Publishing — pushing the `PKGBUILD` to the AUR and hosting the `.deb` in an apt
> repo / PPA — is deferred to **v1.1**. The instructions below build and install the
> packages **locally** from this repository.

### Ubuntu (`.deb`)

Verified on Ubuntu 24.04 (the GTK4 VTE — `gir1.2-vte-3.91` 0.76 — is in `main`, no PPA
needed).

```bash
# 1. Build dependencies (one-time):
sudo apt install meson ninja-build debhelper

# 2. Build the package from the repository root:
dpkg-buildpackage -us -uc -b
#    → produces ../arduis_1.0.0_all.deb

# 3. Install it (apt resolves the runtime dependencies):
sudo apt install ../arduis_1.0.0_all.deb
```

Runtime dependencies (declared in `debian/control`, pulled in automatically): the system
VTE 0.76 (`gir1.2-vte-3.91` / `libvte-2.91-gtk4-0`), `python3-gi`, `gir1.2-gtk-4.0`,
`gir1.2-adw-1`, and `python3` (>= 3.12). **No pip, no Flatpak.**

After install, `arduis` is on `PATH` and appears in the GNOME app grid with its icon.

### Arch (AUR)

Uses the system `vte4` (0.84) and the rest of the core GNOME stack.

```bash
# 1. Produce the source tarball from the repository (until a published release exists):
git archive --format=tar.gz --prefix=arduis-1.0.0/ -o arduis-1.0.0.tar.gz HEAD

# 2. Build and install from the PKGBUILD (in the directory holding PKGBUILD + the tarball):
makepkg -si
```

Runtime dependencies (declared in `PKGBUILD` `depends`, installed by pacman):
`python-gobject`, `gtk4`, `libadwaita`, `vte4`, `python`. The `PKGBUILD` ships **no
`.install` scriptlet** — pacman hooks refresh the icon and desktop-entry caches.

### Development

No install is needed to hack on arduis. From the repository root:

```bash
./run.sh          # or: python3 src/main.py
```

`run.sh` is the dev launcher and is unchanged by packaging; the installed `arduis`
launcher (from the `.deb` / AUR package) is the equivalent for end users.
