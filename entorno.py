# Datos del entorno en tiempo real
# APIs: Open-Meteo (clima) y TomTom (trafico)

import requests
from datetime import datetime
import time
import logging
from config import CLAVE_TOMTOM, CENTRO_MADRID, CACHE_ENTORNO

logger = logging.getLogger(__name__)

# Coordenadas de Madrid extraidas del config
LAT_MADRID = CENTRO_MADRID[0]
LON_MADRID = CENTRO_MADRID[1]

# Cache para no exceder limites de peticiones
_cache = {}
_tiempo_cache = CACHE_ENTORNO


def _obtener_cache(clave, funcion_consulta, tiempo_limite=None):
    tiempo_limite = tiempo_limite or _tiempo_cache
    ahora = time.time()

    if clave in _cache:
        datos, marca_tiempo = _cache[clave]
        if ahora - marca_tiempo < tiempo_limite:
            return datos

    try:
        datos = funcion_consulta()
        _cache[clave] = (datos, ahora)
        return datos
    except Exception as e:
        logger.warning(f"Error obteniendo {clave}: {e}")
        if clave in _cache:
            return _cache[clave][0]
        return None


def obtener_clima_madrid():
    def consultar():
        url = "https://api.open-meteo.com/v1/forecast"
        parametros = {
            "latitude": LAT_MADRID,
            "longitude": LON_MADRID,
            "current_weather": True,
            "timezone": "Europe/Madrid"
        }

        resp = requests.get(url, params=parametros, timeout=5)
        resp.raise_for_status()
        datos = resp.json()

        actual = datos.get("current_weather", {})
        codigo_clima = actual.get("weathercode", 0)
        condicion = interpretar_codigo_clima(codigo_clima)

        return {
            "temperatura": actual.get("temperature"),
            "viento_kmh": actual.get("windspeed"),
            "direccion_viento": actual.get("winddirection"),
            "codigo": codigo_clima,
            "condicion": condicion,
            "es_dia": actual.get("is_day", 1) == 1,
            "ultima_actualizacion": datetime.now().isoformat()
        }

    return _obtener_cache("clima_madrid", consultar, tiempo_limite=600)


def interpretar_codigo_clima(codigo):
    codigos = {
        0: ("despejado", "buenas", 1.0),
        1: ("mayormente despejado", "buenas", 1.0),
        2: ("parcialmente nublado", "buenas", 1.0),
        3: ("nublado", "normales", 0.95),
        45: ("niebla", "reducidas", 0.7),
        48: ("niebla helada", "peligrosas", 0.5),
        51: ("llovizna ligera", "reducidas", 0.85),
        53: ("llovizna moderada", "reducidas", 0.8),
        55: ("llovizna intensa", "reducidas", 0.75),
        61: ("lluvia ligera", "reducidas", 0.8),
        63: ("lluvia moderada", "reducidas", 0.7),
        65: ("lluvia intensa", "peligrosas", 0.6),
        66: ("lluvia helada ligera", "peligrosas", 0.5),
        67: ("lluvia helada intensa", "peligrosas", 0.4),
        71: ("nevada ligera", "peligrosas", 0.5),
        73: ("nevada moderada", "peligrosas", 0.4),
        75: ("nevada intensa", "muy peligrosas", 0.3),
        77: ("granos de nieve", "reducidas", 0.6),
        80: ("chubascos ligeros", "reducidas", 0.8),
        81: ("chubascos moderados", "reducidas", 0.7),
        82: ("chubascos violentos", "peligrosas", 0.5),
        85: ("nevadas ligeras", "peligrosas", 0.5),
        86: ("nevadas intensas", "muy peligrosas", 0.3),
        95: ("tormenta", "peligrosas", 0.5),
        96: ("tormenta con granizo ligero", "peligrosas", 0.4),
        99: ("tormenta con granizo fuerte", "muy peligrosas", 0.3),
    }

    if codigo in codigos:
        return {
            "descripcion": codigos[codigo][0],
            "condiciones_conduccion": codigos[codigo][1],
            "factor_velocidad": codigos[codigo][2]
        }

    return {
        "descripcion": "desconocido",
        "condiciones_conduccion": "normales",
        "factor_velocidad": 1.0
    }


def obtener_estado_trafico():
    def consultar():
        url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
        parametros = {
            "key": CLAVE_TOMTOM,
            "point": f"{LAT_MADRID},{LON_MADRID}",
            "unit": "KMPH"
        }

        resp = requests.get(url, params=parametros, timeout=10)
        resp.raise_for_status()
        datos = resp.json()

        flujo = datos.get("flowSegmentData", {})

        if not flujo:
            return {
                "nivel": "desconocido",
                "factor_velocidad": 1.0,
                "descripcion": "Sin datos de trafico disponibles",
                "fuente": "TomTom",
                "ultima_actualizacion": datetime.now().isoformat()
            }

        vel_actual = flujo.get("currentSpeed", 0)
        vel_libre = flujo.get("freeFlowSpeed", 0)
        confianza = flujo.get("confidence", 0)

        if vel_libre > 0:
            ratio = vel_actual / vel_libre
        else:
            ratio = 1.0

        if ratio >= 0.9:
            nivel = "libre"
            factor = 1.0
        elif ratio >= 0.75:
            nivel = "fluido"
            factor = 0.95
        elif ratio >= 0.6:
            nivel = "moderado"
            factor = 0.85
        elif ratio >= 0.4:
            nivel = "denso"
            factor = 0.7
        else:
            nivel = "muy_denso"
            factor = 0.5

        return {
            "nivel": nivel,
            "factor_velocidad": factor,
            "velocidad_actual_kmh": round(vel_actual, 1),
            "velocidad_libre_kmh": round(vel_libre, 1),
            "ratio_flujo": round(ratio, 2),
            "confianza": round(confianza, 2),
            "descripcion": f"Trafico {nivel} en Madrid",
            "fuente": "TomTom",
            "ultima_actualizacion": datetime.now().isoformat()
        }

    return _obtener_cache("trafico_madrid", consultar, tiempo_limite=180)


def obtener_contexto_entorno_completo():
    clima = obtener_clima_madrid()
    trafico = obtener_estado_trafico()

    factor_clima = clima.get("condicion", {}).get("factor_velocidad", 1.0) if clima else 1.0
    factor_trafico = trafico.get("factor_velocidad", 1.0) if trafico else 1.0
    factor_combinado = factor_clima * factor_trafico

    alertas = []

    if clima:
        cond = clima.get("condicion", {})
        if cond.get("factor_velocidad", 1.0) < 0.7:
            alertas.append(f"Condiciones climaticas adversas: {cond.get('descripcion')}")
        if clima.get("viento_kmh", 0) > 50:
            alertas.append(f"Viento fuerte: {clima.get('viento_kmh')} km/h")

    if trafico:
        if trafico.get("nivel") == "muy_denso":
            alertas.append("Trafico muy denso en Madrid")

    return {
        "clima": clima,
        "trafico": trafico,
        "factor_velocidad_ajustado": round(factor_combinado, 2),
        "alertas_entorno": alertas,
        "timestamp": datetime.now().isoformat()
    }
