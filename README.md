# Home Design Concepts

This repo holds house concept studies for three joined plots. Each concept is a data file. One command turns it into drawings, Blender renders and a Unity scene you can walk through.

**Live page:** https://ali3b.github.io/home-design/ has renders, plans, the progress log and a browser walkthrough.

> **These are concept studies only. Not for construction.** Dimensions come from the owner's title information. There has been no survey. Everything is subject to a boundary survey, legal merger of the titles, setbacks and permits.

## The site rules (enforced by `pipeline/validate.py`)

| | |
|---|---|
| Site | 3 × 4.5 m titles, about 13.5 × 65 m. The village road is to the south and the river to the north. |
| **ONT band** (road side, y 0–19.73 m, 266.4 m²) | The **only** place a building may be shown. |
| **DNN band** (river side, 609 m²) | Existing land. **Planting only**: no buildings, pools, decks or extensions. |
| Existing north-west building | Shown as a grey existing condition only. It is not altered or used. |
| 6.5 m to road centreline | A note from the title sketch only. **Not** treated as a setback. |

The validator fails the build if a room, slab, roof overhang, porch, balcony or fence leaves the ONT band, or if anything other than planting appears on the DNN band.

The private property pack (PDF, coordinates, locality) is **never committed**. `.gitignore` excludes it, and the pre-commit hook `pipeline/scrub_check.sh` blocks it.

## Concept 1: Terracotta Courtyard House

The concept is built from `Concepts and Plan/concept.png`:
- Two storeys, with brick on the ground floor and timber cladding on the upper floor.
- A terracotta hip roof and a front porch roof.
- A 1.5 m service passage on the west side.
- A light court on the east side.
- A 2.2 m shaded balcony facing north.

| | |
|---|---|
| Footprint | 11.4 × 16.5 m (188 m², 71 % of the ONT band) |
| Ground floor | 178 m² enclosed |
| Upper floor | 153 m² enclosed + 25 m² balcony |
| Total | about 331 m² enclosed |

Note: the brief image asks for 230–250 m² on the ground floor. That does not fit in the 266 m² ONT band once you allow for the passage, a forecourt and the eaves. The plan is fitted to the band instead.

The roof eaves sit on the east boundary, so a boundary/setback check is needed.

**Outputs:**
- `out/c1/c1_review.pdf` is the review set: cover, site plan, plans, roof, section, schedule, renders and walkthrough shots. It is also on the Pages site.
- `out/c1/unity/walktest.txt` shows that every room is reachable on foot from the road gate (24/24).

## Concept 3: Four-Bed Garage House

