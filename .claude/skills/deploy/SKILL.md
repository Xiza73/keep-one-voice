---
name: deploy
description: Procedimiento de publicación de keep-one-voice. Actívala al preparar un release, compilar el binario de la CLI con bun build --compile, etiquetar una versión, publicar en GitHub Releases o documentar los requisitos de instalación del worker de Python.
allowed-tools: Read, Edit, Bash(git status:*), Bash(git log:*), Bash(bun run:*), Bash(git tag:*), Bash(gh release:*)
---

# Despliegue — keep-one-voice

## Qué se publica y qué no

- **Se publica:** el binario `kov`, compilado con `bun build --compile` y
  adjunto a un GitHub Release.
- **No se publica:** el worker de Python. Se instala desde el repositorio con
  los extras de la fase que se vaya a usar: `uv sync --extra denoise --extra
  separate --extra diarize --extra transcribe`.
- **No se publica:** ningún peso de modelo. Se descargan bajo demanda desde
  Hugging Face.

## Disposición de la distribución

El binario **no lleva el worker dentro**. Lo busca en tiempo de ejecución, en
este orden: `KOV_WORKER_DIR`, junto al ejecutable (`<dir>/../worker` y
`<dir>/worker`), y el directorio de trabajo. Si no lo encuentra, falla nombrando
la variable y listando dónde buscó.

Un release debe entregarse con esta forma, o el binario solo sirve para
`--stages decode`:

```
kov-0.1.0/
├── bin/kov
└── worker/
```

**Compruébalo siempre desde fuera del repositorio.** Ejecutado dentro del
checkout el binario encuentra el worker por accidente y el fallo no aparece.

## Requisitos del entorno de destino

Esto va **siempre** en las notas del release. Si falta, el usuario obtiene un
error críptico en el primer uso:

1. **FFmpeg** instalado y en el `PATH`. Sin él no se lee `mp3` ni `ogg`.
2. **Python 3.11+** y `uv`, para el worker.
3. **`HF_TOKEN`** en el entorno, y la licencia de
   `pyannote/speaker-diarization-3.1` aceptada en la web del modelo. Sin ambas
   cosas, la etapa de diarización no arranca.

## Compilación multiplataforma

`bun build --compile` produce un binario para la plataforma actual. Para
publicar en varias, hay que pasar el objetivo de forma explícita:

```bash
bun build packages/cli/src/main.ts --compile --target=bun-darwin-arm64 --outfile dist/kov-darwin-arm64
bun build packages/cli/src/main.ts --compile --target=bun-darwin-x64   --outfile dist/kov-darwin-x64
bun build packages/cli/src/main.ts --compile --target=bun-linux-x64    --outfile dist/kov-linux-x64
```

## Versionado

`package.json` y `worker/pyproject.toml` deben llevar **el mismo número**. Un
desajuste entre la CLI y el worker rompe el contrato en tiempo de ejecución y es
difícil de diagnosticar desde el lado del usuario.

## Comprobaciones antes de publicar

Ninguna es opcional:

```bash
git status --short     # árbol limpio
bun run lint
bun run test
bun run typecheck
bun run build && ./dist/kov --version
```

Y una verificación manual sobre audio real: las pruebas unitarias no dicen si el
resultado suena bien. Procesa al menos un archivo de `fixtures/` y escúchalo.

## Reversión

Un release con un binario roto se retira, no se parchea en caliente:

```bash
gh release delete v<version> --yes
git push --delete origin v<version>
```

Después se corrige, se sube el parche de versión y se publica de nuevo.
