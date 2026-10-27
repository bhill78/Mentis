# Atmosphere backdrops

Local, static, and served from this application's own origin. Nothing here is
fetched at runtime — Mentis runs where there is no network, and an atmosphere
that needs the internet is one that sometimes is not there. These files were
downloaded once, at authoring time, and committed.

| file            | atmosphere | mode    | what it tests |
|-----------------|------------|---------|---------------|
| `shoreline.jpg` | Tidewater  | scenic  | focal, high-chroma imagery — the hard case |
| `nightfall.jpg` | Nightfall  | ambient | distributed, dark imagery — needs almost nothing |
| `shoal.jpg`     | Shoal      | texture | a mid-tone image made into a LIGHT ground by `--canvas-image-opacity`, carrying dark text |
| `downland.jpg`  | Downland   | scenic  | warm golden-hour landscape with a central focal subject |
| `monolith.jpg`  | Monolith   | ambient | dark, low-contrast architecture against a storm sky |
| `hailmary-wide.jpg` | Hail Mary | ambient | a red field of fine bright specks over a lit hull; wide screens |
| `hailmary-tall.jpg` | Hail Mary | scenic  | a saturated green-and-orange planet behind a silhouette; phones and tablets |

`shoreline.jpg` and `nightfall.jpg` were supplied by the owner (Pexels).
`downland.jpg` and `monolith.jpg` were supplied by the owner in the Artifacts
& Files Conversation (as AVIF, `adm-62813977231a` and `adm-989684ac6dc5`) and
converted to JPEG at the same size.
`hailmary-wide.jpg` and `hailmary-tall.jpg` are two stills from Project Hail
Mary, supplied by the owner in the Mentis UI/UX Conversation
(`adm-6f8e673a2aff` and `adm-2570e16189fa`, both 2731×1536 JPEG). The wide
one is resized to 2070×1164; the tall one is a 0.9:1 crop of the full height,
centred on the figure, resized to 1240×1380. The originals are not committed.
`shoal.jpg` is a blurred frame from Lorem Picsum (Unsplash-sourced, free to
use), fetched once for the light-ground proof.

To change an atmosphere's backdrop, replace the file. Nothing refers to its
contents: `--canvas-image` in `ui/src/atmosphere.css` is the only reference,
and the presentation properties beside it decide how it participates.
