# Scraper Google + LLM

Script en Python que automatiza búsquedas en Google con Selenium, captura la SERP completa y, opcionalmente, pasa el texto limpio al modelo `gpt-5-mini` mediante la API **Responses** de OpenAI para extraer información relevante.

## Requisitos

- Python 3.10+
- Google Chrome o Chromium instalado (Selenium Manager descarga el driver).
- Dependencias del proyecto:

```bash
python -m pip install -r requirements.txt
```

- Variable `OPENAI_API_KEY` configurada si se usará la parte del LLM.

## Uso rápido

```bash
py -3 serp_scraper.py "mejores hoteles la coruna" \
    --objective "Listar hoteles bien valorados con precios y teléfonos" \
    --show-browser \
    -o hoteles.html \
    --summary-output resumen.txt
```

Parámetros principales:

| Flag | Descripción |
| ---- | ----------- |
| `query` | Consulta a buscar. Si se omite, se pedirá por `stdin`. |
| `-o/--output` | Guarda el HTML completo de la SERP. |
| `--objective` | Activa la llamada al LLM y define el objetivo del resumen. |
| `--summary-output` | Archivo donde se guardará el resumen (stdout por defecto). |
| `--model` | Modelo de OpenAI Responses (default `gpt-5-mini`). |
| `--temperature` | Temperatura del modelo. |
| `--max-output-tokens` | Límite de tokens generados por el modelo. |
| `--show-browser` / `--headless` | Controla si se muestra Chrome. |
| `--timeout` | Timeout base para operaciones de Selenium. |

## Flujo

1. Selenium abre Google con locale español y acepta el banner de consentimiento.
2. Se ejecuta la búsqueda y se obtiene el `page_source`.
3. Se limpia el HTML con BeautifulSoup, manteniendo solo texto visible.
4. Si hay `--objective`, se envía el texto a OpenAI Responses para obtener un resumen estructurado según el objetivo.

## Notas

- El archivo `requirements.txt` incluye Selenium, BeautifulSoup, lxml y el SDK oficial de OpenAI.
- `.gitignore` ignora entornos virtuales, cache y artefactos locales (`*.html`, `*.txt`, etc.) para mantener el repo limpio.

¡Listo para subir el repositorio!
