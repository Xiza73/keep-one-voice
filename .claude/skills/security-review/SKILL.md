---
name: security-review
description: Revisión de seguridad específica de keep-one-voice. Actívala cuando el cambio toque entrada de archivos de audio de terceros, invocación de FFmpeg, arranque del worker de Python, descarga de pesos de modelos, manejo de HF_TOKEN, rutas de escritura o archivos temporales.
allowed-tools: Read, Grep, Glob, Bash(git diff:*), Bash(git log:*)
---

# Revisión de seguridad — keep-one-voice

Esta herramienta recibe **archivos que el usuario no creó** y los pasa por
**procesos externos**. Ese es todo el modelo de amenaza en una frase.

## Superficies de riesgo

### 1. Entrada: archivos de audio de terceros

Un `mp3` u `ogg` es un contenedor complejo parseado por código nativo. Un
archivo manipulado puede provocar consumo desmedido de memoria o disco.

Verifica:
- Se valida el tamaño y la duración **antes** de decodificar, no después.
- Existe un límite superior de duración con un mensaje claro al superarlo.
- El formato se determina por el contenido (`ffprobe`), no por la extensión.

### 2. Invocación de procesos externos (FFmpeg, Python)

Es la vulnerabilidad más probable de este proyecto.

Verifica:
- Los procesos se lanzan con un **arreglo de argumentos**, nunca concatenando
  cadenas en una shell. Nada de `shell: true` con entrada del usuario.
- Un nombre de archivo que empiece con `-` no puede convertirse en una bandera
  de FFmpeg. Se usa `--` o una ruta absoluta.
- Hay timeout y el proceso hijo se termina si se excede.
- Los procesos hijo se limpian al fallar o al interrumpir con `SIGINT`.

### 3. Rutas de archivo

Verifica:
- La ruta de salida se resuelve y se comprueba antes de escribir. Un `../` en la
  entrada no debe permitir escribir fuera del destino previsto.
- Los archivos temporales se crean con permisos restrictivos y se borran, incluso
  cuando el pipeline falla a mitad de camino.
- No se sobrescribe la entrada del usuario sin confirmación explícita.

### 4. Modelos y credenciales

Verifica:
- `HF_TOKEN` se lee del entorno. **Nunca** aparece en código, en logs, en
  mensajes de error ni en el repositorio.
- Los pesos se descargan solo desde repositorios de modelos declarados en el
  código, no desde una URL que venga de la entrada del usuario.
- No hay ejecución de código arbitrario al cargar un modelo. `torch.load` con
  `weights_only=False` sobre un archivo no confiable ejecuta código: no se usa.
- Los pesos no están commiteados.

### 5. Privacidad

El audio procesado puede contener conversaciones privadas.

Verifica:
- Nada del contenido del audio se envía fuera de la máquina sin que el usuario
  lo pida de forma explícita.
- Las transcripciones y los archivos intermedios no quedan en `/tmp` de forma
  indefinida.
- Los logs no incluyen transcripciones ni rutas completas de archivos del usuario
  cuando no hace falta.

## Cómo reportar

Para cada hallazgo: archivo y línea, la superficie afectada, y **el escenario
concreto de explotación**. Si el escenario no se sostiene, no es un hallazgo.
No infles el reporte con observaciones genéricas.
