Yunze Li Academic Homepage
==========================

This repository is a clean static GitHub Pages site for Yunze Li's academic
homepage.

Deployment files:

```text
index.html
assets/main.css
assets/logo.svg
assets/publications/li-2024-optics-letters-fig1.png
assets/projects/journallens-screenshot.png
assets/projects/journallens-thumb.png
assets/projects/zotassets-logo.svg
.nojekyll
```

The site follows a simple academic homepage style: short biography, news,
publication list, projects, and academic links.

Publication entries should only be added after they are verified against Yunze
Li's Google Scholar profile:
https://scholar.google.com/citations?hl=zh-CN&user=NIT1ZyoAAAAJ&view_op=list_works&gmla=ACrTK9V4U4XJGi3u-X1_aEz2C8ieXOJKc-RLPsJrgdb30XDj7qxi1IvGoTiFi14KnZMykgUfMp9R3tKBCERM9Ws

Publication venue names should be italicized, for example:
`<em>Optics Letters</em>, 49(10), 2785-2788, 2024.`

Visitor map
-----------

The Visitors section uses the site's MapMyVisitors map and cumulative recorded
pageview count. The public map ID is in `data-map-id` on the Visitors section in
`index.html`; the statistics link is in `data-stats-url`. Update these values
together if the provider account or map changes.

An unconfigured map sends no visitor data to the provider. Visitors enable
tracking explicitly; this choice is remembered for the current tab only. Only visits recorded
by the provider are included, not historical traffic, blocked requests, or
visitors who do not opt in. The script loads once per page; switching themes
does not reload it. The map shows approximate IP-derived locations rather than
publishing raw IP addresses. Never add private account credentials to this
public repository.

The local placeholder map uses Natural Earth 1:110m geography redistributed by
world-atlas 2.0.2 (ISC license). It is generated using D3's Natural Earth
projection and TopoJSON; Antarctica is omitted for a compact geographic view.
Sources: https://github.com/topojson/world-atlas and
https://www.naturalearthdata.com/about/terms-of-use/.
