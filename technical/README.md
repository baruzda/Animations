# Technical production layer

Эта папка хранит **общую техническую часть производства всех сериалов**. Здесь не должно быть канона конкретного сериала, конкретных персонажей или конкретных сценариев.

## Что хранить здесь

- production pipeline;
- правила AI-video / image generation;
- монтаж и compositing;
- voice / audio pipeline;
- naming / versioning;
- quality gates;
- cost-control rules;
- automation architecture;
- общие требования к master/export/publishing.

## Что НЕ хранить здесь

- character bible;
- сценарии;
- раскадровки;
- сериал-специфичные локации и реквизит;
- конкретные сюжетные решения.

Они живут в `series/<Название сериала>/`.

## Текущие документы

- `PRODUCTION_PIPELINE.md` — общий процесс от идеи до master.
- `QUALITY_COST_RULES.md` — QC и правила контроля расходов.
- `NAMING_VERSIONING.md` — именование и версии файлов/ассетов.

Позже сюда же добавляются `AUTOMATION.md`, `VOICE_PIPELINE.md`, `PUBLISHING.md` по мере фактической сборки конвейера.
