import os
import time
import gspread
import json
import telebot
import requests
import threading
import re
from openai import OpenAI
from google.oauth2.service_account import Credentials

# ============================================================
#  CONFIGURACIÓN
# ============================================================
BOT_TOKEN      = "8760821152:AAFQ-RZ5Z2XUQl6tQlkENm68ry0aGNXvhaI"
IMGBB_API_KEY  = "1bf0e7241781b18bd1176a8a0d6d186a"
OPENAI_API_KEY = "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"
SHEETS_URL     = "https://docs.google.com/spreadsheets/d/1ZYsZE_OaSB-yB9O0Sw5A4c0qljrHs3Zj9qisKFFHodM"

# ============================================================
#  INICIALIZACIÓN
# ============================================================
bot = telebot.TeleBot(BOT_TOKEN)
cliente_ai = OpenAI(api_key=OPENAI_API_KEY)

dir_actual = os.path.dirname(os.path.abspath(__file__))
ruta_json  = os.path.join(dir_actual, "credenciales.json")

try:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds          = Credentials.from_service_account_file(ruta_json, scopes=scopes)
    cliente_sheets = gspread.authorize(creds)
    sheet          = cliente_sheets.open_by_url(SHEETS_URL).sheet1
    print("✅ Conexión a Google Sheets lista.")
except Exception as e:
    print(f"❌ Error crítico de conexión a Sheets: {e}")
    sheet = None

# ============================================================
#  FUNCIÓN CLAVE: ENCUENTRA LA SIGUIENTE FILA VACÍA EN COL A
# ============================================================
def obtener_siguiente_fila_vacia(hoja):
    """
    Busca la primera fila vacía mirando SOLO la columna A.
    Esto evita que gspread se confunda por datos sueltos en
    columnas lejanas (AE, AJ, AO, etc.) y salte filas.
    """
    try:
        col_a = hoja.col_values(1)  # Lee solo la columna A
        # col_values ignora celdas vacías al final, así que
        # len(col_a) + 1 es siempre la siguiente fila libre.
        return len(col_a) + 1
    except Exception as e:
        print(f"Error obteniendo fila vacía: {e}")
        return None

# ============================================================
#  INTELIGENCIA ARTIFICIAL
# ============================================================
def procesar_mensaje(mensaje_texto, urls_fotos):
    prompt = f"""
    Eres un analista de datos experto en gorras streetwear.
    
    REGLA 1: El "Nombre" debe usar EXACTAMENTE las palabras descriptivas del mensaje del usuario. NO abrevies, NO cambies, NO traduzcas ninguna palabra. Conserva toda la descripción tal como la escribió el usuario (marca, edición, color, equipo, etc).
    REGLA 2: Identifica la "Marca" (New Era, Barbas, Dandy, 31 Hats, Innedit, JC, Fino, Big Boss, DR, Rude, Problm, JJ Hats, Báez, Rebel, JC Caps, Markitos, Star Hats).
    REGLA 3: Extrae TODAS las tallas mencionadas y únelas EXCLUSIVAMENTE con el símbolo | (Ejemplo: "7 1/8 | 7 1/4 | 7 1/2"). Si no hay tallas, pon "".
    REGLA 4: Extrae el "Precio" normal y el "Precio Mayoreo" (solo el número, sin el signo de pesos).
    REGLA 5: Si el texto dice 'nuevo', 'new' o algo similar, pon la "Etiqueta" como "NUEVO". Si no, pon "".
    REGLA 6: Devuelve SOLO el JSON, nada de texto extra.
    
    Formato esperado:
    {{
        "Nombre": "NEW ERA EDICION ANAHEIM DUCKS",
        "Marca": "New Era",
        "Precio": 1000,
        "Precio Mayoreo": 750,
        "Etiqueta": "",
        "Tallas": "7 | 7 1/8"
    }}
    
    Mensaje del usuario: "{mensaje_texto}"
    """
    try:
        respuesta = cliente_ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        texto = respuesta.choices[0].message.content

        coincidencia = re.search(r'\{.*\}', texto, re.DOTALL)
        if not coincidencia:
            return "❌ Error IA: El formato devuelto no es válido."

        datos = json.loads(coincidencia.group(0))

        while len(urls_fotos) < 4:
            urls_fotos.append("")

        fila = [
            datos.get("Nombre", "Gorra"),
            datos.get("Marca", ""),
            datos.get("Precio", 0),
            datos.get("Precio Mayoreo", 0),
            datos.get("Etiqueta", ""),
            urls_fotos[0],
            urls_fotos[1],
            urls_fotos[2],
            urls_fotos[3],
            datos.get("Tallas", ""),
        ]

        if sheet:
            # ✅ CORRECCIÓN: buscar la fila vacía real en columna A
            siguiente_fila = obtener_siguiente_fila_vacia(sheet)

            if siguiente_fila:
                # Escribir la fila completa de una sola vez en el rango correcto
                rango = f"A{siguiente_fila}:J{siguiente_fila}"
                sheet.update(rango, [fila])
                print(f"✅ Fila escrita en la fila {siguiente_fila}")
            else:
                return "❌ Error: No se pudo determinar la fila vacía en Sheets."

        return (
            f"✅ ¡Gorra agregada con Éxito!\n"
            f"🧢 {datos.get('Nombre')}\n"
            f"📏 Tallas: {datos.get('Tallas')}\n"
            f"📸 {sum(1 for u in urls_fotos if u != '')} fotos guardadas."
        )
    except Exception as e:
        return f"❌ Error en IA o Sheets: {e}"

