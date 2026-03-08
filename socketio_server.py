# Servidor WebSocket para comunicacion en tiempo real

from flask_socketio import SocketIO, emit, join_room
from datetime import datetime
import threading
import time
import logging
from config import INTERVALO_ACTUALIZACION, MAX_PUNTOS_RASTRO, CORS_ORIGENES

logger = logging.getLogger(__name__)

# Instancia global de SocketIO
socketio = None

# Almacenamiento de conexiones activas
conexiones_activas = {}
bloqueo_conexiones = threading.Lock()

# Sala especial para centro de comando
SALA_DESPACHADORES = 'despachadores'


def inicializar_socketio(app, vehiculos, bloqueo_vehiculos):
    global socketio

    socketio = SocketIO(
        app,
        cors_allowed_origins=CORS_ORIGENES,
        async_mode='gevent',
        ping_timeout=60,
        ping_interval=25
    )

    registrar_manejadores(vehiculos, bloqueo_vehiculos)

    hilo_difusion = threading.Thread(
        target=bucle_difusion,
        args=(vehiculos, bloqueo_vehiculos),
        daemon=True
    )
    hilo_difusion.start()

    return socketio


def registrar_manejadores(vehiculos, bloqueo_vehiculos):

    @socketio.on('connect')
    def manejar_conexion():
        from flask import session, request

        sid = request.sid
        vehiculo_id = session.get('vehiculo_id')
        usuario = session.get('usuario_nombre', session.get('usuario'))
        rol = session.get('usuario_rol', 'operador')

        with bloqueo_conexiones:
            conexiones_activas[sid] = {
                'sid': sid,
                'vehiculo_id': vehiculo_id,
                'usuario': usuario,
                'rol': rol,
                'conectado_at': datetime.now().isoformat()
            }

        if rol == 'despachador':
            join_room(SALA_DESPACHADORES)

        logger.info(f"[WS] Conectado: {usuario} (rol: {rol}, vid: {vehiculo_id})")

        if vehiculo_id:
            with bloqueo_vehiculos:
                if vehiculo_id in vehiculos:
                    veh = vehiculos[vehiculo_id]
                    emit('estado_inicial', {
                        'vehiculo_id': vehiculo_id,
                        'estado': veh.obtener_estado(),
                        'ruta': veh.gps.ruta
                    })

    @socketio.on('disconnect')
    def manejar_desconexion():
        # Cuando un cliente se desconecta, limpiar su sesion y vehiculo
        from flask import request

        sid = request.sid
        vehiculo_id = None
        rol = None

        with bloqueo_conexiones:
            if sid in conexiones_activas:
                info = conexiones_activas.pop(sid)
                vehiculo_id = info.get('vehiculo_id')
                rol = info.get('rol')
                logger.info(f"[WS] Desconectado: {info.get('usuario')} (rol: {rol})")

        if vehiculo_id and rol != 'despachador':
            with bloqueo_vehiculos:
                if vehiculo_id in vehiculos:
                    del vehiculos[vehiculo_id]
                    logger.info(f"[WS] Vehiculo {vehiculo_id[:8]}... eliminado")

            notificar_despachadores('vehiculo_desconectado', {
                'vehiculo_id': vehiculo_id,
                'timestamp': datetime.now().isoformat()
            })

    @socketio.on('control_simulacion')
    def manejar_control(datos):
        # Controlar la simulacion (terminar escenario)
        from flask import session

        vehiculo_id = session.get('vehiculo_id')
        if not vehiculo_id:
            return

        accion = datos.get('accion')

        with bloqueo_vehiculos:
            if vehiculo_id not in vehiculos:
                return

            veh = vehiculos[vehiculo_id]

            if accion == 'terminar':
                veh.terminar_escenario()

            emit('estado_vehiculo', {
                'vehiculo_id': vehiculo_id,
                'estado': veh.obtener_estado()
            })

    @socketio.on('solicitar_todos_vehiculos')
    def manejar_solicitar_todos(datos=None):
        # Despachador solicita estado de todos los vehiculos conectados
        from flask import session, request

        rol = session.get('usuario_rol', 'operador')
        if rol != 'despachador':
            emit('error', {'mensaje': 'Acceso denegado'})
            return

        vehiculos_estado = []

        with bloqueo_conexiones:
            operadores = {sid: dict(info) for sid, info in conexiones_activas.items()
                        if info.get('rol') == 'operador' and info.get('vehiculo_id')}

        with bloqueo_vehiculos:
            for sid, info in operadores.items():
                vid = info.get('vehiculo_id')
                if vid not in vehiculos:
                    continue

                veh = vehiculos[vid]
                estado = veh.obtener_estado()
                gps = estado.get('gps', {})
                esc = estado.get('escenario', {})

                vehiculos_estado.append({
                    'vehiculo_id': vid,
                    'operador': info.get('usuario'),
                    'usuario': info.get('usuario'),
                    'posicion': {'lat': gps.get('latitud'), 'lon': gps.get('longitud')},
                    'velocidad': estado.get('velocidad', 0),
                    'combustible': estado.get('combustible'),
                    'temperatura': estado.get('temperatura_motor'),
                    'escenario': esc.get('activo', 'patrulla'),
                    'fase': 'en_escena' if getattr(veh, 'en_escena', False) else 'transito',
                    'rastro': getattr(veh, 'rastro', [])[-MAX_PUNTOS_RASTRO:],
                    'ruta': veh.gps.ruta or [],
                    'indice_ruta': veh.gps.indice_ruta,
                    'estado': {
                        'combustible': estado.get('combustible'),
                        'temperatura': estado.get('temperatura_motor'),
                        'kilometraje': estado.get('km_totales'),
                        'desgaste_frenos': estado.get('desgaste_frenos'),
                        'desgaste_neumaticos': estado.get('desgaste_neumaticos'),
                        'nivel_aceite': estado.get('nivel_aceite')
                    },
                    'ultima_actualizacion': datetime.now().isoformat()
                })

        emit('todos_vehiculos', {
            'vehiculos': vehiculos_estado,
            'total': len(vehiculos_estado),
            'timestamp': datetime.now().isoformat()
        })


