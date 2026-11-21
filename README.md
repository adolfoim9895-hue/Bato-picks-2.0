# Radar Local / Bato Picks 2.1 · Repositorio nuevo

Aplicación web progresiva (PWA) para Android y GitHub Pages que busca **favoritos locales** de los próximos siete días, sin cuotas del casino y sin dependencias de API-Football.

**Importante:** la distribución incluye el programa, las pruebas y una respuesta inicial vacía. NO incluye partidos ni porcentajes ficticios. GitHub Actions descarga los datos reales después de instalarla. La cobertura mundial **no** está garantizada con proveedores gratuitos.

## Instalación desde cero (sin editar archivos)

1. En GitHub pulsa **New repository** y crea un repositorio **público**, por ejemplo `radar-local`. **No marques** las opciones para agregar README, `.gitignore` o licencia: el ZIP ya los trae. Utiliza `main` como rama principal.
2. Descarga `radar-local-bato-picks-2.1-repositorio-nuevo.zip` y **descomprímelo**. La raíz descomprimida debe contener `index.html`, `app.js`, `styles.css`, `scripts/`, `tests/`, `data/` y **`.github/workflows/`**. GitHub **no** descomprime un ZIP subido como archivo.
3. Sube **todo el contenido descomprimido** a la raíz del repositorio (sin agregar una carpeta exterior). Desde una computadora puedes arrastrar carpetas y archivos a **Add file → Upload files**, comprobando que la carpeta oculta `.github` se haya conservado. Si tu navegador no permite cargar carpetas, usa Git (alternativa más segura indicada abajo).
4. Opcional pero recomendado: crea un token GRATUITO en <https://www.football-data.org/>. En el repositorio entra a **Settings → Secrets and variables → Actions → Secrets → New repository secret**, nombre `FOOTBALL_DATA_TOKEN`, valor tu token. **Sin este token** la app intenta utilizar OpenLigaDB y puede mostrar menos ligas, pero seguirá funcionando sin pagar OpenAI.
5. En **Settings → Pages → Build and deployment → Source** selecciona **GitHub Actions**.
6. En **Actions** selecciona **Actualizar Bato Picks 2.1 y publicar** → **Run workflow** → ejecuta sobre `main`. Si GitHub ejecutó una publicación antes de configurar Pages y falló, vuelve a ejecutarla.
7. Comprueba en el registro los pasos **Ejecutar todas las pruebas**, **Consultar fuentes y modelar partidos**, **Comprobar JSON** y **Publicar GitHub Pages**. En **Settings → Pages** aparece la URL, usualmente `https://TU-USUARIO.github.io/radar-local/`.
8. En Android abre esa URL con Chrome → menú **⋮** → **Instalar aplicación** o **Añadir a la pantalla principal**.

**No es necesario editar ningún archivo** después de subirlo. Si deseas ajustar la cobertura o activar investigación de pago, usa **Settings → Secrets and variables → Actions → Variables**: las opciones del workflow se leen directamente de esas variables.

### Alternativa fiable para subir todas las carpetas con Git

Desde una computadora con Git instalado, coloca los **23 archivos y carpetas contenidos** en una carpeta local vacía y ejecuta ahí:

```bash
git init -b main
git add .
git commit -m "Instalar Radar Local 2.1"
git remote add origin https://github.com/TU-USUARIO/radar-local.git
git push -u origin main
```

Reemplaza solo el nombre de usuario y repositorio **en el comando de terminal**, no en el código. Si Git te solicita iniciar sesión, usa el método de autenticación que GitHub indique. No es necesario tener Python o Node en el teléfono: GitHub Actions ejecutará las tareas.

## Proveedores y costos

