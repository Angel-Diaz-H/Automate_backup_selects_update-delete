import re
from pathlib import Path
from collections import defaultdict
import sqlparse

def limpiar_comentarios(texto_sql: str) -> str:
    # Elimina comentarios de línea y bloque
    texto_limpio = re.sub(r"--.*", "", texto_sql)
    texto_limpio = re.sub(r"/\*.*?\*/", "", texto_limpio, flags=re.DOTALL)
    return texto_limpio

def generar_selects_de_respaldo(texto_sql: str):
    texto_limpio = limpiar_comentarios(texto_sql)
    # Usa sqlparse para dividir en sentencias, aunque no tengan punto y coma
    sentencias = [s for s in sqlparse.split(texto_limpio) if s.strip()]

    agrupados = defaultdict(lambda: defaultdict(set))
    columnas_orden = defaultdict(list)
    selects_individuales = []

    for sentencia in sentencias:
        sentencia = sentencia.strip()
        if not sentencia:
            continue

        # Ignora sentencias irrelevantes
        if sentencia.lower().startswith((
            "set ", "commit", "rollback", "begin", "start transaction", "use ",
            "create ", "drop ", "alter ", "grant ", "revoke"
        )):
            continue

        # Extrae nombre de la tabla y condiciones del WHERE para UPDATE y DELETE
        m_update = re.match(r"^update\s+([a-zA-Z0-9_.]+)\s+set\s+.+?\s+where\s+(.+)", sentencia, re.IGNORECASE)
        m_delete = re.match(r"^delete\s+from\s+([a-zA-Z0-9_.]+)\s+where\s+(.+)", sentencia, re.IGNORECASE)

        if m_update:
            tabla = m_update.group(1)
            condiciones = m_update.group(2).strip().rstrip(";")
        elif m_delete:
            tabla = m_delete.group(1)
            condiciones = m_delete.group(2).strip().rstrip(";")
        else:
            continue

        condiciones_lista = [c.strip() for c in re.split(r"\bAND\b", condiciones, flags=re.IGNORECASE)]
        columnas = []
        valores = []
        todas_simples = True
        condiciones_complejas = []

        for cond in condiciones_lista:
            m_cond = re.match(
                r"([a-zA-Z0-9_]+)\s*(=|>|<|>=|<=|<>|!=|like|in|not in|between|is null|is not null)\s*(.*)",
                cond,
                re.IGNORECASE
            )
            if m_cond:
                operador = m_cond.group(2).lower()
                col = m_cond.group(1)
                val = m_cond.group(3).strip()
                if operador == "=":
                    columnas.append(col)
                    valores.append(val)
                elif operador == "in":
                    val_clean = val.lstrip("(").rstrip(")")
                    for v in [v.strip() for v in val_clean.split(",")]:
                        columnas.append(col)
                        valores.append(v)
                else:
                    todas_simples = False
                    condiciones_complejas.append(cond)
            else:
                todas_simples = False
                condiciones_complejas.append(cond)

        if todas_simples and columnas:
            if not columnas_orden[tabla]:
                columnas_orden[tabla] = columnas
            for col, val in zip(columnas, valores):
                agrupados[tabla][col].add(val)
        else:
            select_where = " AND ".join(condiciones_lista)
            selects_individuales.append(f"SELECT * FROM {tabla} WHERE {select_where};")

    selects_generados = []
    for tabla, columnas_dict in agrupados.items():
        orden = columnas_orden[tabla] if columnas_orden[tabla] else sorted(columnas_dict.keys())
        condiciones = []
        for col in orden:
            vals = columnas_dict[col]
            lista = ",".join(sorted(vals, key=lambda x: str(x)))
            condiciones.append(f"{col} IN ({lista})")
        if condiciones:
            selects_generados.append(f"SELECT * FROM {tabla} WHERE {' AND '.join(condiciones)};")

    selects_generados.extend(selects_individuales)
    return selects_generados

if __name__ == "__main__":
    archivos = [f.name for f in Path('.').iterdir() if f.is_file()]
    if not archivos:
        print("No se encontraron archivos en la carpeta actual.")
        exit(1)
    else:
        print("Archivos encontrados en la carpeta actual:")
        for idx, archivo in enumerate(archivos, 1):
            print(f"{idx}. {archivo}")
        print("-----------------------------------------------")
        while True:
            seleccion = input("Selecciona el número de archivo: ")
            if seleccion.isdigit() and 1 <= int(seleccion) <= len(archivos):
                break
            print("Opción no válida. Intenta de nuevo.")
        ruta_entrada = Path(archivos[int(seleccion) - 1])

    ruta_salida = Path("script-selects.txt")

    if ruta_entrada.exists():
        try:
            contenido = ruta_entrada.read_text(encoding="utf-8")
            selects = generar_selects_de_respaldo(contenido)
            with ruta_salida.open("w", encoding="utf-8") as f:
                f.write("-- SELECTS DE RESPALDO AGRUPADOS --\n")
                for sel in selects:
                    f.write(sel + "\n")
            print("-----------------------------------------------")
            print(f"Archivo generado correctamente en: {ruta_salida.resolve()}")
        except Exception as e:
            print(f"Error al procesar los archivos: {e}")
        print("----------------------------------------------------")