def notificar_despachadores(evento, datos):
    if socketio:
        socketio.emit(evento, datos, room=SALA_DESPACHADORES)


def bucle_difusion(vehiculos, bloqueo_vehiculos):
    # Hilo de difusion: envia el estado del vehiculo a cada operador
    intervalo_difusion = INTERVALO_ACTUALIZACION
    intervalo_despachadores = 5
    versiones_ruta = {}
    contador_ticks = 0

    while True:
        try:
            time.sleep(intervalo_difusion)

            if not socketio:
                continue

            contador_ticks += 1

            with bloqueo_conexiones:
                operadores = {sid: dict(info) for sid, info in conexiones_activas.items()
                            if info.get('rol') == 'operador' and info.get('vehiculo_id')}
                hay_despachadores = any(
                    info.get('rol') == 'despachador' for info in conexiones_activas.values()
                )

            if not operadores and not hay_despachadores:
                continue

            with bloqueo_vehiculos:
                for sid, info in operadores.items():
                    vid = info.get('vehiculo_id')
                    if vid not in vehiculos:
                        continue

                    veh = vehiculos[vid]
                    estado = veh.obtener_estado_broadcast()

                    payload = {
                        'vehiculo_id': vid,
                        'estado': estado,
                        'timestamp': datetime.now().isoformat(),
                        'rastro': veh.rastro
                    }

                    version_actual = getattr(veh, 'version_ruta', 0)
                    if versiones_ruta.get(sid) != version_actual:
                        payload['ruta'] = veh.gps.ruta
                        versiones_ruta[sid] = version_actual

                    try:
                        socketio.emit('estado_vehiculo', payload, to=sid)
                    except Exception:
                        pass

                if hay_despachadores and contador_ticks % intervalo_despachadores == 0:
                    for sid, info in operadores.items():
                        vid = info.get('vehiculo_id')
                        if vid not in vehiculos:
                            continue

                        veh = vehiculos[vid]
                        estado = veh.obtener_estado()
                        gps = estado.get('gps', {})
                        esc = estado.get('escenario', {})

                        notificar_despachadores('actualizacion_vehiculo', {
                            'vehiculo_id': vid,
                            'operador': info.get('usuario'),
                            'usuario': info.get('usuario'),
                            'posicion': {'lat': gps.get('latitud'), 'lon': gps.get('longitud')},
                            'velocidad': estado.get('velocidad', 0),
                            'combustible': estado.get('combustible'),
                            'temperatura': estado.get('temperatura_motor'),
                            'escenario': esc.get('activo', 'patrulla'),
                            'fase': 'en_escena' if getattr(veh, 'en_escena', False) else 'transito',
                            'rastro': getattr(veh, 'rastro', [])[-MAX_PUNTOS_RASTRO:],
                            'ruta': veh.gps.ruta or [],
                            'indice_ruta': veh.gps.indice_ruta,
                            'kilometraje': estado.get('km_totales'),
                            'desgaste_frenos': estado.get('desgaste_frenos'),
                            'desgaste_neumaticos': estado.get('desgaste_neumaticos'),
                            'nivel_aceite': estado.get('nivel_aceite'),
                            'timestamp': estado.get('timestamp')
                        })

        except Exception as e:
            logger.error(f"[Difusion] Error: {e}")
            time.sleep(1)

