# Plantillas de prompts para comunicarse con la IA

PROMPT_ESCENARIO_COMBINADO = """
Analiza el siguiente escenario operativo para un vehículo policial.
La simulación ocurre en la ciudad de Madrid, España.

VEHÍCULO:
- Combustible: {combustible}%
- Temperatura motor: {temperatura}°C
- Velocidad actual: {velocidad} km/h
- Kilómetros totales: {km_totales} km

CONTEXTO:
- Tráfico: {trafico}
- Clima: {clima}
- Terreno: {terreno}
- Hora: {hora}

ESCENARIO:
{escenario}

Responde ÚNICAMENTE con un JSON válido sin markdown:

{{
    "deteccion": {{
        "nombre_escenario": "Nombre descriptivo (max 50 chars)",
        "duracion_minutos": número entre 5 y 480,
        "intensidad": decimal entre 0.1 y 1.0,
        "velocidad_objetivo": número entre 0 y 200 km/h (velocidad máxima durante tránsito),
        "tipo_base": "palabra corta que describa el tipo de escenario basándote en la descripción (ej: emergencia, vigilancia, rescate, busqueda, traslado, intervencion, respuesta, etc - una sola palabra en español sin acentos)",
        "ubicacion_destino": {{
            "direccion": "dirección o lugar mencionado en el escenario, o null si no hay",
            "descripcion": "descripción breve del lugar si se menciona",
            "requiere_permanencia": boolean (true si el vehículo debe quedarse en el lugar)
        }},
        "fases_escenario": {{
            "transito_minutos": número (tiempo estimado para llegar al destino),
            "en_escena_minutos": número (tiempo en el lugar, 0 si no aplica),
            "retorno_patrulla": boolean (si debe volver a patrullaje al terminar)
        }},
        "modificadores": {{
            "consumo_factor": decimal 0.5-2.0,
            "temp_factor": decimal 0.5-2.0,
            "desgaste_factor": decimal 0.5-2.0,
            "aceleracion_max": entero 1-10,
            "comportamiento_escena": "estacionario" | "movimiento",
            "velocidad_escena": número (velocidad mientras está en escena, 0 si parado)
        }},
        "perfil_velocidad": {{
            "vel_inicial": número opcional,
            "vel_pico": número opcional,
            "vel_sostenida": número opcional,
            "vel_llegada": número opcional,
            "variabilidad": decimal 0.0-1.0,
            "notas": "explicación breve"
        }}
    }},
    "analisis": {{
        "analisis_riesgos": ["riesgo 1", "riesgo 2"],
        "impacto_recursos": {{
            "combustible_estimado": número % restante,
            "tiempo_estimado": minutos,
            "desgaste_componentes": {{"frenos": "bajo|medio|alto", "motor": "...", "neumaticos": "..."}},
            "temperatura_esperada": número °C
        }},
        "acciones_recomendadas": [{{"paso": 1, "accion": "descripción", "prioridad": "baja|media|alta"}}],
        "requiere_apoyo": boolean,
        "tipo_apoyo_necesario": null | ["tipo1", "tipo2"],
        "alertas_criticas": [],
        "viabilidad": "viable" | "condicionada" | "arriesgado" | "no_recomendado",
        "estado_final_estimado": {{
            "combustible": número,
            "condicion_vehiculo": "óptimo" | "aceptable" | "degradado" | "crítico"
        }},
        "justificacion_viabilidad": "explicación breve"
    }}
}}
"""

def formatear_prompt_combinado(estado, contexto, escenario):
    return PROMPT_ESCENARIO_COMBINADO.format(
        combustible=estado.get('combustible', 0),
        temperatura=estado.get('temperatura_motor', 0),
        velocidad=estado.get('velocidad', 0),
        km_totales=estado.get('km_totales', 0),
        trafico=contexto.get('condiciones_trafico', 'normal'),
        clima=contexto.get('condiciones_clima', 'soleado'),
        terreno=contexto.get('tipo_terreno', 'urbano'),
        hora=contexto.get('hora_dia', 'tarde'),
        escenario=escenario
    )
