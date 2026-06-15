# Install the whole `arduis` package into the Python purelib (site-packages)
# so `import arduis` and `importlib.resources.files('arduis.hooks')` work with
# NO sys.path hacking (RESEARCH Pattern 1 + Pitfall 1). meson has no recursive
# glob, so every .py is enumerated explicitly (paths relative to src/).
#
# `preserve_path: true` keeps the arduis/ + hooks/ + swarm/ nesting intact, so
# the Claude Code hook (arduis/hooks/arduis_hook.py) ships as package data and
# resolves via importlib.resources on the installed copy.
py = import('python').find_installation('python3')

py.install_sources(
  [
    'arduis/__init__.py',
    'arduis/agentconfig.py',
    'arduis/appconfig.py',
    'arduis/attention.py',
    'arduis/caps.py',
    'arduis/compose.py',
    'arduis/containerstate.py',
    'arduis/docker_service.py',
    'arduis/exit_status.py',
    'arduis/gh.py',
    'arduis/git_service.py',
    'arduis/host_runner.py',
    'arduis/keyconfig.py',
    'arduis/keymap.py',
    'arduis/layout.py',
    'arduis/main.py',
    'arduis/project.py',
    'arduis/projects_store.py',
    'arduis/repoconfig.py',
    'arduis/resource_monitor.py',
    'arduis/review.py',
    'arduis/review_cache.py',
    'arduis/session.py',
    'arduis/spawn.py',
    'arduis/task_layout.py',
    'arduis/theme.py',
    'arduis/themes.py',
    'arduis/topbar.py',
    'arduis/trust.py',
    'arduis/window.py',
    'arduis/worktree.py',
    # hooks/ — arduis_hook.py MUST ship as package data (importlib.resources)
    'arduis/hooks/__init__.py',
    'arduis/hooks/arduis_hook.py',
    # swarm/ — package marker (kept for the nested package to import)
    'arduis/swarm/__init__.py',
  ],
  pure: true,
  preserve_path: true,
)

# Generate the launcher (RESEARCH Pattern 2): a thin `bin/arduis` that imports
# the INSTALLED package — NO sys.path insert (the dev shim's hack must not leak).
# @VERSION@ is substituted from the single-sourced project version (D-03).
conf = configuration_data()
conf.set('VERSION', meson.project_version())

configure_file(
  input: '../data/arduis.in',
  output: 'arduis',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)
