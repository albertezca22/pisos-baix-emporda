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

## Complemento en el Mac (rellena Idealista, Fotocasa y Milanuncios)

Idealista, Fotocasa y Milanuncios bloquean las IPs de centros de datos: desde
GitHub devuelven cero, y desde una conexión doméstica funcionan. El complemento
del Mac cubre ese hueco los días que el ordenador esté encendido.

```bash
./bin/instalar-mac.sh          # cada día a las 21:00
./bin/instalar-mac.sh 07 45    # o a la hora que quieras
```

```bash
launchctl start com.albertezca22.pisos-baix-emporda   # lanzarlo ahora
tail -f data/escaneo-local.log                        # ver qué hace
./bin/instalar-mac.sh --quitar                        # desinstalarlo
```

Los dos escaneos **se combinan, no se pisan**: cada ejecución solo puede retirar
anuncios de los portales que ha conseguido consultar de verdad. Si GitHub no
llega a Idealista, los pisos que solo estaban ahí siguen en la lista. Está
cubierto por `tests/test_fusion.py`.

Si el Mac está apagado a la hora prevista, macOS lanza la tarea en cuanto
vuelve a estar disponible.

## Fijar pisos a mano

En [`data/fijados.json`](data/fijados.json) puedes clavar pisos por su enlace.
Salen **siempre** como favoritos de Albert para todo el que abra el enlace
público, incluso si el escaneo no los encuentra, si el anuncio se retira o si
se salen del presupuesto (en ese caso se avisa con la etiqueta *Sobre
presupuesto*).

```json
{"url": "https://www.idealista.com/inmueble/109987514/",
 "precio": 140000, "m2": 77, "municipio": "Palafrugell",
 "titulo": "Piso en Palafrugell", "extras": ["parking"]}
```

El emparejado va por el identificador del anuncio, no por la URL literal, así
que sigue funcionando cuando el portal le cambia los parámetros al enlace.

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

Comprobado con peticiones reales, y no coincide desde los dos sitios:

| Portal | Cómo se consulta | Desde GitHub | Desde el Mac |
|---|---|---|---|
| Idealista | comarca entera, con paginación | bloqueado | funciona |
| Fotocasa | comarca entera, datos del propio portal | bloqueado | funciona |
| pisos.com | comarca entera, con filtro de precio | funciona | funciona |
| Habitaclia | municipio a municipio, despacio | funciona | irregular |
| Milanuncios | municipio a municipio, despacio | bloqueado | funciona |

De ahí el complemento del Mac. Detalles que costaron encontrar:

- Idealista rechaza el perfil TLS de Chrome (403) y acepta el de Safari.
- Milanuncios sirve el muro anti-bot en cuanto recibe una cabecera propia:
  basta un `Accept-Language`. Sin cabeceras personalizadas, responde bien.
- Habitaclia rellena la lista de un pueblo con anuncios de los vecinos, así que
  el municipio se lee del enlace de cada anuncio, nunca de la página consultada.
- En pisos.com el filtro `hasta-160000` sí funciona aunque el título de la
  página no cambie; sin él, las primeras páginas son todas de pisos caros.

Cuando un portal falla, el escaneo **sigue adelante** y lo deja registrado en el
pie de la web, donde cada uno aparece con un punto verde o rojo y el número de
anuncios que aportó. Ninguno puede desaparecer del informe en silencio.

**Pendiente:** el slug de Habitaclia para La Bisbal d'Empordà no está
verificado (devuelve 404 y no pude comprobar el correcto sin que Habitaclia me
bloqueara). No rompe nada: un slug equivocado cuesta una petición y La Bisbal
sigue llegando vía pisos.com y vía las páginas de los pueblos vecinos.

## Estructura

```
scanner/config.py     zona, presupuesto y exclusiones (lo editable)
scanner/portals.py    los cinco escrapers
scanner/pipeline.py   normalizado, deduplicado, fusión de escaneos e histórico
scanner/run.py        orquestador
bin/escaneo-local.sh  el escaneo del Mac
bin/instalar-mac.sh   lo programa con launchd
docs/index.html       la web
docs/data.js          datos que consume la web (se regenera cada día)
data/listings.json    histórico: de aquí sale qué es "nuevo"
data/marks.json       estrellas y favoritos publicados
data/fijados.json     pisos clavados a mano por enlace
tests/test_ui.py      la web pinta, filtra, ordena y guarda marcas
tests/test_fusion.py  deduplicado y combinación de escaneos parciales
```

## Cómo se decide que dos anuncios son el mismo piso

El mismo piso lo anuncian tres agencias con precio distinto (149.000 y 150.000),
superficie distinta (construida o útil) y títulos que no se parecen en nada. En
lugar de exigir coincidencia exacta se comparan varias señales: calle y número
extraídos del título, superficie con tolerancia, precio con tolerancia y
coordenadas cuando las hay.

Y con dos vetos, porque el error grave es fundir pisos distintos del mismo
edificio: **nunca** se fusionan dos anuncios con número de habitaciones distinto
conocido, con superficies desproporcionadas (más de un 12%) o con plantas
distintas. En los datos reales esto evitaba juntar un piso de 2 habitaciones con
uno de 4, y uno de 71 m² con uno de 96.
