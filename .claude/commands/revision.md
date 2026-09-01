---
description: Revisión de código del diff actual en keep-one-voice (TypeScript + worker de Python)
argument-hint: "[ruta o rama base] (opcional, por defecto el diff contra main)"
allowed-tools: Bash(git diff:*), Bash(git status:*), Bash(git log:*), Bash(bun run lint:*), Bash(bun run test:*), Read, Grep, Glob
---

# Revisión de código

Objetivo de revisión: `$ARGUMENTS` (si está vacío, revisa el diff de la rama
actual contra `dev`, que es la rama de integración).

## 1. Reunir el contexto

- `git status --short` para ver el estado del árbol de trabajo.
- `git diff dev...HEAD` (o el objetivo indicado) para obtener el diff completo.
- Lee `CLAUDE.md` si aún no lo tienes en contexto: las convenciones de este
  proyecto mandan sobre cualquier preferencia general.

## 2. Revisar por dimensiones

Reporta solo hallazgos que puedas justificar con un escenario de fallo concreto.
Ordena de más grave a menos grave.

**Corrección**
- ¿El contrato entre TypeScript y Python sigue alineado? Un cambio en
  `packages/core/src/index.ts` que no se refleja en `worker/src/kov_worker/protocol.py`
  (o al revés) rompe el pipeline en silencio. Esta es la falla más común aquí.
- ¿Los errores esperables se devuelven como `Result` en vez de lanzarse?
- ¿Hay casos límite sin cubrir? Audio vacío, un solo hablante, silencio total,
  archivo corrupto, ruta inexistente.

**Pruebas**
- ¿Cada cambio de comportamiento llegó con su prueba? TDD estricto está activo.
- ¿Las pruebas describen comportamiento observable o detalles internos?

**Arquitectura**
- ¿`packages/core` importa algo de `packages/cli` o del worker? Si es así, la
  dependencia está invertida y debe corregirse.

**Recursos**
- ¿Se liberan los procesos hijo y los descriptores de archivo?
- ¿Hay audio o pesos de modelos añadidos al repositorio? No deben estar.

**Convenciones**
- Código, identificadores, comentarios y salida de la CLI en inglés.
- Sin `npm`, `yarn`, `pnpm` ni `pip install` directo.

## 3. Verificar

Ejecuta `bun run lint` y `bun run test` antes de dar la revisión por cerrada.

## 4. Reportar

Para cada hallazgo: archivo y línea, qué falla, y el escenario concreto que lo
provoca. Si no encuentras nada, dilo claramente en lugar de inventar
observaciones menores para llenar el reporte.
