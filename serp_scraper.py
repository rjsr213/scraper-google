"""
Scraper SERP + LLM:
- Ejecuta una busqueda en Google con Selenium y guarda la SERP completa.
- (Opcional) Limpia el texto visible y lo resume usando la API Responses de OpenAI.

Requisitos previos:
    pip install -r requirements.txt
    Chrome o Chromium instalado (Selenium Manager detecta el driver).
    OPENAI_API_KEY definido si se usa la parte del LLM.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

from bs4 import BeautifulSoup
from openai import OpenAI
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

DEFAULT_TIMEOUT = 15
DEFAULT_MODEL = "gpt-5-mini"

CONSENT_SELECTORS: Iterable[tuple[str, str]] = [
    (By.ID, "L2AGLb"),
    (By.CSS_SELECTOR, "button[aria-label='Aceptar todo']"),
    (By.CSS_SELECTOR, "button[aria-label='Aceptarlo todo']"),
    (By.XPATH, "//button/span[contains(., 'Acepto')]"),
    (By.XPATH, "//button[contains(., 'Aceptar todo')]"),
]


def build_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1280,1024")
    service = Service()
    return webdriver.Chrome(service=service, options=options)


def dismiss_consent(driver: webdriver.Chrome, timeout: int) -> None:
    wait = WebDriverWait(driver, timeout)
    for by, selector in CONSENT_SELECTORS:
        try:
            button = wait.until(EC.element_to_be_clickable((by, selector)))
            button.click()
            return
        except TimeoutException:
            continue
        except Exception:
            continue


def wait_for_condition(
    driver: webdriver.Chrome,
    predicate,
    timeout: float = 10,
    poll_frequency: float = 0.5,
) -> None:
    end_time = time.monotonic() + timeout
    while time.monotonic() < end_time:
        try:
            if predicate(driver):
                return
        except Exception:
            pass
        time.sleep(poll_frequency)
    raise TimeoutException(f"Timed out after {timeout} seconds.")


def page_loaded(driver: webdriver.Chrome, timeout: int = 10) -> bool:
    try:
        wait_for_condition(
            driver,
            lambda d: d.execute_script("return document.readyState") == "complete",
            timeout=timeout,
        )
        return True
    except TimeoutException:
        return False


def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def summarize_text_with_llm(
    content: str,
    objective: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_output_tokens: int = 800,
) -> str:
    client = OpenAI()
    prompt = (
        f"Objetivo de la busqueda: {objective.strip()}\n\n"
        "Informacion depurada de la SERP:\n"
        f"{content.strip() or '[Sin texto procesable]'}"
    )

    response = client.responses.create(
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        reasoning={"effort": "medium", "summary": "auto"},
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Eres un resumidor y organizador de informacion RAW. "
                            "Segun el objetivo de la busqueda, organiza los hallazgos "
                            "en bullets o tablas y resalta cifras, URLs y datos accionables."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            },
        ],
    )

    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()

    texts: list[str] = []
    for block in getattr(response, "output", []):
        if getattr(block, "type", None) == "message":
            for piece in getattr(block, "content", []):
                if getattr(piece, "type", None) == "text":
                    texts.append(piece.text)
        elif getattr(block, "type", None) == "output_text":
            content = getattr(block, "content", None)
            if isinstance(content, str):
                texts.append(content)

    cleaned = "\n\n".join(segment.strip() for segment in texts if segment.strip())
    if not cleaned:
        raise RuntimeError("La API de OpenAI no devolvio texto procesable.")
    return cleaned


def fetch_google_serp_html(
    query: str,
    *,
    headless: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    driver = build_driver(headless=headless)
    try:
        driver.get("https://www.google.com/?hl=es")
        page_loaded(driver)
        dismiss_consent(driver, timeout=5)

        wait = WebDriverWait(driver, timeout)
        search_box = wait.until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="APjFqb"]'))
        )
        search_box.clear()
        search_box.send_keys(query)
        search_box.send_keys(Keys.ENTER)

        page_loaded(driver)
        return driver.page_source
    finally:
        driver.quit()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta una busqueda en Google, guarda el HTML y opcionalmente lo resume con GPT."
        )
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Consulta a buscar (por ejemplo: 'mejores hoteles la coruna').",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Ruta para guardar el HTML. Si se omite se imprime por stdout.",
    )
    parser.add_argument(
        "--objective",
        help="Objetivo que se pasa al LLM para extraer datos relevantes del texto.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="Archivo para guardar la respuesta del LLM (stdout si se omite).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Modelo de OpenAI Responses (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Temperatura para el modelo (default: 0.2).",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=800,
        help="Limite de tokens que puede generar el modelo (default: 800).",
    )
    headless_group = parser.add_mutually_exclusive_group()
    headless_group.add_argument(
        "--headless",
        dest="headless",
        action="store_true",
        help="Fuerza modo headless (por defecto).",
    )
    headless_group.add_argument(
        "--show-browser",
        dest="headless",
        action="store_false",
        help="Muestra el navegador para depurar la automatizacion.",
    )
    parser.set_defaults(headless=True)
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Tiempo maximo de espera para los elementos (default: {DEFAULT_TIMEOUT}s).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    query = args.query or input("Que quieres buscar en Google? ").strip()
    if not query:
        print("La consulta no puede estar vacia.", file=sys.stderr)
        return 1

    html = fetch_google_serp_html(
        query,
        headless=args.headless,
        timeout=args.timeout,
    )

    if args.output:
        args.output.write_text(html, encoding="utf-8")
        print(f"HTML guardado en {args.output}")
    else:
        sys.stdout.write(html)

    if args.objective:
        text_content = extract_text_from_html(html)
        summary = summarize_text_with_llm(
            text_content,
            args.objective,
            model=args.model,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
        )
        if args.summary_output:
            args.summary_output.write_text(summary, encoding="utf-8")
            print(f"Resumen guardado en {args.summary_output}")
        else:
            print("\n--- Resumen generado por el LLM ---\n")
            print(summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