`concepts/c3_garage_house.json` adapts a commercial four-bedroom, double-garage floor plan (the owner's brief) to this site. The source brochure is private and is never committed.
- The house is modern, with flat membrane roofs behind parapets.
- The ground floor is white render and the upper floor is white vertical cladding.
- There is a stacked-stone entry pier, a dark garage door and dark aluminium frames.

| | |
|---|---|
| Placement | 10.4 m wide house, x 2.8–13.2 m: a 2.8 m garden strip on the west, and the garage 0.3 m off the blank east party wall |
| Ground floor | Porch, foyer, home office, U-stair, powder room, laundry, IT nook, store, butler's pantry, double garage (5.7 × 5.7 m), and open kitchen / meals / family to a 4.3 × 2.8 m covered alfresco |
| Upper floor | Rumpus, Bedroom 1 with a double WIR and ensuite, Bedrooms 2–4 (each with a WIR or robe), bathroom, powder room, linen, and a covered deck on the garage roof |
| Areas | Footprint 137 m² (52 % of ONT). About 121 m² ground + 117 m² upper enclosed, centre-line. Alfresco 12 m² and deck 7 m² |
| ONT check | Rear wall at y 16.2 m. The alfresco ends at 19.0 m, inside the 19.73 m band |

The plan is adapted from a third-party design for study only. Building it would need that design owner's licence or a new design.

**Outputs:** `out/c3/c3_review.pdf`, `out/c3/unity/walktest.txt`. The browser walkthrough is at https://ali3b.github.io/home-design/play3/.

Pipeline features added for this concept (all opt-in from the concept JSON, so Concepts 1 and 2 build exactly as before):
- `flat` roofs with parapets
- per-level wall skins and a frame colour (`style`)
- ground-level terraces that are open on their outer edges (`style.ground_out_open`)
- a `garage` door kind
- free-standing `features` (piers, posts, aprons), which are validated to stay in ONT
- U-stairs that run along x (`stair.axis: "x"`)

## Walk through it

**Unity editor:**
1. Open `HomeWalk/` in Unity Hub. It needs Unity **6000.6.0f1** with URP.
2. Open `Assets/Home/Scenes/C1_Walkthrough.unity` and press Play.

**Built players:** these are local only and not in git.
- `HomeWalk/Builds/Linux/HomeWalk.x86_64`
- `HomeWalk/Builds/Windows/HomeWalk.exe`

**Browser:** https://ali3b.github.io/home-design/play/

| Key | Action |
|---|---|
| W A S D, mouse | Walk and look (Shift to run, Space to jump) |
| 1–9 | Viewpoints: Street, Entry, Living, Kitchen, Master, Lounge, Balcony, Garden, Aerial |
| R | Roof on / off |
| U | Dollhouse (hide the upper floor and roof) |
| T | Time of day: morning, midday, golden hour, evening |
| F | Fly mode (Space up, C down) |
| M / Tab | Plan minimap with your position |
| H | Help on / off |
| Esc / click | Free / capture the mouse |

## Rebuild everything

```
pipeline/make.sh c1_courtyard_house c1          # full run (about 30–60 min including the WebGL build)
pipeline/make.sh c1_courtyard_house c1 --fast --no-unity   # data, drawings and quick renders only
pipeline/make.sh c3_garage_house c3                         # Concept 3 (Unity step runs HomeTools.ReleaseC3)
```

The steps are:
1. `validate.py` checks the constraints.
2. `sheets.py` makes the A3 drawing sheets.
3. Blender (`pipeline/blender/build.py`) builds the model and FBX, then renders.
4. Unity (`pipeline/unity.sh HomeWalk.EditorTools.HomeTools.ReleaseAll`) rebuilds the scene, takes the review shots, runs the walk test and builds Linux, Windows and WebGL (WebGL goes into `docs/play`).
5. `review.py` assembles the PDF.
6. `publish_docs.py` updates the Pages gallery.

Unity runs headless but needs an X display. `pipeline/unity.sh` uses the desktop session's `:0`.

## Adding Concept 2

1. Copy `concepts/c1_courtyard_house.json` to `concepts/c2_<name>.json`. Edit the `levels` room rectangles (`[name, x0, y0, x1, y1, kind]` in site metres, x east, y north from the road boundary), plus the `doors`, `roofs`, `stair`, `porch` and `viewpoints`.
2. Copy `concepts/c1_furnishing.json` to `c2_furnishing.json` and place the Synty props.
3. Run `python3 pipeline/validate.py concepts/c2_<name>.json` until it says `VALIDATE_OK`.
4. Add a `BuildC2` menu entry next to `BuildC1` in `HomeWalk/Assets/Home/Scripts/Editor/HomeBuilder.cs`, then run `pipeline/make.sh c2_<name> c2`.

Room kinds:

| Kind | Meaning |
|---|---|
| `hab` | Habitable room |
| `serv` | Wet / service room |
| `circ` | Circulation |
| `store` | Storage |
| `spec` | Special room (e.g. the altar room) |
| `out` | Balcony |
| `plant` | Light court, open to the sky |

Rooms listed in a level's `open` list have no walls between them (open plan).

## Layout

```
concepts/          site.json (scrubbed, relative geometry) + one JSON per concept + furnishing
pipeline/          validate, sheets, textures, review, publish, make.sh, unity.sh, autopush.sh
pipeline/lib/      drawing engine + Blender helpers (adapted from the earlier option studies)
pipeline/blender/  build.py: JSON → Blender model, FBX for Unity, Cycles renders
HomeWalk/          Unity 6 URP project (Synty packs are local only, not in git)
docs/              GitHub Pages site (gallery, progress log, review PDF, WebGL walkthrough)
out/               generated drawings, renders and shots
```

Progress is pushed to GitHub automatically every 10 minutes by `pipeline/autopush.sh`. Stop it with `touch .autopush.stop`.
