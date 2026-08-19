"""Configuración del escaneo: zona, presupuesto y criterios de exclusión.

Todo lo editable a mano vive aquí. Cambiar un valor y volver a lanzar el
escaneo es suficiente; no hay que tocar el resto del código.
"""

# --- Presupuesto -----------------------------------------------------------

PRECIO_MAX = 160_000
PRECIO_MIN = 20_000  # descarta plazas de garaje y errores de publicación

# --- Qué es un piso "ideal" (etiqueta fucsia) ------------------------------
# El perfil de buena compra que busca Albert. No se mira el número de baños.
# El tope es inclusivo: un piso de 130.000 € clavados cuenta como ideal.

IDEAL_HABITACIONES = 1
IDEAL_PRECIO_MAX = 130_000

# --- Zona ------------------------------------------------------------------
# Minutos en coche desde Mas de Torrent (Torrent, Baix Empordà), el lugar de
# trabajo. Son estimaciones por carretera; ajusta libremente si algún pueblo
# te cuadra mejor. Solo se publican municipios con <= MINUTOS_MAX.

MINUTOS_MAX = 20

# Municipios preferentes: salen marcados y ordenan por delante a igualdad.
PREFERENTES = {"Palafrugell", "Pals", "Palamós"}

MUNICIPIOS = {
    # municipio                          minutos en coche
    "Torrent": 0,
    "Palafrugell": 5,
    "Regencós": 6,
    "Pals": 7,
    "Mont-ras": 8,
    "Palau-sator": 8,
    "Forallac": 9,
    "Gualta": 9,
    "La Bisbal d'Empordà": 10,
    "Fontanilles": 10,
    "Serra de Daró": 11,
    "Begur": 12,
    "Corçà": 12,
    "Ullastret": 12,
    "Vall-llobrega": 13,
    "Parlavà": 14,
    "Torroella de Montgrí": 14,
    "Ultramort": 14,
    "Cruïlles, Monells i Sant Sadurní de l'Heura": 15,
    "Palamós": 16,
    "Rupià": 16,
    "Ullà": 16,
    "Foixà": 17,
    "Albons": 18,
    "La Pera": 18,
    "Garrigoles": 19,
    "La Tallada d'Empordà": 19,
    "Verges": 19,
    "Calonge i Sant Antoni": 20,
    "Colomers": 20,
    "Jafre": 20,
}

# Alias que devuelven los portales -> nombre canónico de MUNICIPIOS.
# Incluye núcleos y pedanías que los portales publican como municipio propio.
ALIAS_MUNICIPIOS = {
    "calonge": "Calonge i Sant Antoni",
    "sant antoni de calonge": "Calonge i Sant Antoni",
    "calonge i sant antoni": "Calonge i Sant Antoni",
    "la bisbal d'emporda": "La Bisbal d'Empordà",
    "bisbal d'emporda": "La Bisbal d'Empordà",
    "la bisbal": "La Bisbal d'Empordà",
    "cruilles": "Cruïlles, Monells i Sant Sadurní de l'Heura",
    "monells": "Cruïlles, Monells i Sant Sadurní de l'Heura",
    "sant sadurni de l'heura": "Cruïlles, Monells i Sant Sadurní de l'Heura",
    "cruilles, monells i sant sadurni de l'heura": "Cruïlles, Monells i Sant Sadurní de l'Heura",
    "vulpellac": "Forallac",
    "fonteta": "Forallac",
    "peratallada": "Forallac",
    "llofriu": "Palafrugell",
    "calella de palafrugell": "Palafrugell",
    "llafranc": "Palafrugell",
    "tamariu": "Palafrugell",
    "esclanya": "Begur",
    "sa riera": "Begur",
    "aiguablava": "Begur",
    "l'estartit": "Torroella de Montgrí",
    "estartit": "Torroella de Montgrí",
    "torroella de montgri - l'estartit": "Torroella de Montgrí",
    "la fosca": "Palamós",
    "sant joan de palamos": "Palamós",
    "montras": "Mont-ras",
    "la pera": "La Pera",
    "pera": "La Pera",
    "ulla": "Ullà",
    "la tallada d'emporda": "La Tallada d'Empordà",
    "tallada d'emporda": "La Tallada d'Empordà",
    "torrent (girona)": "Torrent",
}

