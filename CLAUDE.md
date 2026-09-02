# keep-one-voice

## 1. Contexto del proyecto

`keep-one-voice` (binario: `kov`) es una CLI que recibe un archivo de audio
(`mp3`, `ogg`, `m4a`, `wav`) y devuelve una pista limpia con **una sola voz: la
principal**. Elimina ruido ambiente, música de fondo y voces secundarias.

**Problema que resuelve.** Las grabaciones reales —entrevistas, notas de voz,
reuniones, capturas de campo— llegan con aire acondicionado, calle, música y
varias personas hablando encima. Aislar una voz a mano exige conocimiento de
edición de audio y mucho tiempo.

**Enfoque.** TypeScript sobre Bun para la CLI y la orquestación; Python como
worker de ML, porque ahí vive el ecosistema real de separación de fuentes
(PyTorch, Demucs, pyannote, DeepFilterNet). La frontera entre ambos es un
contrato explícito, no una llamada dispersa por el código.

## 2. Usuarios y alcance (MVP)

**Usuarios.** Personas que procesan grabaciones habladas: periodistas,
podcasters, investigadores, equipos de soporte, cualquiera con notas de voz
sucias.

**El MVP se construye por capas.** Cada fase es entregable y verificable por sí
sola. No se avanza a la siguiente sin métricas de calidad de la anterior.
Depurar un pipeline de cuatro etapas a ciegas no es una opción.

| Fase | Entrega | Modelo de referencia |
| ---- | ------- | -------------------- |
| F0 | I/O: decodificar a PCM mono 48 kHz, escribir el resultado, contrato con el worker | FFmpeg |
| F1 | Denoise: quitar ruido de fondo con una sola voz presente | DeepFilterNet 3 |
| F2 | Separación de stems: voz contra música e instrumentos | Demucs v4 |
| F3 | Diarización + extracción del hablante dominante | pyannote 3.1 |
| F4 (opcional) | Transcripción de la pista resultante | faster-whisper |

**Selección del hablante.** El MVP elige automáticamente la voz dominante
(mayor energía y mayor tiempo de presencia). Este heurístico **falla** cuando el
interlocutor habla más fuerte o más tiempo que el objetivo. Por eso la selección
vive detrás del puerto `SpeakerSelector`: añadir `--speaker <id>` o una muestra
de referencia después no debe reescribir el pipeline.

**Fuera de alcance del MVP.** Interfaz gráfica, procesamiento en tiempo real,
clonación o síntesis de voz, y despliegue como servicio.

## 3. Stack y herramientas

- **Runtime y packager:** Bun 1.3+. Es el gestor de paquetes del proyecto; no se
  usa `npm`, `yarn` ni `pnpm`.
- **CLI y orquestación:** TypeScript en modo `strict`.
- **Worker de ML:** Python 3.11+, gestionado con `uv`. **No** se usa el Python
  del sistema.
- **Testing:** `bun:test` para TypeScript, `pytest` para Python.
- **Lint y formato:** Biome para TypeScript, Ruff para Python.
- **Audio:** FFmpeg para decodificar y remuestrear.
- **Estructura:** monorepo con workspaces de Bun. Dos runtimes con árboles de
  dependencias y toolchains distintos no comparten un paquete único.

## 4. Comandos clave

```bash
bun install              # dependencias de TypeScript
bun run setup:py         # crea el entorno de Python del worker (uv sync)

# Los modelos son extras opcionales, separados por fase, para no arrastrar el
# stack de una etapa mientras se trabaja en otra:
cd worker && uv sync --extra denoise      # F1: DeepFilterNet 3

bun run dev              # ejecuta la CLI en desarrollo
bun run build            # compila el binario en dist/kov

bun run test             # todas las pruebas (TypeScript + Python)
bun run test:ts          # solo bun:test
bun run test:py          # solo pytest

bun run fixtures         # genera el corpus de medición en fixtures/generated
bun run eval             # mide el corpus con SI-SDR (línea base y mejora)

bun run lint             # Biome + Ruff en modo verificación
bun run format           # Biome + Ruff aplicando cambios
```

## 5. Convenciones de código

**Idioma.** El código, los identificadores, los comentarios, la salida de la CLI
y los mensajes de error se escriben **en inglés**. La documentación del proyecto
se escribe en **español neutro**. No se usan regionalismos en ningún artefacto.

**TypeScript.**
- `strict: true` y `noUncheckedIndexedAccess`. Nada de `any`; si el tipo no se
  conoce, es `unknown` y se estrecha.
- Los errores esperables se devuelven como valores (`Result`), no se lanzan. Las
  excepciones quedan para fallos realmente inesperados.
- Sin efectos secundarios en la importación de un módulo.

