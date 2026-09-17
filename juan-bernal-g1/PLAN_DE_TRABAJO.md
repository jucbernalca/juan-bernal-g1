# PLAN DE TRABAJO — ATLAS CLOUD // SIGNAL-80

## Motor Inteligente de Triage y Correlacion de Incidentes

---

## 1. RESUMEN DEL RETO

| Parametro | Valor |
|---|---|
| Tickets en cola | 12.847 |
| Volumen de soporte | 18x normal |
| Tiempo hasta penalizaciones SLA | 80 minutos |
| Modelo IA | GLM 5.2 |
| Fases principales | 4 |
| Bonos | 4 (hasta +30 puntos) |
| Puntaje base maximo | 100 |

**Mision:** Convertir ruido en decisiones usando GLM 5.2. Construir un motor de
triage asistido por IA que encuentre lo urgente, agrupe senales relacionadas y
entregue una cola accionable.

---

## 2. DECISION DE STACK

| Componente | Tecnologia | Justificacion |
|---|---|---|
| Lenguaje | Python 3.11+ | Ecosistema IA, Pydantic nativo, rapido desarrollo |
| Schema/Validacion | Pydantic v2 | Validacion tipada, serializacion JSON, mencionado en el reto |
| Backend/API | FastAPI | Asincrono, rapido, documentacion automatica |
| Cliente HTTP | httpx | Soporte async, retries, timeouts configurables |
| Interfaz grafica | Streamlit | Minimalista, rapida de construir, sin diseño visual avanzado |
| Tests | pytest + pytest-asyncio | Testing asincrono, fixtures |
| Dataset | JSON | Formato requerido por el reto |
| Env vars | python-dotenv | Gestion de secretos sin hardcodear |

---

## 3. ARQUITECTURA PROPUESTA

```
atlas-signal80/
├── src/
│   ├── core/
│   │   ├── models.py          # Schemas Pydantic (Ticket, TriagedTicket, IncidentGroup, etc.)
│   │   ├── classifier.py      # Clasificacion con GLM 5.2 (Fase 1)
│   │   ├── correlator.py      # Correlacion de tickets (Fase 3)
│   │   └── incident_detector.py  # Deteccion de incidentes mayores (Fase 3)
│   ├── api/
│   │   ├── glm_client.py      # Cliente HTTP GLM 5.2 con retries/backoff (Fase 2)
│   │   └── prompts.py         # Prompts del sistema y plantillas
│   ├── pipeline/
│   │   ├── ingester.py        # Carga y validacion de tickets (Fase 1)
│   │   ├── processor.py       # Pipeline de procesamiento por lote (Fase 2)
│   │   └── validator.py       # Validacion de entrada y salida (Fase 2)
│   ├── ui/
│   │   └── app.py             # Streamlit Control Room (Fase 4)
│   └── config.py              # Configuracion desde variables de entorno
├── tests/
│   ├── test_classifier.py
│   ├── test_validator.py
│   ├── test_correlator.py
│   ├── test_adversarial.py
│   └── test_concurrency.py
├── data/
│   └── tickets_sample.json
├── docs/
│   └── sesion_ia.md           # Bitacora de uso de GLM 5.2
├── .env.example
├── requirements.txt
├── prompt_usado.txt
└── README.md
```

### Flujo de datos

```
tickets_sample.json
       │
       ▼
   Ingester (valida JSON, campos obligatorios, timestamps)
       │
       ▼
   Processor (procesa lote, maneja errores por ticket)
       │
       ▼
   Classifier → GLM 5.2 (prompt + validacion + retries + abstencion)
       │
       ▼
   Correlator (agrupa por similitud semantica, categoria, modulo, region, tiempo)
       │
       ▼
   IncidentDetector (detecta incidentes mayores, reprioriza por blast radius)
       │
       ▼
   Control Room (Streamlit: cola priorizada, filtros, detalle, grupos, formulario)
```

---