# ============================================================
#  SUBIDA DE IMÁGENES
# ============================================================
def subir_foto(file_id):
    try:
        file_info  = bot.get_file(file_id)
        descargada = bot.download_file(file_info.file_path)
        res = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY},
            files={"image": descargada},
            timeout=20,
        )
        if res.status_code == 200:
            return res.json()["data"]["url"]
    except Exception as e:
        print(f"Error subiendo foto: {e}")
    return ""

# ============================================================
#  MANEJADORES DEL BOT
# ============================================================
album_temporal = {}

@bot.message_handler(content_types=["text", "photo"])
def recibir_mensaje_telegram(message):

    # — ÁLBUM DE FOTOS —
    if message.media_group_id:
        mg_id = message.media_group_id

        if mg_id not in album_temporal:
            album_temporal[mg_id] = {"texto": "", "fotos": []}
            msg_estado = bot.reply_to(message, "📸 ¡Álbum detectado! Recolectando fotos (4 seg)... ⏳")

            def procesar_album():
                time.sleep(4.0)
                datos_album = album_temporal.pop(mg_id, None)
                if not datos_album:
                    return

                if not datos_album["texto"]:
                    bot.edit_message_text(
                        "❌ Error: Recibí las fotos pero falta la descripción/precio.",
                        chat_id=msg_estado.chat.id,
                        message_id=msg_estado.message_id,
                    )
                    return

                bot.edit_message_text(
                    f"☁️ Subiendo {len(datos_album['fotos'])} fotos a ImgBB... ⏳",
                    chat_id=msg_estado.chat.id,
                    message_id=msg_estado.message_id,
                )

                fotos_ordenadas  = sorted(datos_album["fotos"], key=lambda x: x[0])
                fotos_para_subir = [f[1] for f in fotos_ordenadas[:4]]
                urls_subidas     = [subir_foto(f.file_id) for f in fotos_para_subir]

                bot.edit_message_text(
                    "🧠 Analizando con Inteligencia Artificial... 🤖",
                    chat_id=msg_estado.chat.id,
                    message_id=msg_estado.message_id,
                )

                resultado = procesar_mensaje(datos_album["texto"], urls_subidas)
                bot.edit_message_text(resultado, chat_id=msg_estado.chat.id, message_id=msg_estado.message_id)

            threading.Thread(target=procesar_album, daemon=True).start()

        if message.caption:
            album_temporal[mg_id]["texto"] = message.caption
        if message.photo:
            album_temporal[mg_id]["fotos"].append((message.message_id, message.photo[-1]))

    # — FOTO INDIVIDUAL O TEXTO —
    else:
        texto = message.caption if message.caption else message.text
        if not texto:
            bot.reply_to(message, "❌ Enviaste una imagen sin descripción.")
            return

        msg_estado = bot.reply_to(message, "☁️ Procesando...")

        urls = []
        if message.photo:
            url = subir_foto(message.photo[-1].file_id)
            if url:
                urls.append(url)

        bot.edit_message_text(
            "🧠 Analizando con Inteligencia Artificial... 🤖",
            chat_id=msg_estado.chat.id,
            message_id=msg_estado.message_id,
        )

        resultado = procesar_mensaje(texto, urls)
        bot.edit_message_text(resultado, chat_id=msg_estado.chat.id, message_id=msg_estado.message_id)

# ============================================================
#  ARRANQUE
# ============================================================
print("🚀 Beto Caps Bot ONLINE en Railway.")
bot.infinity_polling()
    
