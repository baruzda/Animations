# NAMING & VERSIONING v0.1

## Folder model

```text
technical/                  # shared technical production rules
series/
  <Название сериала>/       # isolated creative memory per series
    characters/
    scripts/
    storyboards/
    visual/
    assets/
    backlog/
    decisions/
```

## Asset naming

```text
<SERIES>_<CATEGORY>_<ENTITY>_<TYPE>_<STATE>_v###
```

Примеры:

```text
BFY_CHAR_KLEPP_MODEL_FRONT_v001
BFY_CHAR_FINCH_EXPR_SKEPTICAL_v002
BFY_BG_WORKSHOP_WIDE_v004
BFY_PROP_WISHMACHINE_OVERLOAD_v003
BFY_EP01_SH030_AI_VIDEO_v005
```

`BFY` = рабочий короткий код «Бойся своих желаний».

## Version rule

Approved asset никогда не перезаписывается молча.

- новая генерация → новая версия;
- approved версия фиксируется в episode/asset manifest;
- rejected версии можно хранить вне репозитория или в production storage;
- репозиторий хранит канон, manifests, prompts/rules и ссылки/пути, а не обязан хранить все тяжёлые render-файлы.

## Episode IDs

```text
EP01, EP02, EP03...
```

Shot IDs:

```text
SH010, SH020, SH030...
```

Шаг 10 оставляет место для вставки новых кадров без массового переименования.