## 4. PLAN DETALLADO POR FASE

---

### FASE 0 — Preparacion (0-8 min)

**Objetivo:** Configurar proyecto, entorno y estructura base.

| # | Tarea | Entregable |
|---|---|---|
| 0.1 | Crear estructura de directorios | Arbol de carpetas |
| 0.2 | Crear `requirements.txt` con dependencias | Archivo de dependencias |
| 0.3 | Crear `.env.example` con variables de entorno | Template de config |
| 0.4 | Crear `config.py` para cargar configuracion | Modulo de config |
| 0.5 | Definir modelos Pydantic base (`Ticket`, `TriagedTicket`) | `src/core/models.py` |
| 0.6 | Crear `tickets_sample.json` con dataset de ejemplo (T1-T6) | Dataset inicial |

**Variables de entorno (.env.example):**
```
GLM_API_KEY=your-api-key-here
GLM_API_BASE_URL=https://open.bigmodel.cn/api/paas/v4
GLM_MODEL=glm-5.2
GLM_TIMEOUT=30
GLM_MAX_RETRIES=3
ABSTENTION_THRESHOLD=0.60
MAJOR_INCIDENT_MIN_TICKETS=5
MAJOR_INCIDENT_WINDOW_MINUTES=10
```

---

### FASE 1 — Triage estructurado (8-28 min)

**Objetivo:** Cargar tickets, clasificar con GLM 5.2 y producir salida estructurada.

**Puntaje en juego:** 20 puntos (triage core: 14 + 6)

| # | Tarea | Detalle | Entregable |
|---|---|---|---|
| 1.1 | Implementar `Ingester` | Carga desde JSON, valida campos obligatorios, maneja tickets malformados sin detener el lote | `src/pipeline/ingester.py` |
| 1.2 | Definir prompt de clasificacion | Prompt system con categorias validas, prioridades, guia orientativa. Separar instrucciones de datos del ticket | `src/api/prompts.py` |
| 1.3 | Implementar `GLMClient` basico | Llamada a GLM 5.2 con formato JSON, temperature baja | `src/api/glm_client.py` |
| 1.4 | Implementar `Classifier` | Envia ticket a GLM 5.2, parsea respuesta, mapea a `TriagedTicket` | `src/core/classifier.py` |
| 1.5 | Validar salida | Schema Pydantic valida categoria, prioridad, sentimiento, confianza, etc. | `src/core/models.py` |
| 1.6 | Manejo de errores de entrada | `ticket_id` vacio, `text` vacio, JSON invalido, campos faltantes, timestamps invalidos | `src/pipeline/validator.py` |
| 1.7 | Probar con dataset T1-T6 | Verificar categorias y prioridades orientativas | Test manual |

**Salida esperada por ticket:**
```json
{
  "ticket_id": "T-10482",
  "category": "Cuenta y acceso",
  "priority": "P1",
  "sentiment": "negativo",
  "product_or_module": "SSO",
  "summary": "Organizacion completa sin acceso mediante SSO despues del despliegue.",
  "suggested_action": "Escalar al equipo de identidad y verificar regresion del despliegue.",
  "suggested_response": "Estamos investigando de forma prioritaria...",
  "confidence": 0.94,
  "requires_human_review": false
}
```

**Categorias validas:** Cuenta y acceso, Facturacion, Disponibilidad y rendimiento,
Integraciones, Datos y exportacion, Solicitud de funcion, Seguridad, Otro

**Prioridades validas:** P1 (Critica), P2 (Alta), P3 (Normal), P4 (Baja)

---

### FASE 2 — Robustez de IA (28-45 min)

**Objetivo:** Integracion robusta con GLM 5.2, validacion, abstencion y manejo de fallos.

**Puntaje en juego:** 16 puntos (robustez IA: 10 + 6)

