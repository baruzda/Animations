# PRODUCTION HANDOFF — CLEAN CONTEXT

Использовать при старте нового production-чата/агента.

## Обязательное чтение

1. `canon/CANON_INDEX.md`
2. `visual/MODEL_SHEET_LOCK.md`
3. `characters/CHARACTER_BIBLE.md`
4. `visual/STYLE_GUIDE.md`
5. сценарий и storyboard текущего эпизода

## Контекст, который запрещено импортировать

- старые изображения из предыдущих чатов;
- ранние character sheets;
- старые варианты Машины желаний;
- старые мастерские;
- ошибочные storyboard sheets;
- AI-generated подписи, не подтверждённые каноном.

## Production rule

В новый чистый чат загружать только текущие утверждённые visual masters:

- KLEPP_MASTER
- FINCH_MASTER
- DUO_SCALE_MASTER
- WISH_MACHINE_MASTER
- WORKSHOP_MASTER

и материалы текущего эпизода.

Не просить модель «вспомнить» персонажа по истории переписки. Каждый production shot должен явно опираться на master references.

## EP01 resume point

- SH010: scene approved.
- SH020: title card concept approved.
- Перед SH030 повторно проверить, что загружены пять master references.
- SH030 и далее генерировать по одному shot, затем проходить canon gate.

## Gate

`CANON_PASS + IDENTITY_PASS + SCALE_PASS + COSTUME_PASS + STYLE_PASS + PROP_PASS + LOCATION_PASS + STORY_PASS`

Клепп: `HAND_PASS + MONOCLE_PASS`.
Финч: `BACKPACK_PASS`.

Один FAIL = discard/regenerate.
