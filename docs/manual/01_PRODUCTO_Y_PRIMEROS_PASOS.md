# 01 — Producto y primeros pasos

## Explicación simple

Yo construí Wyss como un asistente operativo que recibe una instrucción, la transforma en un plan, evalúa el riesgo, solicita confirmación cuando corresponde, ejecuta mediante herramientas controladas y deja auditoría.

Wyss no es un chatbot con acceso libre a la computadora. El modelo puede proponer, pero una política determinista decide el nivel A, B, C o D.

## Ejemplo cotidiano

Pienso Wyss como una empresa pequeña:

- el owner define el objetivo;
- el orquestador prepara el trabajo;
- la política actúa como seguridad y compliance;
- las herramientas son los empleados que tocan archivos, Git, shell o Notion;
- la auditoría es el libro donde queda registrado todo;
- el teléfono es una consola remota, no la autoridad final.

## Cómo lo explicaría yo

> Yo uso Wyss para delegar tareas operativas sin entregar control absoluto a una IA. Cada acción pasa por una política fija, y las acciones sensibles requieren mi confirmación.

## Niveles de acción

| Nivel | Ejemplo | Comportamiento |
|---|---|---|
| A | leer un archivo o consultar Git | ejecución directa |
| B | mover o registrar un cambio normal | confirmación simple |
| C | borrar, escribir o ejecutar algo sensible | confirmación fuerte `CONFIRMAR` |
| D | formatear discos o romper protecciones | rechazo absoluto |

Yo no permito confirmar un nivel D.

## Capacidades

- indexación y búsqueda híbrida;
- daemon JSON-RPC;
- planificación determinista o LLM opt-in;
- política A–D;
- ejecución de archivos, shell y Git;
- undo para acciones de archivo compatibles;
- auditoría SQLite;
- ledger financiero Pellegrini integrado en el estado actual;
- rutinas programadas;
- memoria del owner con trust tiers;
- digest diario;
- Notion como herramienta gateada;
- intake n8n opt-in;
- web PC/PWA;
- pairing por token y QR;
- APK Android con pinning TOFU.

## Requisitos

- Linux para el flujo principal actual;
- Python 3.12 o superior;
- `uv`;
- `libmagic`;
- Node/npm para la web;
- Android SDK/Gradle para reconstruir el APK;
- Ollama opcional para embeddings locales;
- proveedores externos opcionales según configuración.

## Instalación

```bash
uv sync
cp config/config.example.toml config/config.toml
cp config/.env.example config/.env
```

Yo completo únicamente los secretos que necesito. Para una primera ejecución mantengo:

```toml
[orchestrator]
mode = "deterministic"
```

## Validación

```bash
uv run pytest
uv run mypy
uv run ruff check src tests
uv run lint-imports
```

## Primer arranque

Terminal 1:

```bash
uv run wyss start
```

Terminal 2:

```bash
uv run wyss ask "leé /tmp/wyss-demo.txt"
uv run wyss audit
```

## Primera prueba segura

1. creo un archivo de prueba en `/tmp`;
2. pido una lectura nivel A;
3. pido moverlo o borrarlo;
4. compruebo que queda pendiente;
5. rechazo la primera confirmación;
6. repito y confirmo;
7. reviso auditoría y undo.

No pruebo sobre documentos reales hasta comprender los resultados.

## Web y teléfono

```bash
uv run wyss web --lan --tls
```

El comando imprime URL y huella del certificado. Yo verifico la huella, abro el pairing una vez y luego uso la cookie persistente.

## APK

El APK ya fue validado en un teléfono real para instalación, QR y carga del bridge. Reconstruirlo requiere el toolchain móvil y repetir los checkpoints del capítulo de pruebas.

## Criterio de confianza

Yo aumento permisos y proveedores gradualmente:

1. deterministic + lectura;
2. archivos de prueba;
3. web local;
4. teléfono;
5. rutinas y memoria;
6. Notion en páginas de prueba;
7. LLM real;
8. acciones sobre datos importantes con backup.

El hecho de que una tarea funcione una vez no convierte al sistema en autoridad autónoma.