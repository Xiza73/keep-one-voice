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

**Tipos de ruido.** `white` (siseo de cinta, ventilador), `brown` (tráfico, aire
acondicionado: integral del ruido blanco, pendiente de −6 dB por octava) y `hum`
(zumbido de red a 50 Hz con armónicos).

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

### Limitación conocida: voces graves con ruido de baja frecuencia

El promedio de `brown` esconde el hallazgo importante. Desglosado por hablante:

| Hablante | Ganancia media con `brown` |
| -------- | -------------------------- |
| en-female | +10.0 dB |
| es-female | +1.8 dB |
| **en-male** | **+0.4 dB** |

La voz masculina **no mejora prácticamente nada** con ruido marrón, en ningún
SNR probado (+0.35, +0.35, +0.43, +0.62 dB). El ruido marrón concentra energía
en graves, justo donde una voz grave tiene su fundamental, y el modelo no las
separa.

Trátalo como una señal a investigar, no como un defecto probado: el corpus usa
voz sintetizada, y `Fred` de macOS tiene características espectrales atípicas.
Confirmarlo exige grabaciones reales de voces graves con ruido de tráfico o
motor.

Este hallazgo es la razón de ser del corpus. Sin él, F1 se habría publicado como
"DeepFilterNet funciona bien" y el fallo habría aparecido en producción, en el
caso de uso más común que existe: alguien grabando dentro de un auto.

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
