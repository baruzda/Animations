# ASSET MANIFEST v1.0

**Authority:** сначала читать `../canon/CANON_INDEX.md`. Этот файл описывает production-набор, но не имеет права переопределять утверждённые masters.

## Approved master classes

- `KLEPP_MASTER` — спецификация в `../visual/MODEL_SHEET_LOCK.md`.
- `FINCH_MASTER` — спецификация в `../visual/MODEL_SHEET_LOCK.md`.
- `DUO_SCALE_MASTER` — Клепп 180 см / Финч 167 см.
- `WISH_MACHINE_MASTER` — спецификация в `../visual/STYLE_GUIDE.md`.
- `WORKSHOP_MASTER` — спецификация в `../visual/STYLE_GUIDE.md`.

Любая старая версия этих пяти классов автоматически NON-CANON.

## A. Клепп — производные assets

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
- false confidence.

### Mechanical hand
Производные изображения обязаны сохранять ровно 3 пальца:
- palm/back;
- open;
- closed grip;
- precision grip;
- side/3⁄4 views.

### Monocle
- retracted;
- one-stage extended;
- full telescopic extension;
- glare/reflection overlay.

## B. Финч — производные assets

### Expressions
- neutral;
- analytical;
- skeptical;
- interested;
- delighted by rare object;
- concern;
- panic while still observing;
- dry disappointment;
- shock.

### Poses
- notebook open;
- inspecting object;
- adjusting glasses;
- opening backpack drawer;
- holding labelled specimen;
- running with scarf follow-through;
- crouched behind cover;
- calm contrast to chaos.

### Signature props
- round brass glasses;
- red-orange long scarf;
- rigid mustard backpack-cabinet;
- accordion field notebook;
- labels/tags set.

## C. Машина желаний — states

Все состояния производятся только из `WISH_MACHINE_MASTER`:
- off;
- idle;
- listening;
- wish accepted;
- processing;
- overload;
- emergency stop;
- smoking aftermath.

Запрещено менять габариты, базовый корпус или добавлять кабину/кресло/комнату.

## D. Мастерская — camera presets

Все планы производятся только из `WORKSHOP_MASTER`:
- wide establishing;
- reverse wide;
- medium two-shot;
- machine medium;
- Klepp close-up position;
- Finch close-up position;
- table insert;
- floor/plug insert;
- catastrophe wide.

Планировка не пересобирается под каждый shot.

## E. EP01 props

- rubber duck master;
- duck variants via scale/rotation only;
- sandwich;
- 10 coins;
- multiplier control/dial;
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
- warning pulse;
- comic impact frame.

## G. Audio kit

- Klepp voice preset;
- Finch voice preset;
- machine idle / accept / overload;
- mechanical hand clicks;
- monocle telescope click;
- notebook flip;
- backpack drawer;
- duck squeak;
- impacts;
- room tone;
- music bed;
- punchline sting.

## Naming convention

```text
CHAR_KLEPP_<type>_<state>_v###
CHAR_FINCH_<type>_<state>_v###
PROP_WISHMACHINE_<view-state>_v###
BG_WORKSHOP_<camera-layer>_v###
FX_<name>_v###
AUD_<name>_v###
```

Approved assets are immutable. Новый вариант получает новый version number и проходит canon gate.
