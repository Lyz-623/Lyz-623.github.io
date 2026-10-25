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
assets/projects/euposition-home.jpg
assets/education/polimi-logo.svg
assets/education/sustech-logo.png
assets/visit-count.js
assets/light-ripples.js
assets/publications/li-2026-anal-chem-toc.png
knowledge-map/   (PC-TWINS learning roadmap; see knowledge-map/README.md)
.nojekyll
```

The site follows a simple academic homepage style: short biography, news,
publication list, projects, and academic links.

Publication entries should only be added after they are verified against Yunze
Li's Google Scholar profile:
https://scholar.google.com/citations?hl=zh-CN&user=NIT1ZyoAAAAJ&view_op=list_works&gmla=ACrTK9V4U4XJGi3u-X1_aEz2C8ieXOJKc-RLPsJrgdb30XDj7qxi1IvGoTiFi14KnZMykgUfMp9R3tKBCERM9Ws

Publication venue names should be italicized, for example:
`<em>Optics Letters</em>, 49(10), 2785-2788, 2024.`

School crests
-------------

`assets/education/polimi-logo.svg` is the crest portion of the logo published on
https://www.polimi.it (wordmark paths removed). `assets/education/sustech-logo.png`
is the crest from SUSTech's Visual Identity page
(https://www.sustech.edu.cn/en/school_logo.html). Both are trademarks of their
respective universities and are used only to identify the degree programmes.

Visit count
-----------

`assets/visit-count.js` loads the MapMyVisitors map off-screen on every visit
and shows only its cumulative pageview total in the footer. This sends each
visitor's IP address and visit details to MapMyVisitors
(https://mapmyvisitors.com/b/policy). The map ID is `data-map-id` on
`.footer-visits` in `index.html`. Never add private account credentials here.

Light ripples
-------------

The site uses a single light theme with solid white cards. `assets/light-ripples.js`
draws, with WebGL, a broadband light pulse wherever the background is clicked: eight
wavelength bands (410-690 nm) expand as slow cylindrical waves, each band
interferes coherently with the same band of other ripples, and normal
dispersion spreads every ring into a rainbow, drawn as soft spectral tints on the
light page. It is disabled for visitors who
prefer reduced motion and does nothing without WebGL.
