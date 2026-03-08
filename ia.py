# Conexion con la IA para analisis de escenarios

import json
import logging
from anthropic import Anthropic

logger = logging.getLogger(__name__)

from config import (
    CLAVE_API_ANTHROPIC, MODELO_IA,
    IA_MAX_TOKENS_ESCENARIO,
    IA_TEMP_ESCENARIO
)
from prompts import formatear_prompt_combinado
from helpers import (
    limitar, a_decimal, a_entero,
    extraer_json
)


class MotorDecisionIA:
    def __init__(self, clave_api=None):
        clave = clave_api or CLAVE_API_ANTHROPIC
        self.cliente = Anthropic(api_key=clave)
        self.contexto_operativo = {
            "condiciones_trafico": "normal",
            "condiciones_clima": "soleado",
            "tipo_terreno": "urbano",
            "hora_dia": "tarde"
        }

    def actualizar_contexto(self, **kwargs):
        self.contexto_operativo.update(kwargs)

    def _procesar_resultado_escenario(self, datos):
        # Valida y limpia la respuesta de la IA
        nombre = datos.get("nombre_escenario", "Escenario personalizado")[:50]
        duracion = limitar(a_entero(datos.get("duracion_minutos", 30)), 5, 480)
        intensidad = limitar(a_decimal(datos.get("intensidad", 0.5)), 0.1, 1.0)
        velocidad = limitar(a_entero(datos.get("velocidad_objetivo", 50)), 0, 200)

        tipo_base = datos.get("tipo_base", "patrulla")
        if isinstance(tipo_base, str):
            tipo_base = tipo_base.lower().strip()[:15]
            tipo_base = ''.join(c for c in tipo_base if c.isalnum() or c == '-')
            if not tipo_base:
                tipo_base = 'patrulla'
        else:
            tipo_base = 'patrulla'

        modificadores = self._extraer_modificadores(datos)

        return nombre, duracion, intensidad, velocidad, tipo_base, modificadores

    def _extraer_modificadores(self, datos):
        # Saca los factores de consumo, temperatura y desgaste
        mod = datos.get('modificadores', {}) if isinstance(datos, dict) else {}

        modificadores = {
            'consumo_factor': limitar(a_decimal(mod.get('consumo_factor', 1.0)), 0.5, 2.0),
            'temp_factor': limitar(a_decimal(mod.get('temp_factor', 1.0)), 0.5, 2.0),
            'desgaste_factor': limitar(a_decimal(mod.get('desgaste_factor', 1.0)), 0.5, 2.0),
            'aceleracion_max': limitar(a_entero(mod.get('aceleracion_max', 5)), 1, 10),
            'comportamiento_escena': self._validar_comportamiento(mod.get('comportamiento_escena')),
            'velocidad_escena': a_decimal(mod.get('velocidad_escena')) if mod.get('velocidad_escena') else None
        }

        perfil_raw = datos.get('perfil_velocidad', {})
        if perfil_raw:
            perfil = self._extraer_perfil_velocidad(perfil_raw)
            if any(v is not None for v in perfil.values()):
                modificadores['perfil_velocidad'] = perfil

        return modificadores

    def _validar_comportamiento(self, comportamiento):
        if comportamiento and str(comportamiento).lower() in ['estacionario', 'movimiento']:
            return str(comportamiento).lower()
        return 'estacionario'

    def _extraer_perfil_velocidad(self, pv):
        # Saca las velocidades para cada fase del escenario
        return {
            'vel_inicial': a_decimal(pv.get('vel_inicial')) if pv.get('vel_inicial') else None,
            'vel_pico': a_decimal(pv.get('vel_pico')) if pv.get('vel_pico') else None,
            'vel_sostenida': a_decimal(pv.get('vel_sostenida')) if pv.get('vel_sostenida') else None,
            'vel_llegada': a_decimal(pv.get('vel_llegada')) if pv.get('vel_llegada') else None,
            'variabilidad': a_decimal(pv.get('variabilidad')) if pv.get('variabilidad') else None,
            'notas': pv.get('notas') if isinstance(pv.get('notas'), str) else None
        }

    def analizar_escenario_completo(self, descripcion, estado_actual):
        # Una sola llamada a la IA para deteccion y analisis
        prompt = formatear_prompt_combinado(estado_actual, self.contexto_operativo, descripcion)

        try:
            respuesta = self.cliente.messages.create(
                model=MODELO_IA,
                max_tokens=IA_MAX_TOKENS_ESCENARIO,
                temperature=IA_TEMP_ESCENARIO,
                messages=[{"role": "user", "content": prompt}]
            )

            texto = extraer_json(respuesta.content[0].text)
            datos = json.loads(texto)

            deteccion = datos.get('deteccion', {})
            analisis = datos.get('analisis', {})

            nombre, duracion, intensidad, velocidad, tipo_base, modificadores = self._procesar_resultado_escenario(deteccion)

            ubicacion_destino = deteccion.get('ubicacion_destino')
            fases_escenario = deteccion.get('fases_escenario')

            for campo in ['analisis_riesgos', 'impacto_recursos', 'viabilidad']:
                if campo not in analisis:
                    analisis[campo] = self._valor_por_defecto(campo, estado_actual)

            apoyo = analisis.get('tipo_apoyo_necesario')
            if isinstance(apoyo, str) and apoyo:
                analisis['tipo_apoyo_necesario'] = [a.strip() for a in apoyo.split(',')]
            elif not apoyo:
                analisis['tipo_apoyo_necesario'] = None

            return {
                'nombre': nombre,
                'duracion': duracion,
                'intensidad': intensidad,
                'velocidad': velocidad,
                'tipo_base': tipo_base,
                'modificadores': modificadores,
                'analisis': analisis,
                'ubicacion_destino': ubicacion_destino,
                'fases_escenario': fases_escenario
            }

        except Exception as e:
            logger.error(f"Error en analizar_escenario_completo: {e}")
            raise

    def _valor_por_defecto(self, campo, estado):
        por_defecto = {
            'analisis_riesgos': ['Analisis no disponible'],
            'impacto_recursos': {
                'combustible_estimado': estado.get('combustible', 50) * 0.8,
                'tiempo_estimado': 30,
                'desgaste_componentes': {'frenos': 'medio', 'motor': 'medio', 'neumaticos': 'medio'},
                'temperatura_esperada': 80
            },
            'viabilidad': 'condicionada'
        }
        return por_defecto.get(campo, None)