**Python.**
- Anotaciones de tipo obligatorias en toda función pública.
- El worker no imprime nada por `stdout` salvo mensajes del protocolo. Los
  registros van a `stderr`.

**Arquitectura.** Hexagonal. `packages/core` define los puertos y la
orquestación y **no conoce** ni la CLI ni el proceso de Python. `packages/cli` y
el worker son adaptadores. Si `core` importa algo específico de un adaptador, la
dependencia está invertida y hay que corregirlo.

**Frecuencia de muestreo.** El pipeline trabaja a 48 kHz porque DeepFilterNet 3
trabaja ahí, y decodificar a una frecuencia menor destruiría la banda que ese
modelo tiene que limpiar. Las etapas que necesitan menos —la diarización opera a
16 kHz— remuestrean de su lado: producen marcas de tiempo, así que su frecuencia
no debe condicionar el audio que la persona escucha.

**Testing (TDD estricto).** Primero la prueba que falla, luego la
implementación mínima, luego el refactor. Las pruebas describen comportamiento
observable, no detalles internos. El audio de prueba vive en `fixtures/` y se
mantiene corto: fragmentos de pocos segundos, nunca archivos pesados en el
repositorio.

**Commits.** Conventional Commits: `<tipo>(<alcance>): <asunto>`. En inglés, en
imperativo, minúsculas, sin punto final. Asunto de 50 caracteres como ideal y
**72 como tope duro**. Sin atribución a IA ni líneas `Co-Authored-By`.

**Ramas.** `dev` es la rama de integración y la rama por defecto. `master`
recibe PRs **exclusivamente desde `dev`**, cuando los cambios acumulados
completan una versión. El trabajo diario sale de `dev` en ramas `feat/`, `fix/`,
`chore/`, `docs/`, `refactor/` o `test/`.

Los merges se hacen siempre con commit de merge (`--no-ff`). No se hace squash
ni rebase sobre la rama destino: ambos destruyen la granularidad intencional de
los commits.

## 6. Estructura del repositorio

```
keep-one-voice/
├── CLAUDE.md                 # este archivo (commiteado)
├── CLAUDE.local.md           # overrides personales (ignorado por git)
├── .mcp.json                 # servidores MCP compartidos del equipo
├── biome.json                # lint y formato de TypeScript
├── package.json              # raíz del workspace y scripts del proyecto
├── tsconfig.json
├── .claude/                  # configuración de Claude Code (ver sección 8)
├── packages/
│   ├── core/                 # dominio: puertos, contratos y orquestación
│   └── cli/                  # adaptador: parseo de argumentos y salida
├── worker/                   # motor de ML en Python
│   ├── pyproject.toml
│   ├── src/kov_worker/
│   └── tests/
└── fixtures/                 # audio corto para pruebas
```

## 7. Integraciones externas

- **FFmpeg** — decodifica `mp3`/`ogg`/`m4a` y remuestrea a PCM mono 48 kHz. Es
  una dependencia del sistema, no del paquete. La CLI debe verificar su presencia
  al arrancar y fallar con un mensaje accionable si falta.
- **Hugging Face Hub** — descarga los pesos de los modelos.
  `pyannote/speaker-diarization-3.1` es una **compuerta manual**: exige aceptar
  la licencia en la web del modelo y un token de acceso en `HF_TOKEN`. Sin eso,
  la fase F3 no arranca. El error debe decirlo con esas palabras.
- **faster-whisper** — transcripción opcional de la pista resultante (F4).

Los pesos de los modelos **nunca** se commitean. Se descargan bajo demanda y se
cachean fuera del repositorio.

## 8. Reglas de trabajo con Claude

**Qué hacer.**
- Leer el contrato entre TypeScript y Python antes de tocar cualquiera de los dos
  lados. Es la frontera más fácil de romper en silencio.
- Escribir primero la prueba que falla. TDD estricto está activo.
- Usar `bun` para todo lo de JavaScript y `uv run` para todo lo de Python.
- Verificar la calidad del audio con métricas (SI-SDR, PESQ) y no con
  impresiones. "Suena mejor" no es un criterio verificable.
- Preguntar cuando el alcance sea ambiguo, en vez de asumir.

**Qué NO hacer.**
- No usar `npm`, `yarn`, `pnpm` ni `pip install` directo.
- No instalar nada en el Python del sistema.
- No añadir modelos, audio pesado ni `node_modules` al repositorio.
- No saltar fases del MVP. F3 sin F1 y F2 medidas es depurar a ciegas.
- No inventar nombres de modelos, versiones ni APIs de Hugging Face: se
  verifican antes de escribirlos.
- No poner regionalismos ni voz de persona en el código, la salida de la CLI, los
  comentarios ni los commits.
- No commitear `CLAUDE.local.md` ni `.claude/settings.local.json`.
