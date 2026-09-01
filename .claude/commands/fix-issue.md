---
description: Workflow completo para resolver un issue de GitHub en keep-one-voice
argument-hint: "<numero-de-issue>"
allowed-tools: Bash(gh issue view:*), Bash(git switch:*), Bash(git status:*), Bash(git diff:*), Bash(bun run test:*), Bash(bun run lint:*), Read, Edit, Grep, Glob
---

# Resolver el issue #$1

## 1. Entender antes de tocar código

- `gh issue view $1 --comments` para leer el issue y toda la discusión.
- Identifica **en qué capa** vive el problema. No es lo mismo un fallo en el
  parseo de argumentos que uno en un modelo de separación:
  - `packages/cli` → argumentos, salida, códigos de retorno.
  - `packages/core` → orquestación, contrato, selección de hablante.
  - `worker/` → decodificación, denoise, separación, diarización.
- Si el issue no describe una reproducción, pídela antes de seguir. No adivines.

## 2. Reproducir

Reproduce el fallo con un caso mínimo y verificable. Si necesitas audio de
prueba, usa un fragmento corto en `fixtures/`; nunca añadas archivos pesados.

**Si no puedes reproducirlo, detente aquí y repórtalo.** Arreglar un bug que no
observaste es escribir código a ciegas.

## 3. Rama

El trabajo siempre sale de `dev`, nunca de `master`:

```bash
git switch -c fix/<descripcion-breve> dev
```

## 4. Corregir con TDD

1. Escribe la prueba que falla y **verifica que falla** por la razón correcta.
2. Implementa el cambio mínimo que la hace pasar.
3. Refactoriza con las pruebas en verde.

Si el cambio toca el contrato entre TypeScript y Python, actualiza **los dos
lados** y prueba ambos. Es el punto donde este proyecto se rompe en silencio.

## 5. Verificar

```bash
bun run lint
bun run test
```

## 6. Commit

Conventional Commits, en inglés, imperativo, asunto de 72 caracteres como
máximo. Cierra el issue desde el cuerpo del commit:

```
fix: reject stage list with unknown entries

Closes #$1
```

Sin atribución a IA ni líneas `Co-Authored-By`.
