# Gemelo Digital - Vehiculo Policial
# Servidor web principal con WebSockets

# Monkey patching de gevent al inicio para compatibilidad con WebSockets
from gevent import monkey
monkey.patch_all()

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_session import Session
import os
import uuid
import threading
import time
import gzip
import logging
from io import BytesIO

# Configurar registro global
nivel_log = logging.DEBUG if os.getenv('FLASK_DEBUG', 'false').lower() == 'true' else logging.INFO
logging.basicConfig(
    level=nivel_log,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)

from config import (
    CLAVE_FLASK, DEPURACION_FLASK, HOST_SERVIDOR, PUERTO_SERVIDOR,
    INTERVALO_ACTUALIZACION, CLAVE_API_ANTHROPIC, TIEMPO_SESION, CACHE_ESTATICOS,
    COOKIE_HTTPONLY, COOKIE_SAMESITE
)

logger = logging.getLogger(__name__)
from vehiculo import VehiculoPolicial
from ia import MotorDecisionIA
from auth import (
    autenticar_usuario, registrar_sesion, cerrar_sesion,
    requerir_login, obtener_usuario_actual
)
from socketio_server import inicializar_socketio


# Inicializacion de Flask
app = Flask(__name__)
app.secret_key = CLAVE_FLASK
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(__file__), 'flask_session')
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = TIEMPO_SESION
app.config['SESSION_COOKIE_HTTPONLY'] = COOKIE_HTTPONLY
app.config['SESSION_COOKIE_SAMESITE'] = COOKIE_SAMESITE
Session(app)


@app.after_request
def comprimir_respuesta(respuesta):
    if respuesta.content_type and any(ct in respuesta.content_type for ct in ['text/', 'application/json', 'application/javascript']):
        if 'gzip' in request.headers.get('Accept-Encoding', ''):
            if respuesta.content_length is None or respuesta.content_length > 500:
                try:
                    datos = respuesta.get_data()
                    buffer_gzip = BytesIO()
                    with gzip.GzipFile(mode='wb', fileobj=buffer_gzip, compresslevel=6) as f:
                        f.write(datos)
                    respuesta.set_data(buffer_gzip.getvalue())
                    respuesta.headers['Content-Encoding'] = 'gzip'
                    respuesta.headers['Vary'] = 'Accept-Encoding'
                    respuesta.headers['Content-Length'] = len(respuesta.get_data())
                except Exception:
                    pass

    if request.path.startswith('/static/'):
        respuesta.headers['Cache-Control'] = f'public, max-age={CACHE_ESTATICOS}'
    else:
        respuesta.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'

    return respuesta


def limpiar_sesiones_antiguas():
    # Elimina archivos de sesion antiguos para empezar limpio
    dir_sesiones = app.config.get('SESSION_FILE_DIR', 'flask_session')
    if os.path.exists(dir_sesiones):
        try:
            for archivo in os.listdir(dir_sesiones):
                ruta = os.path.join(dir_sesiones, archivo)
                if os.path.isfile(ruta):
                    os.remove(ruta)
            logger.info("Sesiones antiguas limpiadas")
        except Exception as e:
            logger.warning(f"Error limpiando sesiones: {e}")


limpiar_sesiones_antiguas()


# Variables globales para los vehiculos de todos los usuarios
vehiculos = {}
bloqueo_vehiculos = threading.Lock()


# Inicializar WebSockets
socketio = inicializar_socketio(app, vehiculos, bloqueo_vehiculos)


def bucle_simulacion():
    # Hilo en segundo plano actualizando todos los vehiculos
    while True:
        try:
            with bloqueo_vehiculos:
                for vid, veh in list(vehiculos.items()):
                    try:
                        veh.actualizar_simulacion(delta_time=INTERVALO_ACTUALIZACION)
                    except Exception as e:
                        logger.error(f"Error vehiculo {vid}: {e}")
            time.sleep(INTERVALO_ACTUALIZACION)
        except Exception as e:
            logger.error(f"Error en simulacion: {e}")
            time.sleep(1)


hilo_simulacion = threading.Thread(target=bucle_simulacion, daemon=True)
hilo_simulacion.start()


def obtener_clave_api():
    if not CLAVE_API_ANTHROPIC:
        raise ValueError("ANTHROPIC_API_KEY no configurada")
    return CLAVE_API_ANTHROPIC


