# Fixtures

## tone.mp3 (commiteado)

Un seno de 440 Hz, dos segundos, estéreo a 44.1 kHz. Deliberadamente **no** es
mono 16 kHz, para que pasarlo por `kov` demuestre que la etapa de decodificación
realmente convierte. Se regenera con:

```bash
ffmpeg -f lavfi -i "sine=frequency=440:duration=2" -ac 2 -ar 44100 -y fixtures/tone.mp3
```

Sirve como prueba de humo de F0. **No sirve** para juzgar calidad de limpieza:
un tono puro no tiene ruido que quitar ni voz que preservar.

## generated/ (no commiteado)

El corpus de medición. Se regenera desde una semilla, así que no se versiona:

```bash
bun run fixtures     # genera el corpus
bun run eval         # lo mide con SI-SDR
```

Estructura:

```
fixtures/generated/
├── clean/       voz sintetizada, sin ruido — la referencia
├── noise/       cada tipo de ruido, para inspección
├── noisy/       las mezclas: 3 hablantes × 3 ruidos × 4 SNR = 36 archivos
└── manifest.json
```

**Por qué es sintético.** SI-SDR compara la señal recuperada contra la señal
limpia original. Una grabación del mundo real no trae esa referencia: no existe
una versión sin ruido de una entrevista grabada en la calle. Al generar la voz
con `say` y el ruido desde una semilla, la referencia se conserva y la métrica
queda definida.

**Qué mide y qué no.** Este corpus responde "¿mejoró, y cuántos decibelios?".
No responde "¿suena bien para una persona". La segunda pregunta también importa,
pero no pertenece a una comprobación automática.

**Tipos de interferencia.**

| Tipo | Qué simula | Cómo se genera |
| ---- | ---------- | -------------- |
| `white` | Siseo de cinta, ventilador | Ruido gaussiano |
| `brown` | Tráfico, aire acondicionado | Integral del blanco, −6 dB por octava |
| `hum` | Zumbido de red eléctrica | 50 Hz con armónicos |
| `music` | Música de fondo (F2) | Progresión I–vi–IV–V con bajo y percusión |

La pista de música es **sintética a propósito**: nada en este repositorio puede
llevar derechos de autor ajenos, y un generador con semilla mantiene el corpus
reproducible. Es un test más débil que música real, que es con lo que Demucs fue
entrenado. Sirve para comparar separadores entre sí; no para afirmar cuánto
mejora sobre una canción de verdad.

**Requisitos.** El generador usa `say`, así que **solo funciona en macOS**, y
`ffmpeg` para convertir a PCM. Ambos fallan con un mensaje accionable si faltan.

El corpus se genera a **48 kHz**, la frecuencia del pipeline. Ojo con esto: `say`
sintetiza a una frecuencia menor, así que la voz del corpus no tiene banda alta
real. Sirve para comparar denoisers entre sí; no sirve para afirmar cómo suena
el resultado sobre una grabación real de banda completa.

## Resultados

Medidos el 2026-09-01. La base es sin ninguna etapa de limpieza; la ganancia es
DeepFilterNet 3 sobre el corpus completo.

| Ruido | Archivos | SI-SDR base | Ganancia F1 |
| ----- | -------- | ----------- | ----------- |
| white | 12 | +8.75 dB | **+12.01 dB** |
| hum | 12 | +8.76 dB | **+10.69 dB** |
| brown | 12 | +8.75 dB | **+4.07 dB** |

### F2: el resultado que nadie esperaba

Las dos configuraciones se midieron sobre los mismos 48 archivos, 48 de 48
procesados, cero fallos:

| Interferencia | Solo denoise | Denoise + separate | Efecto de F2 |
| ------------- | ------------ | ------------------ | ------------ |
| music | +8.38 dB | +8.44 dB | **+0.06** |
| brown | +4.07 dB | **+11.21 dB** | **+7.14** |
| hum | +10.69 dB | **+13.49 dB** | **+2.80** |
| white | +12.01 dB | +11.76 dB | −0.25 |

**F2 casi no aporta en aquello para lo que se construyó, y resuelve un problema
al que no apuntaba.** Sobre música gana 0.06 dB. Sobre ruido de baja frecuencia
gana 7.14 dB, que es exactamente donde F1 quedó documentado como débil.

El mecanismo encaja: `htdemucs` tiene un stem dedicado de `bass`, así que desvía
la energía grave fuera de `vocals`. DeepFilterNet no tiene esa estructura y no
puede separar un retumbe grave de una voz grave.

La voz masculina, que con F1 no ganaba nada contra ruido marrón, se recupera:

