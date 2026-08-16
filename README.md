# Pisos · Baix Empordà

Escaneo diario y automático de pisos en venta por debajo de **160.000 €** en el
Baix Empordà, a **20 minutos o menos en coche de Mas de Torrent**. Publica una
web pública, limpia, donde las novedades del día salen en dorado, lo que
destacas queda con estrella y tus favoritos aparecen en verde para todo el que
abra el enlace.

## Qué hace exactamente

Cada mañana a las **08:00 (hora española)**, sin que nadie tenga que hacer nada:

1. Rastrea **Idealista, Fotocasa, pisos.com, Habitaclia y Milanuncios**.
2. Se queda solo con **pisos** (incluye ático, dúplex, estudio, apartamento y
   planta baja; deja fuera casas, chalets, masías, locales y garajes).
3. **Descarta lo raro**: ocupados, subastas, nuda propiedad, proindiviso,
   usufructo, embargos y viviendas alquiladas con inquilinos dentro.
4. **Funde los duplicados**: el mismo piso anunciado en tres portales aparece
   una sola vez, con los tres enlaces.
5. **Marca las novedades**: compara con el histórico y señala en dorado lo que
   nunca se había visto antes.
6. Publica el resultado en GitHub Pages.

El flujo diario que buscabas: entras, miras lo dorado, y lo que te guste lo
marcas con estrella o lo pones como favorito.

## Los tres colores

| | Qué significa | Quién lo ve |
|---|---|---|
| **Dorado** | Vivienda nueva, no estaba en escaneos anteriores | Todo el mundo |
| **★ Estrella** | Destacado. Se mantiene en todas las versiones posteriores | Todo el mundo |
| **Verde** | Favorito de Albert | Todo el mundo |

## Puesta en marcha (una sola vez)

1. Crea un repositorio en GitHub y sube esta carpeta.
2. Ve a **Settings → Pages**, y en *Source* elige **Deploy from a branch**,
   rama `main` y carpeta **`/docs`**. Guarda.
3. Ve a **Settings → Actions → General**, y en *Workflow permissions* marca
   **Read and write permissions**. Sin esto el escaneo no puede guardar los
   resultados.
4. Entra en la pestaña **Actions**, elige *Escaneo diario de pisos* y pulsa
   **Run workflow** para lanzar el primero a mano.

La web queda en `https://<tu-usuario>.github.io/<repositorio>/`. Ese es el
enlace que puedes pasar a quien quieras: es público y no hace falta cuenta.

## Cómo se guardan las estrellas y los favoritos

Al pulsar una estrella o un favorito, la marca se guarda **al instante en tu
navegador**. Para que la vea todo el mundo:

1. Pulsa **Publicar marcas** en la barra inferior.
2. Copia el contenido que aparece.
3. Pégalo en `data/marks.json` desde GitHub (icono del lápiz → *Commit changes*).

El escaneo de la mañana siguiente las deja fijadas para siempre: aunque el
anuncio cambie de precio o de portal, la marca no se pierde.

## Uso desde el ordenador

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m scanner.run
```

Abre `docs/index.html` en el navegador: funciona también como fichero local,
sin necesidad de servidor.

Opciones útiles mientras trasteas:

```bash
./.venv/bin/python -m scanner.run --portales idealista,fotocasa --paginas 2
```

## Ajustar los criterios

Todo lo editable está en [`scanner/config.py`](scanner/config.py):

- `PRECIO_MAX` — el tope de 160.000 €.
- `MINUTOS_MAX` — los 20 minutos desde Mas de Torrent.
- `MUNICIPIOS` — pueblos y minutos en coche. Para añadir Platja d'Aro (24 min)
  o Sant Feliu de Guíxols (27 min), mete la línea y sube `MINUTOS_MAX`.
- `PREFERENTES` — ahora Palafrugell, Pals y Palamós.
- `EXCLUIR_KW` — las palabras que descartan un anuncio por raro.
- `EXTRAS` — parking, terraza, ascensor, piscina y demás filtros.

## Sobre la fiabilidad de cada portal

| Portal | Cómo se consulta | Fiabilidad |
|---|---|---|
| Idealista | comarca entera, con paginación | alta |
| Fotocasa | comarca entera, datos estructurados del propio portal | alta |
| pisos.com | comarca entera | alta |
| Habitaclia | municipio a municipio, despacio | limita el ritmo con frecuencia |
| Milanuncios | municipio a municipio, despacio | limita el ritmo con frecuencia |

Idealista y Fotocasa cubren la gran mayoría del mercado y son los que mejor
aguantan. Habitaclia y Milanuncios cortan el acceso a menudo: cuando ocurre, el
escaneo **sigue adelante** y lo deja registrado en el pie de la web, donde cada
portal aparece con un punto verde o rojo y el número de anuncios que aportó.

## Estructura

```
scanner/config.py    zona, presupuesto y exclusiones (lo editable)
scanner/portals.py   los cinco escrapers
scanner/pipeline.py  normalizado, deduplicado e histórico
scanner/run.py       orquestador
docs/index.html      la web
docs/data.js         datos que consume la web (se regenera cada día)
data/listings.json   histórico: de aquí sale qué es "nuevo"
data/marks.json      estrellas y favoritos publicados
tests/test_ui.py     comprueba que la web sigue pintando y filtrando bien
```
