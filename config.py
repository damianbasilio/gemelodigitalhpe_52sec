import os
from dotenv import load_dotenv

load_dotenv()

# Configuracion de Flask
CLAVE_FLASK = os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex())
DEPURACION_FLASK = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
HOST_SERVIDOR = os.getenv('HOST_SERVIDOR', '0.0.0.0')
PUERTO_SERVIDOR = int(os.getenv('PUERTO_SERVIDOR', 5000))

# API de Anthropic
CLAVE_API_ANTHROPIC = os.getenv("ANTHROPIC_API_KEY")
MODELO_IA = os.getenv("MODELO_IA", "claude-sonnet-4-20250514")

# Intervalo de actualizacion del simulador (segundos)
INTERVALO_ACTUALIZACION = float(os.getenv('INTERVALO_SIM', 0.1))

# Rangos aleatorios iniciales del vehiculo (minimo, maximo)
RANGO_COMBUSTIBLE_INICIAL = (60, 95)
RANGO_KM_INICIAL = (15000, 80000)
RANGO_TEMP_INICIAL = (65, 75)
RANGO_ACEITE_INICIAL = (80, 100)
RANGO_DESGASTE_FRENOS = (20, 60)
RANGO_DESGASTE_NEUMATICOS = (30, 70)

# Parametros de operacion del vehiculo
VELOCIDAD_PATRULLA = int(os.getenv('VELOCIDAD_PATRULLA', 35))
TASA_REABASTECIMIENTO = float(os.getenv('TASA_REABASTECIMIENTO', 2.0))
UMBRAL_COMBUSTIBLE = int(os.getenv('UMBRAL_COMBUSTIBLE', 15))
TEMP_AMBIENTE = float(os.getenv('TEMP_AMBIENTE', 25.0))
TEMP_MAXIMA = int(os.getenv('TEMP_MAXIMA', 120))
VELOCIDAD_MAXIMA = int(os.getenv('VELOCIDAD_MAXIMA', 200))

# Coordenadas centrales de Madrid (latitud, longitud)
CENTRO_MADRID = (40.4168, -3.7038)

# Limite de tokens para el analisis de escenarios
IA_MAX_TOKENS_ESCENARIO = int(os.getenv('IA_MAX_TOKENS_ESCENARIO', 2000))

# Temperatura de creatividad para la IA
IA_TEMP_ESCENARIO = float(os.getenv('IA_TEMP_ESCENARIO', 0.5))

# Clave API de TomTom para datos de trafico
CLAVE_TOMTOM = os.getenv("TOMTOM_API_KEY")

# Cache de datos de entorno (segundos)
CACHE_ENTORNO = int(os.getenv('CACHE_ENTORNO', 300))

# Tiempo de vida de sesion (segundos)
TIEMPO_SESION = int(os.getenv('TIEMPO_SESION', 3600))

# Maximo de puntos del rastro en difusion
MAX_PUNTOS_RASTRO = int(os.getenv('MAX_PUNTOS_RASTRO', 100))

# Distancia maxima del rastro visual (km)
DIST_MAX_RASTRO = float(os.getenv('DIST_MAX_RASTRO', 0.5))

# Cache de archivos estaticos (segundos)
CACHE_ESTATICOS = int(os.getenv('CACHE_ESTATICOS', 31536000))

# Origenes permitidos para CORS/WebSocket (separados por coma, o * para todos)
_cors_raw = os.getenv('CORS_ORIGENES', '*')
CORS_ORIGENES = _cors_raw if _cors_raw == '*' else [o.strip() for o in _cors_raw.split(',')]

# Seguridad de cookies de sesion
COOKIE_HTTPONLY = True
COOKIE_SAMESITE = 'Lax'
