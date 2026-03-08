# Modulo para gestionar rutas reales usando OSRM

import requests
import random
import math
import logging

logger = logging.getLogger(__name__)

# Limites del area urbana de Madrid para generacion de puntos aleatorios
MADRID_LAT_MIN = 40.370
MADRID_LAT_MAX = 40.490
MADRID_LON_MIN = -3.770
MADRID_LON_MAX = -3.600


def generar_punto_aleatorio_madrid():
    lat = random.uniform(MADRID_LAT_MIN, MADRID_LAT_MAX)
    lon = random.uniform(MADRID_LON_MIN, MADRID_LON_MAX)
    return (round(lat, 6), round(lon, 6))

# URL de la API publica de OSRM
URL_OSRM = "https://router.project-osrm.org/route/v1/driving"

# URL de Nominatim para geocodificacion
URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"


def geocodificar_direccion(direccion, ciudad="Madrid, España"):
    # Convierte una direccion o lugar en coordenadas usando Nominatim
    if not direccion:
        return None

    consulta = direccion
    if "madrid" not in direccion.lower():
        consulta = f"{direccion}, {ciudad}"

    try:
        parametros = {
            "q": consulta,
            "format": "json",
            "limit": 1,
            "countrycodes": "es"
        }
        cabeceras = {
            "User-Agent": "SimuladorVehicular/1.0"
        }

        resp = requests.get(URL_NOMINATIM, params=parametros, headers=cabeceras, timeout=5)
        resp.raise_for_status()
        datos = resp.json()

        if datos and len(datos) > 0:
            lat = float(datos[0]["lat"])
            lon = float(datos[0]["lon"])
            return (lat, lon)

        return None

    except Exception as e:
        logger.warning(f"Geocodificacion error: {e}")
        return None


def generar_ruta_hacia_destino(origen, destino):
    if not origen or not destino:
        return None

    return obtener_ruta_osrm(origen, destino)


def obtener_ruta_osrm(origen, destino):
    coords = f"{origen[1]},{origen[0]};{destino[1]},{destino[0]}"

    try:
        url = f"{URL_OSRM}/{coords}?overview=full&geometries=geojson"
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        datos = resp.json()

        if datos.get('code') != 'Ok':
            logger.warning("OSRM: respuesta sin codigo Ok")
            return None

        ruta = datos['routes'][0]['geometry']['coordinates']
        return [[coord[1], coord[0]] for coord in ruta]

    except Exception as e:
        logger.error(f"OSRM error: {str(e)[:80]}")
        return None


def generar_ruta_patrulla(origen=None):
    # Genera una ruta de patrulla aleatoria por zonas de Madrid
    if origen:
        punto_inicio = origen
    else:
        punto_inicio = generar_punto_aleatorio_madrid()

    num_puntos = random.randint(3, 5)
    puntos_destino = [generar_punto_aleatorio_madrid() for _ in range(num_puntos)]

    ruta_completa = []

    primer_destino = puntos_destino[0]
    segmento = obtener_ruta_osrm(punto_inicio, primer_destino)
    if segmento:
        ruta_completa.extend(segmento)

    for i in range(len(puntos_destino) - 1):
        origen_seg = puntos_destino[i]
        destino_seg = puntos_destino[i + 1]

        segmento = obtener_ruta_osrm(origen_seg, destino_seg)
        if segmento:
            if ruta_completa:
                ruta_completa.extend(segmento[1:])
            else:
                ruta_completa.extend(segmento)

    if len(ruta_completa) < 10:
        ultimo = ruta_completa[-1] if ruta_completa else punto_inicio
        destino_extra = generar_punto_aleatorio_madrid()
        segmento = obtener_ruta_osrm(ultimo, destino_extra)
        if segmento:
            ruta_completa.extend(segmento[1:])

    return ruta_completa


def calcular_distancia(punto1, punto2):
    # Calcula la distancia en km entre dos coordenadas usando Haversine
    lat1, lon1 = math.radians(punto1[0]), math.radians(punto1[1])
    lat2, lon2 = math.radians(punto2[0]), math.radians(punto2[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))

    return 6371 * c


def obtener_distancia_total_ruta(ruta):
    if not ruta or len(ruta) < 2:
        return 0

    total = 0
    for i in range(len(ruta) - 1):
        total += calcular_distancia(ruta[i], ruta[i + 1])

    return total
