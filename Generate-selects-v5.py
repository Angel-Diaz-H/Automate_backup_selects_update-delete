# Librerías necesarias.
import re
from pathlib import Path
from collections import defaultdict

# Función principal que transforma sentencias UPDATE y DELETE en SELECT para respaldo.
def generar_selects_de_respaldo(texto_sql: str):
    # Elimina comentarios de línea (-- y /* */ del SQL para evitar procesar líneas comentadas.
    texto_limpio = re.sub(r"--.*", "", texto_sql)
    texto_limpio = re.sub(r"/\*.*?\*/", "", texto_limpio, flags=re.DOTALL)

    '''Quitamos la agrupación y el criterio de delete y update, por punto y coma.
    # Une todas las líneas en una sola para facilitar el procesamiento con expresiones regulares.
    texto_unido = " ".join(line.strip() for line in texto_limpio.splitlines() if line.strip())

    # Divide el texto en sentencias UPDATE y DELETE usando lookahead para mantener el delimitador.
    sentencias = re.split(r"\b(?=delete|update)\b", texto_unido, flags=re.IGNORECASE)
    '''

    # VERSIÓN 5.
    # Divide el texto en sentencias usando punto y coma como delimitador
    sentencias = [x.strip() for x in re.split(r";", texto_limpio) if x.strip()]

    # Estructuras para agrupar condiciones simples por tabla y columna.
    agrupados = defaultdict(lambda: defaultdict(set))
    columnas_orden = defaultdict(list)
    selects_individuales = []

    for sentencia in sentencias:
        sentencia = sentencia.strip()
        if not sentencia:
            continue

        # Ignora sentencias irrelevantes o de control de transacciones.
        if not sentencia or sentencia.lower().startswith(("set ", "commit", "rollback", "begin", "start transaction", "use ", "create ", "drop ", "alter ", "grant ", "revoke")):
            continue

        # Extrae nombre de la tabla y condiciones del WHERE para UPDATE y DELETE.
        m_update = re.match(r"^update\s+([a-zA-Z0-9_.]+)\s+set\s+.+?\s+where\s+(.+)", sentencia, re.IGNORECASE)
        m_delete = re.match(r"^delete\s+from\s+([a-zA-Z0-9_.]+)\s+where\s+(.+)", sentencia, re.IGNORECASE)

        if m_update:
            tabla = m_update.group(1)
            condiciones = m_update.group(2).strip().rstrip(";")
        elif m_delete:
            tabla = m_delete.group(1)
            condiciones = m_delete.group(2).strip().rstrip(";")
        else:
            # Si la sentencia no es UPDATE/DELETE con WHERE, la ignora.
            continue

        # Divide las condiciones del WHERE por AND para procesarlas individualmente.
        condiciones_lista = [c.strip() for c in re.split(r"\bAND\b", condiciones, flags=re.IGNORECASE)]
        columnas = []
        valores = []
        todas_simples = True  # Bandera para saber si todas las condiciones son simples.
        condiciones_complejas = []  # Almacena condiciones no agrupables (complejas).

        for cond in condiciones_lista:
            # Regex extendido para soportar más operadores:
            # =, >, <, >=, <=, <>, !=, like, in, not in, between, is null, is not null
            m_cond = re.match(
                r"([a-zA-Z0-9_]+)\s*(=|>|<|>=|<=|<>|!=|like|in|not in|between|is null|is not null)\s*(.*)", 
                cond, 
                re.IGNORECASE
            )
            if m_cond:
                operador = m_cond.group(2).lower()
                col = m_cond.group(1)
                val = m_cond.group(3).strip()
                # Solo agrupamos condiciones simples (=) y también IN.
                if operador == "=":
                    columnas.append(col)
                    valores.append(val)
                elif operador == "in":
                    # Agrupa los valores del IN en el respaldo.
                    val_clean = val.lstrip("(").rstrip(")")
                    for v in [v.strip() for v in val_clean.split(",")]:
                        columnas.append(col)
                        valores.append(v)
                else:
                    # Cualquier otro operador se considera complejo.
                    todas_simples = False
                    condiciones_complejas.append(cond)
            else:
                # Si la condición no coincide con el patrón, también se considera compleja.
                todas_simples = False
                condiciones_complejas.append(cond)

        if todas_simples and columnas:
            # Si todas las condiciones son agrupables, se guardan para generar un SELECT de respaldo agrupado.
            if not columnas_orden[tabla]:
                columnas_orden[tabla] = columnas
            for col, val in zip(columnas, valores):
                agrupados[tabla][col].add(val)
        else:
            # Junta todas las condiciones (complejas y las simples que no son =/IN) en un SELECT individual.
            select_where = " AND ".join(condiciones_lista)
            selects_individuales.append(f"SELECT * FROM {tabla} WHERE {select_where};")

    # Genera los SELECTs agrupados usando IN para cada columna involucrada.
    selects_generados = []
    for tabla, columnas_dict in agrupados.items():
        # Mantiene el orden original de las columnas o las ordena alfabéticamente si no hay orden previo.
        orden = columnas_orden[tabla] if columnas_orden[tabla] else sorted(columnas_dict.keys())
        condiciones = []
        for col in orden:
            vals = columnas_dict[col]
            lista = ",".join(sorted(vals, key=lambda x: str(x)))
            condiciones.append(f"{col} IN ({lista})")
        if condiciones:
            selects_generados.append(f"SELECT * FROM {tabla} WHERE {' AND '.join(condiciones)};")

    # Agrega los SELECTs individuales generados por condiciones complejas.
    selects_generados.extend(selects_individuales)
    return selects_generados