# --- Tipo de vivienda ------------------------------------------------------
# "Solo pisos": se incluye todo lo que es vivienda dentro de un edificio
# (piso, ático, dúplex, estudio, apartamento, planta baja) y se excluyen
# casas, chalets, masías y todo lo que no sea vivienda.
# En la web hay un filtro por tipo para afinar más.

TIPOS_INCLUIDOS = {"piso", "ático", "dúplex", "estudio", "apartamento", "planta baja", "loft"}

TIPOS_EXCLUIDOS_KW = [
    "casa", "chalet", "chalé", "xalet", "masia", "masía", "mas ", "torre",
    "adosad", "paread", "aparead", "unifamiliar", "finca", "terreno", "solar",
    "parcela", "local", "nave", "garaje", "garatge", "plaza de aparcamiento",
    "plaça d'aparcament", "trastero", "edificio", "edifici", "oficina",
    "hotel", "masover", "cortijo", "caserío", "bungalow", "casa de pueblo",
]

# --- Exclusiones: "nada de ocupados, subastas ni cosas raras" ---------------

EXCLUIR_KW = [
    # ocupación
    "ocupad", "okupa", "okupad", "ocupat", "con okupas", "sin posesion",
    "sin posesión", "posesion no garantizada", "posesión no garantizada",
    "no se garantiza la posesion", "no se garantiza la posesión",
    "llaves no disponibles", "sin derecho a visita", "no visitable",
    "imposibilidad de visitar", "no se puede visitar",
    "estado ocupacional", "no se pueden realizar visitas",
    "no se puede realizar visita", "solo para inversores",
    "sólo para inversores", "solo inversores",
    # subastas y procesos judiciales
    "subasta", "subhasta", "puja", "adjudicacion judicial", "adjudicación judicial",
    "procedimiento judicial", "embargo", "embargad", "concurso de acreedores",
    "dacion en pago", "dación en pago",
    # propiedad parcial o gravada
    "nuda propiedad", "nua propietat", "nuda propietat", "usufructo",
    "usufructuari", "proindiviso", "pro indiviso", "porcentaje de la vivienda",
    "cuota indivisa", "multipropiedad", "multipropietat", "aprovechamiento por turno",
    # alquilado con inquilinos
    "alquilado con inquilino", "con inquilinos", "llogat amb llogater",
    "rentabilidad garantizada con inquilino",
    # anuncios que no son viviendas, colados en el listado de pisos
    "prestamo hipotecario", "préstamo hipotecario", "prestamos hipotecarios",
    "préstamos hipotecarios", "reunificacion de deudas", "reunificación de deudas",
    "capital privado", "financiacion al 100", "financiación al 100",
    # otras rarezas
    "obra parada", "sin cedula de habitabilidad", "sin cédula de habitabilidad",
    "ruina", "para derribar", "derribo",
]

# --- Extras detectables por palabra clave ----------------------------------
# clave interna -> variantes que buscamos en título, descripción y features.

EXTRAS = {
    "parking": ["parking", "pàrquing", "parquing", "garaje", "garatge", "plaza de garaje",
                "plaça de garatge", "aparcamiento", "aparcament"],
    "terraza": ["terraza", "terrassa"],
    "balcon": ["balcón", "balcon", "balco", "balcó"],
    "ascensor": ["ascensor", "elevador"],
    "piscina": ["piscina"],
    "jardin": ["jardín", "jardin", "jardi", "jardí"],
    "trastero": ["trastero", "traster"],
    "aire": ["aire acondicionado", "aire condicionat", "climatizado", "climatitzat"],
    "calefaccion": ["calefacción", "calefaccion", "calefacció"],
    "amueblado": ["amueblado", "moblat", "amoblado"],
    "reformado": ["reformado", "reformada", "reformat", "reformada íntegramente",
                  "a estrenar", "obra nueva", "obra nova"],
    "vistas_mar": ["vistas al mar", "vistes al mar", "primera linea de mar",
                   "primera línea de mar", "frente al mar"],
}

