Yunze Li Academic Homepage
==========================

This repository is a clean static GitHub Pages site for Yunze Li's academic
homepage.

Deployment files:

```text
index.html
assets/main.css
assets/logo.svg  (YL monogram, used by knowledge-map/)
assets/favicon-32.png, favicon-96.png, apple-touch-icon.png  (site icon, from the profile photo)
assets/profile-photo.jpg
assets/publications/li-2024-optics-letters-fig1.png
assets/projects/journallens-screenshot.png
assets/projects/journallens-detail.jpg
assets/projects/zotassets-logo.svg
assets/projects/euposition-detail.jpg
assets/education/polimi-logo.svg
assets/education/sustech-logo.png
assets/visit-count.js
assets/fonts/   (Newsreader for headings, Source Sans 3 for text)
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

Design notes
------------

A single light theme on warm paper (#f7f5f0). Newsreader (serif) sets the name,
section and entry titles; Source Sans 3 sets everything else. Deep teal
(#2f6a71) is the only accent colour, and ochre (#8c621c) is reserved for small
labels such as news dates and project kinds. Only publications and projects sit
in cards; the remaining sections are plain typography. Motion is limited to the
sliding nav underline and the back-to-top button.
