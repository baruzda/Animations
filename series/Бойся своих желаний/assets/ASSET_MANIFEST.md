# ASSET MANIFEST v0.1

Цель: минимальный набор переиспользуемых assets, достаточный для пилота и первых 5–10 эпизодов.

## A. Клепп

### Model sheet
- front;
- 3/4 left;
- 3/4 right;
- profile;
- back;
- silhouette sheet.

### Expressions
- neutral;
- delight / idea;
- confident;
- suspicious;
- surprise;
- panic;
- irritation;
- fake calm;
- embarrassment;
- tiny victorious grin.

### Poses
- presenting invention;
- leaning over machine;
- pointing / explaining;
- mechanical hand tool-use;
- running;
- bracing against force;
- buried/blocked reaction;
- arms akimbo / false confidence.

### Mechanical hand
Отдельный reference sheet:
- palm/back;
- exactly 3 fingers;
- closed grip;
- precision grip;
- screwdriver/tool mode;
- electrode/spark mode.

### Monocle
- retracted;
- one-stage extended;
- full telescopic extension;
- glare/reflection overlay.

---

## B. Финч

### Model sheet
- front;
- 3/4 left;
- 3/4 right;
- profile;
- back with backpack;
- silhouette sheet.

### Expressions
- neutral;
- analytical;
- skeptical;
- interested;
- delighted by rare object;
- concern;
- panic while still writing;
- dry disappointment;
- shock;
- «I told you» without smugness.

### Poses
- notebook open;
- inspecting object;
- adjusting glasses;
- opening backpack drawer;
- holding labelled specimen;
- running with scarf follow-through;
- crouched behind cover;
- standing in calm contrast to chaos.

### Signature props
- round brass glasses;
- red-orange long scarf;
- modular mustard/orange backpack-cabinet;
- accordion field notebook;
- labels/tags/stickers set.

---

## C. Машина желаний

### Master views
- front;
- 3/4;
- side;
- back;
- silhouette.

### Mandatory elements
- handmade asymmetrical body;
- main lamp / bulb;
- readable activation area;
- lever or dial labelled «Множитель»;
- power cable/plug;
- pipes / gauges / indicator lights;
- one visually memorable red control.

### States
- off;
- idle;
- listening;
- wish accepted;
- processing;
- overload;
- emergency stop;
- smoking aftermath.

---

## D. Мастерская

### Base layers
1. clean master background;
2. back wall / shelves;
3. machine zone;
4. central table;
5. foreground clutter;
6. window / key light layer;
7. practical light overlay;
8. steam/dust particles;
9. shadow overlays.

### Camera presets
- wide establishing;
- medium two-shot;
- machine medium;
- Klепп close-up position;
- Финч close-up position;
- table insert;
- floor/plug insert;
- catastrophe wide.

---

## E. Пилот 01 props

- rubber duck master;
- duck variants via scale/rotation only;
- sandwich;
- 10-coin stack / loose coins;
- «Множитель» label and dial;
- power plug close-up;
- foreground duck pile masks.

## F. Reusable FX

- machine glow;
- spark;
- steam puff;
- small explosion smoke;
- vibration/shake preset;
- speed lines / smear accent;
- dust;
- object pop-in;
- warning light pulse;
- comic impact frame.

## G. Audio kit

- Klепп voice preset;
- Финч voice preset;
- machine idle;
- machine accept;
- machine overload;
- metal hand clicks;
- monocle telescope click;
- notebook flip;
- backpack drawer;
- duck squeak;
- impacts;
- room tone;
- reusable music bed;
- sting before/after punchline.

## Naming convention

```text
CHAR_KLEPP_<type>_<state>_v###
CHAR_FINCH_<type>_<state>_v###
PROP_WISHMACHINE_<view/state>_v###
BG_WORKSHOP_<camera/layer>_v###
FX_<name>_v###
AUD_<name>_v###
```

Approved assets must never be silently overwritten. New generations get a new version, and the approved version is referenced from the episode manifest.