| Hablante | brown, solo F1 | brown, F1 + F2 |
| -------- | -------------- | -------------- |
| en-female | +10.0 dB | +14.4 dB |
| es-female | +1.8 dB | +10.7 dB |
| **en-male** | **+0.4 dB** | **+8.5 dB** |

**No leas esto como "Demucs no sirve con música".** El corpus usa una progresión
de acordes sintética: periódica y tonal, probablemente mucho más fácil de quitar
para DeepFilterNet que una grabación real. La conclusión honesta es que nuestro
sustituto de música es demasiado fácil para distinguir a los dos modelos, no que
F2 carezca de valor sobre música real. Confirmarlo exigiría música con licencia,
fuera del alcance de un corpus que vive en un repositorio público.

## Conversaciones (F3)

Una mezcla con ruido necesita una referencia limpia. Una conversación necesita
más: la contribución de **cada** hablante a la línea de tiempo, quién habla
cuándo, y **dos respuestas distintas** a "qué voz conservamos":

- `dominant` — a quién elegirá el heurístico automático: más tiempo hablando,
  desempate por volumen. Es el espejo exacto de `dominantSpeakerSelector` en
  `packages/core`.
- `intended` — a quién quiere conservar la persona.

En los escenarios fáciles coinciden. En dos escenarios **no coinciden a
propósito**, porque el heurístico está documentado como frágil justo ahí.

```
fixtures/generated/conversations/
├── two-clean.wav              # la mezcla
├── two-clean_en-female.wav    # lo que un extractor perfecto devolvería
├── two-clean_en-male.wav
└── ...
```

Cada referencia es la pista de ese hablante sobre la línea de tiempo compartida,
en silencio donde no habla. La mezcla es la suma exacta de las referencias.

### Escenarios y línea base

| Escenario | Quiere | Elige el heurístico | ¿Acierta? | SI-SDR base |
| --------- | ------ | ------------------- | --------- | ----------- |
| `two-clean` | en-female | en-female | sí | +8.33 dB |
| `two-overlap` | en-female | en-female | sí | +8.34 dB |
| `three-overlap` | en-female | en-female | sí | +2.04 dB |
| `two-hard-duration` | en-female | **en-male** | **NO** | +3.12 dB |
| `two-hard-loudness` | en-female | **en-male** | **NO** | −0.18 dB |

La línea base mide cuán enterrada está la voz deseada dentro de la mezcla. F3
tiene que superarla.

`two-hard-loudness` es el caso más duro: **−0.18 dB**, la voz que se quiere está
por debajo de todo lo demás junto. El interlocutor estaba más cerca del
micrófono, habló lo mismo, y el heurístico se va con él.

### Qué debe medir F3

Dos cosas separadas, y confundirlas es el error fácil:

1. **¿Apuntó a la voz correcta?** Es binario, y `heuristic_agrees` ya lo reporta.
2. **¿Qué tan limpia quedó la voz extraída?** SI-SDR contra la referencia de
   `intended`.

Una extracción perfecta de la voz equivocada da un SI-SDR pésimo contra
`intended`. Un promedio que mezcle ambos casos no dice nada útil. **Reporta las
dos por separado.**

Los dos escenarios difíciles existen para que ese fallo aparezca en una tabla y
no en la grabación de alguien. Cuando exista `--speaker <id>` o la selección por
muestra de referencia, estos son los archivos donde se demuestra que sirven.

## Por qué existe este corpus

Sin medición, F1 se habría publicado como "DeepFilterNet funciona bien" y el
fallo con voces graves habría aparecido en producción. Y F2 se habría publicado
como "separa la música", cuando su valor medible hoy es otro completamente
distinto.

En los dos casos, el promedio agregado escondía el hallazgo. **Desglosa siempre
por hablante y por tipo de interferencia.**

Dos comprobaciones respaldan estos números:

- **El SI-SDR medido coincide con el SNR solicitado** en cada mezcla (0.00, 5.00,
  10.00, 20.00 dB). El mezclador y el medidor son rutas de código independientes;
  que concuerden descarta un error de escala en cualquiera de las dos.
- **El corpus se regenera byte a byte idéntico.** Verificado por hash sobre voz,
  ruido y mezclas. `say` resultó ser determinista, así que las mediciones se
  pueden comparar entre regeneraciones sin recalibrar.

**F1 tiene que superar estos números.** Un denoiser que no mueva la aguja sobre
esta tabla no entra, por bien que suene en una escucha informal.

## Reglas

Los clips se mantienen cortos: pocos segundos. Nunca se commitea audio pesado ni
con derechos de autor. Si aportas grabaciones reales, van fuera del repositorio.
