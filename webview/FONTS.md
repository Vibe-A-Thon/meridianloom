# Fonts (V3, DECISIONS.md)

Self-hosted from npm (`@fontsource/archivo`, `@fontsource/jetbrains-mono` —
both SIL Open Font License, redistribution permitted). Vite emits the
woff2 files as hashed assets next to the bundle; the extension host serves
them through `asWebviewUri` under `font-src ${cspSource}` (VIGUIX_Final §17).

Status for GF0:

- **Shipped:** Archivo 400/500/600 and JetBrains Mono 400/500, latin subset
  (the fontsource default subset). Token stacks in
  `src/theme/tokens.css` carry the documented fallback
  (`'Archivo', 'Helvetica Neue', Helvetica, Arial, sans-serif` and
  `'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace`)
  per VIGUIX_Final §6 P-12.
- **TODO (post-GF0):** subset beyond latin (currency/symbols ranges as the
  screens demand) and trim weights once the type ramp stabilises.
- **Commit Mono** is not shipped: its redistribution terms were not verified
  at build time. The data stack falls back to JetBrains Mono, which is
  shipped, so the visual check passes without it.