| # | Tarea | Detalle | Entregable |
|---|---|---|---|
| 2.1 | Schema de salida con Pydantic | `TriagedTicketSchema` con validacion estricta de todos los campos | `src/core/models.py` |
| 2.2 | Parser robusto de respuesta GLM | Extraer JSON de texto con pretexto, manejar JSON incompleto, limpiar markdown | `src/api/glm_client.py` |
| 2.3 | Politica de retries con backoff | Exponencial: 1s, 2s, 4s. Max 3 intentos. Evitar loops infinitos | `src/api/glm_client.py` |
| 2.4 | Timeouts configurables | Timeout por solicitud y total del lote | `src/api/glm_client.py` |
| 2.5 | Abstencion | Si `confidence < 0.60` → `requires_human_review = true` | `src/core/classifier.py` |
| 2.6 | Defensa contra prompt injection | Separar instrucciones (system) de datos (user). No incluir secretos. Validar salida estrictamente. Sanitizar texto del ticket | `src/api/prompts.py` |
| 2.7 | Registro auditable | Log por ticket: model, attempts, validation_status, correlation_id, processed_at. Sin secretos | `src/pipeline/processor.py` |
| 2.8 | Degradacion graceful | Si GLM falla tras retries: marcar `requires_human_review = true`, categoria "Otro", prioridad "P3" | `src/core/classifier.py` |
| 2.9 | Tests de robustez | Test JSON invalido, test timeout, test abstencion, test prompt injection | `tests/test_validator.py` |

**Ejemplo de registro auditable:**
```json
{
  "ticket_id": "T-10482",
  "model": "GLM-5.2",
  "attempts": 1,
  "validation_status": "valid",
  "correlation_id": "corr-A91D2",
  "processed_at": "2026-09-16T14:11:02Z"
}
```

---

### FASE 3 — Correlacion de incidentes (45-62 min)

**Objetivo:** Agrupar tickets relacionados, detectar incidentes mayores, repriorizar.

**Puntaje en juego:** 18 puntos (correlacion: 10 + 8)

| # | Tarea | Detalle | Entregable |
|---|---|---|---|
| 3.1 | Extraccion de caracteristicas | Categoria, modulo, region, entidades mencionadas, ventana temporal | `src/core/correlator.py` |
| 3.2 | Similitud semantica | Usar GLM 5.2 para evaluar si dos tickets describen el mismo problema. Alternativa: embeddings + umbral coseno | `src/core/correlator.py` |
| 3.3 | Algoritmo de agrupacion | Agrupar tickets por similitud (categoria + modulo + region + proximidad temporal + similitud semantica). Asignar `incident_group_id` | `src/core/correlator.py` |
| 3.4 | Resumen del grupo | Generar titulo, ticket_count, highest_priority, affected_module, affected_region, summary | `src/core/correlator.py` |
| 3.5 | Deteccion de incidente mayor | Regla: 5+ tickets P1/P2 + mismo grupo + ventana 10 min = `major_incident_candidate: true` | `src/core/incident_detector.py` |
| 3.6 | Repriorizacion por blast radius | Prioridad del incidente agregado basada en numero de clientes, regiones, servicio. No modifica prioridad individual | `src/core/incident_detector.py` |
| 3.7 | Tests de correlacion | Test con tickets relacionados, test con tickets similares pero NO relacionados (falsos positivos) | `tests/test_correlator.py` |

**Salida de grupo:**
```json
{
  "incident_group_id": "INC-003",
  "title": "Errores 503 en API de latam-north",
  "ticket_count": 18,
  "highest_priority": "P1",
  "affected_module": "API Gateway",
  "affected_region": "latam-north",
  "summary": "Multiples clientes reportan errores 503 despues del despliegue.",
  "major_incident_candidate": true
}
```

---

### FASE 4 — ATLAS Control Room (62-72 min)

**Objetivo:** Interfaz grafica funcional para que el jurado verifique sin curl/Postman.

**Puntaje en juego:** 12 puntos (interfaz: 8 + 4)

