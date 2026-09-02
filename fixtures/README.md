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

## Línea base

Medida el 2026-09-01, sin ninguna etapa de limpieza implementada:

| Ruido | Archivos | SI-SDR base |
| ----- | -------- | ----------- |
| white | 12 | +8.75 dB |
| brown | 12 | +8.75 dB |
| hum | 12 | +8.76 dB |

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