def obtener_o_crear_vehiculo():
    if 'vehiculo_id' not in session:
        session['vehiculo_id'] = str(uuid.uuid4())

    vid = session['vehiculo_id']
    with bloqueo_vehiculos:
        if vid not in vehiculos:
            vehiculos[vid] = VehiculoPolicial(vid)
    return vid


def obtener_vehiculo():
    vid = session.get('vehiculo_id')
    with bloqueo_vehiculos:
        if vid not in vehiculos:
            vehiculos[vid] = VehiculoPolicial(vid)
        return vehiculos[vid]


@app.before_request
def iniciar_sesion():
    # Se ejecuta antes de cada peticion para verificar login
    if request.endpoint in ['login', 'static', 'index']:
        return

    if request.path.startswith('/api/'):
        if not session.get('autenticado'):
            return jsonify({'error': 'No autenticado'}), 401
        rol = session.get('rol', 'operador')
        if rol != 'despachador':
            obtener_o_crear_vehiculo()
        return

    if not session.get('autenticado'):
        return redirect(url_for('login'))

    rol = session.get('rol', 'operador')
    if rol != 'despachador':
        obtener_o_crear_vehiculo()

    try:
        session['ia_configurada'] = bool(obtener_clave_api())
    except Exception:
        session['ia_configurada'] = False


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        contrasena = request.form.get('contrasena', '').strip()

        if not usuario or not contrasena:
            return render_template('login.html', error='Debe ingresar usuario y contraseña')

        datos_usuario = autenticar_usuario(usuario, contrasena)
        if datos_usuario:
            registrar_sesion(datos_usuario)
            session['rol'] = datos_usuario.get('rol', 'operador')
            session.modified = True

            if datos_usuario.get('rol') == 'despachador':
                return redirect(url_for('centro_comando'))
            return redirect(url_for('index_simulador'))

        return render_template('login.html', error='Usuario o contraseña incorrectos')

    if session.get('autenticado'):
        if session.get('rol') == 'despachador':
            return redirect(url_for('centro_comando'))
        return redirect(url_for('index_simulador'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    cerrar_sesion()
    return redirect(url_for('login'))


@app.route('/')
def index():
    return render_template('landing.html')


@app.route('/simulador')
@requerir_login
def index_simulador():
    usuario = obtener_usuario_actual()
    vid = session.get('vehiculo_id')

    with bloqueo_vehiculos:
        veh = vehiculos.get(vid)
        estado = veh.obtener_estado() if veh else {}

    return render_template('simulador.html',
                           estado_actual=estado,
                           ia_configurada=session.get('ia_configurada', False),
                           usuario=usuario)


@app.route('/api/simular', methods=['POST'])
@requerir_login
def api_simular():
    # Recibe texto libre y usa la IA para crear un escenario
    from rutas import generar_ruta_patrulla, obtener_distancia_total_ruta, geocodificar_direccion, generar_ruta_hacia_destino
    from config import CENTRO_MADRID
    from entorno import obtener_contexto_entorno_completo

    datos = request.json
    texto_escenario = datos.get('escenario', '').strip()

    if not texto_escenario:
        return jsonify({'error': 'Escenario vacío'}), 400

    try:
        motor = MotorDecisionIA(clave_api=obtener_clave_api())

        veh = obtener_vehiculo()
        estado = veh.obtener_estado()

        contexto_entorno = obtener_contexto_entorno_completo()

        clima_real = "soleado"
        trafico_real = "normal"

        if contexto_entorno:
            datos_clima = contexto_entorno.get('clima')
            if datos_clima and datos_clima.get('condicion'):
                clima_real = datos_clima['condicion'].get('descripcion', 'soleado')

            datos_trafico = contexto_entorno.get('trafico')
            if datos_trafico:
                trafico_real = datos_trafico.get('nivel', 'normal')

        motor.actualizar_contexto(
            condiciones_trafico=trafico_real,
            condiciones_clima=clima_real,
            tipo_terreno=datos.get('terreno', 'urbano'),
            hora_dia=datos.get('hora', 'tarde')
        )

        ubicacion_destino = None
        fases_escenario = None

        resultado = motor.analizar_escenario_completo(texto_escenario, estado)
        nombre = resultado['nombre']
        duracion = resultado['duracion']
        intensidad = resultado['intensidad']
        velocidad = resultado['velocidad']
        tipo_base = resultado['tipo_base']
        modificadores = resultado['modificadores']
        analisis = resultado['analisis']

        ubicacion_destino = resultado.get('ubicacion_destino')
        fases_escenario = resultado.get('fases_escenario')

        posicion_cliente = datos.get('posicion')
        if posicion_cliente and posicion_cliente.get('lat') and posicion_cliente.get('lng'):
            origen = (posicion_cliente.get('lat'), posicion_cliente.get('lng'))
        else:
            gps_actual = estado.get('gps')
            if gps_actual:
                origen = (gps_actual.get('latitud', CENTRO_MADRID[0]), gps_actual.get('longitud', CENTRO_MADRID[1]))
            else:
                origen = CENTRO_MADRID

        coordenadas_destino = None
        ruta = None

        if ubicacion_destino and ubicacion_destino.get('direccion'):
            direccion = ubicacion_destino['direccion']
            coordenadas_destino = geocodificar_direccion(direccion)

            if coordenadas_destino:
                ruta = generar_ruta_hacia_destino(origen, coordenadas_destino)

        if not ruta:
            ruta = generar_ruta_patrulla(origen)

        if ruta and origen:
            pos_actual = list(origen)
            if ruta[0] != pos_actual:
                primer_punto = ruta[0]
                dist = ((primer_punto[0] - pos_actual[0])**2 + (primer_punto[1] - pos_actual[1])**2)**0.5
                if dist > 0.00001:
                    ruta.insert(0, pos_actual)

        distancia_ruta = obtener_distancia_total_ruta(ruta) if ruta else 0

        veh.aplicar_escenario(
            tipo_escenario=tipo_base,
            duracion_minutos=duracion,
            intensidad=intensidad,
            velocidad_objetivo=velocidad,
            nombre_personalizado=nombre,
            modificadores=modificadores,
            ruta=ruta
        )

        num_puntos = 6
        progresion = []
        for i in range(num_puntos):
            progreso = i / (num_puntos - 1)
            minuto = duracion * progreso
            comb_inicial = estado['combustible']
            comb_final = analisis.get('estado_final_estimado', {}).get('combustible', comb_inicial * 0.7)
            temp_inicial = estado['temperatura_motor']
            temp_max = analisis.get('impacto_recursos', {}).get('temperatura_esperada', 85)

            progresion.append({
                'minuto': round(minuto, 1),
                'progreso': round(progreso * 100, 1),
                'combustible': round(comb_inicial - (comb_inicial - comb_final) * progreso, 1),
                'temperatura': round(temp_inicial + (temp_max - temp_inicial) * min(progreso * 2, 1), 1),
                'velocidad_estimada': velocidad
            })

        return jsonify({
            'exito': True,
            'analisis': {
                'nombre': nombre,
                'tipo': tipo_base,
                'duracion_estimada_min': duracion,
                'intensidad': intensidad,
                'velocidad_objetivo': velocidad,
                'modificadores': modificadores,
                'analisis_ia': analisis,
                'progresion_temporal': progresion,
                'ubicacion_destino': ubicacion_destino,
                'fases': fases_escenario,
                'coordenadas_destino': coordenadas_destino
            },
            'ruta': ruta,
            'distancia_ruta_km': round(distancia_ruta, 2),
            'entorno': contexto_entorno
        })

    except Exception as e:
        logger.error(f"Error en escenario: {e}", exc_info=True)
        return jsonify({'error': 'Error interno del servidor'}), 500


@app.route('/comando')
@requerir_login
def centro_comando():
    usuario = obtener_usuario_actual()

    if usuario.get('rol') != 'despachador':
        return redirect(url_for('index_simulador'))

    return render_template('comando.html', usuario=usuario)


@app.errorhandler(404)
def no_encontrado(e):
    return jsonify({'error': 'No encontrado'}), 404


@app.errorhandler(500)
def error_servidor(e):
    logger.error(f"Error 500: {e}")
    return jsonify({'error': 'Error interno del servidor'}), 500


if __name__ == '__main__':
    socketio.run(app, debug=DEPURACION_FLASK, host=HOST_SERVIDOR, port=PUERTO_SERVIDOR)
