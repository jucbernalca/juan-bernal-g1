# ATLAS CLOUD // SIGNAL-80

## Motor Inteligente de Triage y Correlacion de Incidentes

Aplicacion que recibe tickets de soporte en espanol y los convierte en informacion
operacional estructurada usando **GLM 5.2** como motor semantico principal.

---

## Stack

| Componente | Tecnologia |
|---|---|
| Lenguaje | Python 3.12 |
| Schema/Validacion | Pydantic v2 |
| Cliente HTTP | httpx (async) |
| Interfaz grafica | Streamlit |
| Tests | pytest + pytest-asyncio |
| Env vars | python-dotenv |

---

## Arquitectura

```
tickets_sample.json
    │
    ▼
Ingester (valida JSON, campos, timestamps)
    │
    ▼
Processor (lote async con semaforo de concurrencia)
    │
    ▼
Classifier → GLM 5.2 (prompt + validacion + retries + abstencion)
    │
    ▼
Correlator (agrupa por similitud, categoria, modulo, region, tiempo)
    │
    ▼
IncidentDetector (detecta incidentes mayores, reprioriza)
    │
    ▼
Control Room (Streamlit: cola, filtros, detalle, grupos, formulario)
```

### Estructura de directorios

```
src/
├── config.py              # Variables de entorno
├── core/
│   ├── models.py          # Schemas Pydantic
│   ├── classifier.py      # Clasificacion GLM 5.2
│   ├── correlator.py      # Correlacion de tickets
│   └── incident_detector.py  # Incidentes mayores + brief ejecutivo
├── api/
│   ├── glm_client.py      # Cliente GLM 5.2 (retries, backoff, rate limit)
│   └── prompts.py         # Prompts del sistema
├── pipeline/
│   ├── ingester.py        # Carga y validacion de tickets
│   ├── processor.py       # Pipeline de procesamiento por lote
│   └── validator.py       # Validacion de entrada/salida
└── ui/
    └── app.py             # Streamlit Control Room
tests/                     # pytest
data/                      # Dataset de ejemplo
docs/                      # Bitacora de IA
```

---

## Configuracion de GLM 5.2

1. Copia `.env.example` a `.env`
2. Edita `GLM_API_KEY` con tu API key real
3. Las demas variables tienen valores por defecto

### Variables de entorno

| Variable | Default | Descripcion |
|---|---|---|
| `GLM_API_KEY` | (vacio) | API key de GLM 5.2 |
| `GLM_API_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | URL base de la API |
| `GLM_MODEL` | `glm-5.2` | Modelo a usar |
| `GLM_TIMEOUT` | `30` | Timeout por solicitud (segundos) |
| `GLM_MAX_RETRIES` | `3` | Maximo de reintentos |
| `GLM_TEMPERATURE` | `0.1` | Temperature del modelo |
| `GLM_MAX_TOKENS` | `1024` | Max tokens de respuesta |
| `ABSTENTION_THRESHOLD` | `0.60` | Umbral de abstencion |
| `MAJOR_INCIDENT_MIN_TICKETS` | `5` | Min tickets para incidente mayor |
| `MAJOR_INCIDENT_WINDOW_MINUTES` | `10` | Ventana temporal para correlacion |
| `MAX_CONCURRENCY` | `5` | Concurrencia maxima de procesamiento |
| `RATE_LIMIT_RPS` | `2.0` | Rate limit (requests por segundo) |

---

## Instalacion

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## Ejecucion

### Interfaz grafica (Control Room)

```bash
streamlit run src/ui/app.py
```

### Procesamiento por lote (script)

```python
import asyncio
from src.pipeline.processor import Processor

async def main():
    processor = Processor()
    result = await processor.process_file("data/tickets_sample.json")
    print(f"Exitosos: {result.successful}, Fallidos: {result.failed}")

asyncio.run(main())
```

---

## Tests

```bash
pytest tests/ -v
```

---

## Validacion de respuestas

- Schema Pydantic valida todos los campos de salida
- Categoria invalida → degrada a "Otro"
- Prioridad invalida → degrada a "P3"
- Confianza fuera de rango → clampeada a [0.0, 1.0]
- Campos faltantes → error de validacion

---

## Politica de retries

- Backoff exponencial: 1s, 2s, 4s
- Maximo 3 intentos (configurable via `GLM_MAX_RETRIES`)
- Rate limit (429) → espera exponencial adicional
- Tras agotar retries → degrada graceful (categoria "Otro", prioridad "P3", revision humana)

---

## Criterio de abstencion

- Si `confidence < 0.60` → `requires_human_review = true`
- Umbral configurable via `ABSTENTION_THRESHOLD`

---

## Estrategia de correlacion

- Union-Find para agrupar tickets relacionados
- Heuristica basada en: categoria, modulo, region, proximidad temporal, entidades compartidas
- Score >= 0.50 → tickets relacionados
- Opcional: GLM 5.2 para validacion semantica (`use_glm=True`)
- Deteccion de incidente mayor: 5+ tickets P1/P2 + mismo grupo + ventana 10 min
- Repriorizacion por blast radius: 10+ tickets → P1 operacional

---

## Defensa contra prompt injection

- Instrucciones del sistema separadas del texto del ticket (system vs user prompt)
- No se incluyen secretos en el prompt
- Validacion estricta de salida (schema Pydantic)
- Texto del ticket sanitizado (truncado, whitespace normalizado)
- El prompt explicitamente indica que el texto del ticket es DATO, no instruccion

---

## Bonos implementados

- **Bono A (Defensa adversarial):** Suite de tests con prompt injection, instrucciones contradictorias, texto largo, JSON incrustado
- **Bono B (Concurrencia):** Procesamiento async con semaforo y rate limiting
- **Bono C (Explicabilidad):** Registro auditable por ticket (model, attempts, validation_status, correlation_id)
- **Bono D (Brief ejecutivo):** Generacion automatica con GLM 5.2 para incidentes mayores

---

## Escenarios de demo

| Escenario | Entrada | Resultado |
|---|---|---|
| A — P1 evidente | "2300 usuarios sin acceso SSO" | P1 |
| B — Solicitud no urgente | "Modo oscuro" | P4 |
| C — Ticket ambiguo | "Tengo un problema" | confidence baja, requires_human_review |
| D — Respuesta invalida GLM | Salida incorrecta | App no se cae, reintenta o degrada |
| E — Tickets correlacionados | Multiples 503 API latam-north | INCIDENT_GROUP |
| F — Incidente mayor | 5+ tickets P1/P2 relacionados | major_incident_candidate = true |