| # | Tarea | Detalle | Entregable |
|---|---|---|---|
| 4.1 | Layout principal de Streamlit | Sidebar con filtros, area principal con cola priorizada | `src/ui/app.py` |
| 4.2 | Cola priorizada | Tabla/lista con badges de color por prioridad (P1=rojo, P2=naranja, P3=amarillo, P4=verde) | `src/ui/app.py` |
| 4.3 | Filtros | Por prioridad, categoria, modulo, region, grupo de incidente | `src/ui/app.py` |
| 4.4 | Inspector de ticket | Panel de detalle: texto original, categoria, prioridad, sentimiento, resumen, accion, respuesta, confianza, revision humana, grupo | `src/ui/app.py` |
| 4.5 | Visualizacion de grupos | Vista de incidentes agrupados con tickets miembros, indicador de incidente mayor | `src/ui/app.py` |
| 4.6 | Formulario de ticket manual | Input de texto + boton para ejecutar pipeline completo sobre un ticket nuevo | `src/ui/app.py` |
| 4.7 | Carga de dataset | Boton para cargar `tickets_sample.json` y procesar lote completo | `src/ui/app.py` |

---

### FASE 5 — Bonos (72-78 min)

#### Bono A — Defensa adversarial (+8 puntos)

| # | Tarea | Entregable |
|---|---|---|
| A.1 | Crear suite de tickets adversariales | `data/tickets_adversarial.json` |
| A.2 | Tests: prompt injection, instrucciones contradictorias, texto largo, JSON incrustado, solicitud de secretos, contenido ambiguo | `tests/test_adversarial.py` |
| A.3 | Verificar que el sistema mantiene schema y no expone secretos | Validacion automatica |

#### Bono B — Procesamiento concurrente (+8 puntos)

| # | Tarea | Entregable |
|---|---|---|
| B.1 | Procesamiento async con `asyncio` y semaforo de concurrencia | `src/pipeline/processor.py` |
| B.2 | Control de cuota (rate limiting) | `src/api/glm_client.py` |
| B.3 | Test reproducible: no perder/duplicar/mezclar resultados | `tests/test_concurrency.py` |

#### Bono C — Explicabilidad exportable (+7 puntos)

| # | Tarea | Entregable |
|---|---|---|
| C.1 | Generar reporte estructurado para P1 e incidentes mayores | `src/core/reporter.py` |
| C.2 | Incluir: evidencia, decision, confianza, factores, timestamp, modelo, recomendacion | Reporte JSON/PDF |

#### Bono D — Brief ejecutivo automatico (+7 puntos)

| # | Tarea | Entregable |
|---|---|---|
| D.1 | Prompt a GLM 5.2 para generar brief ejecutivo de `MAJOR_INCIDENT_CANDIDATE` | `src/api/prompts.py` |
| D.2 | Manejar timeout, error API, respuesta vacia, formato invalido | `src/core/incident_detector.py` |
| D.3 | Salida: executive_summary, affected_scope, probable_pattern, recommended_next_actions | `src/core/models.py` |

---

### FASE 6 — Cierre (78-80 min)

| # | Tarea | Entregable |
|---|---|---|
| 6.1 | README.md completo | Stack, arquitectura, config, instalacion, ejecucion, tests, interfaz, bonos |
| 6.2 | Bitacora de IA (`docs/sesion_ia.md`) | Prompts, iteraciones, fallos resueltos, edge cases |
| 6.3 | Esquema de salida documentado | JSON Schema / Pydantic docs |
| 6.4 | Tests finales | Ejecutar suite completa |
| 6.5 | Commit final | Repositorio limpio, sin secretos |
| 6.6 | Preparacion de demo | Escenarios A-F listos para presentar |

---

## 5. ESCENARIOS DE DEMO (A-F)