| Proveedor | Clave requerida | Función | Estado |
|---|---|---|---|
| [football-data.org](https://www.football-data.org/pricing) | `FOOTBALL_DATA_TOKEN`, gratuita | Calendarios y resultados de competiciones admitidas | Recomendado |
| [OpenLigaDB](https://api.openligadb.de/index.html) | Ninguna | Bundesliga y segunda división alemana; histórico para validación | Gratuito; se utiliza de respaldo o como fuente principal de Bundesliga |
| [TheSportsDB](https://www.thesportsdb.com/) | `THESPORTSDB_KEY`, individual | Respaldo adicional opcional | Desactivado sin clave individual |
| [OpenAI Responses Web Search](https://developers.openai.com/api/docs/guides/tools-web-search) | `OPENAI_API_KEY` | Investigación contextual opcional de noticias | **Desactivado por defecto: US$0** |

La suscripción a ChatGPT **no incluye** créditos de API. Nunca pongas claves en HTML, JavaScript público ni JSON. El backend del proyecto es GitHub Actions, que publica únicamente ficheros estáticos; no existe servidor de consultas en vivo en GitHub Pages. La cobertura de ligas depende de cada API y su plan.

## Configuración SIN editar archivos

En **Settings → Secrets and variables → Actions** configura lo siguiente únicamente si lo necesitas:

**Secrets** (valores privados):

| Nombre | Para qué | Requerido |
|---|---|---|
| `FOOTBALL_DATA_TOKEN` | Calendarios/estadísticas adicionales | No, pero recomendado |
| `OPENAI_API_KEY` | Búsqueda web con IA opcional | No |
| `THESPORTSDB_KEY` | Proveedor adicional opcional | No |

**Variables** (valores públicos del repositorio):

| Nombre | Valor por defecto | Para qué |
|---|---|---|
| `MAX_WEB_SEARCHES` | `0` | **0 = sin costos**. Para investigar hasta 5 partidos por ejecución, define `5` y agrega la clave OpenAI |
| `APP_TIMEZONE` | `America/Tijuana` | Huso horario del calendario |
| `FD_COMPETITIONS` | `PL,PD,BL1,SA,FL1,DED,PPL,BSA,ELC` | Competiciones solicitadas a football-data.org |
| `OPENAI_MODEL` | `gpt-6.2-sol` | Modelo de la investigación web, si está habilitada |

La actualización programada ocurre aproximadamente dos veces al día, con demoras posibles por GitHub Actions. Los partidos **no** se actualizan en tiempo real. La app no usa API-Football ni su clave de acceso, aunque la hayas tenido antes.

## Cómo se calcula la confianza estadística

- El modelo calcula goles esperados con Poisson independiente, promedios casa/fuera, forma y Elo. La lista H2H es **descriptiva** y no altera porcentajes sin validación.
- **Alta (ESTADÍSTICA):** el local debe tener P(victoria) ≥75%; al menos 55 partidos de liga previos, 8 de cada equipo y 5 del local en casa / visitante fuera; y la validación **walk-forward** debe incluir al menos 25 favoritos anteriores con P≥75%, frecuencia observada de victoria ≥70% y diferencia absoluta entre frecuencia y predicción media ≤10 puntos porcentuales. Son **criterios de evaluación**, no garantías ni un porcentaje de «confianza» inventado. Si falta evidencia suficiente, permanece como media.
- **Media (ESTADÍSTICA):** local con probabilidad calculada de al menos 60% que no supera todos los requisitos de alta.
- **DATOS INSUFICIENTES:** faltan resultados para calcular una probabilidad. Los encuentros que no alcanzan 60% se muestran por separado como «Local no favorito» y no se inventan cifras.
- **Verificación contextual, separada de la clasificación:** aun en categoría alta, lesiones, sanciones, alineaciones y rotaciones pueden aparecer como **NO VERIFICADAS**. Si la búsqueda opcional señala una noticia, la muestra como posible riesgo por comprobar, no como lesión confirmada. Esos avisos **no fuerzan la confianza media**, ni modifican arbitrariamente las probabilidades.
- Se muestra el número de partidos históricos comprobados, tasa observada, diferencia de calibración, Brier e intervalo Wilson 95%. Datos sintéticos se usan **solo en tests**, jamás en la app publicada.

**Limitaciones:** no se proporciona evidencia de que este modelo esté calibrado para todas las ligas. Los criterios de alta necesitan bastantes favoritos históricos y podrían no cumplirse en algunas temporadas o torneos. El historial gratuito de football-data.org puede ser limitado; OpenLigaDB permite intentar dos temporadas previas. La IA no comprueba por sí sola que no existan bajas. Los valores de Transfermarkt siguen marcados **NO VERIFICADOS**; no se hace scraping prohibido.

## Archivos y automatización

Los **23 archivos** conservan su estructura original:

```text
.github/workflows/publicar.yml
.github/workflows/tests.yml
.env.example
.gitignore
LICENSE
README.md
app.js
styles.css
index.html
sw.js
manifest.webmanifest
icon.svg
icon-192.png
icon-512.png
data/predictions.json
scripts/backtest.py
scripts/model.py
scripts/providers.py
scripts/research.py
scripts/update.py
scripts/validate_data.py
tests/test_model.py
tests/test_pipeline.py
```

`publicar.yml` hace checkout, restaura caché, ejecuta tests, descarga los resultados, calcula pronósticos, valida el JSON, crea `_site` sin secretos y lo despliega a Pages. `tests.yml` repite tests en pushes y pull requests. El frontend solo lee `data/predictions.json`. Si fallan las APIs se informa del fallo; caché anterior de menos de 36 h, si existe, se marca degradada.

## Pruebas disponibles

Con Python 3.12+ y Node.js:

```bash
python -m unittest discover -s tests -v
python scripts/validate_data.py
node --check app.js
node --check sw.js
python -m http.server 8000
```

Entra a `http://localhost:8000` para ver la interfaz. El proyecto **no requiere paquetes externos de Python ni npm**. Los tests usan datos de prueba y no requieren red, secretos ni pagos.

**Pruebas efectuadas en la preparación del ZIP:** tests unitarios y de integración con respuestas simuladas, comprobación de que alta existe sin OpenAI, backtest matemático con historial sintético, validación del JSON inicial, sintaxis JS y revisión de estructura de workflows. **No se ha comprobado una publicación real de GitHub Pages ni consultas autenticadas a los proveedores** desde este entorno. La primera ejecución en tu repositorio será la prueba real de red, límites de API, permisos y publicación.

## Errores frecuentes

- **Sin partidos:** abre Actions y mira `errores_proveedores` y `cobertura` en el registro o `data/predictions.json` publicado. OpenLigaDB cubre ligas concretas y el filtro exige historial; no es una falla si no hay picks.
- **HTTP 401/403:** token incorrecto o competición no incluida en tu plan. Puedes omitir Football-Data y seguir con OpenLigaDB.
- **Pages no aparece:** selecciona GitHub Actions en Settings → Pages y ejecuta el workflow manualmente. Asegúrate de subir también `.github/workflows`.
- **Confianza alta vacía:** con pocas predicciones históricas no se valida. No se debe forzar alta artificialmente.
- **Claves filtradas:** nunca las subas al repositorio. Si una clave se publica por accidente, revócala inmediatamente y crea una nueva.

## Licencias y fuentes

Código del proyecto bajo su `LICENSE`. Los derechos de resultados y escudos pertenecen a sus titulares. [OpenLigaDB](https://www.openligadb.de/en/terms-of-use) utiliza Open Database License (ODbL 1.0); su atribución está indicada en la interfaz. Respeta los términos y límites de cada proveedor. Las noticias citadas no deben interpretarse como confirmación médica o deportiva sin consultar la fuente primaria.
