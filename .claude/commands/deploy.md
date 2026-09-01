---
description: Publicar una versión de keep-one-voice — compila el binario de la CLI y crea el release en GitHub
argument-hint: "[patch|minor|major]"
allowed-tools: Bash(git status:*), Bash(git log:*), Bash(git diff:*), Bash(bun run:*), Bash(bun test:*), Bash(git tag:*), Bash(gh release:*), Read, Edit
---

# Publicar versión (`$ARGUMENTS`)

Incremento solicitado: `$ARGUMENTS` (por defecto `patch`).

`keep-one-voice` se distribuye como un **binario compilado con Bun**, no como un
paquete de npm. El worker de Python no se publica: se instala desde el
repositorio con `uv sync`.

## 1. Comprobaciones previas (obligatorias)

Detente si alguna falla. No se publica sobre un árbol sucio ni con pruebas en
rojo.

Una versión se publica desde `master`, y `master` solo recibe cambios por PR
desde `dev`. Si estás en otra rama, detente.

```bash
git status --short          # el árbol debe estar limpio
git branch --show-current   # debe ser master
bun run lint
bun run test
bun run typecheck
```

## 2. Verificación manual del pipeline

Las pruebas unitarias no dicen si el audio suena bien. Antes de publicar,
procesa al menos un archivo real de `fixtures/` y confirma que la salida es
correcta:

```bash
bun run dev fixtures/sample.mp3 --output /tmp/kov-check.wav
```

## 3. Versión

Actualiza el campo `version` en `package.json` y en `worker/pyproject.toml`.
Ambos números deben coincidir.

## 4. Compilar

```bash
bun run build      # produce dist/kov
./dist/kov --version
```

## 5. Etiquetar y publicar

```bash
git commit -am "chore: release v<version>"
git tag -a v<version> -m "release: v<version>"
git push origin master --tags
gh release create v<version> dist/kov --title "v<version>" --generate-notes
```

## 6. Después de publicar

Verifica que el binario adjunto al release se descarga y ejecuta. Un release con
un binario roto es peor que no publicar.

## Requisitos del entorno para quien instala

Recuerda dejarlo escrito en las notas del release: el binario **necesita FFmpeg
en el sistema**, y la diarización **exige un token en `HF_TOKEN`** y haber
aceptado la licencia de `pyannote/speaker-diarization-3.1`.