# --- Portales --------------------------------------------------------------
# Los tres primeros barren la comarca entera en pocas peticiones y son la
# fuente principal. Habitaclia y Milanuncios limitan el ritmo con fuerza, así
# que van municipio a municipio, despacio y como "mejor esfuerzo": si un día
# no responden, el escaneo continúa igual y se registra en el informe.

PORTALES = {
    "idealista":   {"activo": True, "modo": "comarca",   "prioridad": 1, "pausa": (2.0, 4.5)},
    "fotocasa":    {"activo": True, "modo": "comarca",   "prioridad": 2, "pausa": (1.5, 3.5)},
    "pisos":       {"activo": True, "modo": "comarca",   "prioridad": 3, "pausa": (1.5, 3.0)},
    "habitaclia":  {"activo": True, "modo": "municipio", "prioridad": 4, "pausa": (5.0, 9.0)},
    "milanuncios": {"activo": True, "modo": "municipio", "prioridad": 5, "pausa": (5.0, 9.0)},
}

MAX_PAGINAS = 15          # tope de páginas por portal y búsqueda
TIMEOUT = 20
# Si un portal lento encadena este número de municipios sin responder, se le
# deja por hoy. Evita que Habitaclia o Milanuncios alarguen el escaneo veinte
# minutos cuando han decidido bloquearnos.
FALLOS_SEGUIDOS_MAX = 3

# Tiempo máximo que puede consumir cada portal. Habitaclia y Milanuncios pueden
# responder muy despacio sin llegar a fallar, y sin este tope un solo portal se
# come el margen del workflow. Al agotarse, se publica lo que se lleve.
PRESUPUESTO_SEGUNDOS = {
    "idealista": 420, "fotocasa": 300, "pisos": 300,
    "habitaclia": 360, "milanuncios": 300,
}

# Municipios que se consultan uno a uno en los portales lentos. Solo los que
# realmente tienen stock de pisos; los pueblos pequeños salen igualmente vía
# Idealista/Fotocasa/pisos.com, que barren la comarca entera.
MUNICIPIOS_LENTOS = [
    "Palafrugell", "Palamós", "La Bisbal d'Empordà", "Torroella de Montgrí",
    "Calonge i Sant Antoni", "Begur", "Pals", "Mont-ras", "Vall-llobrega",
    "Verges", "Corçà", "Forallac",
]

# Slugs por portal para el modo municipio.
SLUGS_HABITACLIA = {
    "Palafrugell": "palafrugell", "Palamós": "palamos",
    "La Bisbal d'Empordà": "la_bisbal_d_emporda", "Torroella de Montgrí": "torroella_de_montgri",
    "Calonge i Sant Antoni": "calonge", "Begur": "begur", "Pals": "pals",
    "Mont-ras": "mont_ras", "Vall-llobrega": "vall_llobrega", "Verges": "verges",
    "Corçà": "corca", "Forallac": "forallac",
}

SLUGS_MILANUNCIOS = {
    "Palafrugell": "palafrugell-girona", "Palamós": "palamos-girona",
    "La Bisbal d'Empordà": "la-bisbal-demporda-girona",
    "Torroella de Montgrí": "torroella-de-montgri-girona",
    "Calonge i Sant Antoni": "calonge-girona", "Begur": "begur-girona",
    "Pals": "pals-girona", "Mont-ras": "mont-ras-girona",
    "Vall-llobrega": "vall-llobrega-girona", "Verges": "verges-girona",
    "Corçà": "corca-girona", "Forallac": "forallac-girona",
}

# --- Rutas -----------------------------------------------------------------

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATOS = RAIZ / "data"
DIR_WEB = RAIZ / "docs"
FICHERO_ESTADO = DIR_DATOS / "listings.json"   # histórico con first_seen
FICHERO_MARCAS = DIR_DATOS / "marks.json"      # estrellas y favoritos de Albert
FICHERO_FIJADOS = DIR_DATOS / "fijados.json"   # favoritos fijados a mano por URL
FICHERO_SALIDA = DIR_WEB / "data.json"         # lo que consume la web
ZONA_HORARIA = "Europe/Madrid"
