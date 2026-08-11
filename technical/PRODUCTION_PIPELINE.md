# PRODUCTION PIPELINE v0.1

Общий технический процесс для всех сериалов.

## 1. Pre-production

`idea → script → scratch voice → storyboard → animatic → asset check → production approval`

Ключевое правило: **не запускать дорогую video generation до утверждения animatic**.

## 2. Asset preparation

Для каждого сериала используются его собственные approved references из `series/<Название>/assets/` и `characters/`.

Перед производством эпизода должны быть определены:
- approved character references;
- location/background references;
- prop references;
- shot list;
- episode asset manifest;
- voice presets.

## 3. Limited animation layer

По умолчанию дешёвые и управляемые сцены собираются через:
- layered stills;
- facial swaps / mouth states;
- small head/body motion;
- parallax;
- camera push/pan/crop;
- foreground overlays;
- particles/light/steam;
- reaction cuts;
- speed changes and compositing.

## 4. Full AI-video layer

Использовать только когда движение является главным визуальным событием:
- hook/cold open;
- сложная физическая эскалация;
- кульминационный gag;
- payoff, который теряет качество в limited animation.

Стартовый ориентир: **5–12 уникальных дорогих AI-video секунд на 45–55 секунд готового ролика**.

## 5. Edit

Порядок:
1. rough assembly;
2. timing pass;
3. dialogue sync;
4. reaction cuts;
5. FX/compositing;
6. sound design;
7. music;
8. captions;
9. mobile-safe crop check;
10. master export.

## 6. Audio

Звук считается частью анимации.

Минимальный слой:
- dialogue;
- room tone;
- signature object/mechanism sounds;
- impacts;
- movement accents;
- short music bed;
- intentional silence before major punchline when useful.

## 7. Master

Базовый short-form master:
- 9:16;
- 1080×1920 minimum;
- 24/25/30 fps в зависимости от production preset, без случайного смешивания;
- key information inside mobile-safe composition;
- captions проверены на читаемость;
- no intro card before hook.

## 8. Measurement

Для тестовых выпусков фиксировать:
- фактическое число генераций;
- количество отбракованных generations;
- уникальные AI-video seconds;
- стоимость генерации;
- human editing time;
- total episode cost;
- retention 1–3s / 10s / completion;
- rewatch/loop signals, если платформа их даёт.

Технические правила должны корректироваться по этим данным, а не по предположениям.