# Ejecución principal del script.
if __name__ == "__main__":
    # Archivos de entrada.
    archivos = [f.name for f in Path('.').iterdir() if f.is_file()]

    # Versión 5: Indicar el archivo de entrada.
    # Valida que haya archivos en la carpeta actual.
    if not archivos:
        # Si no hay archivos, muestra un mensaje y termina el script.
        print("No se encontraron archivos en la carpeta actual.")
        exit(1)
    else:
        # Si hay archivos, permite al usuario seleccionar uno.
        print("Archivos encontrados en la carpeta actual:")
        # Muestra los archivos encontrados y permite al usuario seleccionar uno.
        for idx, archivo in enumerate(archivos, 1):
            print(f"{idx}. {archivo}")
        print("-----------------------------------------------")
        while True:
            seleccion = input("Selecciona el número de archivo: ")
            if seleccion.isdigit() and 1 <= int(seleccion) <= len(archivos):
                break
            print("Opción no válida. Intenta de nuevo.")
        ruta_entrada = Path(archivos[int(seleccion) - 1])

    # Archivo de salida.
    ruta_salida = Path("script-selects.txt")

    # Continuar solo si existe el archivo de entrada.
    if ruta_entrada.exists():
        try:
            # Lee el archivo de entrada y genera los SELECTs de respaldo.
            contenido = ruta_entrada.read_text(encoding="utf-8")
            # Genera los SELECTs de respaldo agrupados. Retorna una lista de SELECTs.
            selects = generar_selects_de_respaldo(contenido)
            # Abre el archivo de salida y escribe los SELECTs generados.
            with ruta_salida.open("w", encoding="utf-8") as f:
                # Escribe el encabezado en el archivo de salida.
                f.write("-- SELECTS DE RESPALDO AGRUPADOS --\n")
                # Agrega los SELECTs generados al archivo de salida.
                for sel in selects:
                    f.write(sel + "\n")
            # Mensaje de éxito.
            print("-----------------------------------------------")
            print(f"Archivo generado correctamente en: {ruta_salida.resolve()}")
        except Exception as e:
            # Manejo de errores al procesar los archivos.
            print(f"Error al procesar los archivos: {e}")
        print("----------------------------------------------------")