| Escenario | Entrada | Resultado esperado |
|---|---|---|
| A — P1 evidente | "2.000 usuarios sin acceso" | Prioridad P1 |
| B — Solicitud no urgente | "Feature request modo oscuro" | Prioridad P4 |
| C — Ticket ambiguo | Informacion insuficiente | confidence baja, requires_human_review = true |
| D — Respuesta invalida GLM | Salida incorrecta simulada | App no se cae, reintenta o degrada |
| E — Tickets correlacionados | Varios clientes, mismo fallo, misma ventana | INCIDENT_GROUP asignado |
| F — Incidente mayor | Multiples tickets criticicos relacionados | major_incident_candidate = true |

---

## 6. CRITERIOS DE EVALUACION (Rubrica)

| Categoria | Criterio | Max |
|---|---|---|
| Triage core | GLM 5.2 clasifica categoria y prioridad con salida estructurada | 14 |
| Triage core | Extrae sentimiento, modulo, resumen, accion y respuesta sugerida | 6 |
| Robustez IA | Validacion de schema, salida invalida y errores API | 10 |
| Robustez IA | Retries/backoff + abstencion/revision humana | 6 |
| Correlacion | Agrupa tickets relacionados | 10 |
| Correlacion | Detecta y resume candidatos a incidente mayor | 8 |
| Generalizacion | Funciona con tickets ocultos y ambiguos | 8 |
| Interfaz | Cola priorizada, detalle y formulario manual | 8 |
| Interfaz | Visualizacion clara de grupos | 4 |
| Calidad tecnica | Arquitectura, config externa, errores y claridad | 8 |
| Tests | Tests relevantes de exito + error + schema | 6 |
| Uso efectivo GLM 5.2 | Evidencia de iteracion, debugging y pensamiento critico | 8 |
| Demo | Demuestra los escenarios principales | 4 |
| **Subtotal base** | | **100** |
| Bonos | A + B + C + D | **hasta +30** |

---

## 7. ENTREGABLES FINALES

- [ ] Codigo fuente funcional
- [ ] README.md (stack, arquitectura, config, instalacion, ejecucion, tests, interfaz, bonos)
- [ ] requirements.txt
- [ ] Bitacora de uso de GLM 5.2 (`docs/sesion_ia.md`)
- [ ] Esquema de salida documentado
- [ ] Tests creados por el equipo
- [ ] Interfaz grafica funcional (Streamlit)
- [ ] .env.example (sin secretos)
- [ ] prompt_usado.txt (prompts documentados)

---

## 8. ORDEN DE EJECUCION RECOMENDADO

```
Fase 0 (Preparacion)
    │
    ▼
Fase 1 (Triage estructurado)  ←  Nucleo del producto
    │
    ▼
Fase 2 (Robustez de IA)       ←  Hace Fase 1 confiable
    │
    ▼
Fase 4 (Control Room)         ←  Mover aqui para validar Fases 1-2 visualmente
    │
    ▼
Fase 3 (Correlacion)          ←  Requiere Fases 1-2 funcionando
    │
    ▼
Fase 5 (Bonos)                ←  A, B, C, D en orden de valor/esfuerzo
    │
    ▼
Fase 6 (Cierre)               ←  README, bitacora, tests, demo
```

**Nota:** Fase 4 (UI) se mueve antes de Fase 3 para permitir validacion visual
temprana de las Fases 1-2. La UI se extiende despues con la visualizacion de
grupos de la Fase 3.

---

## 9. RIESGOS Y MITIGACIONES

| Riesgo | Mitigacion |
|---|---|
| GLM 5.2 no disponible o lento | Mock/fallback para desarrollo, timeouts configurables |
| Prompt injection exitoso | Separar system/user prompts, validacion estricta de salida |
| JSON invalido de GLM | Parser robusto, retries, degradacion graceful |
| Falsos positivos en correlacion | Umbral configurable, validacion con GLM 5.2 |
| Rate limiting de API | Semaforo de concurrencia, backoff exponencial |
| Dataset oculto diferente | No hardcodear, razonar sobre contenido completo |
